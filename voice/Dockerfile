FROM python:3.12-slim

WORKDIR /app

# ffmpeg is required for faster-whisper/ctranslate2 to decode non-WAV audio
# (browser MediaRecorder output is typically webm/opus).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV PYTHONUNBUFFERED=1
# Downloaded model weights land in the default HF cache; mount a volume at
# /root/.cache/huggingface in docker-compose.yml so re-creating this
# container doesn't re-download the model every time.
EXPOSE 8090

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
