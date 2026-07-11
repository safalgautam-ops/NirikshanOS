FROM python:3.12-slim

WORKDIR /app

# Docker CLI — needed so docker_runner.py can call `docker run` from inside the container.
RUN apt-get update \
 && apt-get install -y --no-install-recommends docker.io docker-cli \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

CMD ["python", "-m", "workers.worker_main"]
