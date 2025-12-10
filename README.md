# Token Routing Service (Python + Flask + Postgres)

## 概述
- 提供 `POST /alloc` 与 `POST /free` 两个接口，保证并发下不超卖。
- 数据库：PostgreSQL（开发默认支持 SQLite 便于本地测试）。
- 分配策略：默认 Best-Fit，可通过 `ALLOC_STRATEGY=largest` 切换。

## 环境变量
- `DATABASE_URL`：例如 `postgresql+psycopg2://user:password@localhost:5432/token_routing`
- `PORT`：默认 `3000`
- `NODES`：默认 `2`
- `NODE_BUDGET`：默认 `300`
- `ALLOC_STRATEGY`：`best|largest`，默认 `best`

## 快速开始
1. 安装依赖：`pip install -r requirements.txt`
2. 初始化节点：`python scripts/seed.py`
3. 启动服务：`python app.py`

## 接口
### POST /alloc
请求体：`{"request_id": "<唯一ID>", "token_count": <int>}`
成功：`200 {"node_id": <int>, "remaining_quota": <int>}`
无资源：`429 {"error": "overloaded"}`

### POST /free
请求体：`{"request_id": "<之前申请ID>}`
成功：`200 {"node_id": <int>}`
失败：`404 {"error": "not_found"}`

## 测试
- 运行：`pytest -q`
- 包含并发模拟，验证不超卖与策略正确性。

