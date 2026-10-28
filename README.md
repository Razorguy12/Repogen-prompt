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

See `.env.example` for the configuration template.

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
