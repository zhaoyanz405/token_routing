import json
import pytest
from app import create_app
from db.models import Node, Allocation
from config import Settings


@pytest.fixture
def app():
    settings = Settings(
        DATABASE_URL="sqlite+pysqlite:///:memory:",
        PORT=0,
        NODES=6,
        NODE_BUDGET=300,
        ALLOC_STRATEGY="best",
    )
    app = create_app(settings)
    SessionLocal = app.config["DB_SESSION_FACTORY"]
    with SessionLocal() as session:
        with session.begin():
            session.query(Allocation).delete()
            session.query(Node).delete()
            for i in range(settings.NODES):
                session.add(Node(id=i, capacity_m=settings.NODE_BUDGET, used_quota=0))
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_alloc_success(client):
    body = {"request_id": "rid-1", "token_count": 30}
    resp = client.post("/alloc", data=json.dumps(body), content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "node_id" in data and "remaining_quota" in data
    assert isinstance(data["node_id"], int)
    assert data["remaining_quota"] == 270


def test_alloc_bad_request(client):
    body = {"request_id": "", "token_count": 0}
    resp = client.post("/alloc", data=json.dumps(body), content_type="application/json")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "bad_request"
    assert isinstance(data.get("detail"), list)


def test_alloc_overloaded(client):
    body = {"request_id": "rid-big", "token_count": 301}
    resp = client.post("/alloc", data=json.dumps(body), content_type="application/json")
    assert resp.status_code == 429
    assert resp.get_json() == {"error": "overloaded"}


def test_alloc_idempotent(client):
    body = {"request_id": "same", "token_count": 50}
    r1 = client.post("/alloc", data=json.dumps(body), content_type="application/json")
    r2 = client.post("/alloc", data=json.dumps(body), content_type="application/json")
    assert r1.status_code == 200 and r2.status_code == 200
    d1 = r1.get_json()
    d2 = r2.get_json()
    assert d1["node_id"] == d2["node_id"]
    assert d1["remaining_quota"] == d2["remaining_quota"]


def test_free_success(client):
    alloc_body = {"request_id": "tofree", "token_count": 40}
    alloc_resp = client.post("/alloc", data=json.dumps(alloc_body), content_type="application/json")
    assert alloc_resp.status_code == 200
    free_resp = client.post("/free", data=json.dumps({"request_id": "tofree"}), content_type="application/json")
    assert free_resp.status_code == 200
    data = free_resp.get_json()
    assert "node_id" in data


def test_free_not_found(client):
    resp = client.post("/free", data=json.dumps({"request_id": "missing"}), content_type="application/json")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "not_found"}


def test_alloc_internal_error(client, monkeypatch):
    class Dummy:
        def alloc(self, request_id, token_count):
            raise Exception("boom")

    from routes import tokens as tokens_module
    monkeypatch.setattr(tokens_module, "_allocator", lambda: Dummy())
    resp = client.post("/alloc", data=json.dumps({"request_id": "e", "token_count": 10}), content_type="application/json")
    assert resp.status_code == 500
    assert resp.get_json() == {"error": "internal"}


def test_free_internal_error(client, monkeypatch):
    class Dummy:
        def free(self, request_id):
            raise Exception("boom")

    from routes import tokens as tokens_module
    monkeypatch.setattr(tokens_module, "_allocator", lambda: Dummy())
    resp = client.post("/free", data=json.dumps({"request_id": "e"}), content_type="application/json")
    assert resp.status_code == 500
    assert resp.get_json() == {"error": "internal"}
