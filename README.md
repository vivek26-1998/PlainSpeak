# PlainSpeak MVP

A consultation and post-care voice assistant. Reson8 captures the clinician-patient conversation
live. Claude combines the saved transcript and discharge document into a draft for clinician
approval, then answers caregiver questions from the reviewed context and records confirmed
progress updates for a central report.

**This is a synthetic-data demonstration, not a clinical application.** Use only the fictional
fixture; do not upload real patient records.

See [the team handoff](PlainSpeak-MVP-Team-Handoff.md) for scope, ownership and the demo script,
and [the architecture](PlainSpeak-architecture.md) for diagrams, data flow and agent tools.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12 or later, FastAPI, one process (`src/plainspeak/`) |
| Frontend | Static HTML/JS served by the backend (`src/plainspeak/static/`) |
| Reasoning | Anthropic Python SDK, one manual tool-use loop, structured JSON outputs |
| Speech | Reson8 Realtime with diarization for consultation; Turns for caregiver questions |
| PDF | `pypdf` text extraction, passages `page_{n}_p{k}` |
| Storage | One JSON file per case in `data/cases/` (atomic writes, per-case lock) |
| Tooling | `uv`, `ruff` (lint + format), `pytest` |

## Setup

```powershell
uv sync
if (!(Test-Path .env)) { Copy-Item .env.example .env }
uv run python scripts/make_fixture.py
```

Fill in `ANTHROPIC_API_KEY` and `RESON8_API_KEY` in your local `.env`. The copy command preserves
an existing file. On macOS/Linux, use `test -f .env || cp .env.example .env` instead.
The fixture command generates `fixtures/discharge.pdf`. Permanent keys are used only by the
backend; the browser receives a temporary speech token.

`.env` settings:

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude calls (backend only) |
| `ANTHROPIC_MODEL` | Default `claude-opus-5-5` |
| `ANTHROPIC_EFFORT` | `low`/`medium`/`high`/`xhigh`/`max`; empty to omit |
| `ANTHROPIC_FALLBACKS` | `default` enables server-side refusal fallback; empty to disable |
| `RESON8_API_KEY` | Exchanged for 10-minute browser tokens (backend only) |
| `PORT` | Default `3001` |

## Run

```bash
uv run plainspeak
```

Open http://127.0.0.1:3001. Microphone access requires `localhost`/`127.0.0.1` or HTTPS.

## Demo

1. **Doctor view:** Load demo case, confirm participant consent, and select English or German.
2. **Start consultation:** Speak as clinician and patient; finalized lines save automatically.
   Pauses do not end the session. Select **End and save consultation** when finished.
   Confirm each anonymous voice as clinician or patient. A labelled manual fallback is available.
   If saving fails, keep the page open and use **Retry saving transcript** before continuing.
3. Upload `fixtures/discharge.pdf`, then **Generate draft with Claude**. Review the conversation
   and document together, edit the summary and tasks, then approve.
4. **Caregiver view:** ask aloud (or type) "What should I arrange before the follow-up?" and the answer shows source chips (hover for the passage text).
5. Say "Transport is arranged." A confirmation card appears and the status changes only after **Confirm**.
6. Ask something the document doesn't cover, such as "Can he take a shower?". The question is recorded locally for the care team; no message is sent automatically.
7. **Central report:** approved instructions, self-reported updates, open tasks and unresolved questions.

New transcript lines, speaker-role changes or documents require another review. Approval saves
an evidence snapshot. Drafts generated against an older input revision cannot be approved by
the current UI. The app does not store raw audio, automatically correct medical instructions,
or run live clinical alerts. Transcript-based uncertainty is highlighted in the combined draft.

Post-care uses `get_case_context` to load the approved evidence before asking Claude. Only
`get_case_context` and `propose_progress_update` are exposed as model tools. Approval, update
confirmation and rejection are application actions. Checklist generation is part of summary
drafting; there is no separate Generate plan step. Progress applies to its approved version.

## Memory clinic demo pack

For the two-person memory-care scenario, use the
[conversation script and caregiver test guide](fixtures/memory-care-demo-script.md).
Record that consultation, then upload the
[fictional memory clinic summary](output/pdf/plainspeak-memory-care-discharge.pdf)
as the supporting document. Do not upload the script or expected answers.

This is a separate scenario from the fall-related `fixtures/discharge.pdf`. Reset the demo case
only when ready to clear the previous run. The memory clinic pack includes a corrected
misunderstanding and spoken-only details to test consultation context. Its medicine record
is synthetic and is not a real prescription.

To regenerate the one-page PDF without adding a permanent project dependency:

```powershell
uv run --with reportlab python scripts/make_memory_care_demo.py
```

## Development checks

```bash
uv run ruff check .          # lint
uv run ruff format .         # format
uv run pytest                # tests use a scripted fake Claude; no API keys needed
node --test tests/consultation_frontend.test.cjs  # simulated speech-controller tests
```

## Layout

```text
src/plainspeak/
  main.py          app factory + `plainspeak` entry point
  api.py           HTTP routes and workflow gates
  contracts.py     shared data contracts (camelCase on the wire)
  storage.py       JSON case files
  pdf_extract.py   PDF → passages
  voice.py         Reson8 token issuance
  ai/              Claude client, prompts, tool handlers, agent loop, summary drafting
  static/
    index.html       doctor, caregiver and report tabs
    app.js           review, caregiver voice, checklist and report
    consultation.js  continuous capture, speaker mapping and save recovery
    styles.css       frontend styles
scripts/make_fixture.py   fictional discharge PDF generator
tests/                    Python workflow tests and simulated speech-controller tests
data/                     runtime data (git-ignored)
```

The browser speech-controller tests use fake WebSocket and microphone APIs. They verify
multi-speaker session persistence, finalization and save recovery, not live microphone quality
or provider connectivity. Test a real microphone with Reson8 credentials before the demo.
