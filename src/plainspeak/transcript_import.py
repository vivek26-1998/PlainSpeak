"""Parse a written consultation transcript into speaker-labelled segments.

The expected shape is one spoken turn per line, each starting with a speaker label::

    [00:00:04] Clinician: Bring your medication list to the follow-up.
    Patient: I thought I only needed my ID card.

Leading timestamps are optional and become `start_ms`. A line without a label continues
the previous turn, which is how wrapped paragraphs survive PDF extraction. Lines before
the first labelled turn (titles, headers) are ignored.

Roles are inferred only from unambiguous labels; anything else stays `unknown` so the
clinician confirms it in the same mapping UI used for live capture.
"""

import re
from collections.abc import Sequence

from plainspeak.contracts import SpeakerRole, TranscriptSegment

MAX_SEGMENTS = 300
MAX_SPEAKERS = 8  # TranscriptSegment.speaker_id accepts 0-7
MAX_SEGMENT_CHARS = 10000  # TranscriptSegment.text upper bound
MAX_LABEL_WORDS = 4

_TIMESTAMP = re.compile(
    r"^[\[(]?\s*(?:(?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{2})"
    r"(?:[.,](?P<ms>\d{1,3}))?\s*[\])]?\s*"
)
# The curly apostrophe and fullwidth colon are deliberate: both turn up in exported PDFs.
_SPEAKER = re.compile(r"^(?P<label>[^\W\d_][\w .'’-]{0,38}?)\s*[:：]\s*(?P<text>\S.*)$")  # noqa: RUF001

_CLINICIAN_WORDS = frozenset(
    {"clinician", "doctor", "dr", "physician", "consultant", "nurse", "gp", "arzt", "arztin"}
)
_PATIENT_WORDS = frozenset({"patient", "patientin"})


class TranscriptFormatError(ValueError):
    """The text was readable but does not look like a speaker-labelled transcript."""


def _split_timestamp(line: str) -> tuple[str, int | None]:
    match = _TIMESTAMP.match(line)
    if not match:
        return line, None
    minutes, seconds = int(match.group("m")), int(match.group("s"))
    rest = line[match.end() :].strip()
    if minutes > 59 or seconds > 59 or not rest:
        return line, None
    total_seconds = (int(match.group("h") or 0) * 60 + minutes) * 60 + seconds
    return rest, total_seconds * 1000 + int((match.group("ms") or "").ljust(3, "0"))


def _split_speaker(line: str) -> tuple[str, str] | None:
    """Return `(label, text)` when the line opens with a short speaker label."""
    match = _SPEAKER.match(line)
    if not match:
        return None
    label = match.group("label").strip()
    if not label or len(label.split()) > MAX_LABEL_WORDS:
        return None
    return label, match.group("text").strip()


def _role_for(label: str) -> SpeakerRole:
    words = {word.strip(".'’") for word in label.casefold().replace("-", " ").split()}  # noqa: RUF001
    if words & _CLINICIAN_WORDS:
        return "clinician"
    if words & _PATIENT_WORDS:
        return "patient"
    return "unknown"


def parse_transcript(
    lines: Sequence[str],
    session_id: str,
) -> tuple[list[TranscriptSegment], dict[str, SpeakerRole]]:
    """Turn transcript lines into segments plus the speaker roles read from their labels."""
    turns: list[tuple[str, str, int | None]] = []
    labels: list[str] = []  # casefolded labels, in order of first appearance
    for line in lines:
        rest, start_ms = _split_timestamp(line.strip())
        speaker = _split_speaker(rest)
        if speaker is None:
            if turns:
                label, text, first_ms = turns[-1]
                turns[-1] = (label, f"{text} {rest}".strip(), first_ms)
            continue  # leading titles and headers carry no turn of their own
        label, text = speaker
        key = label.casefold()
        if key not in labels:
            labels.append(key)
        turns.append((key, text, start_ms))

    if not turns:
        raise TranscriptFormatError(
            "No speaker-labelled lines found. Start each turn with a label, "
            "for example 'Clinician: ...' or 'Speaker 1: ...'."
        )
    if len(labels) < 2:
        raise TranscriptFormatError(
            f"Only one speaker ({labels[0]!r}) was found. A consultation transcript "
            "needs at least two labelled speakers."
        )
    if len(labels) > MAX_SPEAKERS:
        raise TranscriptFormatError(
            f"Found {len(labels)} speaker labels; at most {MAX_SPEAKERS} are supported. "
            "Check that this file is a transcript rather than a discharge document."
        )
    if len(turns) > MAX_SEGMENTS:
        raise TranscriptFormatError(
            f"Transcript has {len(turns)} turns; at most {MAX_SEGMENTS} are supported. "
            "Split it into smaller files."
        )
    if any(len(text) > MAX_SEGMENT_CHARS for _, text, _ in turns):
        raise TranscriptFormatError(f"A single turn is longer than {MAX_SEGMENT_CHARS} characters.")

    segments: list[TranscriptSegment] = []
    roles: dict[str, SpeakerRole] = {}
    for index, (key, text, start_ms) in enumerate(turns, start=1):
        speaker_id = labels.index(key)
        segments.append(
            TranscriptSegment(
                id=f"seg_{session_id}_{index:03d}",
                session_id=session_id,
                text=text,
                speaker_id=speaker_id,
                start_ms=start_ms,
            )
        )
        roles.setdefault(f"{session_id}:{speaker_id}", _role_for(key))
    return segments, roles
