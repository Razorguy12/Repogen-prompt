# Repogen Reports

### A focused workspace for drafting radiology reports from natural-language prompts

Describe the examination, clinical context, and findings in your own words. repogen creates three structured draft options, then gives you a place to review, refine, export, and find each case again.

> **For qualified radiologists:** AI-generated reports are drafts. Verify every statement against the study and clinical record before approving or using a report.

---

## At a glance

- **Prompt-first workflow:** Type or dictate a case instead of completing a multi-step form.
- **Three versions per case:** Compare concise, standard, and detailed drafts built from the same supplied facts.
- **Your report style:** Optionally provide a house format or choose a preset for headings and order.
- **Review and edit:** Preview, select, edit, save, or copy the version that fits the case.
- **Export when ready:** Download a polished PDF or a Word document for further editing.
- **A timestamped library:** Reopen prompt sessions from recent history or find reports in the dashboard.
- **Secure workspace:** Sign-in, account-scoped reports, and role-restricted administration.

## How prompt-based drafting works

1. **Describe the case.** Include the modality and body region, relevant clinical details, and the findings you want reported. The prompt can be up to 8,000 characters.
2. **Add a format if you need one.** Use the Classic, Numbered Impression, or Organ-wise preset, or enter your preferred headings and order. This step is optional.
3. **Generate three drafts.** repogen returns concise (80–120 words), standard (150–200 words), and detailed (200–280 words) alternatives. Each version is intended to preserve the same case facts while varying its level of detail.
4. **Choose and refine.** Switch between versions, edit the report in the workspace, save your edits, or copy the text.
5. **Export or return later.** Download the selected report as PDF or DOCX. Generated prompt sessions are saved with their timestamp and can be reopened from history or the Library dashboard.

### What you can include in a prompt

Give the model the information needed to draft the report, such as:

- Examination and modality (for example, MRI lumbar spine or chest radiograph)
- Clinical indication and relevant history
- Findings, measurements, and locations
- Any requested report style, headings, or impression format

Example:

```text
MRI lumbar spine. Low back pain radiating to the left leg. L4-L5 disc bulge
contacts the left traversing nerve root. Use headings for Examination,
Technique, Findings by level, and a numbered Impression.
```

The workspace includes starter prompts for CT brain, MRI lumbar spine, chest X-ray, and abdominal ultrasound. These are examples; the drafting prompt is designed for a broad range of imaging examinations.

## Features

| Feature | What it does |
| --- | --- |
| **Natural-language composer** | Enter the study, context, and findings in one prompt. Generate with the button or `Ctrl+Enter` (`⌘+Enter` on Mac). |
| **Voice dictation** | Dictate into the prompt using your microphone; recognized speech is added to the composer. |
| **Custom formats and presets** | Add a preferred layout, or start from Classic, Numbered Impression, and Organ-wise formats. |
| **Three report lengths** | Compare concise, standard, and detailed alternatives for the same case. |
| **Draft selection** | Select the preferred alternative; the choice is saved with the session. |
| **Inline editing** | Edit the report text and save it back to the selected draft. |
| **Copy and export** | Copy report text, download a PDF, or download a DOCX to continue editing in Word-compatible software. |
| **Recent report history** | Open the seven most recent prompt reports from the workspace sidebar; use the Library link for the full dashboard. |
| **Report library** | Browse reports by date, search by date or study type, filter by modality, and view account report statistics. |
| **Draft and final status** | Mark a report final after review. Finalized reports are protected from editing in the standard report workflow. |
| **Structured report workflow** | An additional, separate wizard is available at `/generate-structured` for template-driven generation, PDF text extraction, voice tools, and scan attachments. |
| **Administration** | Admin users can manage accounts from the protected admin area. |

## Getting started

### Requirements

- Python 3.10 or newer
- Node.js and npm
- A Groq API key for report generation and voice transcription

### Configure the backend

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env            # Windows: copy .env.example .env
```

Edit `.env` and set `GROQ_API_KEY`. Configure `DATABASE_URL` and `SECRET_KEY` as appropriate for your deployment. SQLite is used when no database URL is provided.

### Install and run the frontend

```bash
cd web
npm install
npm run dev
```

In another terminal, from the repository root, start the API:

```bash
python -m uvicorn main:app --reload
```

Run Uvicorn from the activated project environment (or use `.venv/bin/python -m uvicorn ...` directly). A globally installed `uvicorn` can use a different Python environment from the one where project dependencies are installed. `sniffio` is listed explicitly because the installed Groq client imports it at startup.

Open the Vite URL printed by the frontend command (usually `http://localhost:5173`). The Vite development server proxies API requests to the backend on port 8000.

### Production build

```bash
cd web
npm install
npm run build
cd ..
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. FastAPI serves the built frontend. API documentation is available at `/docs`.

## Main pages

| Path | Purpose |
| --- | --- |
| `/` | Product introduction and workflow overview |
| `/login` | Sign in |
| `/generate` | Prompt-based drafting workspace |
| `/dashboard` | Report library, search, modality filters, and report statistics |
| `/generate-structured` | Template-driven structured report wizard |
| `/reports/:id` | Structured report preview and editing |
| `/admin` | User administration for authorized admins |

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `GROQ_API_KEY` | Yes for AI generation and transcription | API key used by Groq-backed report generation and Whisper transcription. |
| `DATABASE_URL` | No | SQLAlchemy database URL. The app falls back to SQLite when omitted. |
| `SECRET_KEY` | Recommended | Secret used for signing authentication tokens. Set a private value in deployed environments. |
| `AUDIT_LOG_DIR` | No | Restricted JSON audit log directory. Defaults to `/var/log/repogen`; set a writable local path for development. |
| `TRUSTED_PROXY_IPS` | No | Comma-separated trusted reverse proxy IPs/CIDRs. Forwarded client IPs are ignored unless the direct peer matches. |

See `.env.example` for the configuration template.

## Audit logs and EC2 operations

Audit records are stored in PostgreSQL's `audit_events` table and written independently to a rotating JSONL file. Schema changes are Alembic migrations in `alembic/versions/`; they are applied by `python migrate.py` during deploy and, as a safety net, at app startup under a Postgres advisory lock. It does not expose audit mutation or deletion endpoints. Event metadata is limited to activity identifiers and operational context; report bodies, patient identifiers, credentials, and tokens are excluded.

Before deploying, back up the database and configure the service account to write to the log directory. Use the actual account and paths from the EC2 systemd unit:

```bash
sudo install -d -o repogen -g repogen -m 0750 /var/log/repogen
```

Add `AUDIT_LOG_DIR=/var/log/repogen` to the existing deployment environment without replacing other secrets. Set `TRUSTED_PROXY_IPS` to the Nginx address seen by Uvicorn (or leave it unset); do not trust arbitrary forwarded headers. Keep Nginx static roots outside `/var/log/repogen`. File rotation is 10 MiB with ten retained files; database retention and backups should follow the deployment's approved audit retention policy. No dashboard deletion action is provided.

Admin audit endpoints apply per-process request limits (including five CSV exports per administrator per hour), cap pages at 100 records, cap exports at 10,000 records, and cap analytics windows at one year. The request counters are in memory; deployments running multiple Uvicorn workers should also apply Nginx rate limits or move throttling to a shared store.

Run the schema migration and restart the service from the repository checkout:

```bash
source .venv/bin/activate
python migrate.py          # alembic upgrade head
# roll back one revision if needed:  alembic downgrade -1
sudo systemctl restart repogen
sudo systemctl is-active repogen
curl --fail http://127.0.0.1:8000/api/health
```

Inspect the current file and rotations (use an account allowed to read the protected logs):

```bash
sudo tail -n 50 /var/log/repogen/audit.log
sudo ls -lh /var/log/repogen/audit.log*
sudo journalctl -u repogen --since today
```

Verify the database table and recent event types:

```sql
SELECT id, created_at, event_type, user_id, status, resource_type, resource_id, request_id
FROM audit_events ORDER BY created_at DESC LIMIT 25;
```

Example JSONL event:

```json
{"timestamp":"2026-11-04T15:30:00Z","event_type":"REPORT_GENERATED","user_id":104,"status":"SUCCESS","resource_type":"report","resource_id":"812","ip_address":"192.168.1.10","user_agent":"Mozilla/5.0","request_id":"d7c7d2b2-7758-431f-b44e-2c9db2764cd0","duration_ms":4200,"details":{"workflow":"prompt","variants":3}}
```

Example PostgreSQL row:

```text
id | event_type       | user_id | status  | resource_type | resource_id | details
42 | REPORT_GENERATED | 104     | SUCCESS | report        | 812         | {"workflow":"prompt","variants":3}
```

The GitHub deployment workflow already builds the frontend and restarts `repogen`; it does not own or rewrite the external systemd unit. Confirm that unit's `User`, environment file, and `ReadWritePaths` permit access to the configured directory. The root administrator is bootstrapped only when missing, from `ROOT_ADMIN_USERNAME` / `ROOT_ADMIN_PASSWORD` (plus optional `ROOT_ADMIN_NAME`, `ROOT_ADMIN_EMAIL`) in the environment. No credentials live in the code.

Run the dependency-free audit service tests with:

```bash
python -m unittest discover -s tests -v
```

## Project layout

```text
.
├── main.py                  # FastAPI routes and application setup
├── auth.py                  # Authentication helpers
├── database.py              # Database models and setup
├── model/
│   ├── model.py             # Report generation and document export
│   ├── system_prompt.txt    # Drafting instructions
│   └── templates.json      # Structured workflow templates
└── web/
    └── src/
        ├── pages/           # Landing, prompt workspace, library, and other pages
        ├── components/      # Dictation, report cards, scan tools, and shared UI
        └── api/              # Frontend API client
```

## Clinical review

repogen assists with drafting and organization. It does not replace image interpretation, clinical judgment, or verification by a qualified radiologist. Confirm findings, measurements, protocol details, and recommendations against the source study before marking a report final or using it for patient care.

## License

Provided as-is for educational and demonstration purposes.
