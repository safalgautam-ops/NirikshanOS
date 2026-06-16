"""Security headers middleware."""

from quart import Quart, Response

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",  # prevents MIME confusion attacks
    "X-Frame-Options": "DENY",  # prevents clickjacking attacks
    "Referrer-Policy": "same-origin",  # prevents leaking referrer info to other origins
    # CSP is a security policy that prevents loading resources from other origins
    # default-src 'self' means only resources from the same origin are allowed with default rule for all content types
    # style-src allows 'unsafe-inline' for inline style="" attributes (e.g. dynamic
    # progress bar widths); script-src stays at the strict default-src 'self'.
    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'",  # prevents Cross-Site Scripting (XSS) attacks
}


# app: Quart - a type annotation on a function parameter
def apply_security_headers(app: Quart) -> None:
    @app.after_request
    async def set_security_headers(response: Response) -> Response:
        # setdefault: don't override a header a route deliberately set itself.
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response
