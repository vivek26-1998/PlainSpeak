
# PlainSpeak: Technology Stack, APIs, Frameworks, and Tools

## 1. Overview

PlainSpeak combines browser-based speech capture, external speech recognition, a Python API, an LLM-powered summarization and question-answering layer, and local persistence.

The stack has five main layers:

1. **Frontend:** HTML, CSS, and JavaScript.
2. **Speech interface:** Reson8 Realtime and Turns APIs.
3. **Application backend:** Python, FastAPI, Pydantic, and Uvicorn.
4. **Language intelligence:** Anthropic Claude API and a controlled backend tool-use loop.
5. **Persistence and document processing:** Local JSON storage, PDF text extraction, and evidence references.

## 2. Core technology stack

| Technology | Category | Role in PlainSpeak |
|---|---|---|
| Python | Programming language | Backend implementation, workflow orchestration, validation, and persistence. |
| FastAPI | Backend framework | HTTP endpoints, request handling, dependency injection, and OpenAPI generation. |
| Uvicorn | ASGI server | Runs the FastAPI application locally. |
| Pydantic | Data validation | Defines typed request/response models and validates structured application data. |
| pydantic-settings | Configuration | Loads configuration from environment variables and `.env` files. |
| Anthropic Claude | Hosted LLM API | Generates draft summaries and care tasks, and answers caregiver questions using approved context. |
| Reson8 | Speech API platform | Provides real-time consultation transcription with diarization and turn-based caregiver question transcription. |
| pypdf | PDF processing library | Extracts selectable text from discharge documents and supported transcript PDFs. |
| httpx | HTTP client | Exchanges the backend's Reson8 API key for a temporary access token. |
| HTML5 | Frontend technology | Defines the application interface. |
| CSS | Frontend styling | Controls layout, visual design, and responsive presentation. |
| Vanilla JavaScript | Frontend programming | Handles application interactions, API calls, consultation capture, approval, and caregiver chat. |
| JSON | Serialization format | Stores case state and communicates structured data between frontend and backend. |
| WebSocket | Communication protocol | Carries speech-service streaming traffic where supported by the Reson8 endpoint. |

The actual versions and optional dependencies should be taken from `pyproject.toml` and `uv.lock`.

## 3. Reson8 Speech API

**Reson8 is a core component of PlainSpeak's voice interface.** It provides the speech-recognition capabilities used in two different stages of the workflow.

### 3.1 Realtime speech-to-text

Endpoint:

`wss://api.reson8.dev/v1/speech-to-text/realtime`

Purpose:
- Captures the live clinician-patient consultation through the browser.
- Streams audio for transcription.
- Supports speaker diarization, allowing utterances to be associated with anonymous speaker identifiers.
- Supplies interim and finalized transcript segments to the frontend workflow.

The application allows the user to map anonymous speaker identifiers to roles such as clinician or patient. A diarization identifier is not proof of a person's identity.

### 3.2 Turn-based speech-to-text

Endpoint:

`wss://api.reson8.dev/v1/speech-to-text/turns`

Purpose:
- Captures a caregiver's spoken question.
- Transcribes a bounded speech turn.
- Supplies the resulting text to the PlainSpeak caregiver Q&A workflow.

This is distinct from the continuous consultation capture path. A caregiver question is transcribed and then submitted to the application backend for an answer based on the approved instructions.

### 3.3 Authentication and token exchange

The backend uses the configured `RESON8_API_KEY` to request a temporary access token from:

`https://api.reson8.dev/v1/auth/token`

The request uses an authorization header in the form:

`Authorization: ApiKey <server-side-api-key>`

The backend exposes a token endpoint at `POST /api/voice/token`. The browser receives the temporary token and relevant speech-service connection URLs.

The permanent API key must remain server-side. It must never be embedded in frontend JavaScript or committed to GitHub.

### 3.4 Browser requirements

Voice functionality depends on:

- A browser that supports the required media APIs and WebSocket connections.
- Microphone permission.
- A supported secure browser context, such as `localhost`, `127.0.0.1`, or HTTPS.
- Valid Reson8 credentials.
- Network connectivity to the external speech service.

Speech-provider outages or authentication errors can prevent voice features from working. These failures should be tested separately from the application's local workflow.

### 3.5 Data-handling considerations

PlainSpeak does not persist raw microphone audio as part of its intended application workflow. Transcribed text is stored as consultation or caregiver interaction data when appropriate.

However, audio is sent to Reson8 for processing, and transcription text may subsequently be sent to Anthropic. The absence of local audio storage does not mean the entire processing chain is local.

Before using any real patient information, the provider's data retention, processing, contractual, and privacy terms would need to be reviewed.

## 4. Anthropic Claude API

### Purpose

Claude supplies the language-generation and agent-reasoning capabilities.

The integration supports two principal workflows.

**A. Draft summary generation**

- Receives consultation text and extracted discharge-document passages.
- Produces structured draft summary content and proposed care tasks.
- Supports evidence references and missing-information indicators.
- Returns output that the backend validates before presenting it for review.

**B. Caregiver question answering**

- Receives the caregiver's question and context from the approved care plan.
- Uses a restricted set of backend tools where needed.
- Produces an answer, clarification request, or unresolved response.
- Can propose a structured progress update, which remains pending until confirmed.

### Integration details

The Anthropic Python SDK is used from the backend. Model selection and provider settings are configured through environment variables. Structured output is validated against application contracts.

The permanent Anthropic API key must remain on the server. The frontend must not call Anthropic directly with the permanent credential.

Configuration variables include:

- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL`
- `ANTHROPIC_EFFORT`
- `ANTHROPIC_FALLBACKS`

Check `src/plainspeak/config.py` for the current defaults and exact configuration behavior. Model availability depends on the provider account and the current API.

### Agent tool boundary

The caregiver agent may use permitted tools to retrieve approved context and propose progress updates. It cannot independently approve a care plan or confirm a progress update.

These actions are enforced by the application backend, not by trusting the model to follow instructions alone.

## 5. Backend frameworks and libraries

| Package or component | Purpose |
|---|---|
| `fastapi` | API routing and request handling. |
| `uvicorn` | Local ASGI server. |
| `pydantic` | Typed data contracts and validation. |
| `pydantic-settings` | Environment-based settings. |
| `anthropic` | Claude API integration. |
| `httpx` | HTTP communication for Reson8 token exchange. |
| `pypdf` | Text extraction from PDF documents. |
| `python-multipart` | Multipart file upload parsing in FastAPI. |

The exact dependency declarations should be checked in `pyproject.toml`. Do not infer that a library is installed solely because it is mentioned in documentation.

## 6. Frontend technologies

### HTML5

Defines the page structure, forms, navigation, dialogs, transcript display, and care checklist.

### CSS

Defines the interface appearance, layout, responsive behavior, and component styling.

### Vanilla JavaScript

Implements browser-side workflow logic without requiring a React, Vue, or Angular build pipeline.

The primary frontend files are:

- `src/plainspeak/static/index.html`
- `src/plainspeak/static/app.js`
- `src/plainspeak/static/consultation.js`
- `src/plainspeak/static/styles.css`

The application JavaScript communicates with the backend through HTTP requests and uses browser media APIs for voice capture. The consultation controller manages finalized transcript segments and recovery behavior.

## 7. Document processing and evidence management

### pypdf

Used to extract text from selectable-text PDF files.

The extracted text is organized into page-labelled passages so the application can retain references to the original source.

Limitations:
- Scanned PDFs without an embedded text layer are not supported by the current extraction workflow.
- OCR is not included.
- Extracted text can contain formatting errors or incomplete content.

### Evidence references

PlainSpeak associates generated content with stable source and passage identifiers.

These references make it easier to inspect where a generated instruction came from. They do not, by themselves, guarantee that the model's interpretation is correct.

## 8. Persistence and data formats

### JSON case store

The prototype stores case state in local JSON files. The store supports the demonstration workflow without a separate database server.

### Local filesystem

Uploaded PDFs are stored locally. This simplifies setup but does not provide the encryption, lifecycle management, access controls, backups, or durability guarantees required for production clinical data.

### Pydantic contracts

Structured models define and validate the data passed between endpoints and internal workflow components. These contracts are the primary source for understanding request and response shapes.

## 9. Development and testing tools

| Tool | Role | Typical command |
|---|---|---|
| `uv` | Python environment and dependency management. | `uv sync` |
| `pytest` | Backend tests. | `uv run pytest` |
| Node.js test runner | Frontend controller tests. | `node --test tests/consultation_frontend.test.cjs` |
| Ruff | Python linting and formatting. | `uv run ruff check .` |
| Fixture-generation script | Creates synthetic PDF fixtures for testing and demonstration. | `uv run python scripts/make_fixture.py` |

Tests that inject a fake LLM can run without a live Anthropic API key. They do not establish that live provider authentication, browser microphone capture, or external speech sessions work correctly.

## 10. Configuration and local execution

Install the dependencies:

```bash
uv sync
```

Create the local environment file using the repository's documented example and configure the required provider credentials. Never commit `.env` or real API keys.

Generate the fixture if needed:

```bash
uv run python scripts/make_fixture.py
```

Start the application:

```bash
uv run plainspeak
```

Open:

`http://127.0.0.1:3001`

Check the root README and `src/plainspeak/config.py` for the definitive environment variables, defaults, and setup requirements.

## 11. Technologies not included in the current implementation

The repository should not claim to implement the following unless the code is extended:

- A production relational database or ORM.
- A vector database or semantic-search infrastructure.
- OCR for scanned PDFs.
- A hospital EHR integration.
- Production authentication and authorization.
- A production audit-log service.
- A frontend framework requiring a separate build pipeline.
- A production clinical decision-support or medical-device certification layer.

These are potential future extensions, not current capabilities.

## 12. External documentation

Consult the providers' current official documentation for API contracts and changes:

- Anthropic API documentation: https://docs.anthropic.com/
- FastAPI documentation: https://fastapi.tiangolo.com/
- Pydantic documentation: https://docs.pydantic.dev/
- Uvicorn documentation: https://www.uvicorn.org/
- pypdf documentation: https://pypdf.readthedocs.io/

For Reson8, use the provider's official API documentation or account-provided developer documentation for the current authentication contract, endpoint behavior, supported audio formats, limits, and retention policies.

## 13. Reproducibility note

For a fair technical evaluation, record the Python version, dependency lockfile revision, configured model identifier, and the date of the live-provider test. Distinguish unit tests with mocked services from end-to-end tests using real provider credentials.

This document describes the intended architecture and integration points. The checked-out source code and provider contracts remain authoritative if any detail differs.
