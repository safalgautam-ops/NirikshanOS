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

    APP_URL = os.environ.get("APP_URL", "http://localhost:8000")

    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "NirikshanOS <noreply@example.com>")

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

    WEBAUTHN_RP_ID = os.environ.get("WEBAUTHN_RP_ID", "localhost")
    WEBAUTHN_RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "NirikshanOS")
    WEBAUTHN_RP_ORIGIN = os.environ.get("WEBAUTHN_RP_ORIGIN", "http://localhost:8000")
