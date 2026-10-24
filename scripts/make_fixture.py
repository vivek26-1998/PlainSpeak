"""Generate the fictional discharge PDF used in the demo.

All names, places and clinical wording are fictional and prepared in advance.
Run: uv run python scripts/make_fixture.py
"""

from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent.parent / "fixtures" / "discharge.pdf"

TITLE = "Discharge Summary - FICTIONAL DEMO DOCUMENT (synthetic data, not a real patient)"

PARAGRAPHS = [
    "Hospital: Riverside Demo Hospital (fictional). Patient: Alex Example (fictional). "
    "Primary caregiver: Sam Example. Discharged on 20 October 2026 after an overnight stay "
    "for observation following a fall at home.",
    "Follow-up appointment: Monday 9 November 2026 at 10:30 at the Riverside Demo Hospital "
    "Outpatient Clinic, Building B, second floor. Please arrive 15 minutes early to check in.",
    "What to bring to the follow-up: the patient's current medication list, this discharge "
    "letter and the patient's identification card.",
    "Transport: the patient must not drive to the follow-up appointment. The caregiver should "
    "arrange transport to and from the clinic before the appointment day.",
    "Home care instruction: the patient should use the walking frame provided whenever "
    "walking at home until the follow-up appointment.",
    "If you have questions about these instructions, contact the Outpatient Clinic team at "
    "the number on your appointment card (fictional).",
]


def main() -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 8, TITLE)
    pdf.ln(4)
    pdf.set_font("Helvetica", size=11)
    for paragraph in PARAGRAPHS:
        pdf.multi_cell(0, 6, paragraph)
        pdf.ln(5)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
