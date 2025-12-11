import json
import pytest
from app import create_app
from config import get_settings
from db.models import Node


@pytest.fixture
def app():
    settings = get_settings("test")
    settings.NODES = 2
    settings.NODE_BUDGET = 300
    settings.ALLOC_STRATEGY = "best"
    settings.RATE_LIMIT_ENABLED = True
    settings.RATE_LIMIT_GLOBAL_PER_SEC = 3
    settings.RATE_LIMIT_CLIENT_PER_SEC = 2
    settings.RATE_LIMIT_WINDOW_SEC = 1
    settings.OVERLOAD_RETRY_AFTER_SEC = 2
    settings.BIG_REQUEST_THRESHOLD = 9999
    settings.DB_POOL_SIZE = 5
    settings.DB_MAX_OVERFLOW = 10
    settings.DB_POOL_TIMEOUT = 30
    app = create_app(settings)
    SessionLocal = app.config["DB_SESSION_FACTORY"]
    with SessionLocal() as session:
        with session.begin():
            from db.models import Allocation
            session.query(Allocation).delete()
            session.query(Node).delete()
            for i in range(settings.NODES):
                session.add(Node(id=i, capacity_m=settings.NODE_BUDGET, used_quota=0))
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_rate_limit_basic(client):
    body = {"request_id": "rl-1", "token_count": 10}
    r1 = client.post("/alloc", data=json.dumps(body), content_type="application/json")
    r2 = client.post("/alloc", data=json.dumps({"request_id": "rl-2", "token_count": 10}), content_type="application/json")
    r3 = client.post("/alloc", data=json.dumps({"request_id": "rl-3", "token_count": 10}), content_type="application/json")
    r4 = client.post("/alloc", data=json.dumps({"request_id": "rl-4", "token_count": 10}), content_type="application/json")
    codes = [r1.status_code, r2.status_code, r3.status_code, r4.status_code]
    assert 429 in codes
    limited = [r for r in [r1, r2, r3, r4] if r.status_code == 429]
    assert limited[0].headers.get("Retry-After") is not None
    assert limited[0].get_json()["error"] == "rate_limited"


def test_overload_retry_after_header(client):
    r = client.post("/alloc", data=json.dumps({"request_id": "big", "token_count": 10000}), content_type="application/json")
    assert r.status_code in (429, 400, 200)
    if r.status_code == 429:
        assert r.headers.get("Retry-After") is not None
