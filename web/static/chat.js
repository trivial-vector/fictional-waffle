// Chat page logic. Talks to the assistant API (same origin, /api/*) and the
// separate local voice-transcription service (different container/port).
//
// VOICE_SERVICE_URL: built from the current page's hostname rather than
// hardcoded to localhost, so this works whether you're on the desktop
// itself or on another machine on the LAN (e.g. the MacBook Air client
// talking to the desktop, per the hardware topology in the narrative
// engine's design doc that this project's hardware plan carried over).
// Change VOICE_SERVICE_PORT below if you remapped the port in
// docker-compose.yml.
const VOICE_SERVICE_PORT = 8092;
const VOICE_SERVICE_URL = `${window.location.protocol}//${window.location.hostname}:${VOICE_SERVICE_PORT}/transcribe`;

// Turn-number and session tracking is a client-side workaround for a known
// gap: the backend has no session/turn-counter persistence (see DESIGN.md
// and api/routes.py docstring). Persisted to localStorage so a page reload
// doesn't lose your place mid-conversation, but this is a workaround, not a
// real fix — the backend still doesn't know about sessions.
const SESSION_KEY = "assistant_session_id";
const TURN_KEY = "assistant_turn_number";

function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

function nextTurnNumber() {
  const current = parseInt(localStorage.getItem(TURN_KEY) || "0", 10);
  const next = current + 1;
  localStorage.setItem(TURN_KEY, String(next));
  return next;
}

const messagesEl = document.getElementById("messages");
const composerEl = document.getElementById("composer");
const inputEl = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const micBtn = document.getElementById("mic-btn");
const attachBtn = document.getElementById("attach-btn");
const fileInput = document.getElementById("file-input");
const attachmentChip = document.getElementById("attachment-chip");
const attachmentName = document.getElementById("attachment-name");
const attachmentRemove = document.getElementById("attachment-remove");
const statusLine = document.getElementById("status-line");

let pendingFile = null;

function addMessage(role, text, meta) {
  const el = document.createElement("div");
  el.className = `msg ${role}` + (meta && meta.escalated ? " escalated" : "");
  el.textContent = text;
  if (meta && meta.metaText) {
    const metaEl = document.createElement("div");
    metaEl.className = "msg-meta";
    metaEl.textContent = meta.metaText;
    el.appendChild(metaEl);
  }
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setStatus(text) {
  statusLine.textContent = text;
}

function autoGrow() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 128) + "px";
}
inputEl.addEventListener("input", autoGrow);

// ── Attachments ──────────────────────────────────────────────────────

attachBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) return;
  pendingFile = file;
  attachmentName.textContent = file.name;
  attachmentChip.classList.remove("hidden");
});

attachmentRemove.addEventListener("click", () => {
  pendingFile = null;
  fileInput.value = "";
  attachmentChip.classList.add("hidden");
});

// ── Sending ──────────────────────────────────────────────────────────

composerEl.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = inputEl.value.trim();
  if (!text && !pendingFile) return;

  addMessage("user", text || "(attachment only)", pendingFile ? { metaText: `Attached: ${pendingFile.name}` } : null);
  inputEl.value = "";
  autoGrow();
  sendBtn.disabled = true;
  setStatus("Thinking…");

  const form = new FormData();
  form.append("session_id", getSessionId());
  form.append("user_message", text);
  if (pendingFile) form.append("file", pendingFile);

  const turnNumber = nextTurnNumber();
  const filePendingAtSend = pendingFile;
  pendingFile = null;
  fileInput.value = "";
  attachmentChip.classList.add("hidden");

  try {
    const resp = await fetch(`/api/message?turn_number=${turnNumber}`, {
      method: "POST",
      body: form,
    });
    if (!resp.ok) {
      const detail = await resp.text();
      throw new Error(`${resp.status}: ${detail}`);
    }
    const data = await resp.json();
    const metaBits = [`tier: ${data.tier_used}`];
    if (data.open_commitments_touched && data.open_commitments_touched.length) {
      metaBits.push(`touched: ${data.open_commitments_touched.join(", ")}`);
    }
    addMessage("assistant", data.reply, {
      escalated: data.tier_used === "escalated",
      metaText: metaBits.join(" · "),
    });
    setStatus("");
  } catch (err) {
    console.error(err);
    addMessage("assistant", `Something went wrong: ${err.message}`, null);
    setStatus("Error — see console for details.");
    if (filePendingAtSend) {
      // Restore the attachment so the user doesn't have to re-pick it after
      // a failed send.
      pendingFile = filePendingAtSend;
      attachmentName.textContent = filePendingAtSend.name;
      attachmentChip.classList.remove("hidden");
    }
  } finally {
    sendBtn.disabled = false;
  }
});

// ── Voice input ──────────────────────────────────────────────────────

let mediaRecorder = null;
let audioChunks = [];
let recording = false;

async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioChunks = [];
  mediaRecorder = new MediaRecorder(stream);
  mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
  mediaRecorder.onstop = async () => {
    stream.getTracks().forEach((track) => track.stop());
    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
    await sendForTranscription(blob);
  };
  mediaRecorder.start();
  recording = true;
  micBtn.classList.add("recording");
  setStatus("Recording… click the mic again to stop.");
}

function stopRecording() {
  if (mediaRecorder && recording) {
    mediaRecorder.stop();
    recording = false;
    micBtn.classList.remove("recording");
  }
}

async function sendForTranscription(blob) {
  setStatus("Transcribing…");
  const form = new FormData();
  const ext = (blob.type.split("/")[1] || "webm").split(";")[0];
  form.append("audio", blob, `clip.${ext}`);
  try {
    const resp = await fetch(VOICE_SERVICE_URL, { method: "POST", body: form });
    if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
    const data = await resp.json();
    if (data.text) {
      inputEl.value = (inputEl.value ? inputEl.value + " " : "") + data.text;
      autoGrow();
    }
    setStatus("");
  } catch (err) {
    console.error(err);
    setStatus(`Voice transcription failed: ${err.message}`);
  }
}

micBtn.addEventListener("click", () => {
  if (recording) {
    stopRecording();
  } else {
    startRecording().catch((err) => {
      console.error(err);
      setStatus(`Microphone access failed: ${err.message}`);
    });
  }
});

// Enter to send, shift+Enter for newline.
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    composerEl.requestSubmit();
  }
});
