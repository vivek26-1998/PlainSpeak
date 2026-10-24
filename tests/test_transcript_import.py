import pytest
from fastapi.testclient import TestClient

from plainspeak.transcript_import import TranscriptFormatError, parse_transcript
from tests.conftest import FIXTURE_PDF, TRANSCRIPT_PDF, pdf_with
from tests.test_flow import CASE


def upload(client: TestClient, path=TRANSCRIPT_PDF, name="consultation-transcript.pdf"):
    with path.open("rb") as stream:
        return client.post(f"{CASE}/transcript/document", files={"file": (name, stream)})


def test_upload_imports_turns_with_speakers_timestamps_and_inferred_roles(client: TestClient):
    client.post("/api/cases", json={"reset": True})
    result = upload(client)
    assert result.status_code == 200, result.text
    case = result.json()["case"]

    segments = case["transcriptSegments"]
    assert len(segments) == 13
    assert segments[0]["startMs"] == 4000
    assert segments[0]["text"].startswith("Good morning Alex.")
    # The title line precedes the first label and must not become a turn.
    assert not any("FICTIONAL DEMO DOCUMENT" in s["text"] for s in segments)
    # Wrapped PDF lines continue the turn above instead of splitting it.
    assert segments[0]["text"].endswith("what happens next.")

    session = segments[0]["sessionId"]
    assert session.startswith("pdf_")
    assert case["speakerRoles"] == {f"{session}:0": "clinician", f"{session}:1": "patient"}

    # Imported turns feed the same consultation source as live capture.
    source = next(s for s in case["sources"] if s["id"] == "consultation_001")
    assert source["kind"] == "consultation"
    assert "[clinician at 4000ms]" in source["passages"][0]["text"]
    assert case["workflowState"] == "awaiting_review"


def test_reuploading_the_same_file_changes_nothing(client: TestClient):
    client.post("/api/cases", json={"reset": True})
    first = upload(client).json()["case"]
    again = upload(client).json()["case"]
    assert len(again["transcriptSegments"]) == len(first["transcriptSegments"])
    assert again["inputRevision"] == first["inputRevision"]


def test_importing_a_transcript_replaces_the_previous_one(client: TestClient, tmp_path):
    """Two consultations must never be merged into one patient's record."""
    client.post("/api/cases", json={"reset": True})
    first = upload(client).json()["case"]
    assert len(first["transcriptSegments"]) == 13

    other = tmp_path / "other-consultation.pdf"
    other.write_bytes(pdf_with(["Clinician: A different consultation.", "Patient: Understood."]))
    case = upload(client, other, "other-consultation.pdf").json()["case"]

    assert [s["text"] for s in case["transcriptSegments"]] == [
        "A different consultation.",
        "Understood.",
    ]
    assert not any("Good morning Alex" in s["text"] for s in case["transcriptSegments"])
    # Roles belonging to the discarded transcript must not linger.
    old_session = first["transcriptSegments"][0]["sessionId"]
    assert not any(key.startswith(old_session) for key in case["speakerRoles"])
    source = next(s for s in case["sources"] if s["id"] == "consultation_001")
    assert len(source["passages"]) == 2


def test_importing_a_transcript_clears_lines_captured_another_way(client: TestClient):
    client.post("/api/cases", json={"reset": True})
    live = {
        "id": "seg-live-001",
        "sessionId": "live-001",
        "speakerId": 0,
        "text": "Captured live before the import.",
    }
    assert client.post(f"{CASE}/transcript", json={"segments": [live]}).status_code == 200
    case = upload(client).json()["case"]
    assert len(case["transcriptSegments"]) == 13
    assert not any(s["id"] == "seg-live-001" for s in case["transcriptSegments"])


def test_upload_does_not_overwrite_a_role_the_clinician_confirmed(client: TestClient):
    client.post("/api/cases", json={"reset": True})
    session = upload(client).json()["case"]["transcriptSegments"][0]["sessionId"]
    corrected = client.post(
        f"{CASE}/transcript", json={"speakerRoles": {f"{session}:0": "patient"}}
    )
    assert corrected.status_code == 200
    assert upload(client).json()["case"]["speakerRoles"][f"{session}:0"] == "patient"


def test_a_document_without_speaker_labels_is_rejected(client: TestClient, tmp_path):
    client.post("/api/cases", json={"reset": True})
    plain = tmp_path / "no-labels.pdf"
    plain.write_bytes(pdf_with(["There is no speaker label anywhere in this file."]))
    result = upload(client, plain, "no-labels.pdf")
    assert result.status_code == 422
    assert "speaker-labelled" in result.json()["detail"]
    assert client.get(CASE).json()["case"]["transcriptSegments"] == []


def test_a_non_pdf_upload_is_rejected(client: TestClient):
    client.post("/api/cases", json={"reset": True})
    result = client.post(f"{CASE}/transcript/document", files={"file": ("t.txt", b"Clinician: hi")})
    assert result.status_code == 400


def test_a_discharge_document_imports_only_as_unconfirmed_voices(client: TestClient):
    """A wrong file must never claim clinician or patient roles on the caregiver's behalf."""
    client.post("/api/cases", json={"reset": True})
    case = upload(client, FIXTURE_PDF, "discharge.pdf").json()["case"]
    assert case["transcriptSegments"]
    assert not set(case["speakerRoles"].values()) & {"clinician", "patient"}
    source = next(s for s in case["sources"] if s["id"] == "consultation_001")
    assert all(p["text"].startswith("[unconfirmed speaker") for p in source["passages"])


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (["Clinician: Only one voice here."], "at least two"),
        ([f"Name{i}: line {i}" for i in range(9)], "at most 8"),
        (["Clinician: a", "Patient: b"] * 160, "at most 300"),
    ],
)
def test_shapes_that_are_not_consultation_transcripts_are_rejected(lines, expected):
    with pytest.raises(TranscriptFormatError, match=expected):
        parse_transcript(lines, "pdf_test")


def test_speaker_numbers_without_role_words_stay_unknown():
    segments, roles = parse_transcript(
        ["Speaker 1: Take the walking frame.", "Speaker 2: Every time?"], "pdf_test"
    )
    assert [s.speaker_id for s in segments] == [0, 1]
    assert roles == {"pdf_test:0": "unknown", "pdf_test:1": "unknown"}
