"""Response generation (Sonnet default / Opus escalated) — DESIGN.md §5, §6.
Only the frontier-API seat in this system; there's no re-plan step to port
over (nothing to re-plan — see DESIGN.md §2), so this is simpler than the
narrative engine's equivalent file.

Prompt caching: stable per-user context (user profile, standing facts that
rarely change) goes in a cached system block, same reasoning as the
narrative engine — this is still the biggest lever on cost, arguably more so
here since a personal assistant's context is dominated by slowly-changing
facts about one person rather than a large narrative cast.
"""
from __future__ import annotations

from anthropic import Anthropic

from app.config import settings

_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.anthropic_api_key)
    return _client


def generate_reply(
    *,
    stable_context: str,
    turn_prompt: str,
    tier: str,  # "default" | "escalated"
    max_tokens: int = 800,
) -> str:
    model = settings.response_default_model if tier == "default" else settings.response_escalated_model
    response = get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": stable_context,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": turn_prompt}],
    )
    return response.content[0].text
