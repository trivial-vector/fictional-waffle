# Offline mock of the real assistant backend — see app.py's docstring.
# Deliberately minimal: FastAPI + uvicorn + python-multipart only. No
# asyncpg/kuzu/ollama/vllm/anthropic client libraries, so this image has no
# dependency on the GPU desktop being reachable — that's the entire point.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
