"""SQLite 持久化：连接管理 + 建表（WAL 模式）。

单机自用、零运维。DB 只存配置类数据（策略实例 / 策略组 / 部署 / 回测历史）；
daemon 运行期 state/log 仍走文件（高频追加、进程独占、崩溃可恢复）。

四表：
- strategies       参数化单策略实例（模板 + 参数 = 可命名可复用）
- strategy_groups  策略组（整棵 node 树存 spec_json，支持自引用嵌套）
- deployments      部署配置（多组占比 + 反向 + symbols 单币批量列表）
- backtests        回测历史（替代进程内 _last_bt 跨进程陷阱；equity 曲线外存 parquet）
"""
from __future__ import annotations
import sqlite3
from contextlib import contextmanager

from core.utils.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    template_name TEXT NOT NULL,
    strategy_kind TEXT NOT NULL,
    params_json   TEXT NOT NULL,
    side_mode     TEXT,
    description   TEXT,
    bar           TEXT,
    days          INTEGER,
    symbols_json  TEXT NOT NULL DEFAULT '[]',
    invert        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS strategy_groups (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    spec_json   TEXT NOT NULL,
    description TEXT,
    created_at  TEXT,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS deployments (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL UNIQUE,
    is_demo            INTEGER NOT NULL,
    bar                TEXT NOT NULL,
    symbols_json       TEXT NOT NULL DEFAULT '[]',
    check_interval_sec INTEGER,
    leverage           INTEGER,
    position_ratio     REAL,
    initial_capital    REAL,
    groups_json        TEXT NOT NULL,
    created_at         TEXT,
    updated_at         TEXT
);

CREATE TABLE IF NOT EXISTS backtests (
    id           TEXT PRIMARY KEY,
    node_kind    TEXT NOT NULL,
    ref_id       TEXT,
    spec_json    TEXT NOT NULL,
    symbol       TEXT,
    bar          TEXT,
    days         INTEGER,
    cfg_json     TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    equity_path  TEXT,
    created_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_bt_ref ON backtests(node_kind, ref_id, created_at DESC);
"""


@contextmanager
def get_conn():
    """获取一个 SQLite 连接（WAL 持久属性已在 init_db 设置）。用完自动关闭。"""
    conn = sqlite3.connect(str(settings.DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _ensure_column(conn, table: str, col: str, decl: str):
    """为已建库补列（CREATE IF NOT EXISTS 不会改已存在的表）。"""
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def init_db():
    """建库 + 建表 + 开启 WAL + 轻量迁移。幂等，可多次调用。"""
    settings.ensure_dirs()
    conn = sqlite3.connect(str(settings.DB_PATH))
    try:
        conn.execute("PRAGMA journal_mode=WAL")     # WAL 是持久属性，设置一次后续连接自动继承
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        _ensure_column(conn, "deployments", "symbols_json", "TEXT NOT NULL DEFAULT '[]'")
        # strategies 表补列：bar/days/symbols/invert（随 Explore 保存需求加入）
        _ensure_column(conn, "strategies", "bar", "TEXT")
        _ensure_column(conn, "strategies", "days", "INTEGER")
        _ensure_column(conn, "strategies", "symbols_json", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, "strategies", "invert", "INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    finally:
        conn.close()
