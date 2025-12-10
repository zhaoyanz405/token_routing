from flask import Blueprint, current_app, request
from pydantic import BaseModel, Field, ValidationError
from typing import Literal
from services.allocator import Allocator, OverloadedError, NotFoundError


bp = Blueprint("tokens", __name__)


class AllocBody(BaseModel):
    request_id: str = Field(min_length=1)
    token_count: int = Field(gt=0)


class FreeBody(BaseModel):
    request_id: str = Field(min_length=1)


def _allocator() -> Allocator:
    """
    创建并返回分配器实例。
    - 读取应用配置以确定分配策略（best|largest）和数据库方言。
    - 在 PostgreSQL 下使用行级锁（FOR UPDATE SKIP LOCKED）保证并发原子性；
      在本地 SQLite 验证时使用每节点本地锁避免超卖。
    返回: Allocator
    """
    settings = current_app.config["SETTINGS"]
    session_factory = current_app.config["DB_SESSION_FACTORY"]
    engine = current_app.config["DB_ENGINE"]
    return Allocator(session_factory, strategy=settings.ALLOC_STRATEGY, dialect_name=engine.dialect.name, big_request_threshold=settings.BIG_REQUEST_THRESHOLD)


@bp.post("/alloc")
def alloc_route():
    """
    处理令牌分配请求（POST /alloc）。
    请求体: {"request_id": "<唯一ID>", "token_count": <int>}
    响应:
      - 200 {"node_id": <int>, "remaining_quota": <int>} 分配成功
      - 400 {"error": "bad_request", "detail": [...]} 入参校验失败
      - 429 {"error": "overloaded"} 资源不足无法分配
      - 500 {"error": "internal"} 服务内部错误
    日志: 记录 request_id、token_count、node_id、remaining_quota 与错误信息。
    """
    try:
        body = AllocBody.model_validate_json(request.data)
    except ValidationError as ve:
        current_app.logger.warning("bad_request", extra={"path": "/alloc", "errors": ve.errors()})
        return {"error": "bad_request", "detail": ve.errors()}, 400

    try:
        result = _allocator().alloc(body.request_id, body.token_count)
        current_app.logger.info("alloc_ok", extra={"request_id": body.request_id, "token_count": body.token_count, "node_id": result.get("node_id"), "remaining_quota": result.get("remaining_quota")})
        return result, 200
    except OverloadedError:
        current_app.logger.info("overloaded", extra={"request_id": body.request_id, "token_count": body.token_count})
        return {"error": "overloaded"}, 429, {"Retry-After": str(current_app.config["SETTINGS"].OVERLOAD_RETRY_AFTER_SEC)}
    except Exception:
        current_app.logger.exception("alloc_internal_error", extra={"request_id": body.request_id})
        return {"error": "internal"}, 500


@bp.post("/free")
def free_route():
    """
    处理令牌释放请求（POST /free）。
    请求体: {"request_id": "<之前申请用过的ID>"}
    响应:
      - 200 {"node_id": <int>} 释放成功
      - 404 {"error": "not_found"} 未找到对应分配或已释放
      - 400 {"error": "bad_request", "detail": [...]} 入参校验失败
      - 500 {"error": "internal"} 服务内部错误
    日志: 记录 request_id、node_id 及错误信息。
    """
    try:
        body = FreeBody.model_validate_json(request.data)
    except ValidationError as ve:
        current_app.logger.warning("bad_request", extra={"path": "/free", "errors": ve.errors()})
        return {"error": "bad_request", "detail": ve.errors()}, 400

    try:
        result = _allocator().free(body.request_id)
        current_app.logger.info("free_ok", extra={"request_id": body.request_id, "node_id": result.get("node_id")})
        return result, 200
    except NotFoundError:
        current_app.logger.info("free_not_found", extra={"request_id": body.request_id})
        return {"error": "not_found"}, 404
    except Exception:
        current_app.logger.exception("free_internal_error", extra={"request_id": body.request_id})
        return {"error": "internal"}, 500


@bp.get("/metrics")
def metrics_route():
    try:
        stats = _allocator().get_usage_stats()
        current_app.logger.info("metrics", extra={"utilization": stats.get("utilization")})
        if stats.get("utilization", 0) > 0.85:
            current_app.logger.warning("utilization_high", extra={"utilization": stats.get("utilization")})
        return stats, 200
    except Exception:
        current_app.logger.exception("metrics_internal_error", extra={"path": "/metrics"})
        return {"error": "internal"}, 500


class StrategyBody(BaseModel):
    strategy: Literal["best", "largest"]


@bp.get("/strategy")
def get_strategy():
    settings = current_app.config["SETTINGS"]
    return {"strategy": settings.ALLOC_STRATEGY}, 200


@bp.post("/strategy")
def set_strategy():
    try:
        body = StrategyBody.model_validate_json(request.data)
    except ValidationError as ve:
        return {"error": "bad_request", "detail": ve.errors()}, 400
    settings = current_app.config["SETTINGS"]
    settings.ALLOC_STRATEGY = body.strategy
    current_app.logger.info("strategy_set", extra={"strategy": body.strategy})
    return {"strategy": settings.ALLOC_STRATEGY}, 200
