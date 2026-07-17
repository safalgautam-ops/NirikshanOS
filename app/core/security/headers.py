"""Security headers middleware."""

from flask import Flask, Response

from app.config import Config

BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",  # prevents MIME confusion attacks
    "X-Frame-Options": "DENY",  # prevents clickjacking attacks
    "Referrer-Policy": "same-origin",  # prevents leaking referrer info to other origins
}

# CSP is a security policy that prevents loading resources from unapproved
# origins. Application scripts remain same-origin. jsDelivr is allowed only for
# Tailwind's browser compiler, which requires unsafe-eval. The same-origin Rive
# renderer needs wasm-unsafe-eval. MinIO's presigned endpoint is allowed for
# direct evidence uploads; data:/blob: images support QR and Rive rendering.
PRODUCTION_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; "
    f"connect-src 'self' {Config.MINIO_PRESIGN_ENDPOINT}"
)

# app: Flask - a type annotation on a function parameter
def apply_security_headers(app: Flask) -> None:
    csp = PRODUCTION_CSP

    @app.after_request
    async def set_security_headers(response: Response) -> Response:
        # setdefault: don't override a header a route deliberately set itself.
        for header, value in BASE_SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        response.headers.setdefault("Content-Security-Policy", csp)
        return response
