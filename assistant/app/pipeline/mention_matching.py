"""Pure, dependency-free logic split out of pipeline/retrieval.py
specifically so it can be unit-tested without needing asyncpg/kuzu/ollama
importable (retrieval.py itself pulls those in at module level for the async
DB/graph calls). Mirrors the narrative engine's pipeline/alignment.py, which
was kept dependency-free for the same reason.
"""
from __future__ import annotations


def find_mentioned_people(text: str, known_people: dict[str, str]) -> set[str]:
    """Same crude substring-matching caveat as the narrative engine's
    find_mentioned_entities — misses pronouns/nicknames/indirect reference."""
    lowered = text.lower()
    return {person_id for person_id, name in known_people.items() if name and name.lower() in lowered}


def find_touched_commitments(mentioned_person_ids: set[str], open_commitments: list[dict]) -> list[dict]:
    touched = []
    for commitment in open_commitments:
        if set(commitment.get("concerns") or []) & mentioned_person_ids:
            touched.append(commitment)
    return touched
