import logging
import os
from flask import Flask, request
from config import Settings, get_settings
from routes.tokens import bp as tokens_bp
from db.models import init_engine, init_session_factory, Base
from middleware.ratelimit import TokenBucketLimiter
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _HAS_FLASK_LIMITER = True
except Exception:
    _HAS_FLASK_LIMITER = False


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or get_settings()
    app = Flask(__name__)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    engine = init_engine(settings.DATABASE_URL, pool_size=settings.DB_POOL_SIZE, max_overflow=settings.DB_MAX_OVERFLOW, pool_timeout=settings.DB_POOL_TIMEOUT)
    SessionLocal = init_session_factory(engine)

    Base.metadata.create_all(bind=engine)

    app.config["DB_ENGINE"] = engine
    app.config["DB_SESSION_FACTORY"] = SessionLocal
    app.config["SETTINGS"] = settings
    if settings.RATE_LIMIT_ENABLED:
        provider = getattr(settings, "RATE_LIMIT_PROVIDER", "local")
        if provider == "flask" and _HAS_FLASK_LIMITER:
            storage_uri = getattr(settings, "REDIS_URL", "") or "memory://"
            default_limits = [f"{settings.RATE_LIMIT_GLOBAL_PER_SEC} per second"]
            limiter = Limiter(key_func=get_remote_address, storage_uri=storage_uri, default_limits=default_limits)
            limiter.init_app(app)
            app.config["FLASK_LIMITER"] = limiter
            try:
                from routes.tokens import alloc_route
                endpoint = "tokens.alloc_route"
                app.view_functions[endpoint] = limiter.limit(f"{settings.RATE_LIMIT_CLIENT_PER_SEC} per second")(app.view_functions[endpoint])
            except Exception:
                pass
        else:
            _gb = getattr(settings, "RATE_LIMIT_GLOBAL_BURST", None)
            _cb = getattr(settings, "RATE_LIMIT_CLIENT_BURST", None)
            gb_env = os.getenv("RATE_LIMIT_GLOBAL_BURST")
            cb_env = os.getenv("RATE_LIMIT_CLIENT_BURST")
            global_burst = int(gb_env) if gb_env else min(int(_gb or settings.RATE_LIMIT_GLOBAL_PER_SEC), int(settings.RATE_LIMIT_GLOBAL_PER_SEC))
            client_burst = int(cb_env) if cb_env else min(int(_cb or settings.RATE_LIMIT_CLIENT_PER_SEC), int(settings.RATE_LIMIT_CLIENT_PER_SEC))
            limiter = TokenBucketLimiter(
                global_rate=float(settings.RATE_LIMIT_GLOBAL_PER_SEC),
                global_burst=global_burst,
                client_rate=float(settings.RATE_LIMIT_CLIENT_PER_SEC),
                client_burst=client_burst,
            )
            app.config["RATE_LIMITER"] = limiter

        @app.before_request
        def _rate_limit_guard():
            if request.path == "/alloc" and request.method == "POST":
                client_key = request.remote_addr or "unknown"
                allowed, limit, remaining, retry_after = app.config["RATE_LIMITER"].allow(client_key)
                if not allowed:
                    headers = {
                        "Retry-After": str(max(1, retry_after)),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": str(remaining),
                    }
                    return {"error": "rate_limited"}, 429, headers

    app.register_blueprint(tokens_bp, url_prefix="/")

    @app.get("/health")
    def health():
        app.logger.info("health", extra={"path": "/health"})
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(app.config["SETTINGS"].PORT))
