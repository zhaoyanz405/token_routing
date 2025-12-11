# Token Routing Service (Flask + Postgres)

## 项目功能
- 提供令牌预算分配与释放接口，保证并发场景下不超卖：`POST /alloc`、`POST /free`。
- 提供使用统计与策略管理接口：`GET /metrics`、`GET/POST /strategy`，以及 `GET /health` 健康检查。
- 默认使用 PostgreSQL；开发/测试可使用 SQLite（`db/models.py:48-68` 自动选择方言）。

## 核心技术点
- 并发安全与原子性：
  - PostgreSQL 下使用 `FOR UPDATE SKIP LOCKED` 进行行级锁竞争（`services/allocator.py:97-99`）。
  - 原子条件更新确保不超卖：`(capacity_m - used_quota) >= token_count`（`services/allocator.py:108-117`）。
- 幂等性：
  - 相同 `request_id` 重复分配返回既有结果，处理唯一键冲突并回退查询（`services/allocator.py:120-136`）。
- 策略与大请求优化：
  - `best`（升序剩余）与 `largest`（降序剩余）两种策略（`services/allocator.py:82-91`）。
  - 当 `token_count` 超过阈值时强制按最大剩余选择，降低碎片化与失败率（`config.py:69-72`，`services/allocator.py:85-91`）。
- 速率限制：
  - 内置线程安全的令牌桶限流（`middleware/ratelimit.py:15-48`），或可切换至 `flask-limiter` + Redis（`app.py:29-55`）。
- 服务入口：
  - 应用工厂 `create_app()`（`app.py:16`），WSGI 入口 `wsgi:app`（`wsgi.py:1-3`）。容器中使用 `gunicorn` gthread 并发模型。

## 使用方法（本地）
- 安装依赖：`pip install -r requirements.txt`
- 初始化数据库节点：`python scripts/seed.py`
- 启动服务：`python app.py`
- 默认端口：`PORT=3000`（可通过环境变量覆盖）。

## 使用方法（Docker）
- 构建并启动：`docker compose up -d --build postgres redis app`
- 访问健康检查：`http://localhost:8000/health`
- 关键环境变量已在 `docker-compose.yml` 的 `app` 服务中设置：
  - `DATABASE_URL=postgresql+psycopg2://container:container_pw@postgres:5432/token_routing`
  - `PORT=8000`
  - `RATE_LIMIT_ENABLED=true`、`RATE_LIMIT_PROVIDER=local`（可切换为 `flask` 并设置 `REDIS_URL`）

## API 快速示例
- 分配：
  - `curl -X POST http://localhost:8000/alloc -H "Content-Type: application/json" -d '{"request_id":"r1","token_count":100}'`
- 释放：
  - `curl -X POST http://localhost:8000/free -H "Content-Type: application/json" -d '{"request_id":"r1"}'`
- 统计：
  - `curl http://localhost:8000/metrics`
- 策略：
  - `curl http://localhost:8000/strategy`
  - `curl -X POST http://localhost:8000/strategy -H "Content-Type: application/json" -d '{"strategy":"largest"}'`

## 配置项
- `DATABASE_URL`：数据库连接串；生产必须设置（`config.py:50-57,58-61`）。
- `PORT`：服务端口，默认 `3000`（本地）/ `8000`（容器示例）（`config.py:54-55,61-62`）。
- `NODES`、`NODE_BUDGET`：节点数量与预算（`config.py:55-57,62-64`）。
- `ALLOC_STRATEGY`：`best|largest`，默认 `best`（`config.py:64`）。
- 限流与池参数：`RATE_LIMIT_*`、`DB_POOL_SIZE/DB_MAX_OVERFLOW/DB_POOL_TIMEOUT`（`config.py:14-27,70-76`）。

## 测试
- 运行：`pytest -q`
- 包含并发模拟，验证不超卖、策略切换与限流的正确性。
