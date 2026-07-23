"""Security headers middleware."""

from flask import Flask, Response

from app.config import Config

BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}

# jsDelivr + wasm-unsafe-eval are scoped exceptions for Tailwind's browser compiler only.
PRODUCTION_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; "
    f"connect-src 'self' {Config.MINIO_PRESIGN_ENDPOINT}"
)


def apply_security_headers(app: Flask) -> None:
    csp = PRODUCTION_CSP

    @app.after_request
    async def set_security_headers(response: Response) -> Response:
        for header, value in BASE_SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        response.headers.setdefault("Content-Security-Policy", csp)
        return response
