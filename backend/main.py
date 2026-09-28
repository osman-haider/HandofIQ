import os

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

if __package__:
    from . import db, llm, policy
    from .models import (
        MessageRequest,
        MessageResponse,
        SpeakRequest,
        StartSessionRequest,
        StartSessionResponse,
    )
    from .scenarios import SCENARIOS, get_property_context
else:
    import db
    import llm
    import policy
    from models import (
        MessageRequest,
        MessageResponse,
        SpeakRequest,
        StartSessionRequest,
        StartSessionResponse,
    )
    from scenarios import SCENARIOS, get_property_context

app = FastAPI(title="Handoff IQ")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()

# in-memory cache of session metadata (scenario/mode/language/property/index)
# — the durable record of turns/handoffs lives in SQLite (db.py).
_SESSIONS: dict[str, dict] = {}


@app.get("/api/scenarios")
def list_scenarios():
    return [
        {
            "id": sid,
            "title": s["title"],
            "subtitle": s["subtitle"],
            "expected_branch": s["expected_branch"],
            "property": s["property"],
        }
        for sid, s in SCENARIOS.items()
    ]


@app.get("/api/sessions")
def list_sessions():
    return db.list_sessions()


@app.post("/api/session/start", response_model=StartSessionResponse)
def start_session(req: StartSessionRequest):
    scenario = SCENARIOS.get(req.scenario_id)
    if not scenario:
        raise HTTPException(404, f"Unknown scenario_id '{req.scenario_id}'")

    session_id = db.create_session(req.scenario_id, scenario["title"], req.mode, req.language)

    script = scenario["script_es"] if req.language == "es" else scenario["script_en"]

    _SESSIONS[session_id] = {
        "scenario_id": req.scenario_id,
        "mode": req.mode,
        "language": req.language,
        "property": scenario["property"],
        "turn_index": 0,
    }

    return StartSessionResponse(
        session_id=session_id,
        scenario_title=scenario["title"],
        scenario_subtitle=scenario["subtitle"],
        property=scenario["property"],
        mode=req.mode,
        language=req.language,
        script=script,
    )


@app.post("/api/session/{session_id}/message", response_model=MessageResponse)
def send_message(session_id: str, req: MessageRequest):
    meta = _SESSIONS.get(session_id)
    if not meta:
        raise HTTPException(404, "Unknown session_id — was it started this server run?")

    property_context = get_property_context(meta["property"])
    conversation = db.get_conversation(session_id)
    conversation.append({"role": "caller", "text": req.text})

    turn_index = meta["turn_index"]

    if meta["mode"] == "naive":
        try:
            reply = llm.naive_turn(conversation, property_context, meta["language"])
        except Exception as e:
            reply = f"(agent error: {e})"

        db.add_turn(
            session_id, turn_index, req.text, reply,
            None, None, None, None, "proceed", "Naive mode has no confidence layer.",
        )
        meta["turn_index"] += 1

        return MessageResponse(
            turn_index=turn_index,
            caller_text=req.text,
            agent_reply=reply,
            mode="naive",
        )

    # --- smart mode ---
    try:
        result = llm.smart_turn(conversation, property_context, meta["language"])
        decision, reason = policy.decide(
            intent_confidence=result["intent_confidence"],
            data_sufficiency=result["data_sufficiency"],
            sensitivity_flag=result["sensitivity_flag"],
            sensitivity_reason=result.get("sensitivity_reason"),
        )
        reply = result["reply"]
        intent_confidence = result["intent_confidence"]
        data_sufficiency = result["data_sufficiency"]
        sensitivity_flag = result["sensitivity_flag"]
        sensitivity_reason = result.get("sensitivity_reason")
    except Exception as e:
        decision, reason = policy.fail_safe_decision(e)
        reply = "I want to make sure this gets to the right person — let me connect you with our team."
        intent_confidence = data_sufficiency = None
        sensitivity_flag = None
        sensitivity_reason = None

    db.add_turn(
        session_id, turn_index, req.text, reply,
        intent_confidence, data_sufficiency, sensitivity_flag,
        sensitivity_reason, decision, reason,
    )
    meta["turn_index"] += 1

    handoff_payload = None
    if decision == "escalate":
        full_conversation = conversation + [{"role": "agent", "text": reply}]
        try:
            handoff_payload = llm.build_handoff_card(
                full_conversation, property_context, reason, meta["language"]
            )
        except Exception as e:
            handoff_payload = {
                "caller_summary": "Unavailable — handoff-card generation failed.",
                "issue_summary": str(e),
                "key_facts": {},
                "reason_for_escalation": reason,
                "suggested_next_action": "A human should review the raw transcript.",
            }
        db.save_handoff(session_id, handoff_payload)

    return MessageResponse(
        turn_index=turn_index,
        caller_text=req.text,
        agent_reply=reply,
        mode="smart",
        intent_confidence=intent_confidence,
        data_sufficiency=data_sufficiency,
        sensitivity_flag=sensitivity_flag,
        sensitivity_reason=sensitivity_reason,
        decision=decision,
        reason=reason,
        handoff=handoff_payload,
    )


@app.get("/api/session/{session_id}/trace")
def get_trace(session_id: str):
    return db.get_trace(session_id)


@app.get("/api/session/{session_id}/handoff")
def get_handoff(session_id: str):
    handoff = db.get_handoff(session_id)
    if not handoff:
        raise HTTPException(404, "No handoff generated for this session.")
    return handoff


# ---- Nice-to-have: voice input/output ----

@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    audio_bytes = await audio.read()
    try:
        text = llm.transcribe_audio(audio_bytes, audio.filename)
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")
    return {"text": text}


@app.post("/api/speak")
def speak(req: SpeakRequest):
    try:
        audio_bytes = llm.synthesize_speech(req.text, req.language)
    except Exception as e:
        raise HTTPException(500, f"Speech synthesis failed: {e}")
    return Response(content=audio_bytes, media_type="audio/mpeg")


# ---- Serve the static frontend (so `uvicorn main:app` alone is a full demo) ----

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
