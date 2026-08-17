"""Per-turn extraction pass — DESIGN.md §5 step 5. Runs against Qwen3 7B via
Ollama, JSON-schema constrained. Actual per-record persistence now lives in
pipeline/memory_writer.py, shared with the manual memory-entry API routes
added for the web UI (see that module's docstring for why).
"""
from __future__ import annotations

from app.llm import ollama_client
from app.models.records import ExtractionResult
from app.pipeline import memory_writer


def build_extraction_prompt(*, turn_number: int, user_message: str, assistant_reply: str) -> str:
    return (
        f"Turn {turn_number}.\n"
        f"User message: {user_message}\n"
        f"Assistant reply: {assistant_reply}\n\n"
        "Extract only what's new or changed this turn as typed records matching "
        "the provided schema. Do not restate unchanged facts. Every person "
        "mentioned this turn must appear in mentioned_person_ids even if no "
        "other field about them changed. Do not invent specifics (dates, "
        "names, details) that weren't actually stated."
    )


async def run_extraction(*, turn_number: int, user_message: str, assistant_reply: str) -> ExtractionResult:
    prompt = build_extraction_prompt(turn_number=turn_number, user_message=user_message, assistant_reply=assistant_reply)
    result = ollama_client.extract_turn_records(prompt)

    for p in result.people:
        await memory_writer.write_person(p, last_mentioned_at=turn_number)
    for r in result.relationships:
        await memory_writer.write_relationship(r)
    for f in result.standing_facts:
        await memory_writer.write_standing_fact(f)
    for e in result.episodic_events:
        await memory_writer.write_episodic_event(e)
    for c in result.commitments:
        await memory_writer.write_commitment(c, default_created_turn=turn_number)

    return result
