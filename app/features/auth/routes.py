"""Auth routes.

Thin Quart views — all business logic lives in service.py.
Each route's only job: read the request, call the service, pick a response.
"""

from __future__ import annotations

import secrets

from quart import (
    Blueprint,
    abort,
    current_app,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from app.core.security.sessions import (
    PENDING_2FA_COOKIE,
    SESSION_COOKIE,
    clear_session_cookie,
    create_pending_2fa_token,
    create_session,
    delete_session,
    login_required,
    set_session_cookie,
    verify_pending_2fa_token,
)
from app.features.auth import repository
from app.features.auth.oauth import (
    consume_oauth_state,
    create_oauth_state,
    github_auth_url,
    github_exchange_code,
    google_auth_url,
    google_exchange_code,
)
from app.features.auth.service import (
    AuthError,
    EmailNotVerifiedError,
    TwoFactorRequiredError,
    activate_account,
    authenticate,
    begin_passkey_authentication,
    begin_passkey_registration,
    begin_totp_setup,
    complete_passkey_authentication,
    complete_passkey_registration,
    confirm_totp_setup,
    disable_totp,
    disconnect_provider,
    forgot_password,
    link_oauth_account,
    oauth_authenticate,
    register,
    resend_activation,
    reset_password,
    verify_2fa,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# ── helpers ───────────────────────────────────────────────────────────────────


def _ip() -> str | None:
    return request.remote_addr


def _ua() -> str | None:
    return request.headers.get("User-Agent")


async def _full_login(user_id: str):
    token = await create_session(user_id, _ip(), _ua())
    resp = await make_response(redirect(url_for("dashboard")))
    set_session_cookie(resp, token)
    return resp


# ── login / logout ────────────────────────────────────────────────────────────


@auth_bp.route("/login", methods=["GET", "POST"])
async def login():
    error = None
    activated = request.args.get("activated")
    reset_done = request.args.get("reset")
    if request.method == "POST":
        form = await request.form
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        try:
            user_id = await authenticate(email=email, password=password)
        except EmailNotVerifiedError as exc:
            return redirect(url_for("auth.activate") + f"?email={exc.email}")
        except TwoFactorRequiredError as exc:
            pending = create_pending_2fa_token(
                exc.user_id, current_app.config["SECRET_KEY"]
            )
            resp = await make_response(redirect(url_for("auth.verify_2fa_view")))
            resp.set_cookie(
                PENDING_2FA_COOKIE, pending, max_age=300, httponly=True, samesite="Lax"
            )
            return resp
        except AuthError as exc:
            error = str(exc)
        else:
            return await _full_login(user_id)
    return await render_template(
        "auth/login.html", error=error, activated=activated, reset_done=reset_done
    )


@auth_bp.route("/logout", methods=["POST"])
async def logout():
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await delete_session(token)
    resp = await make_response(redirect(url_for("auth.login")))
    clear_session_cookie(resp)
    return resp


# ── registration + activation ─────────────────────────────────────────────────


@auth_bp.route("/register", methods=["GET", "POST"])
async def register_view():
    error = None
    if request.method == "POST":
        form = await request.form
        name = form.get("name", "").strip()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        confirm = form.get("confirm_password", "")

        if not name or not email:
            error = "Name and email are required."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        else:
            try:
                await register(name=name, email=email, password=password)
            except AuthError as exc:
                error = str(exc)
            else:
                return redirect(url_for("auth.activate") + f"?email={email}")
    return await render_template("auth/register.html", error=error)


@auth_bp.route("/activate", methods=["GET", "POST"])
async def activate():
    email = request.args.get("email", "")
    resent = request.args.get("resent")
    error = None
    if request.method == "POST":
        form = await request.form
        email = form.get("email", "").strip().lower()
        code = form.get("code", "").strip()
        try:
            await activate_account(email, code)
        except AuthError as exc:
            error = str(exc)
        else:
            return redirect(url_for("auth.login") + "?activated=1")
    return await render_template(
        "auth/activate.html", email=email, error=error, resent=resent
    )


@auth_bp.route("/resend-activation", methods=["POST"])
async def resend_activation_view():
    form = await request.form
    email = form.get("email", "").strip().lower()
    await resend_activation(email)
    return redirect(url_for("auth.activate") + f"?email={email}&resent=1")


# ── password reset ────────────────────────────────────────────────────────────


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
async def forgot_password_view():
    if request.method == "POST":
        form = await request.form
        email = form.get("email", "").strip().lower()
        await forgot_password(email)
        return redirect(url_for("auth.reset_password_view") + f"?email={email}")
    return await render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password", methods=["GET", "POST"])
async def reset_password_view():
    # read the email from the URL query string because the reset link user clicked
    # probably looked like /reset-password?email=alice@x.com
    email = request.args.get("email", "")
    # start with no error. if validation fails later, we'll set this to a message.
    error = None
    if request.method == "POST":
        form = await request.form
        email = form.get("email", "").strip().lower()
        code = form.get("code", "").strip()
        new_pw = form.get("password", "")
        confirm = form.get("confirm_password", "")
        if len(new_pw) < 8:
            error = "Password must be at least 8 characters."
        elif new_pw != confirm:
            error = "Passwords do not match."
        else:
            try:
                await reset_password(email, code, new_pw)
            except AuthError as exc:
                error = str(exc)
            else:
                # the else runs only if no exception was raised
                # redirect the user to the login page with a reset=1 query parameter
                # reset=1 indicates that the password was successfully reset to let the login template know about it
                return redirect(url_for("auth.login") + "?reset=1")
    # if there was an error, render the reset password template with the error message
    return await render_template("auth/reset_password.html", email=email, error=error)


# ── Google OAuth ──────────────────────────────────────────────────────────────


@auth_bp.route("/google")
async def google_login():
    state = await create_oauth_state("google", "login")
    return redirect(google_auth_url(state))


@auth_bp.route("/google/callback")
async def google_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return redirect(url_for("auth.login"))
    state_data = await consume_oauth_state(state)
    if not state_data:
        return redirect(url_for("auth.login"))
    try:
        user_info = await google_exchange_code(code)
    except Exception:
        return redirect(url_for("auth.login") + "?error=oauth_failed")

    if state_data.get("intent") == "link":
        try:
            await link_oauth_account(state_data["user_id"], "google", user_info)
        except AuthError:
            pass
        return redirect(url_for("auth.settings_connections"))

    try:
        user_id = await oauth_authenticate("google", user_info)
    except AuthError as exc:
        return await render_template("auth/login.html", error=str(exc))
    return await _full_login(user_id)


# ── GitHub OAuth ──────────────────────────────────────────────────────────────


@auth_bp.route("/github")
async def github_login():
    state = await create_oauth_state("github", "login")
    return redirect(github_auth_url(state))


@auth_bp.route("/github/callback")
async def github_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    if not code or not state:
        return redirect(url_for("auth.login"))
    state_data = await consume_oauth_state(state)
    if not state_data:
        return redirect(url_for("auth.login"))
    try:
        user_info = await github_exchange_code(code)
    except Exception:
        return redirect(url_for("auth.login") + "?error=oauth_failed")

    if state_data.get("intent") == "link":
        try:
            await link_oauth_account(state_data["user_id"], "github", user_info)
        except AuthError:
            pass
        return redirect(url_for("auth.settings_connections"))

    try:
        user_id = await oauth_authenticate("github", user_info)
    except AuthError as exc:
        return await render_template("auth/login.html", error=str(exc))
    return await _full_login(user_id)


# ── 2FA verify (mid-login) ────────────────────────────────────────────────────


@auth_bp.route("/2fa/verify", methods=["GET", "POST"])
async def verify_2fa_view():
    token = request.cookies.get(PENDING_2FA_COOKIE, "")
    user_id = verify_pending_2fa_token(token, current_app.config["SECRET_KEY"])
    if not user_id:
        return redirect(url_for("auth.login"))

    error = None
    if request.method == "POST":
        form = await request.form
        code = form.get("code", "").strip()
        try:
            await verify_2fa(user_id, code)
        except AuthError as exc:
            error = str(exc)
        else:
            resp = await make_response(redirect(url_for("dashboard")))
            resp.delete_cookie(PENDING_2FA_COOKIE)
            real_token = await create_session(user_id, _ip(), _ua())
            set_session_cookie(resp, real_token)
            return resp
    return await render_template("auth/2fa/verify.html", error=error)


# ── 2FA setup (settings) ─────────────────────────────────────────────────────


@auth_bp.route("/2fa/setup", methods=["GET", "POST"])
@login_required
async def setup_2fa():
    user = await repository.get_user_by_id(g.user_id)
    if user and user["twoFactorEnabled"]:
        return redirect(url_for("auth.settings_connections"))

    error = None
    if request.method == "POST":
        form = await request.form
        secret = form.get("secret", "")
        code = form.get("code", "").strip()
        try:
            plain_codes = await confirm_totp_setup(g.user_id, secret, code)
        except AuthError as exc:
            error = str(exc)
            user = await repository.get_user_by_id(g.user_id)
            from app.features.auth.totp import qr_base64

            qr = qr_base64(secret, user["email"])
            return await render_template(
                "auth/2fa/setup.html", secret=secret, qr=qr, error=error
            )
        return await render_template("auth/2fa/backup_codes.html", codes=plain_codes)

    secret, qr = await begin_totp_setup(g.user_id)
    return await render_template(
        "auth/2fa/setup.html", secret=secret, qr=qr, error=None
    )


@auth_bp.route("/2fa/disable", methods=["POST"])
@login_required
async def disable_2fa():
    await disable_totp(g.user_id)
    return redirect(url_for("auth.settings_connections"))


# ── Passkey registration (settings) ──────────────────────────────────────────


@auth_bp.route("/passkey/register-begin", methods=["POST"])
@login_required
async def passkey_register_begin():
    options = await begin_passkey_registration(g.user_id)
    return jsonify(options)


@auth_bp.route("/passkey/register-complete", methods=["POST"])
@login_required
async def passkey_register_complete():
    body = await request.get_json()
    name = (body or {}).pop("name", None)
    try:
        await complete_passkey_registration(g.user_id, body or {}, name)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@auth_bp.route("/passkey/delete/<passkey_id>", methods=["POST"])
@login_required
async def passkey_delete(passkey_id: str):
    await repository.delete_passkey(passkey_id, g.user_id)
    return redirect(url_for("auth.settings_connections"))


# ── Passkey authentication (login) ────────────────────────────────────────────


@auth_bp.route("/passkey/auth-begin", methods=["POST"])
async def passkey_auth_begin():
    challenge_key = secrets.token_urlsafe(16)
    options = await begin_passkey_authentication(challenge_key)
    return jsonify({"options": options, "challenge_key": challenge_key})


@auth_bp.route("/passkey/auth-complete", methods=["POST"])
async def passkey_auth_complete():
    body = await request.get_json() or {}
    challenge_key = body.get("challenge_key", "")
    credential = body.get("credential", {})
    try:
        user_id = await complete_passkey_authentication(challenge_key, credential)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    token = await create_session(user_id, _ip(), _ua())
    resp = await make_response(jsonify({"ok": True, "redirect": url_for("dashboard")}))
    set_session_cookie(resp, token)
    return resp


# ── Account connections (settings) ───────────────────────────────────────────


@auth_bp.route("/settings/connections")
@login_required
async def settings_connections():
    user = await repository.get_user_by_id(g.user_id)
    accounts = await repository.get_accounts_by_user(g.user_id)
    passkeys = await repository.get_passkeys_by_user(g.user_id)
    two_factor = await repository.get_two_factor(g.user_id)
    connected = {a["providerId"] for a in accounts}
    return await render_template(
        "auth/settings/connections.html",
        user=user,
        accounts=accounts,
        passkeys=passkeys,
        two_factor=two_factor,
        connected=connected,
        error=request.args.get("error"),
        success=request.args.get("success"),
    )


@auth_bp.route("/settings/connect/<provider>")
@login_required
async def connect_provider(provider: str):
    if provider not in ("google", "github"):
        abort(404)
    state = await create_oauth_state(provider, "link", user_id=g.user_id)
    if provider == "google":
        return redirect(google_auth_url(state))
    return redirect(github_auth_url(state))


@auth_bp.route("/settings/disconnect/<provider>", methods=["POST"])
@login_required
async def disconnect_provider_view(provider: str):
    try:
        await disconnect_provider(g.user_id, provider)
    except AuthError as exc:
        return redirect(url_for("auth.settings_connections") + f"?error={str(exc)}")
    return redirect(url_for("auth.settings_connections") + "?success=1")
