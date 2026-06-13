"""Application factory.

create_app() builds the Quart instance, registers the security
middleware/routes, and wires up startup/shutdown via Quart's lifespan
hooks (before_serving / after_serving - these map directly onto the
ASGI 'lifespan' protocol's startup/shutdown events when run under
uvicorn).

The actual ASGI app instance lives in run.py at the project root.
"""

from quart import Quart, render_template

from app.config import Config
from app.core.db.pool import close_pool, get_pool, init_pool
from app.core.security.headers import apply_security_headers
from app.extensions import close_redis, get_redis, init_redis


def create_app() -> Quart:
    # template_folder/static_folder are relative to this package (app/),
    # so this picks up app/templates and app/static automatically.
    app = Quart(__name__, template_folder="templates", static_folder="static")
    # Loads SECRET_KEY, DB_*, REDIS_URL etc. from app/config.py (env-backed).
    # Quart reads every uppercase attribute from the class and loads into app.config
    app.config.from_object(Config)

    # Registers the after_request hook that adds CSP/X-Frame-Options/etc.
    apply_security_headers(app)

    @app.before_serving
    async def startup() -> None:
        """ASGI lifespan 'startup': open the DB pool and Redis client once."""
        # Opens the shared MySQL connection pool used by Model/QueryBuilder.
        await init_pool(
            host=app.config["DB_HOST"],
            port=app.config["DB_PORT"],
            user=app.config["DB_USER"],
            password=app.config["DB_PASSWORD"],
            db=app.config["DB_NAME"],
        )
        # Opens the shared Redis client (sessions/rate-limit/pub-sub later).
        await init_redis(app.config["REDIS_URL"])  # create once at start

    @app.after_serving
    async def shutdown() -> None:
        """ASGI lifespan 'shutdown': close the DB pool and Redis client."""
        # Releases pooled MySQL connections cleanly on server stop.
        await close_pool()
        # Closes the Redis connection cleanly on server stop.
        await close_redis()

    @app.route("/")
    async def dashboard():
        # Renders app/templates/dashboard/index.html via layouts/base.html.
        return await render_template("dashboard/index.html")

    @app.route("/healthz")
    async def healthz():
        # Borrows a pooled connection and runs a trivial query to prove
        # the app can actually talk to MySQL (not just that it's configured).
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()

        # Same check for Redis - PING fails fast if Redis is unreachable.
        redis_client = get_redis()
        await redis_client.ping()

        return {"status": "ok"}

    return app
