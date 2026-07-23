"""Application configuration loaded from environment variables."""

import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "nirikshan")

    REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

    MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://127.0.0.1:9000")
    """
    For private files (case evidence), the app doesn't make them public.
    Instead, when an authorized user needs to download one, the app generates
    a special temporary link — a presigned URL — that grants access to that one
    file for a short time. The browser then uses that link to fetch the file
    directly from MinIO, not through the app.
    """
    MINIO_PRESIGN_ENDPOINT = os.environ.get("MINIO_PRESIGN_ENDPOINT", "http://localhost:9000")
    MINIO_PUBLIC_URL = os.environ.get("MINIO_PUBLIC_URL", "http://localhost/media")
    MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET_PUBLIC = os.environ.get("MINIO_BUCKET_PUBLIC", "nirikshan-public")
    MINIO_BUCKET_PRIVATE = os.environ.get("MINIO_BUCKET_PRIVATE", "nirikshan-private")

    MAX_CONTENT_LENGTH = 100 * 1024 * 1024 * 1024

    APP_URL = os.environ.get("APP_URL", "http://localhost:8000")

    JOBS_DIR = os.environ.get("JOBS_DIR", "/storage/jobs")

    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "NirikshanOS <noreply@example.com>")

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

    ESEWA_PRODUCT_CODE = os.environ.get("ESEWA_PRODUCT_CODE", "EPAYTEST")
    ESEWA_SECRET_KEY = os.environ.get("ESEWA_SECRET_KEY", "8gBm/:&EnhH.1/q")
    ESEWA_ENV = os.environ.get("ESEWA_ENV", "sandbox")

    WEBAUTHN_RP_ID = os.environ.get("WEBAUTHN_RP_ID", "localhost")
    WEBAUTHN_RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "NirikshanOS")
    WEBAUTHN_RP_ORIGIN = os.environ.get("WEBAUTHN_RP_ORIGIN", "http://localhost:8000")
