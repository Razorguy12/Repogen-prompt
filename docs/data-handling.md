# Data handling (Repogen)

Patient data handled by Repogen is personal data, and health data, under
India's Digital Personal Data Protection Act, 2023. This note records what
is stored, where it is stored, and what leaves the system.

## What is stored

| Data | Table | Notes |
|---|---|---|
| Doctor accounts (name, username, email, bcrypt password hash) | `users` | |
| Draft reports: the findings prompt, optional format, the three generated variants, `exam`, `flags`, prompt version, model ID | `reports` (`input_params`, `report_data`) | Drafts may contain whatever the doctor typed, which can include identifiers. |
| Uploaded scan images (structured workflow only) | `reports.scan_image` (base64) | |
| Patients: full name (plus a normalized copy for search), optional hospital ID / MRN, gender | `patients` | Private to the doctor who created them. Age is not stored on the patient. |
| Final reports: signed text, exam details, age at study, study date, source prompt, flags and acknowledgement times, prompt version, model ID | `final_reports` | Immutable. Amendments are new rows. There is no delete path. |
| Comparisons: the model's structured result, the doctor's edited summary and impression | `comparisons` | |
| Audit events: who did what to which record ID, and when | `audit_events`, plus the JSONL file in `AUDIT_LOG_DIR` | Record IDs and operational metadata only. Never names, patient IDs or report text (enforced by an allow-list in `audit_service.py`). |

## Where it is stored

- **Database:** PostgreSQL on the EC2 host named in `DATABASE_URL`.
- **Audit file:** `AUDIT_LOG_DIR` (default `/var/log/repogen`), rotated at 10 MiB, ten files kept.
- **Exports:** PDF, DOCX and print output are generated on request. The server writes them to temporary files and does not keep them.
- **Timestamps:** stored in UTC (`timestamptz`) and displayed in Asia/Kolkata.

## What is sent to the LLM provider (Groq, model in `GROQ_MODEL`)

| Feature | Sent | Not sent |
|---|---|---|
| Report generation | The findings text the doctor enters, and the optional house format. | Patient records. Patient details are only collected later, at finalization. Anything the doctor types into the findings box *is* sent, so doctors should not type names or IDs there. |
| Comparison | The two signed report texts, each report's modality, region and laterality, the labels "Baseline" and "Follow-up", and the interval in days. | Patient name, patient ID, gender, age and actual dates. As a safeguard, the patient's name, each part of the name, and the ID are also removed from the report text (replaced with `[redacted]`) before sending. |
| Speech transcription | The audio recording, sent to Groq Whisper. | |

## Access and retention

- Every patient, final-report and comparison route is scoped server-side to the signed-in doctor. Admins do not get patient search.
- A doctor who has patients or final reports cannot be deleted (the API returns 409). Lock the account instead.
- Deleting final reports, for example to honour a data-principal request, is not implemented. If it is needed, it should be an admin-only soft delete (`deleted_at`) reviewed separately.
- Application logs must not contain PHI. Log record IDs only.
