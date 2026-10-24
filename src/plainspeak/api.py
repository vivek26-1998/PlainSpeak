"""HTTP JSON API. The backend owns workflow state, validation and all writes."""

import hashlib
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from plainspeak import voice
from plainspeak.ai import tools
from plainspeak.ai.agent import run_chat
from plainspeak.ai.client import LLM, AIError
from plainspeak.ai.summary import generate_draft
from plainspeak.config import Settings, get_settings
from plainspeak.contracts import (
    ApproveRequest,
    CareTask,
    Case,
    CaseView,
    ChatRequest,
    ChatResponse,
    CreateCaseRequest,
    Message,
    Passage,
    Source,
    SpeakerRole,
    SummaryVersion,
    TaskView,
    TranscriptRequest,
    TranscriptSegment,
    UnresolvedQuestion,
    utc_now,
)
from plainspeak.pdf_extract import NoTextError, extract_lines, extract_passages
from plainspeak.storage import CaseNotFoundError, CaseStore, new_id
from plainspeak.transcript_import import TranscriptFormatError, parse_transcript

DEMO_CASE_ID = "demo-patient"
DOCUMENT_SOURCE_ID = "discharge_001"
CAREGIVER_ACTOR = "caregiver (demo role)"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_TASK_ID = re.compile(r"^task_\d{3}$")

router = APIRouter(prefix="/api")


def get_store(request: Request) -> CaseStore:
    return request.app.state.store


def get_llm(request: Request) -> LLM:
    return request.app.state.llm


Store = Annotated[CaseStore, Depends(get_store)]
Claude = Annotated[LLM, Depends(get_llm)]


def _load(store: CaseStore, case_id: str) -> Case:
    try:
        return store.load(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(404, "Case not found.") from e


def _view(case: Case) -> CaseView:
    tasks = []
    for task in case.care_tasks:
        events = [
            e
            for e in case.progress_events
            if e.task_id == task.id and e.approved_summary_version == case.approved_summary_version
        ]
        tasks.append(
            TaskView(
                **task.model_dump(),
                status=case.task_status(task.id),
                last_event=events[-1] if events else None,
            )
        )
    return CaseView(case=case, checklist=tasks)


@router.post("/cases")
def create_case(store: Store, body: CreateCaseRequest | None = None) -> CaseView:
    reset = body.reset if body else False
    return _view(store.create(DEMO_CASE_ID, reset=reset))


@router.get("/cases/{case_id}")
def get_case(case_id: str, store: Store) -> CaseView:
    return _view(_load(store, case_id))


@router.post("/voice/token")
def voice_token(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    try:
        return voice.request_token(settings.reson8_api_key)
    except voice.VoiceError as e:
        raise HTTPException(503, str(e)) from e


def _read_pdf_upload(file: UploadFile) -> bytes:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "PDF is larger than 10 MB.")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Upload a text-based PDF file.")
    return data


@router.post("/cases/{case_id}/document")
def upload_document(case_id: str, file: UploadFile, store: Store) -> CaseView:
    """Replace the case's discharge document. One case describes one patient."""
    _load(store, case_id)
    data = _read_pdf_upload(file)
    filename = (file.filename or "document.pdf")[:120]
    path = store.upload_path(case_id, DOCUMENT_SOURCE_ID)
    path.write_bytes(data)
    try:
        passages = extract_passages(path)
    except NoTextError as e:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(e)) from e

    with store.update(case_id) as case:
        current = next((s for s in case.sources if s.kind == "document"), None)
        if current and current.filename == filename and current.passages == passages:
            return _view(case)  # same document again; leave the draft and revision alone
        for stale in (s for s in case.sources if s.kind == "document"):
            if stale.id != DOCUMENT_SOURCE_ID:
                store.upload_path(case_id, stale.id).unlink(missing_ok=True)
        case.sources = [s for s in case.sources if s.kind != "document"] + [
            Source(
                id=DOCUMENT_SOURCE_ID,
                filename=filename,
                uploaded_at=utc_now(),
                passages=passages,
            )
        ]
        # A new source invalidates the current draft and requires another review.
        case.draft_summary = None
        case.workflow_state = "awaiting_review"
        case.input_revision += 1
    return _view(case)


def _apply_transcript(
    store: CaseStore,
    case_id: str,
    segments: list[TranscriptSegment],
    speaker_roles: dict[str, SpeakerRole],
    *,
    replace: bool = False,
) -> Case:
    """Append final consultation segments; retries cannot duplicate or silently edit them."""
    with store.update(case_id) as case:
        changed = False
        if replace and {s.id for s in case.transcript_segments} != {s.id for s in segments}:
            # An imported transcript becomes the whole consultation record for the case.
            case.transcript_segments = []
            case.speaker_roles = {}
            changed = True
        existing = {segment.id: segment for segment in case.transcript_segments}
        for segment in segments:
            if not segment.text.strip():
                raise HTTPException(422, "Transcript text must not be empty.")
            previous = existing.get(segment.id)
            if previous:
                fields = {"recorded_at"}
                if previous.model_dump(exclude=fields) != segment.model_dump(exclude=fields):
                    raise HTTPException(409, "A saved segment cannot be overwritten.")
                continue
            saved = segment.model_copy(update={"recorded_at": utc_now()})
            case.transcript_segments.append(saved)
            existing[saved.id] = saved
            changed = True
        known_speakers = {segment.speaker_key() for segment in case.transcript_segments}
        for key, role in speaker_roles.items():
            if key not in known_speakers:
                raise HTTPException(422, "Speaker mapping must reference a saved speaker.")
            if case.speaker_roles.get(key, "unknown") != role:
                case.speaker_roles[key] = role
                changed = True
        if changed:
            passages = []
            for segment in case.transcript_segments:
                role = case.speaker_roles.get(segment.speaker_key(), "unknown")
                label = (
                    role if role != "unknown" else f"unconfirmed speaker {segment.speaker_key()}"
                )
                offset = f" at {segment.start_ms}ms" if segment.start_ms is not None else ""
                passages.append(
                    Passage(
                        id=segment.id,
                        page=0,
                        text=f"[{label}{offset}] {segment.text.strip()}",
                    )
                )
            source = Source(
                id="consultation_001",
                filename="Consultation transcript",
                kind="consultation",
                uploaded_at=utc_now(),
                passages=passages,
            )
            case.sources = [s for s in case.sources if s.id != source.id] + [source]
            case.input_revision += 1
            case.draft_summary = None
            case.workflow_state = "awaiting_review"
    return case


@router.post("/cases/{case_id}/transcript")
def save_transcript(case_id: str, body: TranscriptRequest, store: Store) -> CaseView:
    _load(store, case_id)
    return _view(_apply_transcript(store, case_id, body.segments, body.speaker_roles))


@router.post("/cases/{case_id}/transcript/document")
def upload_transcript(case_id: str, file: UploadFile, store: Store) -> CaseView:
    """Import a written transcript PDF as consultation segments, same as live capture."""
    case = _load(store, case_id)
    data = _read_pdf_upload(file)
    # Content-addressed ids make re-uploading the same file a no-op rather than a duplicate.
    digest = hashlib.sha256(data).hexdigest()[:16]
    session_id = f"pdf_{digest}"
    path = store.upload_path(case_id, f"transcript_{digest}")
    path.write_bytes(data)
    try:
        segments, roles = parse_transcript(extract_lines(path), session_id)
    except (NoTextError, TranscriptFormatError) as e:
        path.unlink(missing_ok=True)
        raise HTTPException(422, str(e)) from e
    # A role the clinician already confirmed outranks the label written in the file. Keys are
    # derived from the file digest, so only a re-upload of the same file can match here.
    roles = {k: v for k, v in roles.items() if case.speaker_roles.get(k, "unknown") == "unknown"}
    return _view(_apply_transcript(store, case_id, segments, roles, replace=True))


@router.post("/cases/{case_id}/summary")
def create_summary(case_id: str, store: Store, llm: Claude) -> CaseView:
    case = _load(store, case_id)
    try:
        draft = generate_draft(llm, case)
    except AIError as e:
        raise HTTPException(502, str(e)) from e
    with store.update(case_id) as case:
        if case.input_revision != draft.input_revision:
            raise HTTPException(409, "Sources changed while drafting. Generate again.")
        case.draft_summary = draft
        case.workflow_state = "awaiting_review"
    return _view(case)


@router.post("/cases/{case_id}/approve")
def approve(case_id: str, body: ApproveRequest, store: Store) -> CaseView:
    if not body.summary.strip():
        raise HTTPException(422, "Summary must not be empty.")
    if not body.care_tasks:
        raise HTTPException(422, "Approve at least one care task.")
    _load(store, case_id)
    with store.update(case_id) as case:
        if not case.sources:
            raise HTTPException(409, "Capture a consultation or upload a document first.")
        if body.input_revision is not None and body.input_revision != case.input_revision:
            raise HTTPException(409, "Inputs changed. Generate and review a fresh draft.")
        known = case.passage_index()
        used_ids = {t.id for t in body.care_tasks if t.id and _TASK_ID.match(t.id)}
        next_number = 1
        seen: set[str] = set()
        tasks: list[CareTask] = []
        for task in body.care_tasks:
            if not task.instruction.strip():
                raise HTTPException(422, "Care task instructions must not be empty.")
            bad = [r for r in task.source_refs if (r.source_id, r.passage_id) not in known]
            if bad:
                raise HTTPException(422, f"Unknown source reference {bad[0].passage_id!r}.")
            task_id = task.id if task.id and _TASK_ID.match(task.id) else None
            if task_id is None or task_id in seen:
                while f"task_{next_number:03d}" in used_ids | seen:
                    next_number += 1
                task_id = f"task_{next_number:03d}"
            seen.add(task_id)
            tasks.append(CareTask(**task.model_dump(exclude={"id"}), id=task_id))

        version = SummaryVersion(
            version=len(case.summary_versions) + 1,
            summary=body.summary.strip(),
            care_tasks=tasks,
            source_ids=[s.id for s in case.sources],
            approved_by=body.approved_by.strip()[:80] or "Demo clinician",
            approved_at=utc_now(),
            input_revision=case.input_revision,
            sources_snapshot=[source.model_copy(deep=True) for source in case.sources],
        )
        case.summary_versions.append(version)  # previous snapshots are preserved
        case.approved_summary_version = version.version
        case.care_tasks = tasks
        case.draft_summary = None
        case.workflow_state = "approved"
    return _view(case)


@router.post("/cases/{case_id}/chat")
def chat(case_id: str, body: ChatRequest, store: Store, llm: Claude) -> ChatResponse:
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "Message must not be empty.")
    if len(text) > 2000:
        raise HTTPException(422, "Message is too long.")
    case = _load(store, case_id)
    if not case.post_care_ready():
        raise HTTPException(409, "Post-care questions open once a clinician approves the summary.")

    question = Message(id=new_id("msg"), role="caregiver", text=text, created_at=utc_now())
    with store.update(case_id) as case:
        case.messages.append(question)

    try:
        reply = run_chat(llm, store, case_id, text)
    except AIError as e:
        raise HTTPException(502, str(e)) from e

    answer = Message(
        id=new_id("msg"), role="assistant", text=reply.text, created_at=utc_now(), reply=reply
    )
    with store.update(case_id) as case:
        case.messages.append(answer)
        if reply.kind == "unresolved":
            case.unresolved_questions.append(
                UnresolvedQuestion(
                    id=new_id("q"), question=text, message_id=question.id, created_at=utc_now()
                )
            )
        if case.workflow_state == "approved":
            case.workflow_state = "post_care_active"
    return ChatResponse(message=question, reply=answer)


@router.post("/cases/{case_id}/updates/{update_id}/confirm")
def confirm_update(case_id: str, update_id: str, store: Store) -> CaseView:
    _load(store, case_id)
    try:
        tools.record_progress_update(store, case_id, update_id, actor=CAREGIVER_ACTOR)
    except tools.ToolError as e:
        raise HTTPException(409, str(e)) from e
    return _view(store.load(case_id))


@router.post("/cases/{case_id}/updates/{update_id}/reject")
def reject_update(case_id: str, update_id: str, store: Store) -> CaseView:
    _load(store, case_id)
    try:
        tools.reject_progress_update(store, case_id, update_id)
    except tools.ToolError as e:
        raise HTTPException(409, str(e)) from e
    return _view(store.load(case_id))
