from fastapi.testclient import TestClient

from tests.conftest import FIXTURE_PDF, FakeLLM, text_response, tool_response
from tests.test_flow import CASE, REF_BRING, reply, setup_approved

SEGMENT = {
    "id": "seg-clinician-001",
    "sessionId": "consult-001",
    "speakerId": 0,
    "text": "Bring your medication list to the follow-up.",
    "startMs": 1200,
    "durationMs": 2500,
}
PATIENT = {
    "id": "seg-patient-001",
    "sessionId": "consult-001",
    "speakerId": 1,
    "text": "I thought I only needed to bring my ID card.",
    "startMs": 4000,
    "durationMs": 3000,
}


def capture(client: TestClient) -> dict:
    client.post("/api/cases", json={"reset": True})
    result = client.post(
        f"{CASE}/transcript",
        json={
            "segments": [SEGMENT, PATIENT],
            "speakerRoles": {"consult-001:0": "clinician", "consult-001:1": "patient"},
        },
    )
    assert result.status_code == 200, result.text
    return result.json()


def test_transcript_persists_with_speakers_timestamps_and_idempotent_retries(client: TestClient):
    capture(client)
    view = client.get(CASE).json()
    segments = view["case"]["transcriptSegments"]
    assert len(segments) == 2
    assert segments[0]["startMs"] == 1200
    source = view["case"]["sources"][0]
    assert source["kind"] == "consultation"
    assert source["passages"][0]["id"] == SEGMENT["id"]
    assert "[clinician at 1200ms]" in source["passages"][0]["text"]
    revision = view["case"]["inputRevision"]
    retry = client.post(f"{CASE}/transcript", json={"segments": [SEGMENT]}).json()
    assert len(retry["case"]["transcriptSegments"]) == 2
    assert retry["case"]["inputRevision"] == revision
    conflict = client.post(
        f"{CASE}/transcript",
        json={
            "segments": [{**SEGMENT, "text": "Silently change the original statement"}],
        },
    )
    assert conflict.status_code == 409
    assert client.get(CASE).json()["case"]["transcriptSegments"][0]["text"] == SEGMENT["text"]


def test_combined_summary_and_caregiver_context_include_consultation(
    client: TestClient,
    llm: FakeLLM,
):
    capture(client)
    with FIXTURE_PDF.open("rb") as stream:
        uploaded = client.post(f"{CASE}/document", files={"file": ("discharge.pdf", stream)})
    assert uploaded.status_code == 200
    refs = [
        {"sourceId": "consultation_001", "passageId": SEGMENT["id"]},
        REF_BRING,
    ]
    llm.queue(
        text_response(
            {
                "summary": "Bring the medication list to the follow-up.",
                "careTasks": [
                    {
                        "instruction": "Bring the medication list",
                        "timing": "At follow-up",
                        "responsibleParty": "patient",
                        "sourceRefs": refs,
                    }
                ],
                "missingInformation": [
                    "Patient thought only ID was needed; clinician should clarify."
                ],
            }
        )
    )
    result = client.post(f"{CASE}/summary")
    assert result.status_code == 200, result.text
    prompt = llm.calls[-1]["messages"][0]["content"]
    assert 'kind="consultation"' in prompt
    assert 'kind="document"' in prompt
    assert SEGMENT["text"] in prompt
    assert PATIENT["text"] in prompt
    draft = result.json()["case"]["draftSummary"]
    result = client.post(
        f"{CASE}/approve",
        json={
            "summary": draft["summary"],
            "careTasks": draft["careTasks"],
            "inputRevision": draft["inputRevision"],
        },
    )
    assert result.status_code == 200
    approved = result.json()["case"]["summaryVersions"][0]
    assert len(approved["sourcesSnapshot"]) == 2
    llm.queue(text_response(reply("answer", "Bring the medication list.", refs=refs)))
    result = client.post(f"{CASE}/chat", json={"text": "What did the clinician say to bring?"})
    assert result.status_code == 200
    # Context is loaded even if the model omits its own context tool call.
    assert SEGMENT["text"] in llm.calls[-1]["messages"][0]["content"]
    assert result.json()["reply"]["reply"]["sourceRefs"] == refs


def test_new_transcript_invalidates_review_and_preserves_approved_evidence(
    client: TestClient,
    llm: FakeLLM,
):
    setup_approved(client, llm)
    original = client.get(CASE).json()["case"]["summaryVersions"][0]
    result = client.post(f"{CASE}/transcript", json={"segments": [SEGMENT]})
    case = result.json()["case"]
    assert case["workflowState"] == "awaiting_review"
    assert case["draftSummary"] is None
    assert case["summaryVersions"][0] == original
    assert client.post(f"{CASE}/chat", json={"text": "What next?"}).status_code == 409
    stale = client.post(
        f"{CASE}/approve",
        json={
            "summary": original["summary"],
            "careTasks": original["careTasks"],
            "inputRevision": original["inputRevision"],
        },
    )
    assert stale.status_code == 409


def test_speaker_mapping_change_invalidates_existing_draft(client: TestClient, llm: FakeLLM):
    capture(client)
    llm.queue(
        text_response(
            {"summary": "Review this conversation.", "careTasks": [], "missingInformation": []}
        )
    )
    assert client.post(f"{CASE}/summary").status_code == 200
    revision = client.get(CASE).json()["case"]["inputRevision"]
    result = client.post(
        f"{CASE}/transcript",
        json={
            "speakerRoles": {"consult-001:0": "patient"},
        },
    ).json()["case"]
    assert result["draftSummary"] is None
    assert result["inputRevision"] == revision + 1
    assert "[patient" in result["sources"][0]["passages"][0]["text"]


def test_unsupported_answer_is_replaced_not_only_relabelled(client: TestClient, llm: FakeLLM):
    setup_approved(client, llm)
    unsupported = "Invented instruction that must not reach the caregiver."
    llm.queue(text_response(reply("answer", unsupported)))
    result = client.post(f"{CASE}/chat", json={"text": "An unsupported question"})
    answer = result.json()["reply"]["reply"]
    assert answer["kind"] == "unresolved"
    assert unsupported not in answer["text"]


def test_progress_and_pending_updates_do_not_apply_to_a_new_approved_plan(
    client: TestClient,
    llm: FakeLLM,
):
    view = setup_approved(client, llm)
    task = view["checklist"][0]
    for _ in range(2):
        llm.queue(
            tool_response(
                "propose_progress_update",
                {
                    "case_id": "demo-patient",
                    "task_id": task["id"],
                    "reported_status": "done",
                    "note": "Reported done",
                },
            ),
            text_response(reply("update_confirmation", "Confirm?")),
        )
        result = client.post(f"{CASE}/chat", json={"text": "Done"})
        pending = result.json()["reply"]["reply"]["pendingUpdateId"]
        if not client.get(CASE).json()["case"]["progressEvents"]:
            assert client.post(f"{CASE}/updates/{pending}/confirm").status_code == 200
    revised = client.post(
        f"{CASE}/approve",
        json={
            "summary": "Revised approved plan",
            "careTasks": [
                {
                    **task,
                    "instruction": "A newly reviewed task",
                }
            ],
        },
    )
    assert revised.status_code == 200
    assert revised.json()["checklist"][0]["status"] == "open"
    assert revised.json()["checklist"][0]["lastEvent"] is None
    assert client.post(f"{CASE}/updates/{pending}/confirm").status_code == 409
