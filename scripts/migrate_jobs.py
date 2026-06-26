"""一次性迁移：把旧 runtime/jobs/*.json 迁入 deployments 表（每个 job → 单组单节点）。

旧 job 格式（单 symbol、单策略或 Ensemble）→ deployment（单组，含一个 leaf 或
signal_combiner）。旧 job 文件保留作备份；daemon 双入口（--job / --deployment）
过渡期并存，确认无遗漏后再下线 --job。

幂等：按 name 跳过已迁移项，可重复运行。
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.persist import db, repositories as R
from core.live.runtime import read_json
from core.utils.config import settings


def job_to_node_spec(strategy_cfg: dict) -> dict:
    """旧 job 的 strategy 配置 → node spec（leaf 或 signal_combiner）。"""
    if strategy_cfg.get("type") == "ensemble":
        return {
            "node_type": "signal_combiner", "name": "migrated_ensemble",
            "mode": strategy_cfg.get("mode", "vote"),
            "children": [
                {"node": {"node_type": "leaf", "name": s["name"], "template_name": s["name"],
                          "strategy_kind": "single", "params": s.get("params", {}), "invert": False},
                 "weight": 1.0, "invert": False}
                for s in strategy_cfg.get("subs", [])
            ],
            "invert": False,
        }
    return {"node_type": "leaf", "name": strategy_cfg.get("name", "migrated"),
            "template_name": strategy_cfg["name"], "strategy_kind": "single",
            "params": strategy_cfg.get("params", {}), "invert": False}


def migrate() -> int:
    db.init_db()
    job_dir = settings.JOBS_DIR
    if not job_dir.exists():
        print("无 jobs 目录，跳过")
        return 0
    n = 0
    for jf in sorted(job_dir.glob("*.json")):
        job = read_json(jf)
        if not job or "strategy" not in job:
            continue
        name = f"migrated_{job.get('job_id', jf.stem)}"
        if R.find_deployment_by_name(name):
            print(f"  跳过已存在: {name}")
            continue
        gid = R.create_group(name=name + "_group", spec=job_to_node_spec(job["strategy"]))
        did = R.create_deployment(
            name=name, is_demo=job.get("is_demo", True), bar=job.get("bar", "1H"),
            groups=[{"group_id": gid, "weight": 1.0,
                     "invert": bool(job.get("invert", False))}],
            leverage=int(job.get("leverage", 5)),
            position_ratio=float(job.get("position_ratio", 0.1)),
            check_interval_sec=int(job.get("check_interval_sec", 3600)))
        n += 1
        print(f"  {jf.name} -> deployment {did} ({name})")
    print(f"完成，共迁移 {n} 个 job")
    return n


if __name__ == "__main__":
    migrate()
