"""Consolidation/reflection pass, served by vLLM on the 3090 — repurposed
seat, same reasoning as before for *why* vLLM on this card (modern Ampere
hardware, vLLM's throughput advantage is largest where it's fully supported),
different job: this is no longer live per-turn NPC dialogue, it's a periodic
batch synthesis job over accumulated episodic_event records (DESIGN.md §4).
Not latency-critical the way a live chat turn is, but benefits from a larger,
higher-quality model than the extraction pass needs, which is the actual
justification for keeping a dedicated GPU seat for it rather than folding it
into the Ollama/1080-Ti extraction model.
"""
from __future__ import annotations

from openai import OpenAI

from app.config import settings

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=settings.vllm_base_url, api_key="not-needed")
    return _client


def run_consolidation_pass(
    *,
    episodes_block: str,
    current_state_block: str,
    schema_instructions: str,
    temperature: float = 0.3,
    max_tokens: int = 1200,
) -> str:
    """Low-ish temperature (not 0): consolidation needs to synthesize and
    paraphrase across many events, not reproduce any single one verbatim, so
    some sampling is appropriate — unlike the deterministic per-turn
    extraction pass. Returns raw text; caller (pipeline/consolidation.py) is
    responsible for parsing against ConsolidationUpdate."""
    system_prompt = (
        "You are the memory-consolidation process for a personal assistant. "
        "Merge the episodic events below into updated current-state records. "
        "Preserve uncertainty rather than inventing specifics you're not given. "
        f"{schema_instructions}\n\n"
        f"CURRENT STATE:\n{current_state_block}"
    )
    response = get_client().chat.completions.create(
        model=settings.consolidation_model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"EPISODIC EVENTS SINCE LAST CONSOLIDATION:\n{episodes_block}"},
        ],
    )
    return response.choices[0].message.content
