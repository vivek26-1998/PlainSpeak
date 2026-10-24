"""Generate the fictional demo PDFs: a discharge summary and a consultation transcript.

All names, places and clinical wording are fictional and prepared in advance.
Run: uv run python scripts/make_fixture.py
"""

from pathlib import Path

from fpdf import FPDF

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
OUT = FIXTURES / "discharge.pdf"
TRANSCRIPT_OUT = FIXTURES / "consultation-transcript.pdf"

TITLE = "Discharge Summary - FICTIONAL DEMO DOCUMENT (synthetic data, not a real patient)"

TRANSCRIPT_TITLE = (
    "Consultation Transcript - FICTIONAL DEMO DOCUMENT (synthetic data, not a real patient)"
)

# One spoken turn per line, each opening with a speaker label the importer can read.
TRANSCRIPT_LINES = [
    "[00:00:04] Clinician: Good morning Alex. Before you go home, let us walk through the "
    "plan together so you and Sam both know what happens next.",
    "[00:00:16] Patient: Thank you. The part I am least sure about is getting to the "
    "appointment next month.",
    "[00:00:25] Clinician: That is a good thing to raise. You must not drive yourself, so "
    "Sam should arrange transport to the clinic and back before the appointment day.",
    "[00:00:38] Patient: Sam can do that. Is the appointment the one on the ninth?",
    "[00:00:45] Clinician: Yes, Monday the ninth of November at half past ten, Outpatient "
    "Clinic, Building B, second floor. Please arrive fifteen minutes early to check in.",
    "[00:00:59] Patient: I thought I only needed to bring my identification card.",
    "[00:01:05] Clinician: Bring your current medication list and the discharge letter as "
    "well. The team needs all three to review how you are doing.",
    "[00:01:18] Patient: Understood. And at home, how careful do I need to be?",
    "[00:01:26] Clinician: Use the walking frame we gave you whenever you walk around the "
    "house, right up until the follow-up appointment.",
    "[00:01:37] Patient: Even for short trips to the kitchen?",
    "[00:01:41] Clinician: Yes, every time. It is the simplest way to avoid another fall "
    "while you are still unsteady.",
    "[00:01:51] Patient: All right. Who do we call if something does not seem right?",
    "[00:01:58] Clinician: The Outpatient Clinic team, on the number printed on your "
    "appointment card. Do not wait for the follow-up if you are worried.",
]

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


def write_pdf(path: Path, title: str, blocks: list[str], gap: int) -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 8, title)
    pdf.ln(4)
    pdf.set_font("Helvetica", size=11)
    for block in blocks:
        pdf.multi_cell(0, 6, block)
        pdf.ln(gap)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    print(f"Wrote {path}")


def main() -> None:
    write_pdf(OUT, TITLE, PARAGRAPHS, gap=5)
    # No paragraph gap: blank lines would split turns into separate passages.
    write_pdf(TRANSCRIPT_OUT, TRANSCRIPT_TITLE, TRANSCRIPT_LINES, gap=1)


if __name__ == "__main__":
    main()
