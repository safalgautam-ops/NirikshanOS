"""Auth routes: register, login, logout.

Thin Quart views - validation/lookup lives in service.py, cookie
mechanics live in core/security/sessions.py. A view's job is just to
glue request data to those and pick a response.
"""

from quart import Blueprint, make_response, redirect, render_template, request, url_for

from app.core.security.sessions import (
    SESSION_COOKIE,
    clear_session_cookie,
    create_session,
    delete_session,
    set_session_cookie,
)
from app.features.auth.service import AuthError, authenticate, register

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
async def login():
    error = None
    if request.method == "POST":
        form = await request.form
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")

        try:
            user_id = await authenticate(email=email, password=password)
        except AuthError as exc:
            error = str(exc)
        else:
            token = await create_session(
                user_id, request.remote_addr, request.headers.get("User-Agent")
            )
            response = await make_response(redirect(url_for("dashboard")))
            set_session_cookie(response, token)
            return response

    return await render_template("auth/login.html", error=error)


@auth_bp.route("/register", methods=["GET", "POST"])
async def register_view():
    error = None
    if request.method == "POST":
        form = await request.form
        name = form.get("name", "").strip()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        confirm_password = form.get("confirm_password", "")

        if not name or not email:
            error = "Name and email are required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm_password:
            error = "Passwords do not match."
        else:
            try:
                await register(name=name, email=email, password=password)
            except AuthError as exc:
                error = str(exc)
            else:
                return redirect(
                    url_for("auth.login")
                )  # auth is the blueprint, login is the name of a view function

    return await render_template("auth/register.html", error=error)


@auth_bp.route("/logout", methods=["POST"])
async def logout():
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await delete_session(token)

    response = await make_response(redirect(url_for("auth.login")))
    clear_session_cookie(response)
    return response
