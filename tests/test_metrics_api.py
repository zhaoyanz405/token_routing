import json
import pytest
from app import create_app
from db.models import Node
from config import Settings


@pytest.fixture
def app():
    settings = Settings(
        DATABASE_URL="sqlite+pysqlite:///:memory:",
        PORT=0,
        NODES=3,
        NODE_BUDGET=300,
        ALLOC_STRATEGY="best",
    )
    app = create_app(settings)
    SessionLocal = app.config["DB_SESSION_FACTORY"]
    with SessionLocal() as session:
        with session.begin():
            session.query(Node).delete()
            for i in range(settings.NODES):
                session.add(Node(id=i, capacity_m=settings.NODE_BUDGET, used_quota=0))
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_metrics_initial(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total_capacity"] == 900
    assert data["used_total"] == 0
    assert data["remaining_total"] == 900
    assert data["utilization"] == 0
    assert isinstance(data["per_node"], list) and len(data["per_node"]) == 3


def test_metrics_after_alloc_free(client):
    body = {"request_id": "m1", "token_count": 150}
    r = client.post("/alloc", data=json.dumps(body), content_type="application/json")
    assert r.status_code == 200

    resp = client.get("/metrics")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["used_total"] == 150
    assert data["remaining_total"] == 750
    assert pytest.approx(data["utilization"], 0.001) == 150 / 900

    rf = client.post("/free", data=json.dumps({"request_id": "m1"}), content_type="application/json")
    assert rf.status_code == 200
    resp2 = client.get("/metrics")
    d2 = resp2.get_json()
    assert d2["used_total"] == 0
    assert d2["utilization"] == 0

