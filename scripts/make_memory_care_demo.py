"""Generate the synthetic memory-care handoff PDF and a PNG for visual QA.

Requires reportlab for generation; pypdf validates text and page count.
Optional PyMuPDF renders the QA image. This is a fixture builder, not clinical software.
"""

from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "pdf" / "plainspeak-memory-care-discharge.pdf"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="DemoTitle",
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            spaceAfter=7,
            textColor=colors.HexColor("#17364a"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="DemoNotice",
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#9a3324"),
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DemoBody",
            fontName="Helvetica",
            fontSize=10.4,
            leading=14.2,
            spaceAfter=8,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DemoHeading",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            spaceBefore=5,
            spaceAfter=4,
            keepWithNext=True,
        )
    )
    story = []

    def paragraph(text: str, style: str = "DemoBody") -> None:
        story.append(Paragraph(text, styles[style]))

    paragraph("Memory clinic visit summary", "DemoTitle")
    paragraph("FICTIONAL SOFTWARE TEST - NOT A REAL PRESCRIPTION OR MEDICAL RECORD", "DemoNotice")
    paragraph(
        "<b>Patient:</b> Alex Example, age 76 &nbsp;&nbsp; <b>Caregiver:</b> Sam Example<br/>"
        "<b>Service:</b> Riverside Demo Memory Clinic (fictional)<br/>"
        "<b>Visit date:</b> 24 October 2026 &nbsp;&nbsp; "
        "<b>Clinician:</b> Dr Rowan Example (fictional)"
    )
    paragraph("Visit and return home", "DemoHeading")
    paragraph(
        "Planned outpatient review of an established diagnosis of mild Alzheimer's disease. "
        "Alex returns home after the appointment. This visit does not establish a new diagnosis. "
        "Alex agreed that Sam may receive and help organize this plan."
    )
    paragraph("Medication record for this fictional patient", "DemoHeading")
    paragraph(
        "<b>Existing medicine:</b> donepezil 5 mg tablet. <b>Existing schedule:</b> one tablet "
        "each evening at 20:00. <b>No medication change was made today.</b> No morning tablet "
        "was added. Sam will remind Alex and record whether the evening tablet was taken. "
        "This synthetic entry is not a valid prescription and must not be used "
        "to obtain or administer medicine."
    )
    paragraph("Home routine and caregiver notes", "DemoHeading")
    paragraph(
        "Sam should help Alex follow a simple written daily checklist. For seven days, "
        "from 25 October through 31 October 2026 inclusive, Sam should make one brief evening "
        "note about memory difficulties, sleep changes or trouble following the routine. "
        "Bring these observations to the next review. These are caregiver reports, "
        "not a clinical assessment."
    )
    paragraph("Booked follow-up and transport", "DemoHeading")
    paragraph(
        "<b>Already booked:</b> Monday 9 November 2026 at 10:30.<br/>"
        "<b>Arrive:</b> 10:15, fifteen minutes before the appointment.<br/>"
        "<b>Location:</b> Riverside Demo Memory Clinic, Building B, second floor.<br/>"
        "<b>Sam's task:</b> arrange transport to the clinic and home before the appointment day. "
        "Transport is not confirmed in this handoff. Do not book a duplicate clinic appointment."
    )
    paragraph("What to bring", "DemoHeading")
    paragraph(
        "Bring this visit summary, Alex's current medication list, identification card, "
        "and the seven-day caregiver notes."
    )
    paragraph("Questions requiring clarification", "DemoHeading")
    paragraph(
        "For unclear medication directions, Sam should ask the pharmacist or clinic care team. "
        "Missed-dose and dose-adjustment instructions are not provided in this handoff. "
        "No clinic phone number, emergency pathway or advice about new symptoms is supplied "
        "in this fictional test record. The assistant must not invent those details."
    )
    story.append(Spacer(1, 3 * mm))

    def footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d7dfe5"))
        canvas.line(18 * mm, 17 * mm, A4[0] - 18 * mm, 17 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#566573"))
        canvas.drawString(
            18 * mm, 12 * mm, "PlainSpeak demo | Entirely synthetic | Not for clinical use"
        )
        canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=23 * mm,
        title="Fictional memory clinic visit summary for PlainSpeak testing",
        author="PlainSpeak demo fixture",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    reader = PdfReader(OUT)
    assert len(reader.pages) == 1, "Keep the demo document to one page."
    text = reader.pages[0].extract_text()
    for expected in ("Alex Example", "donepezil 5 mg", "20:00", "9 November 2026", "10:15"):
        assert expected in text, expected
    assert "Leena" not in text
    assert "noticeboard" not in text
    print(f"Created and text-checked: {OUT}")


if __name__ == "__main__":
    main()
