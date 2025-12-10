import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv


@dataclass
class Settings:
    DATABASE_URL: str
    PORT: int
    NODES: int
    NODE_BUDGET: int
    ALLOC_STRATEGY: str
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_GLOBAL_PER_SEC: int = 100
    RATE_LIMIT_CLIENT_PER_SEC: int = 50
    RATE_LIMIT_WINDOW_SEC: int = 1
    OVERLOAD_RETRY_AFTER_SEC: int = 2
    BIG_REQUEST_THRESHOLD: int = 200
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    RATE_LIMIT_GLOBAL_BURST: int = 100
    RATE_LIMIT_CLIENT_BURST: int = 50
    RATE_LIMIT_PROVIDER: str = "local"
    REDIS_URL: str = ""


def get_settings(env: Optional[str] = None) -> Settings:
    env = (env or os.getenv("APP_ENV") or os.getenv("ENV") or "dev").lower()
    if env not in {"prod", "dev", "test"}:
        env = "dev"

    load_dotenv()
    dotenv_file = f".env.{env}"
    if os.path.exists(dotenv_file):
        load_dotenv(dotenv_file)

    if env == "test":
        default_db = "sqlite+pysqlite:///:memory:"
        default_port = 0
        default_nodes = 6
        default_budget = 300
    elif env == "dev":
        default_db = os.getenv("DEV_DATABASE_URL", "sqlite+pysqlite:///./dev.db")
        default_port = 3000
        default_nodes = 6
        default_budget = 300
    else:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL must be set for prod environment")
        default_db = db_url
        default_port = int(os.getenv("PORT", "8000"))
        default_nodes = int(os.getenv("NODES", "6"))
        default_budget = int(os.getenv("NODE_BUDGET", "300"))

    return Settings(
        DATABASE_URL=os.getenv("DATABASE_URL", default_db),
        PORT=int(os.getenv("PORT", str(default_port))),
        NODES=int(os.getenv("NODES", str(default_nodes))),
        NODE_BUDGET=int(os.getenv("NODE_BUDGET", str(default_budget))),
        ALLOC_STRATEGY=os.getenv("ALLOC_STRATEGY", "best"),
        RATE_LIMIT_ENABLED=os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true",
        RATE_LIMIT_GLOBAL_PER_SEC=int(os.getenv("RATE_LIMIT_GLOBAL_PER_SEC", "100")),
        RATE_LIMIT_CLIENT_PER_SEC=int(os.getenv("RATE_LIMIT_CLIENT_PER_SEC", "50")),
        RATE_LIMIT_WINDOW_SEC=int(os.getenv("RATE_LIMIT_WINDOW_SEC", "1")),
        OVERLOAD_RETRY_AFTER_SEC=int(os.getenv("OVERLOAD_RETRY_AFTER_SEC", "2")),
        # 大请求阈值，超过该值的请求会强制使用剩余降序（largest）选择节点，
        # 以优先匹配剩余最多的节点，提升大请求的成功率并减少容量碎片化/热点风险。
        BIG_REQUEST_THRESHOLD=int(os.getenv("BIG_REQUEST_THRESHOLD", "200")),
        DB_POOL_SIZE=int(os.getenv("DB_POOL_SIZE", "5")),
        DB_MAX_OVERFLOW=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        DB_POOL_TIMEOUT=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        REDIS_URL=os.getenv("REDIS_URL", ""),
    )
