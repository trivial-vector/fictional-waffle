"""Conversation turn orchestration — DESIGN.md §5. Analogous to the narrative
engine's pipeline/turn.py, simplified: no alignment-check-triggered re-plan,
since there's no plot skeleton to protect (DESIGN.md §2). The only thing
carried over from that mechanism is "does this message touch an open
commitment," which just gets surfaced into context rather than triggering
any re-planning step.
"""
from __future__ import annotations

from app.db import postgres
from app.models.records import MessageOutput
from app.pipeline import extraction, response, retrieval


async def run_turn(*, session_id: str, turn_number: int, user_message: str) -> MessageOutput:
    # Step 2: cheap entity-mention pass + open-commitment touch check.
    known_people = await postgres.get_all_person_names()
    mentioned_ids = retrieval.find_mentioned_people(user_message, known_people)

    open_commitments = await postgres.get_open_commitments()
    touched_commitments = retrieval.find_touched_commitments(mentioned_ids, open_commitments)
    touched_sensitive_commitments = any(c.get("sensitive") for c in touched_commitments)

    # Step 3: retrieval.
    retrieved = await retrieval.retrieve_context(query_text=user_message)
    context_block = retrieval.format_context_for_prompt(retrieved)

    touched_sensitive_facts = any(
        row.get("sensitive") for row in retrieved["matches"].get("standing_fact", [])
    )

    # Include touched-but-not-otherwise-retrieved commitments explicitly,
    # same principle as the narrative engine pulling implicated beats into
    # the narrator prompt regardless of retrieval ranking.
    if touched_commitments:
        context_block += "\n[explicitly touched open commitments]\n" + "\n".join(
            f"  {c['description']} (status: {c['status']})" for c in touched_commitments
        )

    # Step 4: response generation, tier resolved via escalation routing.
    profile_row = None
    pool = postgres.get_pool()
    async with pool.acquire() as conn:
        profile_row = await conn.fetchrow("SELECT * FROM user_profile WHERE id = 'user'")
    profile_summary = dict(profile_row) if profile_row else {"name": "unknown", "notes": "no profile on record yet"}

    stable_context = response.build_stable_context(profile_summary=str(profile_summary))
    reply, tier_used = response.compose_reply(
        stable_context=stable_context,
        user_message=user_message,
        retrieved_context=context_block,
        touched_sensitive_commitments=touched_sensitive_commitments,
        touched_sensitive_facts=touched_sensitive_facts,
    )

    # Step 5: extraction pass, now that the reply exists.
    await extraction.run_extraction(turn_number=turn_number, user_message=user_message, assistant_reply=reply)

    # Step 6 (consolidation) is NOT run here — it's a separate scheduled/
    # manually-triggered job (DESIGN.md §4), deliberately kept off the
    # live per-turn latency path.

    return MessageOutput(
        reply=reply,
        tier_used=tier_used,
        open_commitments_touched=[c["id"] for c in touched_commitments],
    )
