import logging
from flask import Flask
from config import Settings, get_settings
from routes.tokens import bp as tokens_bp
from db.models import init_engine, init_session_factory, Base


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or get_settings()
    app = Flask(__name__)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    engine = init_engine(settings.DATABASE_URL)
    SessionLocal = init_session_factory(engine)

    Base.metadata.create_all(bind=engine)

    app.config["DB_ENGINE"] = engine
    app.config["DB_SESSION_FACTORY"] = SessionLocal
    app.config["SETTINGS"] = settings

    app.register_blueprint(tokens_bp, url_prefix="/")

    @app.get("/health")
    def health():
        app.logger.info("health", extra={"path": "/health"})
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(app.config["SETTINGS"].PORT))
