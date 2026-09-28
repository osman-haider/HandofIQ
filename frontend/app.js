const API = ""; // same-origin; FastAPI serves this file too

const state = {
  sessionId: null,
  mode: "smart",
  language: "en",
  script: [],
  scriptIndex: 0,
  scenarioId: null,
};

// ---- Element refs ------------------------------------------------------

const scenarioSelect = document.getElementById("scenario-select");
const modeToggle = document.getElementById("mode-toggle");
const langToggle = document.getElementById("lang-toggle");
const startBtn = document.getElementById("start-btn");
const historyBtn = document.getElementById("history-btn");
const naiveNote = document.getElementById("naive-note");

const scenarioTitle = document.getElementById("scenario-title");
const scenarioSubtitle = document.getElementById("scenario-subtitle");
const transcriptEl = document.getElementById("transcript");
const traceEl = document.getElementById("trace");
const handoffCardEl = document.getElementById("handoff-card");

const scriptBtn = document.getElementById("script-btn");
const textInput = document.getElementById("text-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");

const historyPanel = document.getElementById("history-panel");
const historyList = document.getElementById("history-list");
const historyClose = document.getElementById("history-close");

// ---- Init ---------------------------------------------------------------

async function loadScenarios() {
  const res = await fetch(`${API}/api/scenarios`);
  const scenarios = await res.json();
  scenarioSelect.innerHTML = scenarios
    .map((s) => `<option value="${s.id}">${s.title}</option>`)
    .join("");
}
loadScenarios();

// ---- Toggles --------------------------------------------------------

modeToggle.addEventListener("click", () => {
  state.mode = state.mode === "smart" ? "naive" : "smart";
  modeToggle.dataset.mode = state.mode;
  naiveNote.classList.toggle("hidden", state.mode !== "naive");
});

langToggle.addEventListener("click", () => {
  state.language = state.language === "en" ? "es" : "en";
  langToggle.dataset.lang = state.language;
});

// ---- Starting a call ---------------------------------------------------

startBtn.addEventListener("click", async () => {
  const scenarioId = scenarioSelect.value;
  if (!scenarioId) return;

  const res = await fetch(`${API}/api/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scenario_id: scenarioId,
      mode: state.mode,
      language: state.language,
    }),
  });
  if (!res.ok) {
    alert("Could not start session — check that the backend is running and OPENAI_API_KEY is set.");
    return;
  }
  const data = await res.json();

  state.sessionId = data.session_id;
  state.script = data.script;
  state.scriptIndex = 0;
  state.scenarioId = scenarioId;

  scenarioTitle.textContent = data.scenario_title;
  scenarioSubtitle.textContent = `${data.scenario_subtitle} — ${data.property}`;

  transcriptEl.innerHTML = "";
  traceEl.innerHTML = "";
  handoffCardEl.classList.add("hidden");
  handoffCardEl.innerHTML = "";

  scriptBtn.disabled = false;
  textInput.disabled = false;
  sendBtn.disabled = false;
  micBtn.disabled = false;
  updateScriptButton();
});

function updateScriptButton() {
  if (state.scriptIndex >= state.script.length) {
    scriptBtn.textContent = "Scripted lines finished — keep typing";
    scriptBtn.disabled = true;
  } else {
    scriptBtn.textContent = `Play next scripted line (${state.scriptIndex + 1}/${state.script.length})`;
    scriptBtn.disabled = false;
  }
}

// ---- Sending a turn -----------------------------------------------------

scriptBtn.addEventListener("click", () => {
  if (state.scriptIndex >= state.script.length) return;
  const line = state.script[state.scriptIndex];
  state.scriptIndex += 1;
  updateScriptButton();
  sendTurn(line);
});

sendBtn.addEventListener("click", () => {
  const text = textInput.value.trim();
  if (!text) return;
  textInput.value = "";
  sendTurn(text);
});

textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendBtn.click();
});

async function sendTurn(callerText) {
  appendBubble("caller", callerText);
  const thinkingId = appendBubble("agent", "…thinking", true);

  const res = await fetch(`${API}/api/session/${state.sessionId}/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: callerText }),
  });

  document.getElementById(thinkingId)?.remove();

  if (!res.ok) {
    appendBubble("agent", "(error reaching the agent — see console)");
    console.error(await res.text());
    return;
  }

  const data = await res.json();
  appendBubble("agent", data.agent_reply);
  playReply(data.agent_reply); // nice-to-have TTS, fails silently if unavailable

  if (data.mode === "smart") {
    appendTraceEntry(data);
    if (data.decision === "escalate" && data.handoff) {
      renderHandoffCard(data.handoff);
    }
  } else {
    appendNaiveTraceEntry();
  }
}

function appendBubble(role, text, transient = false) {
  const id = `bubble-${Math.random().toString(36).slice(2)}`;
  const div = document.createElement("div");
  div.id = id;
  div.className = `bubble ${role}`;
  div.innerHTML = `<span class="who">${role === "caller" ? "Caller" : "Agent"}</span>${escapeHtml(text)}`;
  transcriptEl.appendChild(div);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
  return id;
}

function appendTraceEntry(data) {
  const div = document.createElement("div");
  div.className = "trace-entry";
  div.dataset.decision = data.decision;

  const pct = (v) => Math.round((v ?? 0) * 100);

  div.innerHTML = `
    <div class="trace-row">
      <span>turn ${data.turn_index + 1}</span>
      <span class="decision-pill" data-decision="${data.decision}">${data.decision}</span>
    </div>
    <div class="meters">
      <div class="meter">
        <div class="meter-label"><span>intent confidence</span><span>${pct(data.intent_confidence)}%</span></div>
        <div class="meter-track"><div class="meter-fill" style="width:${pct(data.intent_confidence)}%"></div></div>
      </div>
      <div class="meter">
        <div class="meter-label"><span>data sufficiency</span><span>${pct(data.data_sufficiency)}%</span></div>
        <div class="meter-track"><div class="meter-fill" style="width:${pct(data.data_sufficiency)}%"></div></div>
      </div>
    </div>
    <p class="trace-reason">${escapeHtml(data.reason || "")}</p>
  `;
  traceEl.prepend(div);
}

function appendNaiveTraceEntry() {
  const div = document.createElement("div");
  div.className = "trace-entry";
  div.dataset.decision = "";
  div.innerHTML = `
    <div class="trace-row"><span>naive mode</span><span></span></div>
    <p class="trace-reason">No confidence scoring performed — the naive agent always answers as if certain.</p>
  `;
  traceEl.prepend(div);
}

function renderHandoffCard(h) {
  const facts = Object.entries(h.key_facts || {})
    .map(([k, v]) => `<span class="fact-chip">${escapeHtml(k)}: ${escapeHtml(v)}</span>`)
    .join("");

  handoffCardEl.innerHTML = `
    <h3>Handoff to staff</h3>
    <div class="handoff-field"><span class="label">Caller</span><span class="value">${escapeHtml(h.caller_summary)}</span></div>
    <div class="handoff-field"><span class="label">Issue</span><span class="value">${escapeHtml(h.issue_summary)}</span></div>
    <div class="handoff-field"><span class="label">Key facts</span><div class="handoff-facts">${facts || "<span class=\"value\">none confirmed</span>"}</div></div>
    <div class="handoff-field"><span class="label">Why the AI stopped</span><span class="value">${escapeHtml(h.reason_for_escalation)}</span></div>
    <div class="handoff-field"><span class="label">Suggested next action</span><span class="value">${escapeHtml(h.suggested_next_action)}</span></div>
  `;
  handoffCardEl.classList.remove("hidden");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

// ---- Nice-to-have: voice input (mic -> Whisper -> text input) --------

let mediaRecorder = null;
let audioChunks = [];

micBtn.addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
    mediaRecorder.onstop = handleRecordingStop;
    mediaRecorder.start();
    micBtn.classList.add("recording");
  } catch (err) {
    alert("Microphone access failed or was denied.");
    console.error(err);
  }
});

async function handleRecordingStop() {
  micBtn.classList.remove("recording");
  const blob = new Blob(audioChunks, { type: "audio/webm" });
  const form = new FormData();
  form.append("audio", blob, "recording.webm");

  textInput.placeholder = "Transcribing…";
  try {
    const res = await fetch(`${API}/api/transcribe`, { method: "POST", body: form });
    const data = await res.json();
    textInput.value = data.text || "";
  } catch (err) {
    console.error("Transcription failed", err);
  } finally {
    textInput.placeholder = "Or type as the caller…";
  }
}

// ---- Nice-to-have: TTS playback of agent replies ----------------------

async function playReply(text) {
  try {
    const res = await fetch(`${API}/api/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, language: state.language }),
    });
    if (!res.ok) return; // fail silently — TTS is a nice-to-have, not core
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.play().catch(() => {}); // browsers may block autoplay; ignore
  } catch (err) {
    console.warn("TTS unavailable:", err);
  }
}

// ---- Nice-to-have: persisted session history --------------------------

historyBtn.addEventListener("click", async () => {
  historyPanel.classList.remove("hidden");
  const res = await fetch(`${API}/api/sessions`);
  const sessions = await res.json();
  historyList.innerHTML = sessions
    .map(
      (s) => `
      <div class="history-item">
        <div>${escapeHtml(s.scenario_title)}</div>
        <div class="meta">${s.mode} · ${s.language} · ${s.final_decision ?? "in progress"} · ${new Date(s.created_at).toLocaleString()}</div>
      </div>`
    )
    .join("") || `<p style="color:var(--text-dim); font-size:13px;">No past sessions yet.</p>`;
});

historyClose.addEventListener("click", () => historyPanel.classList.add("hidden"));
