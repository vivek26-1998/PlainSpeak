// Controller tests with fake browser APIs; no microphone or provider calls.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { randomUUID } = require("node:crypto");
const vm = require("node:vm");

function setup() {
  const elements = new Map();
  const getElement = (selector) => {
    if (!elements.has(selector)) elements.set(selector, {
      innerHTML: "", textContent: "", checked: true, disabled: false, value: "en",
      addEventListener() {}, querySelectorAll() { return []; },
    });
    return elements.get(selector);
  };
  const state = { transcriptSegments: [], speakerRoles: {}, sources: [] };
  const writes = [];
  const errors = [];
  let socket;
  let failSave = false;
  let flushed = false;
  let stopped = false;
  class Socket {
    static OPEN = 1;
    static CLOSING = 2;
    constructor(url) {
      this.url = url;
      this.readyState = 1;
      socket = this;
      queueMicrotask(() => this.onopen?.());
    }
    emit(data) { this.onmessage({ data: JSON.stringify(data) }); }
    send(raw) {
      if (typeof raw !== "string") return;
      const message = JSON.parse(raw);
      if (message.type === "flush_request") {
        this.emit({ type: "transcript", is_final: true, text: "Final words before stopping.", speaker_id: 0 });
        this.emit({ type: "flush_confirmation", id: message.id });
      }
    }
    close() { this.readyState = 3; }
  }
  const sandbox = {
    console, setTimeout, clearTimeout, crypto: { randomUUID }, URLSearchParams,
    WebSocket: Socket, WORKLET: "", mic: { active: false, ws: null }, CASE_ID: "demo-patient",
    caseView: { case: state }, $: getElement, esc: String,
    showError(message) { errors.push(message); },
    setCase(view) { sandbox.caseView = view; },
    async api(path, options) {
      if (path === "/api/voice/token") return { realtimeUrl: "wss://example.invalid/realtime", accessToken: "fake" };
      if (failSave) throw new Error("Simulated storage outage");
      writes.push(options.json);
      for (const segment of options.json.segments) {
        if (!state.transcriptSegments.some((saved) => saved.id === segment.id)) state.transcriptSegments.push(segment);
      }
      Object.assign(state.speakerRoles, options.json.speakerRoles);
      return { case: state };
    },
    window: { addEventListener() {} },
    run: async (_button, operation) => operation(),
  };
  const context = vm.createContext(sandbox);
  vm.runInContext(readFileSync("src/plainspeak/static/consultation.js", "utf8"), context);
  context.fakeCapture = {
    async flush() { flushed = true; }, stop() { stopped = true; },
  };
  vm.runInContext("createPcmCapture = async () => fakeCapture", context);
  return {
    context, elements, state, writes, errors,
    socket: () => socket,
    failSave(value) { failSave = value; },
    flushed: () => flushed, stopped: () => stopped,
    run(code) { return vm.runInContext(code, context); },
  };
}

test("Realtime keeps both speakers, ignores partials and saves the final flush before closing", async () => {
  const app = setup();
  await app.run("startConsultation()");
  assert.match(app.socket().url, /diarize=true/);
  assert.match(app.socket().url, /include_interim=true/);
  app.socket().emit({ type: "transcript", is_final: false, text: "Unfinished words" });
  assert.equal(app.writes.length, 0);
  app.socket().emit({ type: "transcript", is_final: true, text: "Bring the medication list.", speaker_id: 0, start_ms: 100 });
  await app.run("consultation.queue");
  assert.equal(app.run("consultation.active"), true);
  app.socket().emit({ type: "transcript", is_final: true, text: "I thought I only needed ID.", speaker_id: 1, start_ms: 200 });
  await app.run("consultation.queue");
  assert.equal(app.state.transcriptSegments.length, 2);
  assert.equal(app.state.transcriptSegments[1].speakerId, 1);
  await app.run("endConsultation()");
  assert.equal(app.state.transcriptSegments.length, 3);
  assert.equal(app.state.transcriptSegments[2].text, "Final words before stopping.");
  assert.equal(app.flushed(), true);
  assert.equal(app.stopped(), true);
  assert.equal(app.socket().readyState, 3);
  assert.equal(app.run("consultation.pending.size"), 0);
});

test("Failed saves retain finalized text for retry and disable summary generation", async () => {
  const app = setup();
  app.failSave(true);
  await assert.rejects(app.run(`queueConsultationSegment({
    id: "seg-retry", sessionId: "session-one", text: "Keep this line", speakerId: 0
  })`));
  assert.equal(app.run("consultation.pending.size"), 1);
  assert.equal(app.elements.get("#btn-draft").disabled, true);
  app.failSave(false);
  await app.run("queueConsultationSegment(consultation.pending.get('seg-retry'))");
  assert.equal(app.state.transcriptSegments[0].text, "Keep this line");
  assert.equal(app.run("consultation.pending.size"), 0);
});
