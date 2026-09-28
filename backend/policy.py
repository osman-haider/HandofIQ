"""
The policy layer that turns confidence/risk scores into a decision.

Kept deliberately simple and readable — this is the "judgment" step a
production system would tune with real conversation data, not a place
to hide complexity.
"""

# Tunable thresholds. Not secrets, so they live in code rather than .env —
# a real system would likely make these per-scenario or per-property.
ESCALATE_CONFIDENCE_BELOW = 0.5
CLARIFY_CONFIDENCE_BELOW = 0.75
CLARIFY_DATA_SUFFICIENCY_BELOW = 0.6


def decide(
    intent_confidence: float,
    data_sufficiency: float,
    sensitivity_flag: bool,
    sensitivity_reason: str | None,
) -> tuple[str, str]:
    """
    Returns (decision, reason) where decision is one of:
    "proceed" | "clarify" | "escalate"
    """
    if sensitivity_flag:
        reason = sensitivity_reason or "Sensitivity flag raised by the model."
        return "escalate", f"Sensitivity flag: {reason}"

    if intent_confidence < ESCALATE_CONFIDENCE_BELOW:
        return "escalate", (
            f"Intent confidence too low ({intent_confidence:.2f} < "
            f"{ESCALATE_CONFIDENCE_BELOW}) — a confident guess would be riskier "
            "than a handoff."
        )

    if intent_confidence < CLARIFY_CONFIDENCE_BELOW:
        return "clarify", (
            f"Intent confidence moderate ({intent_confidence:.2f}) — asking a "
            "targeted follow-up instead of guessing."
        )

    if data_sufficiency < CLARIFY_DATA_SUFFICIENCY_BELOW:
        return "clarify", (
            f"Not enough confirmed data yet ({data_sufficiency:.2f} < "
            f"{CLARIFY_DATA_SUFFICIENCY_BELOW}) — e.g. unit or issue not "
            "confirmed."
        )

    return "proceed", "High confidence, sufficient data, no sensitivity flags."


def fail_safe_decision(error: Exception) -> tuple[str, str]:
    """
    Called when the LLM call itself fails. The system should never guess
    confidently just because scoring failed — default to a human handoff.
    """
    return "escalate", f"Model call failed ({type(error).__name__}) — defaulting to handoff, not a guess."
