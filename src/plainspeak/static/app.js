"use strict";

const CASE_ID = "demo-patient";
let caseView = null;   // last CaseView from the backend
let draftEdit = null;  // doctor's working copy of the draft

// ---------- helpers ----------

const $ = (sel) => document.querySelector(sel);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function showError(message) {
  const box = $("#error");
  box.textContent = message;
  box.hidden = !message;
}

async function api(path, options = {}) {
  const opts = { ...options };
  if (opts.json !== undefined) {
    opts.body = JSON.stringify(opts.json);
    opts.headers = { "Content-Type": "application/json" };
    delete opts.json;
  }
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return body;
}

async function run(button, fn) {
  showError("");
  if (button) button.disabled = true;
  try {
    await fn();
  } catch (err) {
    showError(err.message);
  } finally {
    if (button) button.disabled = false;
  }
}

function passageText(ref) {
  const source = caseView?.case.sources.find((s) => s.id === ref.sourceId);
  return source?.passages.find((p) => p.id === ref.passageId)?.text ?? "";
}

function refChips(refs = [], eventRefs = []) {
  const sources = refs.map((r) =>
    `<span class="chip" title="${esc(passageText(r))}">${esc(r.sourceId)} · ${esc(r.passageId)}</span>`);
  const events = eventRefs.map((id) => {
    const ev = caseView?.case.progressEvents.find((e) => e.id === id);
    const title = ev ? `${ev.actor} at ${ev.timestamp}: ${ev.note}` : id;
    return `<span class="chip event" title="${esc(title)}">event · ${esc(id)}</span>`;
  });
  return sources.concat(events).join("");
}

function taskInstruction(taskId) {
  return caseView?.case.careTasks.find((t) => t.id === taskId)?.instruction ?? taskId;
}

// ---------- rendering ----------

function setCase(view) {
  caseView = view;
  const c = view.case;
  $("#state").textContent =
    `Case ${c.caseId} · ${c.workflowState}` +
    (c.approvedSummaryVersion ? ` · approved v${c.approvedSummaryVersion}` : "");
  if (c.draftSummary) {
    if (!draftEdit || draftEdit.createdAt !== c.draftSummary.createdAt) {
      draftEdit = structuredClone(c.draftSummary);
    }
  } else {
    draftEdit = null;
  }
  renderDoctor();
  renderCaregiver();
  renderReport();
  if (typeof renderConsultation === "function") renderConsultation();
}

function renderDoctor() {
  const c = caseView.case;
  $("#sources").innerHTML = c.sources.map((s) => `
    <h3>${esc(s.id)} · ${esc(s.filename)}</h3>
    ${s.passages.map((p) => `<div class="passage"><span class="pid">${esc(p.id)}</span>${esc(p.text)}</div>`).join("")}
  `).join("") || `<p class="muted">No document uploaded yet.</p>`;

  const draft = $("#draft");
  if (!draftEdit) {
    draft.innerHTML = `<p class="muted">${c.sources.length ? "Generate a draft to review." : "Upload a document first."}</p>`;
  } else {
    draft.innerHTML = `
      <h3>Summary</h3>
      <textarea id="draft-summary">${esc(draftEdit.summary)}</textarea>
      <h3>Care tasks</h3>
      ${draftEdit.careTasks.map((t, i) => `
        <div class="task-edit" data-index="${i}">
          <input type="text" data-field="instruction" value="${esc(t.instruction)}" placeholder="Instruction">
          <input type="text" data-field="timing" value="${esc(t.timing ?? "")}" placeholder="Timing (optional)">
          <select data-field="responsibleParty">
            ${["patient", "caregiver", "care_team", "unspecified"].map((p) =>
              `<option ${p === t.responsibleParty ? "selected" : ""}>${p}</option>`).join("")}
          </select>
          <button class="danger" data-remove="${i}">Remove</button>
          <div class="refs">${refChips(t.sourceRefs) || `<span class="muted">No source reference (clinician-authored)</span>`}</div>
        </div>`).join("")}
      <button id="btn-add-task" class="secondary">Add task</button>
      ${draftEdit.missingInformation.length ? `
        <h3>Missing or ambiguous information flagged by Claude</h3>
        <ul class="plain">${draftEdit.missingInformation.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>` : ""}
      <h3>Approve</h3>
      <div class="row">
        <input type="text" id="approved-by" value="Dr. Demo (fictional)" style="max-width:260px">
        <button id="btn-approve">Approve this version</button>
      </div>`;
    draft.querySelectorAll(".task-edit").forEach((row) => {
      const task = draftEdit.careTasks[Number(row.dataset.index)];
      row.querySelectorAll("[data-field]").forEach((el) => {
        el.addEventListener("input", () => {
          const v = el.value;
          task[el.dataset.field] = el.dataset.field === "timing" ? (v.trim() || null) : v;
        });
      });
    });
    $("#draft-summary").addEventListener("input", (e) => { draftEdit.summary = e.target.value; });
    draft.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", () => {
      draftEdit.careTasks.splice(Number(b.dataset.remove), 1);
      renderDoctor();
    }));
    $("#btn-add-task").addEventListener("click", () => {
      draftEdit.careTasks.push({ id: null, instruction: "", timing: null, responsibleParty: "unspecified", sourceRefs: [] });
      renderDoctor();
    });
    $("#btn-approve").addEventListener("click", (e) => run(e.target, approveDraft));
  }

  const approved = c.summaryVersions.find((v) => v.version === c.approvedSummaryVersion);
  $("#approved").innerHTML = approved ? `
    <p class="muted">Version ${approved.version} approved by ${esc(approved.approvedBy)} at ${esc(approved.approvedAt)}
      ${c.summaryVersions.length > 1 ? ` · ${c.summaryVersions.length} versions preserved` : ""}</p>
    <p>${esc(approved.summary)}</p>
    <ul class="plain">${approved.careTasks.map((t) => `<li>${esc(t.instruction)} ${refChips(t.sourceRefs)}</li>`).join("")}</ul>
  ` : `<p class="muted">Nothing approved yet.</p>`;
}

function statusBadge(status) {
  return `<span class="status ${esc(status)}">${esc(status.replace("_", " "))}</span>`;
}

function renderChecklist() {
  const rows = caseView.checklist.map((t) => `
    <tr>
      <td>${esc(t.instruction)}<div>${refChips(t.sourceRefs)}</div></td>
      <td>${esc(t.timing ?? "")}</td>
      <td>${esc(t.responsibleParty)}</td>
      <td>${statusBadge(t.status)}${t.lastEvent ? `<div class="muted">${esc(t.lastEvent.actor)}<br>${esc(t.lastEvent.timestamp)}</div>` : ""}</td>
    </tr>`).join("");
  return `<table><tr><th>Task</th><th>Timing</th><th>Who</th><th>Status</th></tr>${rows}</table>`;
}

function renderCaregiver() {
  const c = caseView.case;
  const approved = c.summaryVersions.find((v) => v.version === c.approvedSummaryVersion);
  const open = approved && c.workflowState !== "awaiting_review" &&
    approved.inputRevision === c.inputRevision;
  $("#cg-locked").hidden = open;
  $("#cg-body").hidden = !open;
  if (!open) return;

  $("#conversation").innerHTML = c.messages.map((m) => {
    if (m.role === "caregiver") return `<div class="msg caregiver">${esc(m.text)}</div>`;
    const r = m.reply ?? { kind: "answer", sourceRefs: [], eventRefs: [] };
    let confirm = "";
    if (r.pendingUpdateId) {
      const u = c.pendingUpdates.find((p) => p.id === r.pendingUpdateId);
      if (u) {
        const label = `${taskInstruction(u.taskId)} → ${u.reportedStatus.replace("_", " ")}`;
        confirm = u.status === "pending" ? `
          <div class="confirm-card">
            <div><strong>Confirm update:</strong> ${esc(label)}</div>
            <div class="muted">${esc(u.note)}</div>
            <div class="row" style="margin:8px 0 0">
              <button data-confirm="${esc(u.id)}">Confirm</button>
              <button class="secondary" data-reject="${esc(u.id)}">Not right</button>
            </div>
          </div>` : `<div class="confirm-card muted">Update ${esc(u.status)}: ${esc(label)}</div>`;
      }
    }
    return `<div class="msg assistant">
      <div class="kind ${esc(r.kind)}">${esc(r.kind.replace("_", " "))}</div>
      <div>${esc(m.text)}</div>
      <div>${refChips(r.sourceRefs, r.eventRefs)}</div>
      ${confirm}
    </div>`;
  }).join("") || `<p class="muted">Ask about the approved instructions, or report progress.</p>`;

  $("#conversation").querySelectorAll("[data-confirm]").forEach((b) => b.addEventListener("click", () =>
    run(b, async () => setCase(await api(`/api/cases/${CASE_ID}/updates/${b.dataset.confirm}/confirm`, { method: "POST" })))));
  $("#conversation").querySelectorAll("[data-reject]").forEach((b) => b.addEventListener("click", () =>
    run(b, async () => setCase(await api(`/api/cases/${CASE_ID}/updates/${b.dataset.reject}/reject`, { method: "POST" })))));

  $("#checklist").innerHTML = renderChecklist();
}

function renderReport() {
  const c = caseView.case;
  const approved = c.summaryVersions.find((v) => v.version === c.approvedSummaryVersion);
  if (!approved) {
    $("#report").innerHTML = `<h2>Central report</h2><p class="muted">No approved instructions yet.</p>`;
    return;
  }
  const openTasks = caseView.checklist.filter((t) => t.status !== "done");
  const openQs = c.unresolvedQuestions.filter((q) => q.status === "open");
  $("#report").innerHTML = `
    <h2>Central report · ${esc(c.caseId)}</h2>
    <p class="muted">Derived from saved approved instructions and attributed events. Self-reported progress does not indicate clinical outcome.</p>
    <h3>Approved instructions (v${approved.version}, ${esc(approved.approvedBy)}, ${esc(approved.approvedAt)})</h3>
    <p>${esc(approved.summary)}</p>
    ${renderChecklist()}
    <h3>Self-reported updates</h3>
    ${c.progressEvents.length ? `<table><tr><th>When</th><th>Who</th><th>Plan</th><th>Task</th><th>Status</th><th>Note</th></tr>
      ${c.progressEvents.map((e) => {
        const version = c.summaryVersions.find((v) => v.version === e.approvedSummaryVersion);
        const instruction = version?.careTasks.find((t) => t.id === e.taskId)?.instruction ?? e.taskId;
        return `<tr><td>${esc(e.timestamp)}</td><td>${esc(e.actor)}</td><td>v${esc(e.approvedSummaryVersion)}</td><td>${esc(instruction)}</td><td>${statusBadge(e.status)}</td><td>${esc(e.note)}</td></tr>`;
      }).join("")}
      </table>` : `<p class="muted">None yet.</p>`}
    <h3>Open tasks</h3>
    ${openTasks.length ? `<ul class="plain">${openTasks.map((t) => `<li>${esc(t.instruction)}</li>`).join("")}</ul>` : `<p class="muted">None.</p>`}
    <h3>Unresolved questions for the care team</h3>
    ${openQs.length ? `<ul class="plain">${openQs.map((q) => `<li>${esc(q.question)} <span class="muted">(${esc(q.createdAt)})</span></li>`).join("")}</ul>` : `<p class="muted">None.</p>`}
  `;
}

// ---------- actions ----------

async function loadCase(reset = false) {
  setCase(await api("/api/cases", { method: "POST", json: { reset } }));
}

async function approveDraft() {
  const body = {
    summary: draftEdit.summary,
    careTasks: draftEdit.careTasks.map((t) => ({
      id: t.id, instruction: t.instruction, timing: t.timing,
      responsibleParty: t.responsibleParty, sourceRefs: t.sourceRefs,
    })),
    approvedBy: $("#approved-by").value,
    inputRevision: draftEdit.inputRevision,
  };
  setCase(await api(`/api/cases/${CASE_ID}/approve`, { method: "POST", json: body }));
}

async function sendQuestion(text) {
  text = text.trim();
  if (!text) return;
  $("#interim").textContent = "Thinking…";
  try {
    await api(`/api/cases/${CASE_ID}/chat`, { method: "POST", json: { text } });
  } finally {
    $("#interim").textContent = "";
    // Reload so the conversation reflects exactly what the backend saved.
    setCase(await api(`/api/cases/${CASE_ID}`));
  }
}

// ---------- speech (Reson8 Turns) ----------

const WORKLET = `
class Pcm16Downsampler extends AudioWorkletProcessor {
  constructor() {
    super(); this.ratio = sampleRate / 16000; this.pos = 0; this.out = [];
    this.port.onmessage = (e) => {
      if (e.data === "flush") { this.emit(); this.port.postMessage({ flushed: true }); }
    };
  }
  emit() {
    if (this.out.length) this.port.postMessage(Int16Array.from(this.out).buffer, []);
    this.out = [];
  }
  process(inputs) {
    const input = inputs[0][0];
    if (!input) return true;
    for (; this.pos < input.length; this.pos += this.ratio) {
      const s = Math.max(-1, Math.min(1, input[Math.floor(this.pos)]));
      this.out.push(s < 0 ? s * 0x8000 : s * 0x7fff);
    }
    this.pos -= input.length;
    if (this.out.length >= 1600) {
      this.emit();
    }
    return true;
  }
}
registerProcessor("pcm16-downsampler", Pcm16Downsampler);`;

const mic = { ws: null, capture: null, lastText: "", active: false };

async function startMic() {
  if (consultation.active || consultation.starting || consultation.stopping) {
    throw new Error("End the consultation before starting a caregiver question.");
  }
  const token = await api("/api/voice/token", { method: "POST" });
  const params = new URLSearchParams({ encoding: "pcm_s16le", sample_rate: "16000", channels: "1", language: "en" });
  const ws = new WebSocket(`${token.turnsUrl}?${params}`, ["bearer", token.accessToken]);
  ws.binaryType = "arraybuffer";
  mic.ws = ws;
  mic.lastText = "";

  ws.onmessage = (ev) => {
    if (typeof ev.data !== "string") return;
    const msg = JSON.parse(ev.data);
    if (msg.type === "turn_end_candidate") {
      mic.lastText = msg.text;
      $("#interim").textContent = msg.text;
    } else if (msg.type === "turn_end") {
      const text = mic.lastText;
      stopMic();
      run(null, () => sendQuestion(text));
    }
  };
  ws.onclose = (ev) => {
    if (mic.active) {
      stopMic();
      showError(`Speech connection closed (${ev.code}${ev.reason ? `: ${ev.reason}` : ""}). Use typed input as a fallback.`);
    }
  };
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = () => reject(new Error("Could not connect to Reson8. Use typed input as a fallback."));
  });

  mic.capture = await createPcmCapture(ws);

  mic.active = true;
  $("#btn-mic").textContent = "■ Finish question";
  $("#btn-mic").classList.add("recording");
  $("#mic-status").textContent = "Listening… the question is sent when you pause.";
}

function stopMic() {
  mic.active = false;
  mic.capture?.stop();
  if (mic.ws && mic.ws.readyState <= WebSocket.OPEN) mic.ws.close(1000);
  Object.assign(mic, { ws: null, capture: null });
  $("#btn-mic").textContent = "🎙 Start speaking";
  $("#btn-mic").classList.remove("recording");
  $("#mic-status").textContent = "";
}

async function finishTurn() {
  // Ask Reson8 to end the turn now; it replies with a final candidate and turn_end.
  if (mic.ws?.readyState === WebSocket.OPEN) {
    await mic.capture?.flush();
    if (mic.ws?.readyState === WebSocket.OPEN) mic.ws.send(JSON.stringify({ type: "flush_request" }));
  }
  else stopMic();
}

// ---------- wiring ----------

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab.dataset.tab}`));
}));

$("#btn-create").addEventListener("click", (e) => run(e.target, () => loadCase(false)));
$("#btn-reset").addEventListener("click", (e) => {
  if (confirm("Reset the demo case? Saved data for this case will be cleared.")) run(e.target, () => loadCase(true));
});
$("#btn-upload").addEventListener("click", (e) => run(e.target, async () => {
  const file = $("#file").files[0];
  if (!file) throw new Error("Choose a PDF first.");
  const form = new FormData();
  form.append("file", file);
  setCase(await api(`/api/cases/${CASE_ID}/document`, { method: "POST", body: form }));
}));
$("#btn-draft").addEventListener("click", (e) => run(e.target, async () => {
  e.target.textContent = "Drafting…";
  try {
    setCase(await api(`/api/cases/${CASE_ID}/summary`, { method: "POST" }));
  } finally {
    e.target.textContent = "Generate draft with Claude";
  }
}));
$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = $("#chat-input");
  const text = input.value;
  input.value = "";
  run(e.submitter, () => sendQuestion(text));
});
$("#btn-mic").addEventListener("click", (e) => {
  if (mic.active) run(e.target, finishTurn);
  else run(e.target, async () => {
    try { await startMic(); } catch (err) { stopMic(); throw err; }
  });
});

run(null, () => loadCase(false));
