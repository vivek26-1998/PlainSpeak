"""Text-based PDF extraction into passages with stable IDs (`page_{n}_p{k}`)."""

import re
from pathlib import Path

from pypdf import PageObject, PdfReader

from plainspeak.contracts import Passage

_BLANK_LINE = re.compile(r"\n\s*\n")
_WHITESPACE = re.compile(r"\s+")
# Matched against layout lines, where wide gaps separate table columns:
#   "Patient: Alex Example (fictional)."  /  "Patient name: Alex Example, age 76"
#   "   Patient          Anna Müller          Discharge date    24 October 2026"
_PATIENT_NAME = re.compile(
    r"(?:\bPatient(?:\s+name)?\s*:|^\s*Patient(?:\s+name)?\s{2,})\s*"
    r"([^\s(),.;:][^(),.;:]*?)\s*(?=[(),.;]|\s{2,}|\s\w+\s*:|$)",
    re.IGNORECASE,
)


class NoTextError(ValueError):
    """The PDF has no extractable text (scanned documents need OCR, which is out of scope)."""


def _page_text(page: PageObject) -> str:
    # Layout mode keeps the original line and paragraph breaks, which gives stable splits.
    return page.extract_text(extraction_mode="layout") or page.extract_text() or ""


def extract_lines(pdf_path: Path) -> list[str]:
    """Non-empty text lines in reading order, for documents written one turn per line."""
    reader = PdfReader(pdf_path)
    lines = [
        cleaned
        for page in reader.pages
        for line in _page_text(page).splitlines()
        if (cleaned := _WHITESPACE.sub(" ", line).strip())
    ]
    if not lines:
        raise NoTextError("No extractable text found in the PDF.")
    return lines


def find_patient_name(lines: list[str]) -> str | None:
    """The patient name from a "Patient" label or table row, if present."""
    for line in lines:
        if match := _PATIENT_NAME.search(line):
            return match.group(1)
    return None


def extract_patient_name(pdf_path: Path) -> str | None:
    reader = PdfReader(pdf_path)
    return find_patient_name(
        [line for page in reader.pages for line in _page_text(page).splitlines()]
    )


def extract_passages(pdf_path: Path) -> list[Passage]:
    reader = PdfReader(pdf_path)
    passages: list[Passage] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = _page_text(page)
        chunks = [_WHITESPACE.sub(" ", chunk).strip() for chunk in _BLANK_LINE.split(text)]
        for index, chunk in enumerate((c for c in chunks if c), start=1):
            passages.append(
                Passage(id=f"page_{page_number}_p{index}", page=page_number, text=chunk)
            )
    if not passages:
        raise NoTextError("No extractable text found in the PDF.")
    return passages
