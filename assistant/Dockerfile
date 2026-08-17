# Build context is the repo root (see docker-compose.yml `build.context: .`,
# `build.dockerfile: assistant/Dockerfile`) so this can COPY the sibling
# web/ directory in alongside the assistant app itself.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY assistant/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY assistant/app ./app
COPY web /web

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
