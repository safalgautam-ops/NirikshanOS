FROM python:3.12-slim

WORKDIR /app

# Same requirements as the web image - kept identical so analyzers can use
# the same custom DB/Redis modules under app/core.
COPY requirements.txt .
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

CMD ["python", "-m", "workers.worker_main"]
