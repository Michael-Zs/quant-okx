"""四表 CRUD 仓库层：strategies / strategy_groups / deployments / backtests。

JSON 字段（params_json / spec_json / groups_json / cfg_json / metrics_json）整存整取；
策略组的整棵 node 树存 spec_json（原子保存、前后端一次传输、node_from_spec 递归重建）。
回测的 equity 曲线外存 parquet（表里只存路径），避免主表膨胀。
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime

from core.persist.db import get_conn
from core.utils.config import settings


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _one(conn, sql, args=()):
    row = conn.execute(sql, args).fetchone()
    return dict(row) if row else None


# ===================== strategies（参数化单策略实例）=====================

def list_strategies() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM strategies ORDER BY updated_at DESC").fetchall()
    return [_decode_strategy(r) for r in rows]


def get_strategy(sid: str) -> dict | None:
    with get_conn() as conn:
        r = _one(conn, "SELECT * FROM strategies WHERE id=?", (sid,))
    return _decode_strategy(r) if r else None


def find_strategy_by_name(name: str) -> dict | None:
    with get_conn() as conn:
        r = _one(conn, "SELECT * FROM strategies WHERE name=?", (name,))
    return _decode_strategy(r) if r else None


def create_strategy(*, name, template_name, strategy_kind, params,
                    side_mode="long_short", description="",
                    bar=None, days=None, symbols=None, invert=False) -> str:
    sid = _new_id("str")
    now = _now()
    symbols = symbols or []
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO strategies "
            "(id,name,template_name,strategy_kind,params_json,side_mode,description,"
            " bar,days,symbols_json,invert,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, name, template_name, strategy_kind, json.dumps(params),
             side_mode, description, bar, days, json.dumps(symbols), 1 if invert else 0, now, now))
        conn.commit()
    return sid


def update_strategy(sid: str, **fields) -> bool:
    allowed = {"name", "template_name", "strategy_kind", "params", "side_mode", "description",
               "bar", "days", "symbols", "invert"}
    sets, args = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "params":
            sets.append("params_json=?"); args.append(json.dumps(v))
        elif k == "symbols":
            sets.append("symbols_json=?"); args.append(json.dumps(v))
        elif k == "invert":
            sets.append("invert=?"); args.append(1 if v else 0)
        else:
            sets.append(f"{k}=?"); args.append(v)
    if not sets:
        return False
    sets.append("updated_at=?")
    args += [_now(), sid]
    with get_conn() as conn:
        cur = conn.execute(f"UPDATE strategies SET {','.join(sets)} WHERE id=?", args)
        conn.commit()
        return cur.rowcount > 0


def delete_strategy(sid: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM strategies WHERE id=?", (sid,))
        conn.commit()
        return cur.rowcount > 0


def _decode_strategy(r) -> dict:
    return {"id": r["id"], "name": r["name"], "template_name": r["template_name"],
            "strategy_kind": r["strategy_kind"], "params": json.loads(r["params_json"]),
            "side_mode": r["side_mode"], "description": r["description"],
            "bar": r["bar"], "days": r["days"],
            "symbols": json.loads(r["symbols_json"]) if r["symbols_json"] else [],
            "invert": bool(r["invert"]) if r["invert"] is not None else False,
            "created_at": r["created_at"], "updated_at": r["updated_at"]}


# ===================== strategy_groups（策略组，node 树）=====================

def list_groups() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM strategy_groups ORDER BY updated_at DESC").fetchall()
    return [_decode_group(r) for r in rows]


def get_group(gid: str) -> dict | None:
    with get_conn() as conn:
        r = _one(conn, "SELECT * FROM strategy_groups WHERE id=?", (gid,))
    return _decode_group(r) if r else None


def find_group_by_name(name: str) -> dict | None:
    with get_conn() as conn:
        r = _one(conn, "SELECT * FROM strategy_groups WHERE name=?", (name,))
    return _decode_group(r) if r else None


def create_group(*, name, spec: dict, description="") -> str:
    gid = _new_id("grp")
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO strategy_groups (id,name,spec_json,description,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (gid, name, json.dumps(spec), description, now, now))
        conn.commit()
    return gid


def update_group(gid: str, *, spec: dict | None = None, name: str | None = None,
                 description: str | None = None) -> bool:
    sets, args = [], []
    if spec is not None:
        sets.append("spec_json=?"); args.append(json.dumps(spec))
    if name is not None:
        sets.append("name=?"); args.append(name)
    if description is not None:
        sets.append("description=?"); args.append(description)
    if not sets:
        return False
    sets.append("updated_at=?"); args += [_now(), gid]
    with get_conn() as conn:
        cur = conn.execute(f"UPDATE strategy_groups SET {','.join(sets)} WHERE id=?", args)
        conn.commit()
        return cur.rowcount > 0


def delete_group(gid: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM strategy_groups WHERE id=?", (gid,))
        conn.commit()
        return cur.rowcount > 0


def _decode_group(r) -> dict:
    return {"id": r["id"], "name": r["name"], "spec": json.loads(r["spec_json"]),
            "description": r["description"],
            "created_at": r["created_at"], "updated_at": r["updated_at"]}


# ===================== deployments（部署配置）=====================

def list_deployments() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM deployments ORDER BY updated_at DESC").fetchall()
    return [_decode_deployment(r) for r in rows]


def get_deployment(did: str) -> dict | None:
    with get_conn() as conn:
        r = _one(conn, "SELECT * FROM deployments WHERE id=?", (did,))
    return _decode_deployment(r) if r else None


def find_deployment_by_name(name: str) -> dict | None:
    with get_conn() as conn:
        r = _one(conn, "SELECT * FROM deployments WHERE name=?", (name,))
    return _decode_deployment(r) if r else None


def create_deployment(*, name, is_demo, bar, groups: list[dict], symbols: list[str] | None = None,
                      check_interval_sec=3600, leverage=5, position_ratio=0.1,
                      initial_capital=10000.0) -> str:
    symbols = symbols or []
    did = _new_id("dep")
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO deployments "
            "(id,name,is_demo,bar,symbols_json,check_interval_sec,leverage,position_ratio,initial_capital,groups_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (did, name, int(is_demo), bar, json.dumps(symbols), check_interval_sec, leverage,
             position_ratio, initial_capital, json.dumps(groups), now, now))
        conn.commit()
    return did


def update_deployment(did: str, **fields) -> bool:
    allowed = {"name", "is_demo", "bar", "check_interval_sec", "leverage",
               "position_ratio", "initial_capital", "groups", "symbols"}
    col_map = {"groups": "groups_json", "symbols": "symbols_json"}
    sets, args = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        col = col_map.get(k, k)
        sets.append(f"{col}=?")
        if k in ("groups", "symbols"):
            args.append(json.dumps(v))
        elif k == "is_demo":
            args.append(int(v))
        else:
            args.append(v)
    if not sets:
        return False
    sets.append("updated_at=?"); args += [_now(), did]
    with get_conn() as conn:
        cur = conn.execute(f"UPDATE deployments SET {','.join(sets)} WHERE id=?", args)
        conn.commit()
        return cur.rowcount > 0


def delete_deployment(did: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM deployments WHERE id=?", (did,))
        conn.commit()
        return cur.rowcount > 0


def _decode_deployment(r) -> dict:
    symbols_raw = r["symbols_json"] if "symbols_json" in r.keys() else "[]"
    return {"id": r["id"], "name": r["name"], "is_demo": bool(r["is_demo"]),
            "bar": r["bar"], "symbols": json.loads(symbols_raw or "[]"),
            "check_interval_sec": r["check_interval_sec"],
            "leverage": r["leverage"], "position_ratio": r["position_ratio"],
            "initial_capital": r["initial_capital"],
            "groups": json.loads(r["groups_json"]),
            "created_at": r["created_at"], "updated_at": r["updated_at"]}


# ===================== backtests（回测历史）=====================

def save_backtest(*, node_kind, spec: dict, metrics: dict, cfg: dict,
                  ref_id=None, symbol="", bar="", days=None,
                  equity_df=None) -> str:
    """保存回测结果。equity 曲线存 parquet 外存（表里存路径），避免主表膨胀。"""
    bid = _new_id("bt")
    now = _now()
    equity_path = ""
    if equity_df is not None and len(equity_df):
        bt_dir = settings.BACKTESTS_DIR
        bt_dir.mkdir(parents=True, exist_ok=True)   # 自保目录存在（不依赖 ensure_dirs 已跑）
        equity_path = str(bt_dir / f"{bid}.parquet")
        equity_df.to_parquet(equity_path)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO backtests "
            "(id,node_kind,ref_id,spec_json,symbol,bar,days,cfg_json,metrics_json,equity_path,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (bid, node_kind, ref_id, json.dumps(spec), symbol, bar, days,
             json.dumps(cfg), json.dumps(metrics), equity_path, now))
        conn.commit()
    return bid


def get_backtest(bid: str, with_equity: bool = False) -> dict | None:
    with get_conn() as conn:
        r = _one(conn, "SELECT * FROM backtests WHERE id=?", (bid,))
    if not r:
        return None
    out = {"id": r["id"], "node_kind": r["node_kind"], "ref_id": r["ref_id"],
           "spec": json.loads(r["spec_json"]), "symbol": r["symbol"], "bar": r["bar"],
           "days": r["days"], "cfg": json.loads(r["cfg_json"]),
           "metrics": json.loads(r["metrics_json"]), "equity_path": r["equity_path"],
           "created_at": r["created_at"]}
    if with_equity and r["equity_path"]:
        import pandas as pd
        try:
            df = pd.read_parquet(r["equity_path"])
            if "ts" in df.columns:
                df["ts"] = df["ts"].astype(str)   # Timestamp → str，可 JSON 序列化
            out["equity"] = df.to_dict("list")
        except Exception:
            out["equity"] = None
    return out


def list_backtests(ref_id: str | None = None, node_kind: str | None = None,
                   limit: int = 50) -> list[dict]:
    sql = "SELECT id,node_kind,ref_id,symbol,bar,days,metrics_json,created_at FROM backtests"
    args, where = [], []
    if ref_id:
        where.append("ref_id=?"); args.append(ref_id)
    if node_kind:
        where.append("node_kind=?"); args.append(node_kind)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [{"id": r["id"], "node_kind": r["node_kind"], "ref_id": r["ref_id"],
             "symbol": r["symbol"], "bar": r["bar"], "days": r["days"],
             "metrics": json.loads(r["metrics_json"]), "created_at": r["created_at"]}
            for r in rows]
