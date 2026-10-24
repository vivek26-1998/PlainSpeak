"""Draft summary and source-linked checklist generation."""

import logging

from pydantic import ValidationError

from plainspeak.ai.client import LLM, AIError, parse_json_output
from plainspeak.ai.prompts import SUMMARY_SCHEMA, SUMMARY_SYSTEM
from plainspeak.contracts import CareTask, Case, DraftSummary, SourceRef

log = logging.getLogger(__name__)


def _documents_prompt(case: Case) -> str:
    parts = []
    for source in case.sources:
        lines = [
            f'<document sourceId="{source.id}" kind="{source.kind}" filename="{source.filename}">'
        ]
        lines += [f'<passage passageId="{p.id}">{p.text}</passage>' for p in source.passages]
        lines.append("</document>")
        parts.append("\n".join(lines))
    return (
        "\n\n".join(parts)
        + "\n\nDraft the plain-language summary and source-linked care checklist."
    )


def generate_draft(llm: LLM, case: Case) -> DraftSummary:
    if not case.sources:
        raise AIError("Capture a consultation or upload a discharge document first.")
    response = llm.create(
        system=SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": _documents_prompt(case)}],
        output_schema=SUMMARY_SCHEMA,
    )
    data = parse_json_output(response)
    known = case.passage_index()
    try:
        tasks = []
        for index, raw in enumerate(data["careTasks"], start=1):
            refs = [SourceRef.model_validate(r) for r in raw["sourceRefs"]]
            valid = [r for r in refs if (r.source_id, r.passage_id) in known]
            if len(valid) != len(refs):
                log.warning(
                    "Dropped %d unknown source ref(s) in draft task", len(refs) - len(valid)
                )
            tasks.append(
                CareTask(
                    id=f"task_{index:03d}",
                    instruction=raw["instruction"],
                    timing=raw["timing"],
                    responsible_party=raw["responsibleParty"],
                    source_refs=valid,
                )
            )
        return DraftSummary(
            summary=data["summary"],
            care_tasks=tasks,
            missing_information=data["missingInformation"],
            source_ids=[s.id for s in case.sources],
            input_revision=case.input_revision,
        )
    except (KeyError, TypeError, ValidationError) as e:
        raise AIError("Claude's draft did not match the expected format.") from e
