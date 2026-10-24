# HTTP API reference

Base URL for local development: `http://127.0.0.1:3001`. All API routes are prefixed with `/api`. Requests and responses use JSON unless an endpoint accepts a multipart file. Field names on the wire are camelCase. The interactive OpenAPI reference is available at `/docs` and the schema at `/openapi.json` while the server is running.

> This API belongs to a synthetic-data prototype. It has no production authentication or authorization. Do not expose it to the public internet or submit real patient data.

## Common response and error behavior

Most workflow endpoints return a `CaseView`, containing the current case plus a projected checklist. FastAPI/Pydantic validation errors use HTTP 422. Missing cases generally return 404; invalid workflow transitions or invalid files return a 4xx response. Provider failures are surfaced as safe application errors. Consult the implementation in `src/plainspeak/api.py` for exact status codes and response details as the code is authoritative.

## Endpoints

### `POST /api/cases`

Create or load the fixed demo case (`demo-patient`). Optional JSON body:

```json
{ "reset": false }
```

Set `reset` to `true` only when you intentionally want to clear the demo case. The browser's demo startup flow resets the case on page load, so refreshes are destructive to the current demo session.

### `GET /api/cases/{case_id}`

Returns the case state and derived checklist. The demo case ID is `demo-patient`.

### `POST /api/voice/token`

Exchanges the backend-only `RESON8_API_KEY` for a short-lived browser access token. Response fields include `accessToken`, `expiresIn`, `turnsUrl`, and `realtimeUrl`. The permanent API key must never be sent to the browser.

### `POST /api/cases/{case_id}/document`

Multipart upload with a `file` field containing a text-based PDF. Stores the PDF in the local uploads directory, extracts page-labelled passages, and replaces the case's existing discharge document. Upload size is limited to 10 MiB. Scanned PDFs without extractable text are not supported because OCR is not implemented.

### `POST /api/cases/{case_id}/transcript`

JSON body with finalized transcript segments and optional speaker-role mapping. Segment fields include `id`, `sessionId`, `text`, `speakerId`, `startMs`, `durationMs`, and `recordedAt`. Role values are `clinician`, `patient`, or `unknown`. Segment IDs make retries idempotent; a saved segment is not silently overwritten. The request contract caps a batch at 100 segments.

Example:

```json
{
  "segments": [
    {
      "id": "seg_001",
      "sessionId": "session_001",
      "text": "Please bring your medication list to the follow-up.",
      "speakerId": 0,
      "startMs": 4000,
      "durationMs": 2500
    }
  ],
  "speakerRoles": { "session_001:0": "clinician" }
}
```

### `POST /api/cases/{case_id}/transcript/document`

Multipart upload with a `file` field containing a written transcript PDF. Parses speaker-labelled lines into transcript segments and replaces the existing consultation transcript. Format, speaker-count, turn-count and file-size constraints are enforced in the parser/API; see `src/plainspeak/transcript_import.py` and the README's transcript format section.

### `POST /api/cases/{case_id}/summary`

Generates a draft summary and care checklist from the current consultation and discharge document using Claude. The output is a draft, not an approved care plan. The clinician must review and edit it.

### `POST /api/cases/{case_id}/approve`

Persists a clinician-reviewed, versioned snapshot. JSON body:

```json
{
  "summary": "Reviewed plain-language summary.",
  "careTasks": [
    {
      "id": "task_001",
      "instruction": "Bring the medication list to the follow-up appointment.",
      "timing": "At the follow-up appointment",
      "responsibleParty": "caregiver",
      "sourceRefs": [
        { "sourceId": "discharge_001", "passageId": "page_1_p1" }
      ]
    }
  ],
  "approvedBy": "Demo clinician",
  "inputRevision": 1
}
```

`responsibleParty` is one of `patient`, `caregiver`, `care_team`, or `unspecified`. `inputRevision` prevents approval of a draft based on stale inputs. Approval records an evidence snapshot so later source changes do not silently rewrite the historical version. The `approvedBy` value is supplied by the client and is not verified identity.

### `POST /api/cases/{case_id}/chat`

Submits a caregiver question. The backend loads approved case context before the model call and returns a message plus a structured reply. Reply `kind` values include `answer`, `clarification`, `unresolved`, and `update_confirmation`. Replies can contain `sourceRefs`, `eventRefs`, and `pendingUpdateId`. An unresolved question is recorded for later team review; the prototype does not send a notification to a care team.

### `POST /api/cases/{case_id}/updates/{update_id}/confirm`

Explicitly confirms a pending proposed progress update. Only this application action writes the attributed progress event and changes the projected task status. The update must still refer to the current approved plan version.

### `POST /api/cases/{case_id}/updates/{update_id}/reject`

Rejects a pending progress update without changing task status.

## Core wire concepts

- **Source**: uploaded document or consultation, with a stable source ID and passages.
- **Source reference**: `{ "sourceId": "...", "passageId": "..." }` points to a specific evidence passage.
- **Care task**: instruction, optional timing, responsible party, and evidence references. Completion status is projected from progress events, not freely edited on the task.
- **Approved version**: immutable version of the reviewed summary/tasks, tied to an input revision and source snapshot.
- **Pending update**: model-proposed self-report awaiting an explicit human confirmation.
- **Progress event**: event appended after confirmation and tied to the approved summary version.

For the full Pydantic schema, inspect `src/plainspeak/contracts.py`; the generated OpenAPI schema is the definitive live contract.
