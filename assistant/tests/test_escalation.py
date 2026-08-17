from app.routing.escalation import resolve_response_tier


def test_default_tier_for_routine_message():
    tier = resolve_response_tier(
        touched_sensitive_commitments=False,
        touched_sensitive_facts=False,
        user_message="What's a good recipe for pasta?",
    )
    assert tier == "default"


def test_escalates_on_sensitive_commitment_touch():
    tier = resolve_response_tier(
        touched_sensitive_commitments=True,
        touched_sensitive_facts=False,
        user_message="How's Sarah?",
    )
    assert tier == "escalated"


def test_escalates_on_sensitive_fact_touch():
    tier = resolve_response_tier(
        touched_sensitive_commitments=False,
        touched_sensitive_facts=True,
        user_message="Anything I should know?",
    )
    assert tier == "escalated"


def test_escalates_on_emotionally_intense_message():
    tier = resolve_response_tier(
        touched_sensitive_commitments=False,
        touched_sensitive_facts=False,
        user_message="I just found out my dad was diagnosed with something serious.",
    )
    assert tier == "escalated"


def test_does_not_escalate_on_neutral_message_with_no_touches():
    tier = resolve_response_tier(
        touched_sensitive_commitments=False,
        touched_sensitive_facts=False,
        user_message="Can you help me plan my week?",
    )
    assert tier == "default"
