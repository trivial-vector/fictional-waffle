"""Manually (re-)apply schema.sql. Not required with docker-compose as-is
(Postgres auto-runs it from /docker-entrypoint-initdb.d/ on first init) —
exists for local dev or re-applying after an edit (schema.sql is idempotent).

Usage (from the repo root): python scripts/init_db.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "assistant"))

import asyncpg  # noqa: E402

from app.config import settings  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "assistant" / "app" / "db" / "schema.sql"


async def main() -> None:
    schema_sql = SCHEMA_PATH.read_text()
    conn = await asyncpg.connect(dsn=settings.postgres_dsn)
    try:
        await conn.execute(schema_sql)
        print(f"Applied {SCHEMA_PATH} to {settings.postgres_db}.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
