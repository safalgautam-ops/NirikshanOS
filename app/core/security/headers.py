"""Security headers middleware."""

from quart import Quart, Response

BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",  # prevents MIME confusion attacks
    "X-Frame-Options": "DENY",  # prevents clickjacking attacks
    "Referrer-Policy": "same-origin",  # prevents leaking referrer info to other origins
}

# CSP is a security policy that prevents loading resources from other origins.
# default-src 'self' means only resources from the same origin are allowed by
# default; style-src allows 'unsafe-inline' for inline style="" attributes
# (e.g. dynamic progress bar widths). Production keeps script-src at the
# strict default-src 'self' - no third-party script origins, ever.
PRODUCTION_CSP = "default-src 'self'; style-src 'self' 'unsafe-inline'"

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
    "default-src 'self'; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://cdn.jsdelivr.net"
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
