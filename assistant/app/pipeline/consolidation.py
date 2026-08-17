"""Consolidation / reflection pass — DESIGN.md §4. The genuinely new pipeline
stage relative to the narrative engine: not a per-turn operation, triggered
on a schedule or manually (see api/routes.py `/consolidate`). Pulls
unconsolidated episodic_event records, asks the larger local model (vLLM/
3090) to merge them into updated person/standing-fact current-state plus any
synthesized higher-level reflections, then marks the source episodes
consolidated.

No feasibility/sanity check on the model's output before writing it — same
category of gap as the narrative engine's un-validated re-plan step, worth
the same caveat: don't trust this blindly once it's handling a real person's
information, add a review step before this runs unattended long-term.
"""
from __future__ import annotations

import json

from app.db import graph, postgres
from app.llm import ollama_client, vllm_client
from app.models.records import ConsolidationUpdate

SCHEMA_INSTRUCTIONS = (
    "Respond as JSON matching: {\"updated_people\": [...], "
    "\"updated_standing_facts\": [...], \"new_reflections\": [...], "
    "\"consolidated_episode_ids\": [str, ...]}. Each entry in updated_people "
    "and updated_standing_facts/new_reflections must match the PersonRecord "
    "and StandingFact schemas respectively (id, name/fact, etc.)."
)


def _format_episodes(episodes: list[dict]) -> str:
    lines = []
    for e in episodes:
        lines.append(
            f"- [{e['id']}] {e['summary']} (participants: {e.get('participants')}, "
            f"category: {e.get('category')}, sentiment: {e.get('sentiment')}, "
            f"occurred_at: {e.get('occurred_at')})"
        )
    return "\n".join(lines) if lines else "(none)"


def _format_current_state(people: list[dict], facts: list[dict]) -> str:
    lines = ["[people]"]
    for p in people:
        lines.append(f"- [{p['id']}] {p['name']}: {p.get('notes') or 'no notes yet'}")
    lines.append("[standing facts]")
    for f in facts:
        lines.append(f"- [{f['id']}] {f['fact']}")
    return "\n".join(lines)


async def run_consolidation(*, batch_limit: int = 200) -> ConsolidationUpdate:
    episodes = await postgres.get_unconsolidated_episodes(limit=batch_limit)
    if not episodes:
        return ConsolidationUpdate()

    # Current-state snapshot for context. A full implementation would scope
    # this to people/facts actually referenced by the pulled episodes rather
    # than fetching everything — left simple here since batch size is capped.
    pool = postgres.get_pool()
    async with pool.acquire() as conn:
        people_rows = [dict(r) for r in await conn.fetch("SELECT * FROM person_record")]
        fact_rows = [dict(r) for r in await conn.fetch("SELECT * FROM standing_fact")]

    raw = vllm_client.run_consolidation_pass(
        episodes_block=_format_episodes(episodes),
        current_state_block=_format_current_state(people_rows, fact_rows),
        schema_instructions=SCHEMA_INSTRUCTIONS,
    )

    try:
        parsed = json.loads(raw)
        update = ConsolidationUpdate.model_validate(parsed)
    except Exception:  # noqa: BLE001 — best-effort background job, see below
        # Consolidation is best-effort background work, not a live user-facing
        # call — on parse failure, skip this batch rather than raise, so a
        # scheduled job doesn't hard-fail. The episodes stay unconsolidated
        # and get picked up next run.
        return ConsolidationUpdate()

    g = graph.get_graph()
    for p in update.updated_people:
        search_text = " ".join(filter(None, [p.name, p.relation_context, p.notes]))
        embedding = ollama_client.embed_text(search_text) if search_text else None
        await postgres.upsert_record(
            "person_record",
            {
                "id": p.id,
                "name": p.name,
                "relation_context": p.relation_context,
                "notes": p.notes,
                "last_mentioned_at": p.last_mentioned_at,
                "search_text": search_text,
                "embedding": embedding,
            },
        )
        g.upsert_person(p.id, p.name)

    for f in [*update.updated_standing_facts, *update.new_reflections]:
        embedding = ollama_client.embed_text(f.fact)
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
                "search_text": f.fact,
                "embedding": embedding,
            },
        )

    consolidated_ids = update.consolidated_episode_ids or [e["id"] for e in episodes]
    await postgres.mark_episodes_consolidated(consolidated_ids)

    return update
