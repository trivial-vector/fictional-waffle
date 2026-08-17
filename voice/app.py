"""Local speech-to-text microservice, wrapping faster-whisper, CPU-only.

Deliberately kept off both GPUs: the 3090 and 1080 Ti are already committed
(consolidation/response and extraction/embeddings respectively), and
faster-whisper's CTranslate2 int8 CPU path is fast enough for short voice
clips that GPU time isn't worth contesting for this — the Threadripper's 16
cores have headroom this doesn't compete with the LLM stack for.

This is also a deliberate architectural choice, not just a hardware one:
running STT locally rather than reaching for the browser's built-in
SpeechRecognition API keeps voice input consistent with the rest of this
project's privacy stance (DESIGN.md §7) — the browser API sends audio to a
third-party cloud service (typically Google) to transcribe, which is exactly
the kind of thing this project has otherwise gone out of its way to avoid.

NOTE: faster-whisper's `WhisperModel(...).transcribe(...)` call shape below
reflects its long-stable documented API but wasn't re-verified against a live
install this session — same category of caveat as the rest of this project's
unverified integration points. ffmpeg (installed in the Dockerfile) is
required for faster-whisper/ctranslate2 to decode non-WAV browser recording
formats (typically webm/opus from MediaRecorder).
"""
from __future__ import annotations

import os
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel

MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "small")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

app = FastAPI(title="Local Voice-to-Text")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type=COMPUTE_TYPE)
    return _model


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict:
    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio upload")

    suffix = os.path.splitext(audio.filename or "clip.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(content)
        tmp.flush()
        segments, _info = get_model().transcribe(tmp.name, beam_size=5)
        text = " ".join(segment.text.strip() for segment in segments).strip()

    return {"text": text}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model_size": MODEL_SIZE}
