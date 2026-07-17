FROM python:3.12-slim

WORKDIR /app

# Copy the uv binary from the official image (single file, no install needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first so this layer is cached until requirements.txt changes.
# --system  → install into the system Python (no virtualenv inside the container)
# --no-cache → skip uv's download cache to keep the image smaller
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "run:app"]
