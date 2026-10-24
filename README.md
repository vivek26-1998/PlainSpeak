# PlainSpeak MVP

A consultation and post-care voice assistant. Reson8 captures the clinician-patient conversation
live. Claude combines the saved transcript and discharge document into a draft for clinician
approval, then answers caregiver questions from the reviewed context and records confirmed
progress updates for a central report.

**This is a synthetic-data demonstration, not a clinical application.** Use only the fictional
fixture; do not upload real patient records.

## Technical documentation

- [HTTP API reference](docs/API.md): endpoints, payload examples, validation, and workflow semantics.
- [Technical architecture](docs/ARCHITECTURE.md): modules, data flow, case lifecycle, evidence model, agent boundaries, persistence, and trade-offs.
- [APIs, frameworks, and tools inventory](docs/TOOLS.md): backend/frontend libraries, external providers, environment variables, and developer tooling.
- [Security, privacy, and limitations](docs/SECURITY-AND-LIMITATIONS.md): current safeguards, known gaps, and prerequisites for any future real-world deployment.
- [Team handoff](PlainSpeak-MVP-Team-Handoff.md): scope, ownership, and demo script.
- [Original architecture notes](PlainSpeak-architecture.md): additional diagrams and design notes.

While the server is running, FastAPI provides an interactive API explorer at `http://127.0.0.1:3001/docs` and the OpenAPI schema at `http://127.0.0.1:3001/openapi.json`.

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

## Setup and installation

### Prerequisites

- Python **3.12 or later**.
- [`uv`](https://docs.astral.sh/uv/) for Python environment and dependency management.
- A current Node.js installation only if you want to run the frontend controller tests.
- An Anthropic API key for Claude summary/chat functionality.
- A Reson8 API key for live microphone transcription. The app can be explored without using the microphone, but live voice features require this key.

Install `uv` using the [official installation instructions](https://docs.astral.sh/uv/getting-started/installation/). Confirm the tools are available:

```bash
python --version
uv --version
node --version  # optional; only needed for frontend tests
```

Clone the public repository and enter its directory:

```bash
git clone https://github.com/vivek26-1998/PlainsSpeak.git
cd PlainsSpeak
```

If your local repository URL differs, use the URL shown on the GitHub repository page.

### Install dependencies and configure environment

**Windows PowerShell:**

```powershell
uv sync
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

**macOS / Linux:**

```bash
uv sync
test -f .env || cp .env.example .env
```

Edit `.env` and set your provider keys. Keep this file private and never commit it:

```dotenv
ANTHROPIC_API_KEY=your_anthropic_key
ANTHROPIC_MODEL=claude-opus-5-5
ANTHROPIC_EFFORT=medium
ANTHROPIC_FALLBACKS=default
RESON8_API_KEY=your_reson8_key
PORT=3001
PLAINSPEAK_DATA_DIR=data
```

`ANTHROPIC_MODEL` must be a model identifier available to your Anthropic account. Provider model availability can change. `RESON8_API_KEY` is required only for voice capture. Permanent keys are used by the backend; the browser receives a temporary speech token. Never paste secrets into source code, issue reports, or screenshots.

Generate the fictional PDF fixtures:

```bash
uv run python scripts/make_fixture.py
```

This creates `fixtures/discharge.pdf` and `fixtures/consultation-transcript.pdf`. The repository includes synthetic fixture PDFs, but running the generator allows you to recreate them locally.

### Setup (quick version)

After Python 3.12+ and `uv` are installed, these are the core setup commands:

```bash
uv sync
test -f .env || cp .env.example .env
uv run python scripts/make_fixture.py
```

On Windows PowerShell, replace the `test -f` line with `if (!(Test-Path .env)) { Copy-Item .env.example .env }`.

## Run the local server

Start the backend and static frontend from the repository root:

```bash
uv run plainspeak
```

Then open **http://127.0.0.1:3001** in your browser. To use another port, set `PORT` in `.env` before starting. Stop the server with `Ctrl+C` in the terminal. Microphone access requires `localhost`/`127.0.0.1` or HTTPS.

For development, you can also launch Uvicorn directly:

```bash
uv run uvicorn plainspeak.main:create_app --factory --host 127.0.0.1 --port 3001
```

The `plainspeak` command is the recommended path because it loads settings and configures application logging consistently.

> **Every page load starts a clean demo.** The app resets the single demo case
> (`demo-patient`) when the page opens, so refreshing clears the transcript, document, drafts,
> approvals and caregiver conversation. Keep the tab open for the whole demo. While a
> consultation is recording or transcript lines are still unsaved, the browser asks before
> leaving the page.

## Demo

The left rail has three views: **Care @ Clinic**, **Care @ Home** and **Care Overview**. The
progress strip at the top of Care @ Clinic and the journey card on the right follow the case,
not the selected view. They show *Consultation* until a discharge document is uploaded, then
*Clinician review*, then *At-home support* once the current inputs are approved.

1. **Care @ Clinic:** tick the participant consent box. Consent is required for every capture
   method. Choose the consultation language: English, German, or German + English.
2. **Capture the consultation** in one of three ways, then confirm each anonymous voice as
   clinician or patient with the *Voice N* selectors:
   - **Start consultation:** speak as clinician and patient. Interim text appears as you speak,
     and finalized lines save automatically. Pauses do not end the session. Select
     **End & save** when finished. If saving fails, keep the page open and use
     **Retry saving transcript**. While recording, the other capture, upload, draft, approve
     and reset buttons are disabled.
   - **Upload a written transcript PDF:** expand the section, choose a file and select
     **Import transcript**. See [transcript PDF format](#transcript-pdf-format) below.
   - **Manual transcript fallback:** pick *Clinician* or *Patient*, enter one line and select
     **Save line**. Manual lines are pre-assigned to the chosen role and marked as manually
     entered.
3. **Add the discharge document:** choose `fixtures/discharge.pdf` and select **Upload PDF**.
   The status line shows the filename and passage count.
4. **Generate draft with Claude.** Edit the summary and the care tasks (instruction, optional
   timing, and who is responsible: patient, caregiver, care team or unspecified). You can add or
   remove tasks. Enter the approver name and select **Approve this version**. The approved
   version appears under *Approved care instructions*.

   > **One case describes one patient.** Uploading a discharge PDF replaces the case's previous
   > document, and importing a transcript PDF replaces the previous transcript. Drafting sends
   > every source on the case to Claude, so without this a second patient's file would be
   > summarised alongside the first. To start from nothing, use **Reset demo**.
5. **Care @ Home** stays locked until the approval covers the case's current inputs. After
   approval, select **Start speaking** (English only) or type, and ask "What should I arrange
   before the follow-up?" Your question is sent when you pause, or right away if you select
   **Finish question**. Answers show source chips; hover over one to see the passage text.
   Caregiver questions can't be recorded while a consultation is recording.
6. Say "Transport is arranged." A confirmation card appears, and the task status changes only
   after **Confirm**. Select **Not right** to reject it. The *Care checklist* beside the
   conversation shows each task's status and last update.
7. Ask something the document doesn't cover, such as "Can Alex take a shower?" The question is
   recorded locally for the care team; no message is sent automatically.
8. **Care Overview:** approved instructions, the task checklist, self-reported updates (with the
   plan version they apply to), open tasks and unresolved questions.

### Transcript PDF format

All three capture methods produce the same `consultation_001` source, so an imported
transcript is reviewed, approved and cited exactly like a recorded one. Upload
`fixtures/consultation-transcript.pdf` to try it.

```text
Consultation Transcript - FICTIONAL DEMO DOCUMENT   <- ignored: before the first label
[00:00:04] Clinician: Good morning Alex.            <- turn 1, startMs 4000
Patient: I only needed my ID card, I thought.       <- turn 2, no timestamp
and I may have misremembered the date.              <- continues turn 2
```

Each turn starts with a speaker label of at most four words followed by a colon. A leading
timestamp (`[00:00:04]`, `(1:23)`, `12:30.500`) becomes `startMs`. A line with no label
continues the turn above, which is how turns that wrap across PDF lines stay intact. Lines
before the first labelled turn are ignored.

Only unambiguous labels (`Clinician`, `Doctor`, `Dr.`, `Nurse`, `Patient`, …) pre-fill a
role; anything else — including `Speaker 1` — stays unconfirmed for the clinician to set,
and a role already confirmed in the UI is never overwritten by a later upload. Limits: 10 MB,
300 turns, 8 distinct speakers, at least 2.

An import **replaces** whatever was captured before it — live, manual or a previous import —
so one case holds one consultation. Segment IDs are derived from the file's content hash, so
re-uploading the same file is recognised and changes nothing at all.

New transcript lines, speaker-role changes or documents require another review. Approval saves
an evidence snapshot. Drafts generated against an older input revision cannot be approved by
the current UI. The app does not store raw audio, automatically correct medical instructions,
or run live clinical alerts. Transcript-based uncertainty is highlighted in the combined draft.

Post-care uses `get_case_context` to load the approved evidence before asking Claude. Only
`get_case_context` and `propose_progress_update` are exposed as model tools. Approval, update
confirmation and rejection are application actions. Checklist generation is part of summary
drafting; there is no separate Generate plan step. Progress applies to its approved version.

## Development

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
  pdf_extract.py   PDF → passages and lines
  transcript_import.py  transcript PDF lines → speaker-labelled segments
  voice.py         Reson8 token issuance
  ai/              Claude client, prompts, tool handlers, agent loop, summary drafting
  static/
    index.html       Care @ Clinic, Care @ Home and Care Overview views
    app.js           review, caregiver voice, checklist and report
    consultation.js  continuous capture, speaker mapping and save recovery
    styles.css       frontend styles
scripts/make_fixture.py   fictional discharge + consultation transcript PDF generator
tests/                    Python workflow tests and simulated speech-controller tests
data/                     runtime data (git-ignored)
```

The browser speech-controller tests use fake WebSocket and microphone APIs. They verify
multi-speaker session persistence, finalization and save recovery, not live microphone quality
or provider connectivity. Test a real microphone with Reson8 credentials before the demo.

## Frontend notes

The UI is a responsive "PlainSpeak Lab" workspace with a dark navigation rail. Its persona
labels ("Anna's care journey", "Anna Miller", case PS-2048) are fixed in `index.html`. They do
not come from the case data: the fixture patient is *Alex Example* and the backend case ID is
`demo-patient`. Fonts load from Google Fonts when online; system fonts are used otherwise.
