from fastapi.testclient import TestClient

from plainspeak.pdf_extract import extract_passages
from tests.conftest import FIXTURE_PDF, FakeLLM, text_response, tool_response

CASE = "/api/cases/demo-patient"
REF_FOLLOW_UP = {"sourceId": "discharge_001", "passageId": "page_1_p3"}
REF_BRING = {"sourceId": "discharge_001", "passageId": "page_1_p4"}
REF_TRANSPORT = {"sourceId": "discharge_001", "passageId": "page_1_p5"}

DRAFT = {
    "summary": "Follow-up on 9 November 2026. Bring the medication list. Arrange transport.",
    "careTasks": [
        {
            "instruction": "Bring the medication list, discharge letter and ID card",
            "timing": "At the follow-up appointment",
            "responsibleParty": "caregiver",
            "sourceRefs": [REF_BRING],
        },
        {
            "instruction": "Arrange transport to and from the clinic",
            "timing": "Before the appointment day",
            "responsibleParty": "caregiver",
            "sourceRefs": [REF_TRANSPORT, {"sourceId": "discharge_001", "passageId": "page_9_p9"}],
        },
    ],
    "missingInformation": ["Whether the patient may shower is not stated."],
}


def reply(kind: str, text: str, refs=(), events=(), pending=None) -> dict:
    return {
        "kind": kind,
        "text": text,
        "sourceRefs": list(refs),
        "eventRefs": list(events),
        "pendingUpdateId": pending,
    }


def setup_approved(client: TestClient, llm: FakeLLM) -> dict:
    assert client.post("/api/cases", json={"reset": True}).status_code == 200
    with FIXTURE_PDF.open("rb") as f:
        r = client.post(f"{CASE}/document", files={"file": ("discharge.pdf", f, "application/pdf")})
    assert r.status_code == 200, r.text

    llm.queue(text_response(DRAFT))
    r = client.post(f"{CASE}/summary")
    assert r.status_code == 200, r.text
    draft = r.json()["case"]["draftSummary"]
    # Unknown passage reference from the model is dropped by validation.
    assert draft["careTasks"][1]["sourceRefs"] == [REF_TRANSPORT]

    r = client.post(
        f"{CASE}/approve",
        json={
            "summary": draft["summary"],
            "careTasks": draft["careTasks"],
            "approvedBy": "Dr. Test",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_fixture_extracts_stable_passages():
    passages = extract_passages(FIXTURE_PDF)
    assert [p.id for p in passages[:5]] == [f"page_1_p{i}" for i in range(1, 6)]
    assert "Follow-up appointment" in passages[2].text
    assert "Transport" in passages[4].text


def test_chat_blocked_before_approval(client: TestClient):
    client.post("/api/cases", json={"reset": True})
    r = client.post(f"{CASE}/chat", json={"text": "What should I bring?"})
    assert r.status_code == 409


def test_grounded_answer(client: TestClient, llm: FakeLLM):
    setup_approved(client, llm)
    llm.queue(
        tool_response("get_case_context", {"case_id": "demo-patient"}),
        text_response(
            reply(
                "answer",
                "Bring the medication list and arrange transport.",
                refs=[REF_BRING, REF_TRANSPORT],
            )
        ),
    )
    r = client.post(f"{CASE}/chat", json={"text": "What should I arrange before the follow-up?"})
    assert r.status_code == 200, r.text
    answer = r.json()["reply"]["reply"]
    assert answer["kind"] == "answer"
    assert answer["sourceRefs"] == [REF_BRING, REF_TRANSPORT]

    # The tool result returned the approved context to Claude.
    tool_result = llm.calls[-1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is False
    assert "page_1_p5" in tool_result["content"]


def test_answer_without_valid_evidence_becomes_unresolved(client: TestClient, llm: FakeLLM):
    setup_approved(client, llm)
    llm.queue(
        text_response(
            reply(
                "answer",
                "Yes, showering is fine.",
                refs=[{"sourceId": "discharge_001", "passageId": "made_up"}],
            )
        )
    )
    r = client.post(f"{CASE}/chat", json={"text": "Can he take a shower?"})
    body = r.json()
    assert body["reply"]["reply"]["kind"] == "unresolved"
    case = client.get(CASE).json()["case"]
    assert [q["question"] for q in case["unresolvedQuestions"]] == ["Can he take a shower?"]


def test_wrong_case_id_in_tool_is_rejected(client: TestClient, llm: FakeLLM):
    setup_approved(client, llm)
    llm.queue(
        tool_response("get_case_context", {"case_id": "someone-else"}),
        text_response(reply("unresolved", "I can't access that.")),
    )
    client.post(f"{CASE}/chat", json={"text": "hello"})
    tool_result = llm.calls[-1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True


def test_progress_update_requires_confirmation(client: TestClient, llm: FakeLLM):
    view = setup_approved(client, llm)
    transport = next(t for t in view["checklist"] if "transport" in t["instruction"].lower())

    llm.queue(
        tool_response(
            "propose_progress_update",
            {
                "case_id": "demo-patient",
                "task_id": transport["id"],
                "reported_status": "done",
                "note": "Transport is arranged.",
            },
        ),
        text_response(reply("update_confirmation", "Shall I mark transport as arranged?")),
    )
    r = client.post(f"{CASE}/chat", json={"text": "Transport is arranged."})
    answer = r.json()["reply"]["reply"]
    assert answer["kind"] == "update_confirmation"
    update_id = answer["pendingUpdateId"]
    assert update_id

    # No status change before confirmation.
    view = client.get(CASE).json()
    assert next(t for t in view["checklist"] if t["id"] == transport["id"])["status"] == "open"
    assert view["case"]["progressEvents"] == []

    r = client.post(f"{CASE}/updates/{update_id}/confirm")
    assert r.status_code == 200
    # Reload from disk: saved event and checklist agree.
    view = client.get(CASE).json()
    task = next(t for t in view["checklist"] if t["id"] == transport["id"])
    assert task["status"] == "done"
    event = view["case"]["progressEvents"][0]
    assert event["actor"] == "caregiver (demo role)"
    assert task["lastEvent"]["id"] == event["id"]

    # Confirming twice is rejected.
    assert client.post(f"{CASE}/updates/{update_id}/confirm").status_code == 409


def test_new_upload_keeps_previous_approval(client: TestClient, llm: FakeLLM):
    setup_approved(client, llm)
    with FIXTURE_PDF.open("rb") as f:
        client.post(f"{CASE}/document", files={"file": ("v2.pdf", f, "application/pdf")})
    case = client.get(CASE).json()["case"]
    assert case["workflowState"] == "awaiting_review"
    assert case["approvedSummaryVersion"] == 1
    assert len(case["summaryVersions"]) == 1


def test_approve_rejects_unknown_reference(client: TestClient, llm: FakeLLM):
    setup_approved(client, llm)
    r = client.post(
        f"{CASE}/approve",
        json={
            "summary": "x",
            "careTasks": [
                {
                    "instruction": "y",
                    "sourceRefs": [{"sourceId": "discharge_001", "passageId": "nope"}],
                }
            ],
        },
    )
    assert r.status_code == 422
