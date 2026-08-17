"""Offline mock of the real assistant API — see ../docker-compose.test.yml.

This exists so the web UI and the local voice pipeline can be exercised
completely disconnected from the real stack: no Postgres, no Kuzu, no
Ollama/vLLM, no ANTHROPIC_API_KEY, and critically, no reachability to the
desktop that owns the GPUs at all. It reproduces just enough of
`assistant/app/api/routes.py`'s HTTP surface — same paths, same request/
response shapes the web UI already expects — for `web/` to render, submit
messages, and read/write the memory browser against, using nothing but an
in-memory dict.

This is a UI/plumbing test double, not a backend. Replies are canned, there
is no real retrieval/extraction/consolidation/escalation logic, and nothing
persists past a container restart. Don't mistake a working session against
this for a working session against the real `assistant` service — it only
proves the frontend and the voice roundtrip work, not that the memory
pipeline does.
"""
from __future__ import annotations

import itertools

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Assistant Mock Backend (offline test harness)")

# Same reasoning as the real backend's main.py: the web UI calling in is
# cross-origin by construction, so this is wide open. This is a throwaway
# local test double, never meant to be exposed beyond localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory "database" ────────────────────────────────────────────────
# One seed row per table so the memory browser has something to show on
# first load. Wiped back to this exact state on every container restart —
# there is no volume, deliberately, since this is a scratch environment.

_DB: dict[str, dict[str, dict]] = {
    "people": {
        "sarah": {
            "id": "sarah",
            "name": "Sarah",
            "relation_context": "friend",
            "notes": "Seed record from the offline mock backend — not a real person.",
            "last_mentioned_at": 1,
        },
    },
    "relationships": {},
    "standing-facts": {
        "fact_mock": {
            "id": "fact_mock",
            "subject_id": "user",
            "fact": "This is seed data from the offline test harness, not your real memory.",
            "category": "other",
            "sensitive": False,
            "valid_from_turn": 0,
            "valid_to_turn": None,
            "evidence_turn": None,
        },
    },
    "episodic-events": {},
    "commitments": {
        "commit_mock": {
            "id": "commit_mock",
            "description": "Example open commitment, for testing the commitments tab and the chat's 'touched' meta line.",
            "concerns": ["sarah"],
            "status": "open",
            "sensitive": False,
            "created_turn": 0,
            "resolved_turn": None,
            "resolution_note": None,
        },
    },
    "user-profile": {
        "user": {"id": "user", "name": None, "timezone": None, "communication_prefs": []},
    },
}


def _table(kind: str) -> dict[str, dict]:
    if kind not in _DB:
        raise HTTPException(status_code=404, detail=f"Unknown memory kind: {kind}")
    return _DB[kind]


def _upsert(kind: str, payload: dict) -> dict:
    table = _table(kind)
    record_id = payload.get("id")
    if not record_id:
        raise HTTPException(status_code=422, detail="Record is missing an 'id' field.")
    table[record_id] = payload
    return {"status": "ok", "id": record_id}


# ── Chat ─────────────────────────────────────────────────────────────────

_CANNED_REPLIES = itertools.cycle(
    [
        "This is the offline mock backend — no real model or memory behind this "
        "reply. It exists to test the chat UI itself, not conversation quality.",
        "Still the mock backend. Your message round-tripped fine, which is what "
        "this harness is actually checking — the request/response plumbing, not "
        "the answer.",
        "Third canned reply in the cycle — if you're seeing this rotate, the "
        "chat UI's fetch/render loop is working correctly against a fake server.",
    ]
)


@app.post("/api/message")
async def send_message(
    turn_number: int,
    session_id: str = Form(...),
    user_message: str = Form(...),
    file: UploadFile | None = File(None),
) -> dict:
    reply = next(_CANNED_REPLIES)
    if file is not None:
        content = await file.read()
        reply += (
            f" (received attachment '{file.filename}', {len(content)} bytes — "
            "not parsed, this mock doesn't do extraction.)"
        )
    touched = [c["id"] for c in _DB["commitments"].values() if c["status"] == "open"][:1]
    return {"reply": reply, "tier_used": "mock", "open_commitments_touched": touched}


@app.post("/api/consolidate")
async def consolidate(batch_limit: int = 200) -> dict:
    return {
        "updated_people": [],
        "updated_standing_facts": [],
        "new_reflections": [],
        "consolidated_episode_ids": [],
    }


@app.get("/api/commitments/open")
async def open_commitments() -> list[dict]:
    return [c for c in _DB["commitments"].values() if c["status"] == "open"]


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "mode": "offline-mock"}


# ── Memory browser ───────────────────────────────────────────────────────


@app.get("/api/memory/{kind}")
async def list_memory(kind: str) -> list[dict]:
    return list(_table(kind).values())


@app.get("/api/memory/search/{kind}")
async def search_memory(kind: str, q: str, limit: int = 10) -> list[dict]:
    table = _table(kind)
    q_lower = q.lower()
    matches = [row for row in table.values() if q_lower in " ".join(str(v) for v in row.values()).lower()]
    return matches[:limit]


@app.post("/api/memory/people")
async def create_person(payload: dict = Body(...)) -> dict:
    return _upsert("people", payload)


@app.post("/api/memory/relationships")
async def create_relationship(payload: dict = Body(...)) -> dict:
    return _upsert("relationships", payload)


@app.post("/api/memory/standing-facts")
async def create_standing_fact(payload: dict = Body(...)) -> dict:
    return _upsert("standing-facts", payload)


@app.post("/api/memory/episodic-events")
async def create_episodic_event(payload: dict = Body(...)) -> dict:
    return _upsert("episodic-events", payload)


@app.post("/api/memory/commitments")
async def create_commitment(payload: dict = Body(...)) -> dict:
    return _upsert("commitments", payload)


@app.post("/api/memory/user-profile")
async def upsert_user_profile(payload: dict = Body(...)) -> dict:
    payload.setdefault("id", "user")
    return _upsert("user-profile", payload)
