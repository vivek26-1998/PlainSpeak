# Security, privacy, and limitations

## Intended use

PlainSpeak is a hackathon/MVP demonstration using fictional data. It is not a medical device or clinical decision-support system and has not been clinically validated. It must not be used to diagnose, prescribe, determine treatment, or manage real patient care. Do not upload real patient records, identifiers, recordings, or other confidential health information.

## Security properties implemented

- Permanent Anthropic and Reson8 keys are read by the backend from environment configuration; the Reson8 key is exchanged for a short-lived token before browser use.
- The model receives a limited tool set. Plan approval and progress confirmation are application-controlled actions, not model tools.
- Caregiver context is gated on a current clinician-approved version and loaded before the model's first response.
- Source references are checked against stored source/passages, and task updates must refer to a task in the approved plan.
- Progress updates require explicit confirmation and are tied to the approved plan version.
- Upload size and transcript structure limits constrain inputs.

These controls are prototype safeguards, not a complete security review.

## Important limitations

- There is no real user authentication, authorization, tenant isolation, or verified clinician identity. `approvedBy` is a client-provided label.
- The fixed demo case and page-load reset behavior are not suitable for concurrent users or real data.
- JSON files and uploaded PDFs are stored locally without encryption-at-rest, managed backups, retention policies, or a regulated audit trail.
- No rate limiting, CSRF strategy, abuse detection, or production secret manager is configured.
- Source-reference existence does not establish medical correctness or entailment.
- Generated text may be incorrect, incomplete, or misleading; human review is mandatory.
- Raw audio is not stored by this app, but speech text is sent to the speech provider and model inputs are sent to Anthropic. Review those providers' terms and data-handling policies before any use beyond synthetic data.
- Scanned PDFs and OCR are unsupported. German/English UI options do not imply validated clinical performance in either language.
- The single-process local file store is not designed for horizontal scaling or concurrent production traffic.

## Before any real-world deployment

A substantial redesign and review would be required: authenticated roles and authorization, secure per-patient tenancy, encrypted storage and transport, retention/deletion controls, audited access and edits, durable transactional storage, concurrency controls, threat modelling, input/output safety evaluation, clinical validation, human-factors testing, incident response, provider/legal review, and jurisdiction-specific privacy/regulatory assessment. Do not expose the demo server directly to the public internet.

## Reporting an issue

For this public hackathon repository, report reproducible software issues through GitHub Issues. Do not include personal, patient, or other confidential data in issue reports.
