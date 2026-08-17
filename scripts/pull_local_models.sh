#!/usr/bin/env bash
# Pulls the local models onto the Ollama service (1080 Ti). Run after
# `docker compose up -d ollama`. The vLLM/consolidation model downloads
# automatically from CONSOLIDATION_MODEL_HF_REPO on first container start.

set -euo pipefail

: "${EXTRACTION_MODEL:=qwen3:7b}"
: "${EMBEDDING_MODEL:=qwen3-embedding:0.6b}"

echo "Pulling ${EXTRACTION_MODEL} (extraction pass)..."
docker compose exec ollama ollama pull "${EXTRACTION_MODEL}"

echo "Pulling ${EMBEDDING_MODEL} (embeddings)..."
docker compose exec ollama ollama pull "${EMBEDDING_MODEL}"

echo "Done."
