import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from plainspeak.config import Settings
from plainspeak.main import create_app

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURE_PDF = FIXTURES / "discharge.pdf"
TRANSCRIPT_PDF = FIXTURES / "consultation-transcript.pdf"


def pdf_with(paragraphs: list[str]) -> bytes:
    """A minimal text PDF, for shapes the committed fixtures do not cover."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for paragraph in paragraphs:
        pdf.multi_cell(0, 6, paragraph)
        pdf.ln(1)  # multi_cell leaves the cursor mid-line; ln() returns it to the margin
    return bytes(pdf.output())


def text_response(data: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id="msg_fake",
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=json.dumps(data))],
    )


def tool_response(name: str, tool_input: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        id="msg_fake",
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", id=f"toolu_{name}", name=name, input=tool_input)],
    )


class FakeLLM:
    """Returns scripted responses in order and records every request."""

    def __init__(self) -> None:
        self.responses: list[SimpleNamespace] = []
        self.calls: list[dict[str, Any]] = []

    def queue(self, *responses: SimpleNamespace) -> None:
        self.responses.extend(responses)

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self.responses.pop(0)


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def client(tmp_path: Path, llm: FakeLLM) -> TestClient:
    settings = Settings(plainspeak_data_dir=tmp_path, anthropic_api_key="", reson8_api_key="")
    return TestClient(create_app(settings, llm=llm))
