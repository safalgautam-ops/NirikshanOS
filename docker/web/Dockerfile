FROM python:3.12-slim

WORKDIR /app

# Copy only requirements first so this layer is cached unless deps change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Overridden by docker-compose.yml's `command:` (adds --reload) in dev.
CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "8000"]
