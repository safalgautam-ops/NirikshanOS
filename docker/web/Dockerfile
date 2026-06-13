# Dockerfile defines the image used to run the web service (quart app)
FROM python:3.12-slim

# Working directory inside the container
WORKDIR /app

# layer-caching optimization
# by copying only requirements.txt first and installing dependencies before copying the rest of the code,
# Docker can reuse the cached "pip install" layer on every rebuild - as long as txt hasn't changed
# Any code change would invalidate the cache and force a full pip install every build without this process
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Runs your ASGI app via unicorn
CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8000"]
