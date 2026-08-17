"""Postgres + pgvector access layer. Ported from the narrative engine's
db/postgres.py — same hybrid-search pattern, retargeted table set. Unlike that
project's `plot_beat.preconditions`, no table in this schema uses JSONB (the
array-typed columns here — `communication_prefs`, `participants`, `concerns`
— are plain Postgres TEXT[], which asyncpg encodes/decodes natively without
the explicit-cast workaround JSONB needed), so that codepath is dropped here
rather than carried over unused.
"""
from __future__ import annotations

from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

from app.config import settings

SEARCHABLE_TABLES = {
    "user_profile",
    "person_record",
    "relationship_record",
    "standing_fact",
    "episodic_event",
    "commitment",
}

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.postgres_dsn,
            min_size=2,
            max_size=10,
            init=_init_connection,
        )
    return _pool


async def _init_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Postgres pool not initialized — call init_pool() at startup")
    return _pool


async def upsert_record(table: str, row: dict[str, Any], conflict_col: str = "id") -> None:
    if table not in SEARCHABLE_TABLES:
        raise ValueError(f"Unrecognized table: {table}")

    columns = list(row.keys())
    values = list(row.values())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
    update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != conflict_col)

    query = f"""
        INSERT INTO {table} ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT ({conflict_col}) DO UPDATE SET {update_clause}, updated_at = now()
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(query, *values)


async def hybrid_search(
    table: str,
    query_text: str,
    query_embedding: list[float],
    limit: int = 10,
    lexical_weight: float = 0.4,
    semantic_weight: float = 0.6,
) -> list[dict[str, Any]]:
    """Same two-halves-in-one-query pattern as the narrative engine: lexical
    rank fused with cosine similarity, 0.4/0.6 starting weights — a knob to
    tune once there are real retrieval failures to look at, not a tuned
    value."""
    if table not in SEARCHABLE_TABLES:
        raise ValueError(f"Table not searchable: {table}")

    query = f"""
        WITH lexical AS (
            SELECT id, ts_rank_cd(search_vector, plainto_tsquery('english', $1)) AS lex_score
            FROM {table}
            WHERE search_vector @@ plainto_tsquery('english', $1)
            ORDER BY lex_score DESC
            LIMIT 40
        ),
        semantic AS (
            SELECT id, 1 - (embedding <=> $2) AS sem_score
            FROM {table}
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> $2
            LIMIT 40
        ),
        fused AS (
            SELECT COALESCE(l.id, s.id) AS id,
                   COALESCE(l.lex_score, 0) * $3 + COALESCE(s.sem_score, 0) * $4 AS combined_score
            FROM lexical l
            FULL OUTER JOIN semantic s ON l.id = s.id
        )
        SELECT t.*, f.combined_score
        FROM fused f
        JOIN {table} t ON t.id = f.id
        ORDER BY f.combined_score DESC
        LIMIT $5
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, query_text, query_embedding, lexical_weight, semantic_weight, limit)
    return [dict(r) for r in rows]


_LIST_ORDER_COLUMN = {
    "user_profile": "updated_at",
    "person_record": "updated_at",
    "relationship_record": "updated_at",
    "standing_fact": "updated_at",
    "episodic_event": "created_at",
    "commitment": "updated_at",
}


async def list_table(table: str, limit: int = 500) -> list[dict[str, Any]]:
    """Generic "list everything" for the web UI's memory browser. `table` is
    checked against a fixed map rather than interpolated from caller input
    directly, since it still ends up in the SQL string."""
    if table not in _LIST_ORDER_COLUMN:
        raise ValueError(f"Unrecognized table: {table}")
    order_col = _LIST_ORDER_COLUMN[table]
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT * FROM {table} ORDER BY {order_col} DESC LIMIT $1", limit)
    return [dict(r) for r in rows]


async def get_open_commitments() -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM commitment WHERE status = 'open' ORDER BY created_turn NULLS LAST")
    return [dict(r) for r in rows]


async def get_person(person_id: str) -> dict[str, Any] | None:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM person_record WHERE id = $1", person_id)
    return dict(row) if row else None


async def get_all_person_names() -> dict[str, str]:
    """id -> name, used by the entity-mention matcher (same pattern as the
    narrative engine's alignment check, retargeted to real people)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name FROM person_record")
    return {r["id"]: r["name"] for r in rows}


async def get_unconsolidated_episodes(limit: int = 200) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM episodic_event WHERE consolidated = false ORDER BY created_at ASC LIMIT $1", limit
        )
    return [dict(r) for r in rows]


async def mark_episodes_consolidated(episode_ids: list[str]) -> None:
    if not episode_ids:
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE episodic_event SET consolidated = true WHERE id = ANY($1::text[])", episode_ids)
