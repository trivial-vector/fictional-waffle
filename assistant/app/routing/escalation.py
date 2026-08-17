"""Response-tier escalation routing — DESIGN.md §6. Direct port of the
narrative engine's routing/escalation.py: piggybacks on `sensitive` flags
already in the schema (standing_fact, episodic_event, commitment) rather than
a separate classifier, for the same reason as before — sensitive material is
often already known at write time, so tagging it costs nothing extra.

`_looks_emotionally_intense` carries the exact same caveat as the narrative
engine's version: a deliberately crude keyword-matching placeholder, not a
real implementation. If anything, the bar for replacing this is higher here
than in the storytelling project — this is gating how a real person's
sensitive disclosures get handled, not a fictional character's.
"""
from __future__ import annotations

# Placeholder only — see module docstring.
_INTENSITY_MARKERS = {
    "cry", "crying", "scream", "screaming", "furious", "heartbroken",
    "betray", "betrayed", "grief", "grieving", "confess", "confession",
    "afraid", "terrified", "depressed", "anxious", "panic", "suicidal",
    "diagnosed", "divorce", "died", "death", "fired", "breakup",
}


def _looks_emotionally_intense(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _INTENSITY_MARKERS)


def resolve_response_tier(
    *,
    touched_sensitive_commitments: bool,
    touched_sensitive_facts: bool,
    user_message: str,
) -> str:
    """Returns "escalated" (Opus) or "default" (Sonnet)."""
    if touched_sensitive_commitments or touched_sensitive_facts:
        return "escalated"
    if _looks_emotionally_intense(user_message):
        return "escalated"
    return "default"
