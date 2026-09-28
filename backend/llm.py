"""
All LLM/audio calls live here. Everything reads its config from .env via
python-dotenv — no keys are ever hardcoded.

Design choice: the "smart" agent does its natural-language reply AND its
confidence/risk scoring in ONE chat completion call (via a required tool
call), not two separate calls — this keeps per-turn latency and cost down,
which matters for a voice product.
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=os.environ.get("OPENAI_BASE_URL") or None,
)

CHAT_MODEL = os.environ["OPENAI_MODEL_NAME"]
STT_MODEL = os.environ.get("OPENAI_STT_MODEL", "whisper-1")
TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "tts-1")

ASSESS_AND_REPLY_TOOL = {
    "type": "function",
    "function": {
        "name": "assess_and_reply",
        "description": (
            "Reply to the caller AND assess your own confidence in this turn. "
            "You must always call this function — never reply with plain text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reply": {
                    "type": "string",
                    "description": "What you would actually say back to the caller.",
                },
                "intent_confidence": {
                    "type": "number",
                    "description": (
                        "0-1. How confident are you that you correctly understood "
                        "what the caller wants? Low if the request is ambiguous, "
                        "garbled, or could mean multiple things."
                    ),
                },
                "data_sufficiency": {
                    "type": "number",
                    "description": (
                        "0-1. Do you have enough confirmed facts (unit, issue, "
                        "name) to actually act, or would you be filling gaps with "
                        "an assumption?"
                    ),
                },
                "sensitivity_flag": {
                    "type": "boolean",
                    "description": (
                        "True if this turn touches something a human must "
                        "handle per policy: housing voucher/Section 8 "
                        "eligibility, mold/asbestos/lead, or any other "
                        "compliance-sensitive topic in the property context."
                    ),
                },
                "sensitivity_reason": {
                    "type": ["string", "null"],
                    "description": "One short phrase explaining the flag, or null if not flagged.",
                },
                "extracted_facts": {
                    "type": "object",
                    "description": "Key facts confirmed so far, e.g. {\"unit\": \"4C\", \"issue\": \"garbage disposal humming\"}.",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": [
                "reply",
                "intent_confidence",
                "data_sufficiency",
                "sensitivity_flag",
                "sensitivity_reason",
                "extracted_facts",
            ],
        },
    },
}


def _system_prompt(property_context: str, language: str) -> str:
    lang_line = (
        "Respond in Spanish, matching the caller's language."
        if language == "es"
        else "Respond in English."
    )
    return f"""You are Super, an AI receptionist for a property management company.
{lang_line}

You are speaking with a resident/prospect by phone or text. Be warm, brief,
and practical, the way a good front-desk person would be.

Property context you know:
{property_context}

Rules:
- If you are genuinely unsure what the caller means, ask ONE short
  clarifying question instead of guessing.
- Never confirm, deny, or speculate about anything in the compliance/
  voucher notes above — flag it and say a specialist will follow up.
- Keep replies to 1-3 sentences, like a real phone call.
- You must always respond by calling the assess_and_reply function.
"""


def smart_turn(
    conversation: list[dict],
    property_context: str,
    language: str,
) -> dict:
    """
    conversation: list of {"role": "caller"|"agent", "text": str}
    Returns the parsed tool-call arguments as a dict.
    """
    messages = [{"role": "system", "content": _system_prompt(property_context, language)}]
    for turn in conversation:
        role = "user" if turn["role"] == "caller" else "assistant"
        messages.append({"role": role, "content": turn["text"]})

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        tools=[ASSESS_AND_REPLY_TOOL],
        tool_choice={"type": "function", "function": {"name": "assess_and_reply"}},
        temperature=0.3,
    )

    tool_call = response.choices[0].message.tool_calls[0]
    args = json.loads(tool_call.function.arguments)
    return args


def naive_turn(conversation: list[dict], property_context: str, language: str) -> str:
    """
    The deliberate "before" contrast: a plain agent with no confidence
    layer, no policy, and no ability to say 'let me get someone' — it
    always answers as if it's sure. Used for the smart-vs-naive toggle.
    """
    lang_line = "Respond in Spanish." if language == "es" else "Respond in English."
    system = f"""You are an AI receptionist for a property management company.
{lang_line}
Property context:
{property_context}
Always answer directly and confidently in 1-3 sentences. Do not ask
clarifying questions and do not say you'll get a human — just answer."""

    messages = [{"role": "system", "content": system}]
    for turn in conversation:
        role = "user" if turn["role"] == "caller" else "assistant"
        messages.append({"role": role, "content": turn["text"]})

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.3,
    )
    return response.choices[0].message.content


HANDOFF_CARD_TOOL = {
    "type": "function",
    "function": {
        "name": "build_handoff_card",
        "description": "Summarize this conversation into a clean handoff for staff.",
        "parameters": {
            "type": "object",
            "properties": {
                "caller_summary": {"type": "string", "description": "Who is calling and about what, one sentence."},
                "issue_summary": {"type": "string", "description": "The core issue/question, 1-2 sentences."},
                "key_facts": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Confirmed facts, e.g. property, unit, contact preference.",
                },
                "reason_for_escalation": {"type": "string"},
                "suggested_next_action": {"type": "string", "description": "What staff should do next, one sentence."},
            },
            "required": [
                "caller_summary",
                "issue_summary",
                "key_facts",
                "reason_for_escalation",
                "suggested_next_action",
            ],
        },
    },
}


def build_handoff_card(
    conversation: list[dict],
    property_context: str,
    reason_for_escalation: str,
    language: str,
) -> dict:
    system = f"""You are preparing a handoff summary for a human property-management
staff member. Property context:
{property_context}

The AI stopped here because: {reason_for_escalation}

Write the summary in English regardless of the caller's language, since
staff need to scan it quickly. Call build_handoff_card with your summary."""

    messages = [{"role": "system", "content": system}]
    for turn in conversation:
        role = "user" if turn["role"] == "caller" else "assistant"
        messages.append({"role": role, "content": turn["text"]})

    response = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        tools=[HANDOFF_CARD_TOOL],
        tool_choice={"type": "function", "function": {"name": "build_handoff_card"}},
        temperature=0.2,
    )
    tool_call = response.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments)


def transcribe_audio(file_bytes: bytes, filename: str) -> str:
    """Nice-to-have: browser-mic voice input via Whisper."""
    import io

    buf = io.BytesIO(file_bytes)
    buf.name = filename or "audio.webm"
    result = client.audio.transcriptions.create(model=STT_MODEL, file=buf)
    return result.text


def synthesize_speech(text: str, language: str) -> bytes:
    """Nice-to-have: TTS playback of the agent's reply."""
    voice = "alloy"
    response = client.audio.speech.create(
        model=TTS_MODEL,
        voice=voice,
        input=text,
    )
    return response.read()
