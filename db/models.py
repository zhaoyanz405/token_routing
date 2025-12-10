from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Enum,
    ForeignKey,
    CheckConstraint,
    DateTime,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker


Base = declarative_base()


class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True)
    capacity_m = Column(Integer, nullable=False)
    used_quota = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("used_quota >= 0", name="ck_nodes_used_quota_nonnegative"),
        CheckConstraint(
            "used_quota <= capacity_m", name="ck_nodes_used_quota_not_exceed_capacity"
        ),
    )

    allocations = relationship("Allocation", back_populates="node")


class Allocation(Base):
    __tablename__ = "allocations"

    request_id = Column(String, primary_key=True)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    token_count = Column(Integer, nullable=False)
    status = Column(Enum("allocated", "freed", name="allocation_status"), nullable=False, default="allocated")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    node = relationship("Node", back_populates="allocations")


def init_engine(database_url: str, pool_size: int | None = None, max_overflow: int | None = None, pool_timeout: int | None = None):
    if database_url.startswith("sqlite"):
        engine_kwargs = {
            "future": True,
            "connect_args": {"check_same_thread": False},
            "pool_pre_ping": True,
        }

        if ":memory:" in database_url:
            from sqlalchemy.pool import StaticPool
            engine_kwargs["poolclass"] = StaticPool
        return create_engine(database_url, **engine_kwargs)
    
    engine_kwargs = {"future": True, "pool_pre_ping": True}
    if pool_size is not None:
        engine_kwargs["pool_size"] = pool_size
    if max_overflow is not None:
        engine_kwargs["max_overflow"] = max_overflow
    if pool_timeout is not None:
        engine_kwargs["pool_timeout"] = pool_timeout
    return create_engine(database_url, **engine_kwargs)


def init_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
