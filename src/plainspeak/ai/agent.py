"""Post-care agent loop: question in, validated AgentReply out."""

import json
import logging
from typing import Any

from pydantic import ValidationError

from plainspeak.ai import tools
from plainspeak.ai.client import LLM, AIError, parse_json_output
from plainspeak.ai.prompts import AGENT_REPLY_SCHEMA, CHAT_SYSTEM, TOOLS
from plainspeak.contracts import AgentReply, Case
from plainspeak.storage import CaseStore

log = logging.getLogger(__name__)

MAX_TURNS = 6


def run_chat(llm: LLM, store: CaseStore, case_id: str, question: str) -> AgentReply:
    try:
        context = tools.get_case_context(store, case_id, case_id)
    except tools.ToolError as e:
        raise AIError(str(e)) from e
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                f"Case ID: {case_id}\n\n<case_context>\n{json.dumps(context)}\n</case_context>"
                f"\n\n<caregiver_transcript>\n{question}\n</caregiver_transcript>"
            ),
        }
    ]
    proposed_update_ids: list[str] = []

    for _ in range(MAX_TURNS):
        response = llm.create(
            system=CHAT_SYSTEM, messages=messages, output_schema=AGENT_REPLY_SCHEMA, tools=TOOLS
        )
        if response.stop_reason != "tool_use":
            data = parse_json_output(response)
            try:
                reply = AgentReply.model_validate(data)
            except ValidationError as e:
                raise AIError("Claude's reply did not match the expected format.") from e
            return validate_reply(reply, store.load(case_id), proposed_update_ids)

        # Append the full assistant content unchanged, then all tool results in one message.
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = _execute(store, case_id, block.name, block.input)
            if "pendingUpdateId" in result.get("content", {}):
                proposed_update_ids.append(result["content"]["pendingUpdateId"])
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result["content"]),
                    "is_error": result["is_error"],
                }
            )
        messages.append({"role": "user", "content": results})

    raise AIError("The assistant did not finish within the allowed number of steps.")


def _execute(store: CaseStore, case_id: str, name: str, args: Any) -> dict[str, Any]:
    try:
        if not isinstance(args, dict):
            raise tools.ToolError("Tool input must be an object.")
        if name == "get_case_context":
            content = tools.get_case_context(store, case_id, str(args.get("case_id", "")))
        elif name == "propose_progress_update":
            content = tools.propose_progress_update(
                store,
                case_id,
                str(args.get("case_id", "")),
                str(args.get("task_id", "")),
                str(args.get("reported_status", "")),
                str(args.get("note", "")),
            )
        else:
            raise tools.ToolError(f"Unknown tool {name!r}.")
        log.info("tool %s ok", name)
        return {"content": content, "is_error": False}
    except tools.ToolError as e:
        log.info("tool %s rejected: %s", name, e)
        return {"content": {"error": str(e)}, "is_error": True}


def validate_reply(reply: AgentReply, case: Case, proposed_update_ids: list[str]) -> AgentReply:
    """Keep only references the backend can verify; downgrade unsupported answers."""
    known_passages = {
        (source.id, passage.id) for source in case.approved_sources() for passage in source.passages
    }
    source_refs = [r for r in reply.source_refs if (r.source_id, r.passage_id) in known_passages]
    event_ids = {
        e.id
        for e in case.progress_events
        if e.approved_summary_version == case.approved_summary_version
    }
    event_refs = [e for e in reply.event_refs if e in event_ids]
    dropped = len(reply.source_refs) - len(source_refs) + len(reply.event_refs) - len(event_refs)
    if dropped:
        log.warning("Dropped %d unverifiable reference(s) from agent reply", dropped)

    kind = reply.kind
    pending_id = reply.pending_update_id
    if pending_id not in proposed_update_ids:
        pending_id = proposed_update_ids[-1] if proposed_update_ids else None
    if pending_id:
        kind = "update_confirmation"
    elif kind == "update_confirmation":
        kind = "clarification"
    text = reply.text
    if kind == "answer" and (dropped or (not source_refs and not event_refs)):
        log.warning("Answer had no verifiable evidence; marking unresolved")
        kind = "unresolved"
        text = (
            "I could not verify an answer against the approved plan. "
            "Please ask the care team to clarify; I have recorded your question."
        )

    return AgentReply(
        kind=kind,
        text=text,
        source_refs=source_refs,
        event_refs=event_refs,
        pending_update_id=pending_id,
    )
