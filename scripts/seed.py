import os
from dotenv import load_dotenv
from config import get_settings
from db.models import Base, init_engine, init_session_factory, Node


def main():
    load_dotenv()
    settings = get_settings()
    engine = init_engine(settings.DATABASE_URL)
    SessionLocal = init_session_factory(engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        with session.begin():
            existing = session.query(Node).count()
            if existing >= settings.NODES:
                return
            for i in range(settings.NODES):
                node = session.get(Node, i)
                if node is None:
                    session.add(Node(id=i, capacity_m=settings.NODE_BUDGET, used_quota=0))


if __name__ == "__main__":
    main()
