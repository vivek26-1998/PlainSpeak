"use strict";

// Realtime remains open across patient/clinician turns. Only finalized text is persisted.
const consultation = {
  active: false, starting: false, stopping: false, ws: null, capture: null,
  sessionId: null, queue: Promise.resolve(), pending: new Map(), flushResolve: null,
};
const manualSessionId = `manual_${crypto.randomUUID()}`;

async function createPcmCapture(ws) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  let ctx;
  try {
    ctx = new AudioContext();
    const blobUrl = URL.createObjectURL(new Blob([WORKLET], { type: "text/javascript" }));
    try { await ctx.audioWorklet.addModule(blobUrl); } finally { URL.revokeObjectURL(blobUrl); }
    const node = new AudioWorkletNode(ctx, "pcm16-downsampler");
    const source = ctx.createMediaStreamSource(stream);
    const silent = ctx.createGain();
    silent.gain.value = 0;
    source.connect(node);
    node.connect(silent).connect(ctx.destination);
    await ctx.resume();
    let flushed = null;
    node.port.onmessage = (e) => {
      if (e.data?.flushed) { flushed?.(); return; }
      if (ws.readyState === WebSocket.OPEN) ws.send(e.data);
    };
    return {
      async flush() {
        source.disconnect();
        await new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(new Error("Audio buffer did not finish flushing.")), 2000);
          flushed = () => { clearTimeout(timer); resolve(); };
          node.port.postMessage("flush");
        });
      },
      stop() {
        stream.getTracks().forEach((track) => track.stop());
        node.disconnect();
        ctx.close();
      },
    };
  } catch (err) {
    stream.getTracks().forEach((track) => track.stop());
    ctx?.close();
    throw err;
  }
}

function renderConsultation() {
  if (!caseView) return;
  const c = caseView.case;
  const segments = c.transcriptSegments ?? [];
  const roles = c.speakerRoles ?? {};
  const keys = [...new Set(segments.map((s) => `${s.sessionId}:${s.speakerId ?? "unknown"}`))];
  $("#consult-speakers").innerHTML = keys.length ? `
    <p class="muted">Speaker IDs are anonymous. Confirm who is speaking before reviewing the draft.</p>
    <div class="speaker-mapping">${keys.map((key, i) => `
      <label>Voice ${i + 1}
        <select data-speaker-key="${esc(key)}" aria-label="Role for voice ${i + 1}">
          ${["unknown", "clinician", "patient"].map((role) =>
            `<option value="${role}" ${(roles[key] ?? "unknown") === role ? "selected" : ""}>${role === "unknown" ? "Not confirmed" : role}</option>`).join("")}
        </select>
      </label>`).join("")}</div>` : "";
  $("#consult-speakers").querySelectorAll("[data-speaker-key]").forEach((select) => {
    select.addEventListener("change", () => run(select, async () => {
      const key = select.dataset.speakerKey;
      const role = select.value;
      consultation.queue = consultation.queue.catch(() => {}).then(async () => {
        setCase(await api(`/api/cases/${CASE_ID}/transcript`, {
          method: "POST", json: { segments: [], speakerRoles: { [key]: role } },
        }));
      });
      await consultation.queue;
    }));
  });
  $("#consult-transcript").innerHTML = segments.map((s) => {
    const key = `${s.sessionId}:${s.speakerId ?? "unknown"}`;
    const role = roles[key] ?? "unknown";
    const voice = keys.indexOf(key) + 1;
    const timing = s.startMs == null ? "" : ` · ${(s.startMs / 1000).toFixed(1)}s`;
    const origin = s.sessionId.startsWith("manual_") ? " · manually entered"
      : s.sessionId.startsWith("pdf_") ? " · imported from PDF" : "";
    return `<div class="transcript-line ${esc(role)}"><strong>${role === "unknown" ? `Voice ${voice} (unconfirmed)` : esc(role)}</strong><span class="muted">${timing}${origin}</span><div>${esc(s.text)}</div></div>`;
  }).join("") || '<p class="muted">No consultation transcript saved yet.</p>';
  $("#consult-transcript").scrollTop = $("#consult-transcript").scrollHeight;
  renderConsultationControls();
}

function renderConsultationControls() {
  const busy = consultation.active || consultation.starting || consultation.stopping;
  $("#btn-consult-start").disabled = busy;
  $("#btn-consult-stop").disabled = !consultation.active || consultation.stopping;
  ["#btn-reset", "#btn-draft", "#btn-manual-transcript", "#btn-transcript-pdf", "#btn-upload"].forEach((id) => {
    $(id).disabled = busy || consultation.pending.size > 0;
  });
  $("#consult-consent").disabled = busy;
  $("#consult-language").disabled = busy;
  const approveButton = $("#btn-approve");
  if (approveButton) approveButton.disabled = busy || consultation.pending.size > 0;
  $("#consult-recovery").innerHTML = consultation.pending.size ? `
    <p class="error">${consultation.pending.size} finalized segment(s) are not saved. Keep this page open.</p>
    <button id="retry-transcript" class="secondary">Retry saving transcript</button>` : "";
  $("#retry-transcript")?.addEventListener("click", (e) => run(e.target, async () => {
    for (const segment of [...consultation.pending.values()]) await queueConsultationSegment(segment);
  }));
}

function queueConsultationSegment(segment, roles = {}) {
  consultation.pending.set(segment.id, segment);
  renderConsultationControls();
  consultation.queue = consultation.queue.catch(() => {}).then(async () => {
    try {
      const view = await api(`/api/cases/${CASE_ID}/transcript`, {
        method: "POST", json: { segments: [segment], speakerRoles: roles },
      });
      consultation.pending.delete(segment.id);
      setCase(view);
    } catch (err) {
      showError(`Transcript save failed: ${err.message}. Use Retry saving transcript.`);
      renderConsultationControls();
      throw err;
    }
  });
  return consultation.queue;
}

function closeConsultationCapture() {
  consultation.capture?.stop();
  consultation.capture = null;
  const ws = consultation.ws;
  consultation.ws = null;
  consultation.active = false;
  consultation.starting = false;
  if (ws && ws.readyState < WebSocket.CLOSING) ws.close(1000);
  $("#consult-interim").textContent = "";
  renderConsultationControls();
}

async function startConsultation() {
  if (!$("#consult-consent").checked) throw new Error("Confirm participant consent before recording.");
  if (mic.active || mic.ws) throw new Error("Finish the caregiver question first.");
  if (consultation.active || consultation.starting || consultation.stopping) return;
  consultation.starting = true;
  renderConsultationControls();
  $("#consult-status").textContent = "Connecting to live transcription…";
  try {
    const token = await api("/api/voice/token", { method: "POST" });
    const params = new URLSearchParams({
      encoding: "pcm_s16le", sample_rate: "16000", channels: "1",
      language: $("#consult-language").value, diarize: "true", max_speakers: "2",
      include_interim: "true", include_timestamps: "true",
    });
    consultation.sessionId = crypto.randomUUID();
    const ws = new WebSocket(`${token.realtimeUrl}?${params}`, ["bearer", token.accessToken]);
    consultation.ws = ws;
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "flush_confirmation") { consultation.flushResolve?.(); return; }
        if (message.type !== "transcript") return;
        if (message.is_final === false) {
          $("#consult-interim").textContent = message.text;
          return;
        }
        $("#consult-interim").textContent = "";
        if (!message.text?.trim()) return;
        queueConsultationSegment({
          id: `seg_${crypto.randomUUID()}`, sessionId: consultation.sessionId,
          text: message.text, speakerId: message.speaker_id ?? null,
          startMs: message.start_ms == null ? null : Math.round(message.start_ms),
          durationMs: message.duration_ms == null ? null : Math.round(message.duration_ms),
        }).catch(() => {});
      } catch (err) { showError(`Could not process transcript: ${err.message}`); }
    };
    ws.onclose = (event) => {
      if (consultation.ws === ws && (consultation.active || consultation.starting || consultation.stopping)) {
        closeConsultationCapture();
        $("#consult-status").textContent = "Connection closed; saved transcript is preserved.";
        showError(`Consultation disconnected (${event.code}). Start again to continue. The newest buffered audio may be missing.`);
      }
    };
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Speech connection timed out.")), 12000);
      ws.onopen = () => { clearTimeout(timer); resolve(); };
      ws.onerror = () => { clearTimeout(timer); reject(new Error("Could not connect to Reson8 Realtime.")); };
    });
    consultation.capture = await createPcmCapture(ws);
    if (ws.readyState !== WebSocket.OPEN) throw new Error("Speech connection closed during microphone setup.");
    consultation.active = true;
    consultation.starting = false;
    $("#consult-status").textContent = "Listening to both speakers. Finalized lines save automatically.";
    renderConsultationControls();
  } catch (err) {
    closeConsultationCapture();
    $("#consult-status").textContent = "Live capture unavailable. Manual fallback is below.";
    throw err;
  }
}

async function endConsultation() {
  if (!consultation.active || consultation.stopping) return;
  consultation.stopping = true;
  renderConsultationControls();
  $("#consult-status").textContent = "Finalizing audio and saving transcript…";
  try {
    await consultation.capture.flush();
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Final transcript timed out. Saved lines remain available.")), 12000);
      consultation.flushResolve = () => { clearTimeout(timer); resolve(); };
      if (consultation.ws?.readyState !== WebSocket.OPEN) {
        clearTimeout(timer); reject(new Error("Speech connection closed before finalization.")); return;
      }
      consultation.ws.send(JSON.stringify({ type: "flush_request", id: crypto.randomUUID() }));
    });
    await consultation.queue;
    if (consultation.pending.size) throw new Error("Some transcript lines still need saving. Use Retry saving transcript.");
    $("#consult-status").textContent = "Consultation saved. Confirm speaker roles, then add the document and generate a draft.";
  } finally {
    consultation.flushResolve = null;
    closeConsultationCapture();
    consultation.stopping = false;
    renderConsultationControls();
  }
}

$("#btn-consult-start").addEventListener("click", () => run(null, startConsultation));
$("#btn-consult-stop").addEventListener("click", () => run(null, endConsultation));
$("#btn-manual-transcript").addEventListener("click", (event) => run(event.target, async () => {
  const input = $("#manual-transcript");
  if (!input.value.trim()) throw new Error("Enter a transcript line first.");
  if (!$("#consult-consent").checked) throw new Error("Confirm participant consent first.");
  const speakerId = Number($("#manual-speaker").value);
  await queueConsultationSegment({
    id: `seg_${crypto.randomUUID()}`, sessionId: manualSessionId,
    speakerId, text: input.value.trim(), startMs: null, durationMs: null,
  }, { [`${manualSessionId}:${speakerId}`]: speakerId === 0 ? "clinician" : "patient" });
  input.value = "";
}));
$("#btn-transcript-pdf").addEventListener("click", (event) => run(event.target, async () => {
  const file = $("#transcript-file").files[0];
  if (!file) throw new Error("Choose a transcript PDF first.");
  if (!$("#consult-consent").checked) throw new Error("Confirm participant consent first.");
  const before = new Set((caseView?.case.transcriptSegments ?? []).map((s) => s.id));
  const form = new FormData();
  form.append("file", file);
  const view = await api(`/api/cases/${CASE_ID}/transcript/document`, { method: "POST", body: form });
  setCase(view);
  const segments = view.case.transcriptSegments ?? [];
  // Compare ids, not counts: a replacement can be the same length as what it replaced.
  const fresh = segments.filter((s) => !before.has(s.id)).length;
  const dropped = before.size - segments.filter((s) => before.has(s.id)).length;
  // Unconfirmed speakers are absent from speakerRoles, so count the segments themselves.
  const voices = new Set(segments.map((s) => `${s.sessionId}:${s.speakerId ?? "unknown"}`)).size;
  const replaced = dropped ? `, replacing ${dropped} previously captured line(s)` : "";
  $("#consult-status").textContent = fresh
    ? `Imported ${fresh} line(s) from ${file.name} across ${voices} voice(s)${replaced}. Confirm each voice before reviewing the draft.`
    : `${file.name} was already imported; nothing changed.`;
}));
window.addEventListener("beforeunload", (event) => {
  if (consultation.active || consultation.starting || consultation.stopping || consultation.pending.size) {
    event.preventDefault();
    event.returnValue = "";
  }
});
