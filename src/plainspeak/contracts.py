"""Shared data contracts.

Field names are snake_case in Python and camelCase on the wire (JSON files and HTTP),
matching the contract agreed in the team handoff.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

WorkflowState = Literal["awaiting_review", "approved", "post_care_active"]
SpeakerRole = Literal["clinician", "patient", "unknown"]
ResponsibleParty = Literal["patient", "caregiver", "care_team", "unspecified"]
ReplyKind = Literal["answer", "clarification", "unresolved", "update_confirmation"]
ReportedStatus = Literal["done", "in_progress", "blocked"]
TaskStatus = Literal["open", "done", "in_progress", "blocked"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Contract(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SourceRef(Contract):
    source_id: str
    passage_id: str


class Passage(Contract):
    id: str
    page: int
    text: str


class Source(Contract):
    id: str
    filename: str
    uploaded_at: str
    passages: list[Passage]
    kind: Literal["document", "consultation"] = "document"


class TranscriptSegment(Contract):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    session_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")
    text: str = Field(min_length=1, max_length=10000)
    speaker_id: int | None = Field(default=None, ge=0, le=7)
    start_ms: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    recorded_at: str = Field(default_factory=utc_now)

    def speaker_key(self) -> str:
        speaker = self.speaker_id if self.speaker_id is not None else "unknown"
        return f"{self.session_id}:{speaker}"


class TranscriptRequest(Contract):
    segments: list[TranscriptSegment] = Field(default_factory=list, max_length=100)
    speaker_roles: dict[str, SpeakerRole] = Field(default_factory=dict, max_length=100)


class CareTask(Contract):
    id: str
    instruction: str
    timing: str | None = None
    responsible_party: ResponsibleParty = "unspecified"
    source_refs: list[SourceRef] = Field(default_factory=list)


class DraftSummary(Contract):
    summary: str
    care_tasks: list[CareTask]
    missing_information: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    input_revision: int = 0


class SummaryVersion(Contract):
    """Immutable approved snapshot. Never overwritten once saved."""

    version: int
    summary: str
    care_tasks: list[CareTask]
    source_ids: list[str]
    approved_by: str
    approved_at: str
    input_revision: int = 0
    sources_snapshot: list[Source] = Field(default_factory=list)


class AgentReply(Contract):
    kind: ReplyKind
    text: str
    source_refs: list[SourceRef] = Field(default_factory=list)
    event_refs: list[str] = Field(default_factory=list)
    pending_update_id: str | None = None


class Message(Contract):
    id: str
    role: Literal["caregiver", "assistant"]
    text: str
    created_at: str
    reply: AgentReply | None = None


class PendingUpdate(Contract):
    id: str
    task_id: str
    reported_status: ReportedStatus
    note: str
    status: Literal["pending", "confirmed", "rejected"] = "pending"
    approved_summary_version: int
    created_at: str
    resolved_at: str | None = None


class ProgressEvent(Contract):
    id: str
    task_id: str
    status: ReportedStatus
    note: str
    actor: str
    timestamp: str
    pending_update_id: str
    approved_summary_version: int


class UnresolvedQuestion(Contract):
    id: str
    question: str
    message_id: str
    created_at: str
    status: Literal["open", "answered"] = "open"


class Case(Contract):
    case_id: str
    patient_name: str | None = None  # read from the discharge document on upload
    workflow_state: WorkflowState = "awaiting_review"
    sources: list[Source] = Field(default_factory=list)
    draft_summary: DraftSummary | None = None
    summary_versions: list[SummaryVersion] = Field(default_factory=list)
    approved_summary_version: int | None = None
    care_tasks: list[CareTask] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    pending_updates: list[PendingUpdate] = Field(default_factory=list)
    progress_events: list[ProgressEvent] = Field(default_factory=list)
    unresolved_questions: list[UnresolvedQuestion] = Field(default_factory=list)
    transcript_segments: list[TranscriptSegment] = Field(default_factory=list)
    speaker_roles: dict[str, str] = Field(default_factory=dict)
    input_revision: int = 0

    def approved_sources(self) -> list[Source]:
        approved = self.approved()
        if approved is None:
            return []
        return approved.sources_snapshot or [
            source for source in self.sources if source.id in approved.source_ids
        ]

    def post_care_ready(self) -> bool:
        approved = self.approved()
        return bool(
            approved
            and self.workflow_state in ("approved", "post_care_active")
            and approved.input_revision == self.input_revision
        )

    def approved(self) -> SummaryVersion | None:
        if self.approved_summary_version is None:
            return None
        return next(
            (v for v in self.summary_versions if v.version == self.approved_summary_version), None
        )

    def passage_index(self) -> set[tuple[str, str]]:
        return {(s.id, p.id) for s in self.sources for p in s.passages}

    def task_status(self, task_id: str) -> TaskStatus:
        """Project task status from saved events; the latest event wins."""
        status: TaskStatus = "open"
        for event in self.progress_events:
            if (
                event.task_id == task_id
                and event.approved_summary_version == self.approved_summary_version
            ):
                status = event.status
        return status


# --- HTTP request/response bodies ---


class CreateCaseRequest(Contract):
    reset: bool = False


class ApproveTask(Contract):
    id: str | None = None
    instruction: str
    timing: str | None = None
    responsible_party: ResponsibleParty = "unspecified"
    source_refs: list[SourceRef] = Field(default_factory=list)


class ApproveRequest(Contract):
    summary: str
    care_tasks: list[ApproveTask]
    approved_by: str = "Demo clinician"
    input_revision: int | None = None


class ChatRequest(Contract):
    text: str


class ChatResponse(Contract):
    message: Message
    reply: Message


class TaskView(CareTask):
    status: TaskStatus
    last_event: ProgressEvent | None = None


class CaseView(Contract):
    """Case plus projected checklist, returned to the frontend."""

    case: Case
    checklist: list[TaskView]
