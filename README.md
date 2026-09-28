# Handoff IQ

A small prototype of a **confidence-aware escalation layer** for property-management
voice/chat agents: instead of an AI that either guesses confidently and gets it
wrong, or dumps a bare transcript on a human, it decides — turn by turn — whether
to **proceed**, **ask a clarifying question**, or **escalate with a complete,
structured handoff card**.

Built as a research-backed demo connected to Super (hiresuper.com)'s own public
release notes and reviews. See `Super_Demo_Strategy_and_Build_Spec.md` for the
full evidence chain behind why this specific pattern was chosen.

This is a demo, not a production system — no real phone numbers, no real PMS
integration, no real customer data. Everything in `backend/scenarios.py` is
fictional.

---

## What's implemented

**Must-have (per the build spec):**
- Two-panel console: live call transcript + live confidence trace
- Single-LLM-call-per-turn structured output: reply + `intent_confidence` +
  `data_sufficiency` + `sensitivity_flag` (via OpenAI function calling)
- Policy layer (`backend/policy.py`) turning those scores into
  proceed / clarify / escalate
- On escalate: a generated, structured **Handoff Card** (caller summary, issue
  summary, key facts, reason, suggested next action) — not a bare transcript
- Fail-safe error handling: if the LLM call itself fails, the system defaults
  to **escalate**, never to a confident guess
- 3 pre-scripted scenarios covering all three decision branches
- FastAPI backend, plain HTML/CSS/JS frontend, SQLite storage

**Nice-to-have (all included):**
- **Smart vs. Naive mode toggle** — a deliberate baseline agent with no
  confidence layer, to contrast against, live, in the same UI
- **English/Spanish toggle** — same scenarios, same policy, different language,
  demonstrating confidence-aware behavior isn't English-only
- **Voice input** — record via the browser mic, transcribed with Whisper into
  the text field
- **Voice output** — the agent's reply is spoken back via TTS
- **Persisted session history** — past sessions are saved to SQLite and
  browsable from the "Past sessions" panel

---

## Setup

```bash
cd backend
python -m venv venv && source venv/bin/activate   # or your preferred env tool
pip install -r requirements.txt
cp .env.example .env
# edit .env and set OPENAI_API_KEY (and OPENAI_BASE_URL / OPENAI_MODEL_NAME
# if you're not using the OpenAI API directly)
```

## Run

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Then open **http://localhost:8000** — FastAPI serves the frontend directly, so
there's nothing separate to start.

## Using it

1. Pick a scenario from the dropdown:
   - **Garbage disposal jam** — routine issue, should resolve cleanly (green trace)
   - **Which unit, which issue?** — vague caller, should trigger a clarifying
     question (amber trace)
   - **Voucher question + possible mold mention** — compliance-sensitive,
     should escalate immediately with a handoff card (red trace)
2. Click **Start call**, then either click **Play next scripted line** to step
   through the pre-written script, or type/speak your own follow-up to see how
   the agent responds to something off-script.
3. Toggle **Mode** to "Naive" and replay a scenario to see the deliberate
   contrast — the naive agent always answers as if certain, with no trace
   entries and no handoff.
4. Toggle **Language** to ES and rerun a scenario in Spanish.
5. Open **Past sessions** to see everything that's been run this session,
   persisted in `handoff_iq.db`.

## Project layout

```
handoff-iq/
  backend/
    main.py         FastAPI routes
    llm.py           OpenAI calls: smart turn, naive turn, handoff card, STT/TTS
    policy.py        confidence/risk scores -> proceed/clarify/escalate
    scenarios.py     fictional "Property Brain" + 3 scripted scenarios
    db.py            SQLite persistence (sessions, turns, handoffs)
    models.py        Pydantic request/response schemas
    requirements.txt
    .env.example
  frontend/
    index.html
    style.css
    app.js
  README.md          (this file)
```

## Known simplifications (worth saying out loud, not hiding)

- Confidence is **self-reported by the model** via function-call arguments —
  a known-imperfect technique. A production system would likely combine this
  with STT confidence scores and retrieval-grounding signals, not rely on
  model self-assessment alone.
- Scenarios are short (2-3 scripted turns) and deliberately engineered to land
  in each policy branch reliably for demo purposes — real conversations are
  messier.
- No telephony (LiveKit/SIP) is used; this demonstrates the *decision layer*,
  not a production voice pipeline.
