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

# Run as a fixed non-root user so analyzer containers launched via
# `--user $(id -u):$(id -g)` inherit a real UID instead of 0 (root).
# UID 1001 is arbitrary; must not collide with the host's important users.
RUN groupadd -g 1001 worker && useradd -u 1001 -g worker -s /bin/false -M worker
USER worker

CMD ["python", "-m", "workers.worker_main"]
