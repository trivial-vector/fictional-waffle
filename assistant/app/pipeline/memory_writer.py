"""Shared per-record-type persistence logic — refactored out of
pipeline/extraction.py so both the automatic per-turn extraction pass and the
manual memory-entry endpoints (api/routes.py, added for the web UI's memory
browser) write through the exact same path: compute search_text, compute
embedding, upsert to Postgres, mirror into Kuzu where applicable. Two writers
producing memory through different code paths was the alternative, and it's
exactly the kind of duplication that drifts out of sync over time — not worth
it here.
"""
from __future__ import annotations

from app.db import graph, postgres
from app.llm import ollama_client
from app.models.records import Commitment, EpisodicEvent, PersonRecord, RelationshipRecord, StandingFact


def _status_value(status) -> str:
    return status.value if hasattr(status, "value") else status


async def write_person(p: PersonRecord, *, last_mentioned_at: int | None = None) -> None:
    search_text = " ".join(filter(None, [p.name, p.relation_context, p.notes]))
    embedding = ollama_client.embed_text(search_text) if search_text else None
    await postgres.upsert_record(
        "person_record",
        {
            "id": p.id,
            "name": p.name,
            "relation_context": p.relation_context,
            "notes": p.notes,
            "last_mentioned_at": last_mentioned_at if last_mentioned_at is not None else p.last_mentioned_at,
            "search_text": search_text,
            "embedding": embedding,
        },
    )
    graph.get_graph().upsert_person(p.id, p.name)


async def write_relationship(r: RelationshipRecord) -> None:
    search_text = " ".join(filter(None, [r.party_a, r.party_b, r.relation_type]))
    embedding = ollama_client.embed_text(search_text) if search_text else None
    await postgres.upsert_record(
        "relationship_record",
        {
            "id": r.id,
            "party_a": r.party_a,
            "party_b": r.party_b,
            "relation_type": r.relation_type,
            "polarity": r.polarity,
            "valid_from_turn": r.valid_from_turn,
            "search_text": search_text,
            "embedding": embedding,
        },
    )
    # Graph only models Person<->Person relationships explicitly — a party of
    # "user" has no Person node by default, so user-involving relationships
    # are stored in Postgres but not mirrored into Kuzu. Known gap, not a
    # silent one; see DESIGN.md.
    if r.party_a != "user" and r.party_b != "user":
        graph.get_graph().upsert_relationship(r.party_a, r.party_b, r.relation_type or "", r.polarity, r.valid_from_turn)


async def write_standing_fact(f: StandingFact) -> None:
    search_text = f.fact
    embedding = ollama_client.embed_text(search_text) if search_text else None
    await postgres.upsert_record(
        "standing_fact",
        {
            "id": f.id,
            "subject_id": f.subject_id,
            "fact": f.fact,
            "category": f.category,
            "sensitive": f.sensitive,
            "valid_from_turn": f.valid_from_turn,
            "valid_to_turn": f.valid_to_turn,
            "evidence_turn": f.evidence_turn,
            "search_text": search_text,
            "embedding": embedding,
        },
    )


async def write_episodic_event(e: EpisodicEvent) -> None:
    search_text = " ".join(filter(None, [e.summary, e.occurred_at, *e.participants]))
    embedding = ollama_client.embed_text(search_text) if search_text else None
    await postgres.upsert_record(
        "episodic_event",
        {
            "id": e.id,
            "summary": e.summary,
            "participants": e.participants,
            "occurred_at": e.occurred_at,
            "category": e.category,
            "sentiment": e.sentiment,
            "sensitive": e.sensitive,
            "session_id": e.session_id,
            "consolidated": e.consolidated,
            "search_text": search_text,
            "embedding": embedding,
        },
    )


async def write_commitment(c: Commitment, *, default_created_turn: int | None = None) -> None:
    search_text = c.description
    embedding = ollama_client.embed_text(search_text) if search_text else None
    status = _status_value(c.status)
    await postgres.upsert_record(
        "commitment",
        {
            "id": c.id,
            "description": c.description,
            "concerns": c.concerns,
            "status": status,
            "sensitive": c.sensitive,
            "created_turn": c.created_turn if c.created_turn is not None else default_created_turn,
            "resolved_turn": c.resolved_turn,
            "resolution_note": c.resolution_note,
            "search_text": search_text,
            "embedding": embedding,
        },
    )
    g = graph.get_graph()
    g.upsert_commitment(c.id, c.description, status)
    for person_id in c.concerns:
        g.upsert_concern(c.id, person_id)
