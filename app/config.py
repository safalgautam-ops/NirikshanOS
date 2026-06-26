"""Application configuration loaded from environment variables.

Docker Compose injects these via env_file (.env). No external config
library is used - plain os.environ with sensible local defaults.
"""

import os


# Wrapping a group of related settings
class Config:
    # Used to sign sessions/CSRF tokens later - override via .env in real use.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    DEBUG = os.environ.get("QUART_DEBUG", "false").lower() == "true"

    # MySQL connection details - "mysql"/"redis" as defaults match the
    # service names in docker-compose.yml, so this works inside containers
    # out of the box; 127.0.0.1 defaults are for running outside Docker.
    # Docker compose sets this to "db" (used when running in containers)
    # 127.0.0.1 is fallback if env var not set (used when running locally)
    DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "nirikshan")

    REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

    # holds all the MinIO storage settings the app needs
    # ties together the Docker setup and the nginx setup you saw earlier
    # MinIO needs different addresses depending on who is talking to it.
    # MINIO_ENDPOINT is the address the app itself uses to reach MinIO.
    # Inside Docker, containers talk to each other by service name, so the app reaches MinIO at http://minio:9000
    # The name minio only works inside the Docker network -- your browser has no idea what minio means
    MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://127.0.0.1:9000")
    """
    For private files (case evidence), the app doesn't make them public.
    Instead, when an authorized user needs to download one, the app generates
    a special temporary link — a presigned URL — that grants access to that one
    file for a short time. The browser then uses that link to fetch the file
    directly from MinIO, not through the app.
    """
    MINIO_PRESIGN_ENDPOINT = os.environ.get(
        "MINIO_PRESIGN_ENDPOINT", "http://localhost:9000"
    )
    # for public files, no signed link is needed. The browser just hits http://localhost/media/...
    # and connecting back to the nginx config -- nginx's /media/ location
    MINIO_PUBLIC_URL = os.environ.get("MINIO_PUBLIC_URL", "http://localhost/media")
    MINIO_ACCESS_KEY = os.environ.get(
        "MINIO_ACCESS_KEY", "minioadmin"
    )  # username for the app's S3 client to log in
    MINIO_SECRET_KEY = os.environ.get(
        "MINIO_SECRET_KEY", "minioadmin"
    )  # password for the same
    MINIO_BUCKET_PUBLIC = os.environ.get(
        "MINIO_BUCKET_PUBLIC", "nirikshan-public"
    )  # bucket for the public file
    MINIO_BUCKET_PRIVATE = os.environ.get(
        "MINIO_BUCKET_PRIVATE", "nirikshan-private"
    )  # bucket for the private file

    # A file upload is a part of the request body, so this affects uploads.
    # This is the Quart app outer limit.
    # Now, Nginx and quart app allows up to 100GB uploads.
    # platform-level maxmium
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024 * 1024  # 100 GB

    APP_URL = os.environ.get("APP_URL", "http://localhost:8000")

    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL = os.environ.get(
        "RESEND_FROM_EMAIL", "NirikshanOS <noreply@example.com>"
    )

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

    WEBAUTHN_RP_ID = os.environ.get("WEBAUTHN_RP_ID", "localhost")
    WEBAUTHN_RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "NirikshanOS")
    WEBAUTHN_RP_ORIGIN = os.environ.get("WEBAUTHN_RP_ORIGIN", "http://localhost:8000")
