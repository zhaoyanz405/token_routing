from typing import Optional
import threading
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from db.models import Node, Allocation


class OverloadedError(Exception):
    """资源过载异常。

    在分配阶段找不到任何能容纳 `token_count` 的节点，或原子更新失败（剩余不足）时抛出。
    """
    pass


class NotFoundError(Exception):
    """未找到分配异常。

    在释放阶段，根据 `request_id` 未找到处于 allocated 状态的记录时抛出。
    """
    pass


class Allocator:
    """令牌预算分配器。

    设计要点：
    - 并发安全：使用数据库事务与原子 `UPDATE` 保证 `used_quota` 不会超卖；
      PostgreSQL 下采用 `FOR UPDATE SKIP LOCKED` 进行行级锁竞争，避免热点阻塞；
      本类的原子更新条件 `(capacity_m - used_quota) >= token_count` 进一步确保逻辑正确。
    - 幂等性：针对相同 `request_id` 的重复 `/alloc` 调用，若已分配则直接返回既有结果；
      当并发写入发生唯一键冲突时，回退并查询已有记录返回（保证客户端幂等）。
    - 策略选择：`best`（最佳适配，升序剩余）或 `largest`（最大剩余，降序），通过构造查询排序实现。
    """

    def __init__(self, session_factory, strategy: str = "best", dialect_name: Optional[str] = None):
        """构造分配器。

        参数：
        - `session_factory`：SQLAlchemy 会话工厂（`sessionmaker`），每次操作创建独立会话
        - `strategy`：分配策略（`best`|`largest`）影响候选节点的排序顺序
        - `dialect_name`：数据库方言名称，用于判定是否支持 `SKIP LOCKED`
        """
        self._Session = session_factory
        self._strategy = strategy
        self._dialect_name = dialect_name
        # 保留本地锁字典（目前逻辑依赖数据库原子更新，锁仅预留不使用）
        self._locks: dict[int, threading.Lock] = {}

    def _skip_locked_supported(self) -> bool:
        """判断方言是否支持 `FOR UPDATE SKIP LOCKED`（PostgreSQL）。"""
        return (self._dialect_name or "").startswith("postgres")

    def alloc(self, request_id: str, token_count: int) -> dict:
        """分配令牌预算。

        流程：
        1. 幂等检查：若 `request_id` 已分配，直接返回既有节点与当前剩余；
        2. 根据策略选择候选节点（满足 `remaining >= token_count`），Postgres 下加行锁（可跳过被占用行）；
        3. 使用条件更新将 `used_quota` 原子递增：仅当剩余足够才更新，防止竞态超卖；
        4. 写入 `allocations` 记录；若唯一键冲突，回滚并查询既有记录返回。
        返回：`{"node_id": int, "remaining_quota": int}`
        异常：`OverloadedError` 无可用节点或原子更新失败。
        """
        with self._Session() as session:
            with session.begin():  # 事务边界：查询→原子更新→写分配记录
                existing = session.get(Allocation, request_id)
                if existing and existing.status == "allocated":
                    node = session.get(Node, existing.node_id)
                    remaining = node.capacity_m - node.used_quota
                    return {"node_id": node.id, "remaining_quota": remaining}

                # 选择候选节点：满足剩余 >= 需求，按策略排序；Postgres 下尝试跳过已锁行
                remaining_expr = Node.capacity_m - Node.used_quota
                order = remaining_expr.asc() if self._strategy == "best" else remaining_expr.desc()
                stmt = (
                    select(Node)
                    .where(remaining_expr >= token_count)
                    .order_by(order, Node.id.asc())
                )
                if self._skip_locked_supported():
                    stmt = stmt.with_for_update(skip_locked=True)

                node = session.execute(stmt).scalars().first()
                if not node:
                    raise OverloadedError()

                # 原子条件更新：只有当 (capacity - used) >= token_count 时才递增 used_quota
                # 这一步在并发下保证不会出现负剩余或超卖
                result = session.execute(
                    update(Node)
                    .where(Node.id == node.id)
                    .where((Node.capacity_m - Node.used_quota) >= token_count)
                    .values(used_quota=Node.used_quota + token_count)
                )
                if result.rowcount == 0:
                    # 可能在本事务读到后，其他事务已占用该节点剩余，视为过载
                    raise OverloadedError()

                # 写入分配记录；唯一键冲突表示其他并发已写入，同请求幂等地返回既有分配
                alloc = Allocation(
                    request_id=request_id,
                    node_id=node.id,
                    token_count=token_count,
                    status="allocated",
                )
                session.add(alloc)
                try:
                    session.flush()
                except IntegrityError:
                    session.rollback()
                    existing = session.get(Allocation, request_id)
                    node = session.get(Node, existing.node_id)
                    remaining = node.capacity_m - node.used_quota
                    return {"node_id": node.id, "remaining_quota": remaining}

                # 返回最新剩余（再次读取以反映更新后的值）
                node = session.get(Node, node.id)
                remaining = node.capacity_m - node.used_quota
                return {"node_id": node.id, "remaining_quota": remaining}

    def free(self, request_id: str) -> dict:
        """释放令牌预算。

        流程：
        1. 查询分配记录，若不存在或已释放，抛出 `NotFoundError`；
        2. 对应节点 `used_quota` 原子递减；
        3. 将分配记录状态标记为 `freed` 并提交。
        返回：`{"node_id": int}`
        """
        with self._Session() as session:
            with session.begin():
                alloc = session.get(Allocation, request_id)
                if not alloc or alloc.status != "allocated":
                    raise NotFoundError()

                node = session.get(Node, alloc.node_id)
                session.execute(
                    update(Node)
                    .where(Node.id == node.id)
                    .values(used_quota=Node.used_quota - alloc.token_count)
                )
                alloc.status = "freed"
                session.flush()
                return {"node_id": node.id}

    def get_remaining_capacity(self) -> int:
        """返回所有节点的总剩余配额之和。

        计算公式：sum(capacity_m - used_quota) across nodes。
        仅读取，不开启显式事务。
        """
        with self._Session() as session:
            rows = session.execute(select(Node.capacity_m, Node.used_quota)).all()
            return sum(cap - used for cap, used in rows)

    def get_usage_stats(self) -> dict:
        with self._Session() as session:
            nodes = session.execute(select(Node)).scalars().all()
            total_capacity = sum(n.capacity_m for n in nodes) or 0
            used_total = sum(n.used_quota for n in nodes) or 0
            remaining_total = sum(n.capacity_m - n.used_quota for n in nodes) or 0
            utilization = (used_total / total_capacity) if total_capacity > 0 else 0.0
            per_node = [
                {
                    "id": n.id,
                    "capacity_m": n.capacity_m,
                    "used_quota": n.used_quota,
                    "remaining": n.capacity_m - n.used_quota,
                    "utilization": (n.used_quota / n.capacity_m) if n.capacity_m > 0 else 0.0,
                }
                for n in nodes
            ]
            def _gini(values: list[float]) -> float:
                vals = sorted([v for v in values if v >= 0])
                if not vals:
                    return 0.0
                n = len(vals)
                s = sum(vals)
                if s == 0:
                    return 0.0
                cum = 0.0
                for i, v in enumerate(vals, 1):
                    cum += i * v
                return (2 * cum) / (n * s) - (n + 1) / n
            imbalance_gini = _gini([n.used_quota for n in nodes])
            return {
                "total_capacity": total_capacity,
                "used_total": used_total,
                "remaining_total": remaining_total,
                "utilization": utilization,
                "per_node": per_node,
                "imbalance_gini": imbalance_gini,
            }
