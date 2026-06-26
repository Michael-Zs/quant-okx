"""全局配置：从 .env 读取，提供 Settings 单例 + 项目路径。

所有路径以项目根目录为基准，避免依赖 cwd。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 项目根目录：core/utils/config.py -> 上溯两级
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


class Settings:
    # OKX 凭证
    OKX_API_KEY: str = os.getenv("OKX_API_KEY", "")
    OKX_API_SECRET: str = os.getenv("OKX_API_SECRET", "")
    OKX_API_PASSPHRASE: str = os.getenv("OKX_API_PASSPHRASE", "")

    # REST API 鉴权
    API_TOKEN: str = os.getenv("API_TOKEN", "change_me")
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8787"))

    # 默认交易参数
    DEFAULT_LEVERAGE: int = int(os.getenv("DEFAULT_LEVERAGE", "5"))
    DEFAULT_POSITION_RATIO: float = float(os.getenv("DEFAULT_POSITION_RATIO", "0.1"))
    DEFAULT_FEE: float = float(os.getenv("DEFAULT_FEE", "0.0005"))
    DEFAULT_SLIPPAGE: float = float(os.getenv("DEFAULT_SLIPPAGE", "0.0005"))

    # 路径
    ROOT: Path = ROOT
    CACHE_DIR: Path = ROOT / "cache"
    RUNTIME_DIR: Path = ROOT / "runtime"
    JOBS_DIR: Path = ROOT / "runtime" / "jobs"
    STATE_DIR: Path = ROOT / "runtime" / "state"
    LOGS_DIR: Path = ROOT / "runtime" / "logs"
    STRATEGIES_DIR: Path = ROOT / "strategies"
    DB_PATH: Path = ROOT / "runtime" / "console.db"
    BACKTESTS_DIR: Path = ROOT / "runtime" / "backtests"
    INTENTS_DIR: Path = ROOT / "runtime" / "intents"

    # Executor 参数
    EXECUTOR_INTERVAL_SEC: int = int(os.getenv("EXECUTOR_INTERVAL_SEC", "60"))
    INTENT_MAX_AGE_SEC: int = int(os.getenv("INTENT_MAX_AGE_SEC", "7200"))

    @classmethod
    def ensure_dirs(cls):
        """确保运行时所需目录存在。"""
        for d in (cls.CACHE_DIR, cls.JOBS_DIR, cls.STATE_DIR, cls.LOGS_DIR,
                  cls.STRATEGIES_DIR, cls.BACKTESTS_DIR, cls.INTENTS_DIR):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
