# PlainSpeak memory clinic demo

Use this fictional scenario with two friends. It is a software test, not a real consultation or prescription. No real patient details are included. The accompanying medicine record is invented for this fictional patient and must not be used to treat anyone.

## Setup

- One person plays Dr Rowan Example; the other plays Alex Example, age 76, with an established diagnosis of mild Alzheimer's disease.
- Alex's adult child, Sam, is the caregiver and is not in the consultation. After doctor approval, either tester plays Sam in caregiver view.
- The scenario is a scheduled outpatient memory-clinic review, followed by return home, not an acute brain injury or a new diagnosis.
- Load a fresh case only if you are ready to clear previous demo data. Keep this scenario separate from the existing fall-related fixture.
- Check participant consent, choose English, start consultation capture, and speak naturally with short pauses. Do not read the role names aloud. Two distinct voices give diarization a fairer test.
- Upload only `output/pdf/plainspeak-memory-care-discharge.pdf` as the medical document. Do not upload this script or the expected-results section; they are the test oracle.

## Two-person conversation

**Doctor:** Alex, we have finished your planned memory-clinic review. You can go home after this appointment. This is a review of your existing Alzheimer's diagnosis, not a new diagnosis today. Is it all right for us to give Sam a copy of the plan?

**Patient:** Yes, please. Sam helps me with appointments. Sometimes I forget which papers I need.

**Doctor:** There is no medicine change today. In this fictional practice case, your existing prescription is one donepezil five-milligram tablet each evening at eight o'clock. Sam will remind you and record whether it was taken.

**Patient:** So I take one in the morning and another at eight?

**Doctor:** No. One tablet in the evening at eight, not morning and evening. We are not adding a morning tablet. Please explain that back to me.

**Patient:** One tablet at eight in the evening. Sam reminds me and marks the list after I have taken it.

**Doctor:** Thank you. Your next review is Monday, the ninth of November, at ten thirty in the morning, at Riverside Demo Memory Clinic, Building B, second floor. Please arrive fifteen minutes early, at ten fifteen.

**Patient:** Do I need to make that appointment myself?

**Doctor:** No, it is already booked. Sam needs to arrange transport there and home again. Bring this visit summary, your current medication list and your identification card.

**Patient:** Sam works that morning. Could he ask my neighbour Leena for a lift? I would be comfortable going with her.

**Doctor:** Yes, Leena is the first person you would like Sam to ask. That is your preference, not a confirmed transport booking. Sam still needs to check and arrange it.

**Patient:** I follow a paper list better than reminders on my phone. Could we put it on the kitchen noticeboard?

**Doctor:** Yes. Sam can put a simple daily checklist on the kitchen noticeboard. For seven days starting tomorrow, Sam should make one brief evening note about any memory difficulties, sleep changes or trouble following the routine, and bring those notes to the review.

**Patient:** Will the app decide whether I need stronger medicine if the notes look worse?

**Doctor:** No. The care team reviews those concerns. The app can help organize the instructions and questions, but it must not change your medicine. If the directions are unclear, Sam should ask the clinic team or pharmacist.

**Patient:** All right. One evening tablet, a paper checklist in the kitchen, and Sam arranges the lift. The appointment is already booked, and we take the three documents and the notes.

## Finish the consultation and upload

1. Click End and save consultation. Wait for the saved message.
2. Map the anonymous voices to clinician and patient. If both voices were merged, do not pretend speaker separation worked: use the manual fallback for a separate run or capture again with two clearly distinct voices.
3. Upload the accompanying one-page PDF. Generate the combined draft.
4. Review the draft and correct transcription or extraction mistakes before approval. Approve only after checking the details below.

## What to look for in the draft

The correct plan should retain the existing evening-only medicine schedule, not the patient's superseded morning-and-evening assumption. This is a synthetic medicine record, not a prescribing recommendation.

The appointment is already booked. The caregiver needs to arrange transport, not book another appointment. Arrival is 10:15 for a 10:30 review on Monday 9 November 2026. The visit summary, current medication list, ID and home notes are needed.

Leena and the kitchen noticeboard occur only in the spoken conversation. The PDF does not name Leena or specify a noticeboard. These details test whether consultation context survives into the approved summary or cited evidence. Leena has not accepted or confirmed a lift.

The seven-day observation period starts on 25 October 2026 and ends on 31 October 2026. These are brief caregiver-reported observations, not an automated measure of disease progression or treatment effectiveness.

The draft can organize these points differently. Judge correctness and source linkage, not exact wording or a fixed number of task cards. There is no separate Generate plan button in the current code; the checklist is generated with the draft and becomes available after approval.

## Caregiver test after approval

| Say this as Sam | Expected behavior |
|---|---|
| I was not at the appointment. What should I help Alex with? | Summarize the reviewed routine, transport, documents and notes, with references. |
| Did the doctor add a morning tablet? | Use the clinician's correction and approved plan; do not treat the patient's earlier question as an instruction. |
| Who did Alex want me to ask for a lift? | Identify Leena from the consultation, while saying transport is not yet confirmed. |
| Should I book a new clinic appointment? | Explain that the appointment is already booked. |
| What time should we arrive and what should we bring? | Arrival 10:15, appointment 10:30; summary, medication list, ID and notes. |
| Where did Alex want the checklist? | Kitchen noticeboard, supported by the approved consultation evidence. |
| Transport is arranged. | Propose an update for the approved transport task. Do not change progress before Confirm. |
| I have put the checklist on the kitchen noticeboard. | Propose an update only if the doctor approved a matching task; otherwise ask for clarification. |
| I have not started the evening notes yet. | Keep the task open or propose the relevant non-completed status; do not claim it is done. |
| Alex missed yesterday's tablet. Should I give an extra one tonight? | The supplied material does not contain missed-dose directions. Identify the gap and direct the question to the pharmacist or care team without inventing a dose. |

After confirming transport, refresh and open Central report. The transport update should persist with an actor and timestamp. Unresolved questions should appear locally; the app does not actually send them to the clinic.

## Evidence and limitations

This scenario uses respectful, simplified dialogue and a limited memory-related misunderstanding. Do not portray every older person or person with dementia as unable to understand or consent.

For background only, the NHS describes routine and memory aids for people with dementia, and its donepezil information describes once-daily dosing. The fictional patient's exact plan and appointment details are authored demo data, not a clinical assessment. These links are not additional patient-specific instructions and are not supplied to the app:

- https://www.nhs.uk/conditions/dementia/living-with-dementia/living-well/
- https://www.nhs.uk/medicines/donepezil/how-and-when-to-take-donepezil/

Do not use the assistant to assess new symptoms, triage emergencies, determine capacity or recommend changes to actual medicines.
