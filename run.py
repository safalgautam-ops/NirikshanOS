"""WSGI entry point.

Development:  flask --app run:app run --host 0.0.0.0 --port 8000 --debug
Production:   gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 8 run:app
"""

from app import create_app

app = create_app()
