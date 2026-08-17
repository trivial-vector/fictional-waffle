-- Typed record store for assistant long-term memory. See ../../../DESIGN.md §3.
-- EMBED_DIM (1024 below) must match the embedding model's output dimension —
-- see the narrative engine's schema.sql for the same note; unchanged here
-- (Qwen3-Embedding-0.6B, native max 1024).

CREATE EXTENSION IF NOT EXISTS vector;

-- ── User profile (effectively a singleton; schema doesn't prevent more) ───
CREATE TABLE IF NOT EXISTS user_profile (
    id                  TEXT PRIMARY KEY,
    name                TEXT,
    timezone            TEXT,
    communication_prefs TEXT[] NOT NULL DEFAULT '{}',
    search_text         TEXT NOT NULL DEFAULT '',
    search_vector       tsvector GENERATED ALWAYS AS (to_tsvector('english', search_text)) STORED,
    embedding           vector(1024),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS user_profile_search_idx ON user_profile USING GIN (search_vector);

-- ── Person record — people other than the user ─────────────────────────
CREATE TABLE IF NOT EXISTS person_record (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    relation_context  TEXT,             -- free text: "user's sister", "colleague at Acme"
    notes             TEXT,
    last_mentioned_at INTEGER NOT NULL DEFAULT 0,  -- turn/message counter
    search_text       TEXT NOT NULL DEFAULT '',
    search_vector     tsvector GENERATED ALWAYS AS (to_tsvector('english', search_text)) STORED,
    embedding         vector(1024),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS person_record_search_idx ON person_record USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS person_record_embedding_idx ON person_record USING hnsw (embedding vector_cosine_ops);

-- ── Relationship record — pairs of people, including user-to-person ────
-- character_a/character_b may be a person_record.id or the literal string
-- 'user' to represent the user's own profile without a self-join to
-- user_profile (kept as plain TEXT rather than a FK for that reason).
CREATE TABLE IF NOT EXISTS relationship_record (
    id                TEXT PRIMARY KEY,
    party_a           TEXT NOT NULL,
    party_b           TEXT NOT NULL,
    relation_type     TEXT,
    polarity          REAL,
    valid_from_turn   INTEGER NOT NULL DEFAULT 0,
    search_text       TEXT NOT NULL DEFAULT '',
    search_vector     tsvector GENERATED ALWAYS AS (to_tsvector('english', search_text)) STORED,
    embedding         vector(1024),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (party_a, party_b)
);
CREATE INDEX IF NOT EXISTS relationship_record_search_idx ON relationship_record USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS relationship_record_embedding_idx ON relationship_record USING hnsw (embedding vector_cosine_ops);

-- ── Standing fact — durable facts/preferences ───────────────────────────
CREATE TABLE IF NOT EXISTS standing_fact (
    id                TEXT PRIMARY KEY,
    subject_id        TEXT NOT NULL DEFAULT 'user',  -- 'user' or a person_record.id
    fact              TEXT NOT NULL,
    category          TEXT,             -- preference | biographical | constraint | other
    sensitive         BOOLEAN NOT NULL DEFAULT false,  -- drives escalation routing
    valid_from_turn   INTEGER NOT NULL DEFAULT 0,
    valid_to_turn     INTEGER,
    evidence_turn     INTEGER,
    search_text       TEXT NOT NULL DEFAULT '',
    search_vector     tsvector GENERATED ALWAYS AS (to_tsvector('english', search_text)) STORED,
    embedding         vector(1024),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS standing_fact_search_idx ON standing_fact USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS standing_fact_embedding_idx ON standing_fact USING hnsw (embedding vector_cosine_ops);

-- ── Episodic event — discrete, timestamped happenings ───────────────────
-- The "new" table relative to the narrative engine's schema — see DESIGN.md §2.
CREATE TABLE IF NOT EXISTS episodic_event (
    id                TEXT PRIMARY KEY,
    summary           TEXT NOT NULL,
    participants      TEXT[] NOT NULL DEFAULT '{}',  -- person_record.id list, may include 'user'
    occurred_at       TEXT,              -- free-text approximate date/time; not a hard timestamp
    category          TEXT,              -- emotional | practical | factual | other
    sentiment         REAL,              -- -1.0 .. 1.0, app-defined scale
    sensitive         BOOLEAN NOT NULL DEFAULT false,
    session_id        TEXT,
    consolidated      BOOLEAN NOT NULL DEFAULT false,  -- has this been folded into standing_fact/person_record yet
    search_text       TEXT NOT NULL DEFAULT '',
    search_vector     tsvector GENERATED ALWAYS AS (to_tsvector('english', search_text)) STORED,
    embedding         vector(1024),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS episodic_event_search_idx ON episodic_event USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS episodic_event_embedding_idx ON episodic_event USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS episodic_event_consolidated_idx ON episodic_event (consolidated);

-- ── Commitment — open loops (design doc's direct carryover of plot_beat/
-- npc_obligation: a promise that must eventually be followed through on) ──
CREATE TABLE IF NOT EXISTS commitment (
    id                TEXT PRIMARY KEY,
    description       TEXT NOT NULL,
    concerns          TEXT[] NOT NULL DEFAULT '{}',  -- person_record.id list this commitment concerns
    status            TEXT NOT NULL DEFAULT 'open',  -- open | completed | dropped | deferred
    sensitive         BOOLEAN NOT NULL DEFAULT false,
    created_turn      INTEGER,
    resolved_turn     INTEGER,
    resolution_note   TEXT,
    search_text       TEXT NOT NULL DEFAULT '',
    search_vector     tsvector GENERATED ALWAYS AS (to_tsvector('english', search_text)) STORED,
    embedding         vector(1024),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS commitment_search_idx ON commitment USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS commitment_embedding_idx ON commitment USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS commitment_status_idx ON commitment (status);
