"""HTTP surface. Extended for the web UI: /message now accepts an optional
file attachment (multipart/form-data instead of a plain JSON body — see
pipeline/file_ingest.py for why), and a /memory/* family of endpoints backs
the memory browser page (list, create/update, and search across every typed
record table, all going through the same pipeline/memory_writer.py path the
automatic extraction pass uses).

Same gap as before, still not solved here: no session/turn-counter
persistence — `turn_number` is caller-supplied. The web UI tracks it
client-side (see web/static/chat.js) as a practical workaround, not a fix.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.db import postgres
from app.llm import ollama_client
from app.models.records import (
    Commitment,
    ConsolidationUpdate,
    EpisodicEvent,
    MessageOutput,
    PersonRecord,
    RelationshipRecord,
    StandingFact,
    UserProfile,
)
from app.pipeline import file_ingest, memory_writer
from app.pipeline.consolidation import run_consolidation
from app.pipeline.turn import run_turn

router = APIRouter()

TABLE_MAP = {
    "people": "person_record",
    "relationships": "relationship_record",
    "standing-facts": "standing_fact",
    "episodic-events": "episodic_event",
    "commitments": "commitment",
    "user-profile": "user_profile",
}


@router.post("/message", response_model=MessageOutput)
async def send_message(
    turn_number: int,
    session_id: str = Form(...),
    user_message: str = Form(...),
    file: UploadFile | None = File(None),
) -> MessageOutput:
    full_message = user_message
    if file is not None:
        content = await file.read()
        extracted = file_ingest.extract_text(file.filename or "attachment", content)
        full_message += file_ingest.format_attachment_block(file.filename or "attachment", extracted)

    try:
        return await run_turn(session_id=session_id, turn_number=turn_number, user_message=full_message)
    except Exception as exc:  # noqa: BLE001 — prototype-level error surface
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/consolidate", response_model=ConsolidationUpdate)
async def consolidate(batch_limit: int = 200) -> ConsolidationUpdate:
    try:
        return await run_consolidation(batch_limit=batch_limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/commitments/open")
async def open_commitments() -> list[dict]:
    return await postgres.get_open_commitments()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ── Memory browser: list ────────────────────────────────────────────────


@router.get("/memory/{kind}")
async def list_memory(kind: str) -> list[dict]:
    table = TABLE_MAP.get(kind)
    if table is None:
        raise HTTPException(status_code=404, detail=f"Unknown memory kind: {kind}")
    return await postgres.list_table(table)


@router.get("/memory/search/{kind}")
async def search_memory(kind: str, q: str, limit: int = 10) -> list[dict]:
    table = TABLE_MAP.get(kind)
    if table is None or table == "user_profile":
        raise HTTPException(status_code=404, detail=f"Unknown or unsearchable memory kind: {kind}")
    query_embedding = ollama_client.embed_text(q)
    return await postgres.hybrid_search(table, q, query_embedding, limit=limit)


# ── Memory browser: manual create/update ────────────────────────────────
# Each accepts the same Pydantic model the automatic extraction pass
# produces — the manual-entry form on the web UI and the LLM-driven
# extraction pass write through the identical schema and the identical
# pipeline/memory_writer.py functions.


@router.post("/memory/people")
async def create_person(person: PersonRecord) -> dict:
    await memory_writer.write_person(person)
    return {"status": "ok", "id": person.id}


@router.post("/memory/relationships")
async def create_relationship(relationship: RelationshipRecord) -> dict:
    await memory_writer.write_relationship(relationship)
    return {"status": "ok", "id": relationship.id}


@router.post("/memory/standing-facts")
async def create_standing_fact(fact: StandingFact) -> dict:
    await memory_writer.write_standing_fact(fact)
    return {"status": "ok", "id": fact.id}


@router.post("/memory/episodic-events")
async def create_episodic_event(event: EpisodicEvent) -> dict:
    await memory_writer.write_episodic_event(event)
    return {"status": "ok", "id": event.id}


@router.post("/memory/commitments")
async def create_commitment(commitment: Commitment) -> dict:
    await memory_writer.write_commitment(commitment)
    return {"status": "ok", "id": commitment.id}


@router.post("/memory/user-profile")
async def upsert_user_profile(profile: UserProfile) -> dict:
    search_text = " ".join(filter(None, [profile.name, profile.timezone, *profile.communication_prefs]))
    embedding = ollama_client.embed_text(search_text) if search_text else None
    await postgres.upsert_record(
        "user_profile",
        {
            "id": profile.id,
            "name": profile.name,
            "timezone": profile.timezone,
            "communication_prefs": profile.communication_prefs,
            "search_text": search_text,
            "embedding": embedding,
        },
    )
    return {"status": "ok", "id": profile.id}
