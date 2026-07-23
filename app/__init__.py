"""Application factory."""

from flask import Flask, g, redirect, render_template, request, url_for

from app.config import Config
from app.core.async_runtime import AsyncFlask
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
from app.core.templating import asset_version, cn, html_attrs
from app.extensions import close_redis, get_redis, init_redis
from app.features.analysis.routes import analysis_bp
from app.features.auth.repository import get_user_by_id
from app.features.auth.routes import auth_bp
from app.features.admin_modules.routes import admin_modules_bp
from app.features.instances.routes import instances_bp
from app.features.categories.routes import categories_bp
from app.features.plans.routes import plans_bp
from app.features.plans.public_routes import public_plans_bp
from app.features.notes.routes import notes_bp
from app.features.reports.routes import reports_bp
from app.features.cases.routes import cases_bp
from app.features.dashboard.service import get_admin_dashboard, get_org_dashboard
from app.features.evidence.routes import evidence_bp
from app.features.finance.routes import finance_bp
from app.features.finance.billing_routes import billing_bp
from app.features.onboarding.routes import onboarding_bp
from app.features.organizations.routes import organizations_bp
from app.features.rbac.routes import rbac_bp
from app.features.staff.routes import staff_bp
from app.features.timeline.routes import timeline_bp
from app.features.users.routes import users_bp


def create_app() -> Flask:
    app = AsyncFlask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)

    app.jinja_env.globals["cn"] = cn
    app.jinja_env.globals["html_attrs"] = html_attrs
    app.jinja_env.globals["asset_version"] = asset_version
    app.jinja_env.globals["set"] = set

    apply_security_headers(app)
    apply_session_loader(app)
    apply_csrf_protection(app)

    _PASSWORD_GATE_EXEMPT = {"auth.change_password_view", "auth.logout", "static", None}

    @app.before_request
    async def require_password_change() -> None:
        if g.must_change_password and request.endpoint not in _PASSWORD_GATE_EXEMPT:
            return redirect_or_htmx(url_for("auth.change_password_view"))

    _ORG_GATE_EXEMPT = {
        "onboarding.index",
        "onboarding.create_view",
        "onboarding.join_view",
        "onboarding.regenerate_invite_view",
        "onboarding.download_document_view",
        "onboarding.upload_document_view",
        "onboarding.delete_document_view",
        "onboarding.delete_organization_view",
        "onboarding.leave_view",
        "onboarding.transfer_ownership_view",
        "auth.settings_connections",
        "auth.update_profile_view",
        "auth.change_password_settings_view",
        "auth.setup_2fa",
        "auth.disable_2fa",
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
    app.register_blueprint(analysis_bp)
    app.register_blueprint(admin_modules_bp)
    app.register_blueprint(instances_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(timeline_bp)
    app.register_blueprint(plans_bp)
    app.register_blueprint(public_plans_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(billing_bp)

    @app.before_serving
    async def startup() -> None:
        """Open the DB pool and Redis client once per Flask process."""
        await init_pool(
            host=app.config["DB_HOST"],
            port=app.config["DB_PORT"],
            user=app.config["DB_USER"],
            password=app.config["DB_PASSWORD"],
            db=app.config["DB_NAME"],
        )
        await init_redis(app.config["REDIS_URL"])

        await bootstrap_buckets()

        await sync_permissions_to_db()
        await sync_org_permissions_to_db()

    @app.after_serving
    async def shutdown() -> None:
        """Close the DB pool and Redis client at process shutdown."""
        await close_pool()
        await close_redis()

    @app.route("/")
    async def home():
        return render_template("home/index.html")

    @app.route("/get-started")
    async def get_started():
        """Send the homepage CTA to the correct authoritative destination."""
        if g.user_id is None:
            return redirect(url_for("auth.login", next=url_for("get_started")))
        if g.is_platform_staff:
            return redirect(url_for("plans.list_view"))
        return redirect(url_for("billing.plan_picker_view"))

    @app.route("/dashboard")
    @login_required
    async def dashboard():
        user = await get_user_by_id(g.user_id)
        visible_keys = await get_visible_nav_keys(g.user_id)
        admin_dashboard = await get_admin_dashboard() if g.is_platform_staff else None
        org_dashboard = None if g.is_platform_staff else await get_org_dashboard(g.user_id)
        return render_template(
            "dashboard/dashboard.html",
            user=user,
            visible_keys=visible_keys,
            admin=admin_dashboard,
            org_dash=org_dashboard,
        )

    @app.route("/healthz")
    async def healthz():
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()

        redis_client = get_redis()
        await redis_client.ping()

        return {"status": "ok"}

    return app
