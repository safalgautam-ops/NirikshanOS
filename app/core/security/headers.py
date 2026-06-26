"""Security headers middleware."""

from quart import Quart, Response

from app.config import Config

BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",  # prevents MIME confusion attacks
    "X-Frame-Options": "DENY",  # prevents clickjacking attacks
    "Referrer-Policy": "same-origin",  # prevents leaking referrer info to other origins
}

# CSP is a security policy that prevents loading resources from other origins.
# default-src 'self' means only resources from the same origin are allowed by
# default, and that also covers connect-src (XHR/fetch targets) when
# connect-src isn't set explicitly - which is exactly why evidence part
# uploads need a real connect-src directive: app/static/js/evidence-upload.js
# PUTs each part straight to MinIO's presigned URL via XMLHttpRequest, on a
# different origin (MINIO_PRESIGN_ENDPOINT, e.g. http://localhost:9000) than
# the page itself. Without explicitly allowing that origin, the browser
# blocks the request before it's even sent - indistinguishable from a real
# network failure to the JS (xhr.onerror fires either way), which is exactly
# what "Network error during upload" on every single part turned out to be.
# style-src allows 'unsafe-inline' for inline style="" attributes (e.g.
# dynamic progress bar widths). img-src adds data: on top of 'self' - without
# it, default-src's 'self' silently blocks data: URIs, which is how the TOTP
# setup page embeds its QR code (no origin to fetch it from, it's generated
# server-side and inlined directly). Production keeps script-src at the
# strict default-src 'self' - no third-party script origins, ever.
PRODUCTION_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    f"connect-src 'self' {Config.MINIO_PRESIGN_ENDPOINT}"
)

# Dev-only: layouts/base.html loads @tailwindcss/browser from jsdelivr when
# debug=True (live-compiles input.css in the browser - see templating.py's
# read_input_css_for_browser_runtime()). wasm-unsafe-eval is needed because
# that runtime is a WASM build of Tailwind's engine; 'unsafe-inline' on
# script-src is needed because it injects its own inline <script> to re-scan
# the DOM as elements change (dialogs/popups opening, etc.) - without it the
# first paint works but newly-revealed elements silently lose their styles.
# This meaningfully weakens CSP's main XSS protection, which is exactly why
# it's gated to QUART_DEBUG and never applied in production.
DEV_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; "
    f"connect-src 'self' {Config.MINIO_PRESIGN_ENDPOINT}"
)


# app: Quart - a type annotation on a function parameter
def apply_security_headers(app: Quart) -> None:
    csp = DEV_CSP if app.config["DEBUG"] else PRODUCTION_CSP

    @app.after_request
    async def set_security_headers(response: Response) -> Response:
        # setdefault: don't override a header a route deliberately set itself.
        for header, value in BASE_SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        response.headers.setdefault("Content-Security-Policy", csp)
        return response
