"""Typed record models — mirrors DESIGN.md §3 and db/schema.sql. Same double
duty as the narrative engine's records.py: DB row shape, and (via
`model_json_schema()`) the JSON schema handed to Ollama's constrained
decoding for the extraction pass.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CommitmentStatus(str, Enum):
    open = "open"
    completed = "completed"
    dropped = "dropped"
    deferred = "deferred"


class UserProfile(BaseModel):
    id: str = "user"
    name: str | None = None
    timezone: str | None = None
    communication_prefs: list[str] = Field(default_factory=list)


class PersonRecord(BaseModel):
    id: str
    name: str
    relation_context: str | None = None
    notes: str | None = None
    last_mentioned_at: int = 0


class RelationshipRecord(BaseModel):
    id: str
    party_a: str  # person_record.id or literal "user"
    party_b: str
    relation_type: str | None = None
    polarity: float = Field(default=0.0, ge=-1.0, le=1.0)
    valid_from_turn: int = 0


class StandingFact(BaseModel):
    id: str
    subject_id: str = "user"
    fact: str
    category: str | None = None  # preference | biographical | constraint | other
    sensitive: bool = False
    valid_from_turn: int = 0
    valid_to_turn: int | None = None
    evidence_turn: int | None = None


class EpisodicEvent(BaseModel):
    id: str
    summary: str
    participants: list[str] = Field(default_factory=list)
    occurred_at: str | None = None
    category: str | None = None  # emotional | practical | factual | other
    sentiment: float | None = Field(default=None, ge=-1.0, le=1.0)
    sensitive: bool = False
    session_id: str | None = None
    consolidated: bool = False


class Commitment(BaseModel):
    id: str
    description: str
    concerns: list[str] = Field(default_factory=list)  # person_record.id list
    status: CommitmentStatus = CommitmentStatus.open
    sensitive: bool = False
    created_turn: int | None = None
    resolved_turn: int | None = None
    resolution_note: str | None = None


class ExtractionResult(BaseModel):
    """Schema handed to the per-turn extraction model (Qwen3 7B via Ollama).
    Only changed/new records — compression happens by merging into current
    state downstream, not by re-stating everything each turn (DESIGN.md §1)."""
    people: list[PersonRecord] = Field(default_factory=list)
    relationships: list[RelationshipRecord] = Field(default_factory=list)
    standing_facts: list[StandingFact] = Field(default_factory=list)
    episodic_events: list[EpisodicEvent] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    mentioned_person_ids: list[str] = Field(
        default_factory=list,
        description="Every person referenced this turn, used by the cheap "
        "commitment-touch check — not a full record, just an id list.",
    )


class ConsolidationUpdate(BaseModel):
    """Schema handed to the consolidation model (DESIGN.md §4) — merges a
    batch of episodic_event records into updated current-state, plus any
    higher-level observations that don't map to a single event."""
    updated_people: list[PersonRecord] = Field(default_factory=list)
    updated_standing_facts: list[StandingFact] = Field(default_factory=list)
    new_reflections: list[StandingFact] = Field(
        default_factory=list,
        description="Synthesized observations spanning multiple episodic "
        "events (e.g. a pattern noticed across several mentions), written "
        "as standing_fact rows with category='reflection'.",
    )
    consolidated_episode_ids: list[str] = Field(default_factory=list)


class MessageInput(BaseModel):
    session_id: str
    user_message: str


class MessageOutput(BaseModel):
    reply: str
    tier_used: str
    open_commitments_touched: list[str] = Field(default_factory=list)
