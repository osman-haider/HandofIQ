"""
Fictional "Property Brain" context and scripted demo scenarios.

Nothing here is real customer, property, or transcript data — it exists
only to give the agent enough grounded context to demonstrate the
confidence-aware escalation pattern.
"""

PROPERTY_BRAIN = {
    "Cedar Grove Apartments": {
        "address": "140 Cedar Grove Way, Unit varies",
        "units": ["2B", "4C", "7A"],
        "pet_policy": "Cats and dogs under 40 lbs allowed with a $300 refundable deposit.",
        "emergency_definition": (
            "An emergency is anything posing immediate danger or major property "
            "damage: active water leaks, no heat below 55F, gas smell, no power, "
            "lockouts, or fire/smoke."
        ),
        "voucher_policy": (
            "Cedar Grove participates in the local Housing Choice Voucher "
            "program. Questions about voucher eligibility, rent portion "
            "calculations, or inspection scheduling must be routed to a "
            "human leasing specialist — the AI should never confirm or deny "
            "eligibility on its own."
        ),
    },
    "Maple Ridge HOA": {
        "address": "Maple Ridge Community, 60 townhomes",
        "units": ["12", "38", "45"],
        "pet_policy": "Two pets max per unit, per HOA bylaw Section 4.2.",
        "emergency_definition": (
            "Emergency = risk to life/safety or common-area damage in progress "
            "(e.g., a burst pipe flooding a shared hallway)."
        ),
        "compliance_note": (
            "Any mention of mold, asbestos, or lead paint must be escalated to "
            "a human property manager. The AI should never speculate about the "
            "presence, cause, or health risk of these substances."
        ),
    },
}

# intent_confidence / data_sufficiency / sensitivity_flag are produced by the
# model at runtime — these scripts only seed what the simulated caller says.

SCENARIOS = {
    "clean_resolve": {
        "title": "Garbage disposal jam",
        "subtitle": "A routine issue the agent should resolve on its own.",
        "expected_branch": "proceed",
        "property": "Cedar Grove Apartments",
        "script_en": [
            "Hi, my garbage disposal in unit 4C stopped working, it just hums.",
            "Ok let me check... nothing's stuck that I can see.",
            "That did it, thank you!",
        ],
        "script_es": [
            "Hola, el triturador de basura en la unidad 4C dejó de funcionar, solo zumba.",
            "Bien, déjame revisar... no veo nada atascado.",
            "¡Eso lo arregló, gracias!",
        ],
    },
    "ambiguous_clarify": {
        "title": "Which unit, which issue?",
        "subtitle": "The caller is vague — the agent should ask, not guess.",
        "expected_branch": "clarify",
        "property": "Cedar Grove Apartments",
        "script_en": [
            "Hey it's me again, the thing I called about last week is still doing it.",
            "You know, the water thing. It's happening in the kitchen I think, or maybe the bathroom.",
            "Oh — unit 7A. And it's the sink, sorry, I should've said that.",
        ],
        "script_es": [
            "Hola, soy yo otra vez, lo que llamé la semana pasada sigue pasando.",
            "Ya sabes, lo del agua. Creo que es en la cocina, o tal vez el baño.",
            "Ah, unidad 7A. Y es el fregadero, perdón, debí decir eso.",
        ],
    },
    "sensitive_escalate": {
        "title": "Voucher question + possible mold mention",
        "subtitle": "Compliance-sensitive — the agent should stop and hand off.",
        "expected_branch": "escalate",
        "property": "Maple Ridge HOA",
        "script_en": [
            "Hi, I wanted to ask about my Housing Choice Voucher paperwork for unit 12.",
            "Also, while I have you — there's a weird dark spot on the bathroom ceiling, could that be mold? Does that affect my voucher inspection?",
        ],
        "script_es": [
            "Hola, quería preguntar sobre mi papeleo del Housing Choice Voucher para la unidad 12.",
            "Y ya que hablamos — hay una mancha oscura rara en el techo del baño, ¿podría ser moho? ¿Eso afecta mi inspección del voucher?",
        ],
    },
}


def get_property_context(property_name: str) -> str:
    """Render a small text block describing the property, for the prompt."""
    p = PROPERTY_BRAIN.get(property_name)
    if not p:
        return ""
    lines = [f"Property: {property_name} ({p['address']})", f"Units: {', '.join(p['units'])}"]
    for key in ("pet_policy", "emergency_definition", "voucher_policy", "compliance_note"):
        if key in p:
            lines.append(f"- {key.replace('_', ' ').title()}: {p[key]}")
    return "\n".join(lines)
