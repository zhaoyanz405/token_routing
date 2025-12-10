import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
from config import get_settings
from db.models import Base, init_engine, init_session_factory, Node
from services.allocator import Allocator, OverloadedError, NotFoundError


def setup_allocator(nodes=2, budget=300):
    settings = get_settings("test")
    engine = init_engine(settings.DATABASE_URL)
    SessionLocal = init_session_factory(engine)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        with session.begin():
            session.query(Node).delete()
            for i in range(nodes):
                session.add(Node(id=i, capacity_m=budget, used_quota=0))

    return Allocator(SessionLocal, strategy=settings.ALLOC_STRATEGY, dialect_name=engine.dialect.name)


def test_basic_alloc_and_free():
    alloc = setup_allocator(2, 300)
    # 初始总容量 600
    res1 = alloc.alloc("req-1", 80)
    assert "node_id" in res1 and "remaining_quota" in res1
    # 检查剩余容量：600 - 80 = 520
    assert alloc.get_remaining_capacity() == 520

    res2 = alloc.alloc("req-2", 120)
    # 检查剩余容量：520 - 120 = 400
    assert alloc.get_remaining_capacity() == 400

    res_free = alloc.free("req-1")
    assert "node_id" in res_free
    # 检查剩余容量：400 + 80 = 480
    assert alloc.get_remaining_capacity() == 480

    res3 = alloc.alloc("req-3", 200)
    # 检查剩余容量：480 - 200 = 280
    assert alloc.get_remaining_capacity() == 280

    res_free2 = alloc.free("req-2")
    # 检查剩余容量：280 + 120 = 400
    assert alloc.get_remaining_capacity() == 400

    res4 = alloc.alloc("req-4", 300)
    # 检查剩余容量：400 - 300 = 100
    assert alloc.get_remaining_capacity() == 100

    res_free3 = alloc.free("req-3")
    # 检查剩余容量：100 + 200 = 300
    assert alloc.get_remaining_capacity() == 300

    res5 = alloc.alloc("req-5", 250)
    # 检查剩余容量：300 - 250 = 50
    assert alloc.get_remaining_capacity() == 50

    alloc.free("req-4")
    # 检查剩余容量：50 + 300 = 350
    assert alloc.get_remaining_capacity() == 350

    alloc.free("req-5")
    # 检查剩余容量：350 + 250 = 600
    assert alloc.get_remaining_capacity() == 600


def test_overloaded():
    alloc = setup_allocator(1, 100)
    try:
        alloc.alloc("a", 200)
        assert False
    except OverloadedError:
        assert True


def test_idempotent_alloc():
    alloc = setup_allocator(1, 300)
    r1 = alloc.alloc("same", 50)
    r2 = alloc.alloc("same", 50)
    assert r1["node_id"] == r2["node_id"]


def test_free_not_found():
    alloc = setup_allocator(1, 300)
    try:
        alloc.free("missing")
        assert False
    except NotFoundError:
        assert True


def test_concurrency_no_oversell():
    alloc = setup_allocator(2, 300)
    tokens_each = 30
    requests = [f"rid-{i}" for i in range(40)]  # total 1200, nodes have 600

    successes = []
    failures = []
    lock = threading.Lock()

    def worker(rid):
        try:
            res = alloc.alloc(rid, tokens_each)
            with lock:
                successes.append(res)
        except OverloadedError:
            with lock:
                failures.append(rid)
        except Exception:
            with lock:
                failures.append(rid)

    with ThreadPoolExecutor(max_workers=16) as ex:
        for rid in requests:
            ex.submit(worker, rid)

    # At most capacity 600 / 30 = 20 successes
    assert len(successes) <= 20
    assert len(successes) + len(failures) == len(requests)
