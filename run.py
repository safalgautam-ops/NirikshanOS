"""ASGI entry point.

Run with: uvicorn run:app
"""

from app import create_app

# Build the Quart instance once at import time - this is the object
# uvicorn loads when run as `uvicorn run:app`.
app = create_app()
