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
            session.add(Node(id=0, capacity_m=settings.NODE_BUDGET, used_quota=250))
            session.add(Node(id=1, capacity_m=settings.NODE_BUDGET, used_quota=100))
            session.add(Node(id=2, capacity_m=settings.NODE_BUDGET, used_quota=0))
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_get_and_set_strategy(client):
    r = client.get("/strategy")
    assert r.status_code == 200
    assert r.get_json()["strategy"] == "best"

    r2 = client.post("/strategy", data=json.dumps({"strategy": "largest"}), content_type="application/json")
    assert r2.status_code == 200
    assert r2.get_json()["strategy"] == "largest"


def test_strategy_effect_on_alloc(client):
    body = {"request_id": "s1", "token_count": 150}
    r = client.post("/alloc", data=json.dumps(body), content_type="application/json")
    assert r.status_code == 200
    node_best = r.get_json()["node_id"]
    assert node_best == 1

    client.post("/strategy", data=json.dumps({"strategy": "largest"}), content_type="application/json")
    r2 = client.post("/alloc", data=json.dumps({"request_id": "s2", "token_count": 150}), content_type="application/json")
    assert r2.status_code == 200
    node_largest = r2.get_json()["node_id"]
    assert node_largest == 2
