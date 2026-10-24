# APIs, frameworks, and tools inventory

This document describes technologies directly used by the repository. Provider APIs may change; consult their official documentation before changing SDK versions or productionizing the prototype.

## Runtime and backend

| Technology | Use in PlainSpeak | Where to look |
|---|---|---|
| Python 3.12+ | Application language and runtime. | `pyproject.toml`, `src/plainspeak/` |
| FastAPI | HTTP API, dependency injection, request parsing, validation integration, and generated OpenAPI docs. | `src/plainspeak/main.py`, `src/plainspeak/api.py` |
| Uvicorn | ASGI server used by the `plainspeak` command. | `src/plainspeak/main.py` |
| Pydantic | Typed request/response contracts and data validation. | `src/plainspeak/contracts.py` |
| pydantic-settings | Environment and `.env` configuration loading. | `src/plainspeak/config.py` |
| Anthropic Python SDK | Calls Claude for structured summaries and the post-care agent loop. | `src/plainspeak/ai/client.py` |
| httpx | HTTP request to Reson8's token endpoint. | `src/plainspeak/voice.py` |
| pypdf | Text extraction from PDF documents and transcript PDFs. | `src/plainspeak/pdf_extract.py`, `src/plainspeak/transcript_import.py` |
| python-multipart | FastAPI multipart upload parsing. | `pyproject.toml`, `src/plainspeak/api.py` |

## External APIs

### Anthropic Claude Messages API

Used for (1) generating a draft plain-language summary and care checklist from the transcript plus discharge-document passages, and (2) caregiver Q&A after loading the approved evidence snapshot. The SDK is configured for structured JSON-schema output and can expose a limited set of tools to the model. Model name, reasoning effort, fallback behavior, and API key are configurable via environment variables. The default model string in the current configuration is `claude-opus-5-5`; availability depends on the provider account and may need to be changed.

Required configuration: `ANTHROPIC_API_KEY`. Optional: `ANTHROPIC_MODEL`, `ANTHROPIC_EFFORT`, `ANTHROPIC_FALLBACKS`. No key is required to run the test suite because tests inject a scripted fake LLM.

### Reson8 Speech API

The backend sends `RESON8_API_KEY` to `https://api.reson8.dev/v1/auth/token` using an `Authorization: ApiKey ...` header. The returned short-lived token is provided to the browser with the WebSocket URLs:

- Realtime transcription: `wss://api.reson8.dev/v1/speech-to-text/realtime`
- Turn-based transcription: `wss://api.reson8.dev/v1/speech-to-text/turns`

Realtime capture supports consultation transcription and diarization. Turns supports caregiver question transcription. The frontend needs microphone permission and a secure context (`localhost`, `127.0.0.1`, or HTTPS). Permanent keys must remain in `.env` on the backend.

## Frontend technologies

- **HTML5**: static application structure in `src/plainspeak/static/index.html`.
- **CSS**: responsive layout and visual styling in `styles.css`.
- **Vanilla JavaScript**: browser interaction and workflow logic in `app.js` and `consultation.js`; no frontend build step or package manager is required.
- **WebSocket and browser media APIs**: speech provider streaming and microphone capture. Automated tests mock these APIs; a real microphone/provider smoke test is still needed.
- **Google Fonts**: optional remote font loading. System fallbacks are used if unavailable.

## Developer and quality tools

| Tool | Purpose | Command |
|---|---|---|
| `uv` | Python environment and dependency/lockfile management. | `uv sync` |
| `pytest` | Backend/workflow tests, using a fake LLM. | `uv run pytest` |
| Node.js test runner | Simulated consultation speech-controller tests. | `node --test tests/consultation_frontend.test.cjs` |
| Ruff | Python lint and formatting. | `uv run ruff check .`; `uv run ruff format .` |
| `fpdf2` | Generates synthetic PDF fixtures in the helper script. | `uv run python scripts/make_fixture.py` |

The project uses `pyproject.toml` for dependency metadata and Ruff/Pytest settings, and `uv.lock` to pin the resolved Python dependency graph.

## Not used / scope boundaries

There is no React/Vue frontend, database server, ORM, vector database, OCR engine, cloud file store, text-to-speech engine, or production identity provider in this repository. Do not describe these as implemented capabilities. The app extracts selectable text from PDFs; scanned-image OCR is not implemented.
