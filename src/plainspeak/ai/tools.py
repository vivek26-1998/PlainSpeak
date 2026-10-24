"""Backend tool handlers. Claude requests these; only the backend executes them."""

from typing import Any

from plainspeak.contracts import PendingUpdate, ProgressEvent, utc_now
from plainspeak.storage import CaseStore, new_id

RECENT_MESSAGES = 10


class ToolError(ValueError):
    """Invalid tool request; returned to Claude as an error tool_result."""


def get_case_context(store: CaseStore, permitted_case_id: str, case_id: str) -> dict[str, Any]:
    if case_id != permitted_case_id:
        raise ToolError(f"Case {case_id!r} is not available in this conversation.")
    case = store.load(case_id)
    approved = case.approved()
    if approved is None or not case.post_care_ready():
        raise ToolError("No clinician-approved summary exists for this case yet.")
    sources = case.approved_sources()
    return {
        "caseId": case.case_id,
        "approvedSummary": {
            "version": approved.version,
            "approvedAt": approved.approved_at,
            "summary": approved.summary,
        },
        "careTasks": [
            {**t.model_dump(by_alias=True), "status": case.task_status(t.id)}
            for t in approved.care_tasks
        ],
        "sources": [
            {
                "sourceId": s.id,
                "filename": s.filename,
                "kind": s.kind,
                "passages": [{"passageId": p.id, "text": p.text} for p in s.passages],
            }
            for s in sources
        ],
        "recentMessages": [
            {"role": m.role, "text": m.text, "createdAt": m.created_at}
            for m in case.messages[-RECENT_MESSAGES:]
        ],
        "progressEvents": [e.model_dump(by_alias=True) for e in case.progress_events],
        "pendingUpdates": [
            u.model_dump(by_alias=True) for u in case.pending_updates if u.status == "pending"
        ],
        "openQuestions": [q.question for q in case.unresolved_questions if q.status == "open"],
    }


def propose_progress_update(
    store: CaseStore,
    permitted_case_id: str,
    case_id: str,
    task_id: str,
    reported_status: str,
    note: str,
) -> dict[str, Any]:
    if case_id != permitted_case_id:
        raise ToolError(f"Case {case_id!r} is not available in this conversation.")
    if reported_status not in ("done", "in_progress", "blocked"):
        raise ToolError(f"Unsupported status {reported_status!r}.")
    with store.update(case_id) as case:
        approved = case.approved()
        if approved is None or not case.post_care_ready():
            raise ToolError("No clinician-approved summary exists for this case yet.")
        if not any(t.id == task_id for t in approved.care_tasks):
            raise ToolError(f"Task {task_id!r} is not an approved care task.")
        update = PendingUpdate(
            id=new_id("upd"),
            task_id=task_id,
            reported_status=reported_status,  # type: ignore[arg-type]
            note=note.strip()[:500],
            approved_summary_version=approved.version,
            created_at=utc_now(),
        )
        case.pending_updates.append(update)
    return {
        "pendingUpdateId": update.id,
        "taskId": task_id,
        "reportedStatus": reported_status,
        "saved": False,
        "note": "Pending caregiver confirmation in the app. Task status is unchanged.",
    }


def record_progress_update(
    store: CaseStore, case_id: str, pending_update_id: str, actor: str
) -> ProgressEvent:
    """Append an event for a pending update. Call only after explicit user confirmation.

    Actor and timestamp come from application state, not from model output.
    """
    with store.update(case_id) as case:
        update = next((u for u in case.pending_updates if u.id == pending_update_id), None)
        if update is None:
            raise ToolError("Unknown pending update.")
        if update.status != "pending":
            raise ToolError(f"Update is already {update.status}.")
        if (
            not case.post_care_ready()
            or update.approved_summary_version != case.approved_summary_version
        ):
            raise ToolError(
                "The approved plan changed. Review this update against the current plan."
            )
        now = utc_now()
        event = ProgressEvent(
            id=new_id("evt"),
            task_id=update.task_id,
            status=update.reported_status,
            note=update.note,
            actor=actor,
            timestamp=now,
            pending_update_id=update.id,
            approved_summary_version=update.approved_summary_version,
        )
        update.status = "confirmed"
        update.resolved_at = now
        case.progress_events.append(event)
        if case.workflow_state == "approved":
            case.workflow_state = "post_care_active"
    return event


def reject_progress_update(store: CaseStore, case_id: str, pending_update_id: str) -> None:
    with store.update(case_id) as case:
        update = next((u for u in case.pending_updates if u.id == pending_update_id), None)
        if update is None:
            raise ToolError("Unknown pending update.")
        if update.status != "pending":
            raise ToolError(f"Update is already {update.status}.")
        update.status = "rejected"
        update.resolved_at = utc_now()
