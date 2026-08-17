"""Two-stage retrieval — DESIGN.md §5 step 3. Direct port of the narrative
engine's pipeline/retrieval.py: hybrid (lexical+vector) search over the
compact typed records, then one-hop graph expansion from matched people, plus
(new here) commitments concerning those people pulled in explicitly. Same gap
as before: no evidence-pointer/verbatim lookup implemented yet.

Also relies on the cheap non-LLM step in pipeline/mention_matching.py (split
out into its own dependency-free module — see that file's docstring), the
retargeted analog of the narrative engine's alignment check, simplified per
DESIGN.md §2: there's no plot skeleton to protect, so this only needs to
answer "does this message touch a known person or an open commitment," not
"does it invalidate a beat's precondition."
"""
from __future__ import annotations

from app.db import graph, postgres
from app.llm import ollama_client
from app.pipeline.mention_matching import find_mentioned_people, find_touched_commitments  # noqa: F401 — re-exported


async def retrieve_context(*, query_text: str, limit_per_table: int = 5) -> dict:
    query_embedding = ollama_client.embed_text(query_text)

    results = {}
    for table in ("person_record", "relationship_record", "standing_fact", "episodic_event", "commitment"):
        results[table] = await postgres.hybrid_search(table, query_text, query_embedding, limit=limit_per_table)

    g = graph.get_graph()
    expanded_relationships = {
        person["id"]: g.one_hop_relationships(person["id"]) for person in results["person_record"]
    }
    concerning_commitments = {
        person["id"]: g.commitments_concerning(person["id"]) for person in results["person_record"]
    }

    return {
        "matches": results,
        "one_hop_relationships": expanded_relationships,
        "commitments_concerning": concerning_commitments,
    }


def format_context_for_prompt(retrieved: dict) -> str:
    lines: list[str] = []
    for table, rows in retrieved["matches"].items():
        if not rows:
            continue
        lines.append(f"[{table}]")
        for row in rows:
            lines.append(f"  {row}")
    if retrieved["one_hop_relationships"]:
        lines.append("[relationships]")
        for person_id, rels in retrieved["one_hop_relationships"].items():
            for r in rels:
                lines.append(f"  {person_id} -> {r['other_name']} ({r['relation_type']}, polarity {r['polarity']})")
    if retrieved["commitments_concerning"]:
        lines.append("[commitments concerning matched people]")
        for person_id, commitments in retrieved["commitments_concerning"].items():
            for c in commitments:
                lines.append(f"  {person_id}: {c['description']} ({c['status']})")
    return "\n".join(lines)
