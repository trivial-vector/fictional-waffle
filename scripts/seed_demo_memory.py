"""Seeds a minimal demo memory so the turn/retrieval/consolidation pipeline is
exercisable end to end: a user profile, one person, a standing fact, an
open (sensitive) commitment concerning that person, and an unconsolidated
episodic event.

Usage (from the repo root): python scripts/seed_demo_memory.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "assistant"))

from app.config import settings  # noqa: E402
from app.db import graph, postgres  # noqa: E402
from app.llm import ollama_client  # noqa: E402


async def main() -> None:
    await postgres.init_pool()
    g = graph.init_graph(settings.kuzu_db_path)

    profile_text = "Justin prefers concise direct answers works in tech"
    await postgres.upsert_record(
        "user_profile",
        {
            "id": "user",
            "name": "Justin",
            "timezone": "America/Denver",
            "communication_prefs": ["concise", "direct", "minimal formatting"],
            "search_text": profile_text,
            "embedding": ollama_client.embed_text(profile_text),
        },
    )

    sarah_text = "Sarah Justin's sister lives in Denver going through a hard time at work"
    await postgres.upsert_record(
        "person_record",
        {
            "id": "sarah",
            "name": "Sarah",
            "relation_context": "user's sister",
            "notes": "Going through a difficult stretch at work",
            "last_mentioned_at": 0,
            "search_text": sarah_text,
            "embedding": ollama_client.embed_text(sarah_text),
        },
    )
    g.upsert_person("sarah", "Sarah")

    fact_text = "Justin wants to be reminded to check in on Sarah regularly right now"
    await postgres.upsert_record(
        "standing_fact",
        {
            "id": "fact_checkin_sarah",
            "subject_id": "user",
            "fact": fact_text,
            "category": "preference",
            "sensitive": True,
            "valid_from_turn": 0,
            "valid_to_turn": None,
            "evidence_turn": 0,
            "search_text": fact_text,
            "embedding": ollama_client.embed_text(fact_text),
        },
    )

    commitment_text = "Follow up with Justin about how Sarah is doing"
    await postgres.upsert_record(
        "commitment",
        {
            "id": "commit_checkin_sarah",
            "description": commitment_text,
            "concerns": ["sarah"],
            "status": "open",
            "sensitive": True,
            "created_turn": 0,
            "resolved_turn": None,
            "resolution_note": None,
            "search_text": commitment_text,
            "embedding": ollama_client.embed_text(commitment_text),
        },
    )
    g.upsert_commitment("commit_checkin_sarah", commitment_text, "open")
    g.upsert_concern("commit_checkin_sarah", "sarah")

    event_text = "Justin mentioned Sarah had a rough week at work and seemed stressed on the phone"
    await postgres.upsert_record(
        "episodic_event",
        {
            "id": "event_sarah_rough_week",
            "summary": event_text,
            "participants": ["sarah"],
            "occurred_at": "last week",
            "category": "emotional",
            "sentiment": -0.4,
            "sensitive": True,
            "session_id": "demo-session",
            "consolidated": False,
            "search_text": event_text,
            "embedding": ollama_client.embed_text(event_text),
        },
    )

    print("Seeded demo memory: user profile, sarah, standing fact, open commitment, unconsolidated event.")
    await postgres.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
