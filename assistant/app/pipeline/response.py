"""Response generation — DESIGN.md §5 step 4. Analogous to the narrative
engine's pipeline/narrator.py, minus anything narrator/story-specific."""
from __future__ import annotations

from app.llm import anthropic_client
from app.routing.escalation import resolve_response_tier


def build_stable_context(*, profile_summary: str) -> str:
    """Everything stable within a session (user profile, standing
    preferences) goes here so it can be cached — same reasoning as the
    narrative engine's build_stable_context."""
    return (
        "You are a personal assistant with long-term memory of this user and "
        "the people in their life. Respond grounded strictly in the "
        "information provided below — do not invent facts about the user or "
        "people they've mentioned. If you're not sure whether something is "
        "still true, say so rather than asserting it.\n\n"
        f"KNOWN CONTEXT:\n{profile_summary}"
    )


def compose_reply(
    *,
    stable_context: str,
    user_message: str,
    retrieved_context: str,
    touched_sensitive_commitments: bool,
    touched_sensitive_facts: bool,
) -> tuple[str, str]:
    """Returns (reply, tier_used)."""
    tier = resolve_response_tier(
        touched_sensitive_commitments=touched_sensitive_commitments,
        touched_sensitive_facts=touched_sensitive_facts,
        user_message=user_message,
    )
    turn_prompt = (
        f"User message: {user_message}\n\n"
        f"Relevant retrieved memory:\n{retrieved_context}\n\n"
        "Reply to the user."
    )
    reply = anthropic_client.generate_reply(stable_context=stable_context, turn_prompt=turn_prompt, tier=tier)
    return reply, tier
