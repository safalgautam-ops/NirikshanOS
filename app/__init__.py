"""Application factory.

create_app() builds the Quart instance, registers the security
middleware/routes, and wires up startup/shutdown via Quart's lifespan
hooks (before_serving / after_serving - these map directly onto the
ASGI 'lifespan' protocol's startup/shutdown events when run under
uvicorn).

The actual ASGI app instance lives in run.py at the project root.
"""

from quart import Quart, g, render_template, request, url_for

from app.config import Config
from app.core.db.pool import close_pool, get_pool, init_pool
from app.core.object_storage import bootstrap_buckets
from app.core.security.csrf import apply_csrf_protection
from app.core.security.headers import apply_security_headers
from app.core.security.htmx import redirect_or_htmx
from app.core.security.org_permission_registry import (
    sync_to_db as sync_org_permissions_to_db,
)
from app.core.security.organization_gate import needs_organization_onboarding
from app.core.security.permission_registry import sync_to_db as sync_permissions_to_db
from app.core.security.permissions import get_visible_nav_keys
from app.core.security.sessions import apply_session_loader, login_required
from app.core.templating import cn, html_attrs, read_input_css_for_browser_runtime
from app.extensions import close_redis, get_redis, init_redis
from app.features.auth.repository import get_user_by_id
from app.features.auth.routes import auth_bp
from app.features.cases.routes import cases_bp
from app.features.evidence.routes import evidence_bp
from app.features.onboarding.routes import onboarding_bp
from app.features.organizations.routes import organizations_bp
from app.features.rbac.routes import rbac_bp
from app.features.staff.routes import staff_bp
from app.features.timeline.routes import timeline_bp
from app.features.users.routes import users_bp


def create_app() -> Quart:
    # template_folder/static_folder are relative to this package (app/),
    # so this picks up app/templates and app/static automatically.
    app = Quart(__name__, template_folder="templates", static_folder="static")
    # Loads SECRET_KEY, DB_*, REDIS_URL etc. from app/config.py (env-backed).
    # Quart reads every uppercase attribute from the class and loads into app.config
    app.config.from_object(Config)

    # components/ui/*.html macros call cn()/html_attrs() directly as globals.
    app.jinja_env.globals["cn"] = cn
    app.jinja_env.globals["html_attrs"] = html_attrs
    # Jinja doesn't expose Python's builtin set() by default - templates need
    # it for `x in (value or set())` patterns against role_ids/etc.
    app.jinja_env.globals["set"] = set
    # layouts/base.html uses these to pick the dev-only @tailwindcss/browser
    # runtime (live, no build step) vs. the static built tailwind.css used in
    # production - flip QUART_DEBUG=true/false in .env to switch.
    app.jinja_env.globals["debug"] = app.config["DEBUG"]
    app.jinja_env.globals["read_input_css_for_browser_runtime"] = (
        read_input_css_for_browser_runtime
    )

    # Registers the after_request hook that adds CSP/X-Frame-Options/etc.
    apply_security_headers(app)
    # Sets g.user_id from the session cookie on every request.
    apply_session_loader(app)
    # Double-submit cookie CSRF check on every POST/PUT/PATCH/DELETE.
    apply_csrf_protection(app)

    # When an admin creates a staff account, the system may create that account with a temporary password.
    # Until the account is activated, the user must change their password before they can log in. (g.must_change_password=True)
    # Routes that are allowed to be accessed without a password change: change-password, logout, static files, and None (default route).
    _PASSWORD_GATE_EXEMPT = {"auth.change_password_view", "auth.logout", "static", None}

    @app.before_request
    async def require_password_change() -> None:
        if g.must_change_password and request.endpoint not in _PASSWORD_GATE_EXEMPT:
            return redirect_or_htmx(url_for("auth.change_password_view"))

    # Self-registered users (no role permissions, no organization yet) get
    # routed straight to the create-or-join page on login/register, not the
    # dashboard - Dashboard itself is locked along with everything else
    # until they create or join an organization (sidebar shows a lock icon -
    # see sidebar.html). A direct hit on any locked URL, including "/",
    # bounces to onboarding rather than a dashboard there's nothing to do on
    # yet.
    _ORG_GATE_EXEMPT = {
        "onboarding.index",
        "onboarding.create_view",
        "onboarding.join_view",
        "onboarding.regenerate_invite_view",
        "onboarding.download_document_view",
        # Document management while pending/rejected (fix/add what was
        # submitted before a platform admin reviews it) and deleting the
        # organization itself (e.g. to start over after a rejection) both
        # need to work in every non-active state, not just once approved.
        "onboarding.upload_document_view",
        "onboarding.delete_document_view",
        "onboarding.delete_organization_view",
        # Leaving (or, for the owner, transferring ownership first) needs to
        # work in every non-active state too - a member shouldn't be stuck
        # in a pending/rejected org with no way out.
        "onboarding.leave_view",
        "onboarding.transfer_ownership_view",
        # Account settings (profile, password, 2FA, passkeys, connected
        # providers) are personal to the user, not tied to organization
        # membership - every account needs access to these regardless of
        # onboarding state, the same way logout always works.
        "auth.settings_connections",
        "auth.update_profile_view",
        "auth.change_password_settings_view",
        "auth.setup_2fa",
        "auth.disable_2fa",
        "auth.passkey_register_begin",
        "auth.passkey_register_complete",
        "auth.passkey_delete",
        "auth.connect_provider",
        "auth.disconnect_provider_view",
        "auth.google_callback",
        "auth.github_callback",
        "auth.logout",
        "static",
        None,
    }

    @app.before_request
    async def require_organization() -> None:
        if g.user_id is None or g.must_change_password:
            return
        if request.endpoint in _ORG_GATE_EXEMPT:
            return
        # check if this logged-in user still needs organization onboarding
        if await needs_organization_onboarding(g.user_id):
            return redirect_or_htmx(url_for("onboarding.index"))

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(organizations_bp)
    app.register_blueprint(rbac_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(cases_bp)
    app.register_blueprint(evidence_bp)
    app.register_blueprint(timeline_bp)

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

        # Belt-and-suspenders: the docker-compose minio-init service already
        # creates both buckets + the public-read policy on every `compose up`,
        # but this makes the app self-sufficient too (e.g. after wiping the
        # minio_data volume, or running `compose up web` on its own).
        await bootstrap_buckets()

        # Every feature's permissions.py module ran register_permissions() at
        # import time (above, via each routes.py import) - upsert them into the
        # DB and grant them to System Admin, so a new permission never needs a
        # hand-written migration.
        await sync_permissions_to_db()
        # Same idea, for the org-scoped permission catalog (organization_permissions) -
        # see org_permission_registry.sync_to_db()'s docstring for why this one does
        # NOT auto-grant anything (there's no single global "Org Admin" to grant to).
        await sync_org_permissions_to_db()

    @app.after_serving
    async def shutdown() -> None:
        """ASGI lifespan 'shutdown': close the DB pool and Redis client."""
        # Releases pooled MySQL connections cleanly on server stop.
        await close_pool()
        # Closes the Redis connection cleanly on server stop.
        await close_redis()

    @app.route("/")
    @login_required
    async def dashboard():
        user = await get_user_by_id(g.user_id)
        visible_keys = await get_visible_nav_keys(g.user_id)
        return await render_template(
            "dashboard/dashboard.html", user=user, visible_keys=visible_keys
        )

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
