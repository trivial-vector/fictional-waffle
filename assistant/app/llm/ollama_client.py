"""Per-turn extraction + embeddings, served by Ollama on the 1080 Ti. Direct
port of the narrative engine's ollama_client.py — same model tier, same
reasoning (schema-constrained decoding closes the local/frontier gap for
structured output specifically), same unverified-API-shape caveat on
`client.embed()`, retargeted to ExtractionResult.
"""
from __future__ import annotations

import json

import ollama

from app.config import settings
from app.models.records import ExtractionResult

_client: ollama.Client | None = None


def get_client() -> ollama.Client:
    global _client
    if _client is None:
        _client = ollama.Client(host=settings.ollama_host)
    return _client


def extract_turn_records(prompt: str) -> ExtractionResult:
    response = get_client().chat(
        model=settings.extraction_model,
        messages=[{"role": "user", "content": prompt}],
        format=ExtractionResult.model_json_schema(),
        options={"temperature": 0},
    )
    content = response["message"]["content"]
    return ExtractionResult.model_validate(json.loads(content))


def embed_text(text: str) -> list[float]:
    response = get_client().embed(model=settings.embedding_model, input=text)
    return response["embeddings"][0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    response = get_client().embed(model=settings.embedding_model, input=texts)
    return response["embeddings"]
