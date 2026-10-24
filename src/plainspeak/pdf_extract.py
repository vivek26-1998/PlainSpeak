"""Text-based PDF extraction into passages with stable IDs (`page_{n}_p{k}`)."""

import re
from pathlib import Path

from pypdf import PageObject, PdfReader

from plainspeak.contracts import Passage

_BLANK_LINE = re.compile(r"\n\s*\n")
_WHITESPACE = re.compile(r"\s+")


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
