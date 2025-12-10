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
    )
