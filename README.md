# Capstone Assistant

**Current release:** Version 5 — Sprint 5 complete

**Application:** Streamlit

**Purpose:** AI-assisted management of UC Canberra Capstone information and
project workspaces.

Capstone Assistant answers questions from approved Capstone documents and,
when authorised, project-specific records. It combines local document
retrieval, Trellis Data Agentaus AI, SQLite persistence, role-based access and
project-management workflows.

## What is included

- General and authorised project-specific question answering.
- Retrieval for PDF, DOCX, XLSX, CSV, PPTX, Markdown and text files.
- Local OCR for scanned PDFs through Tesseract.
- Project profiles, team members, meetings, milestones and document uploads.
- Database-backed login, sessions, password reset and role-based access.
- Administrator monitoring for API health, retrieval quality, feedback, prompts,
  evaluations and vector-index health.
- Word, Excel, PDF and PowerPoint response exports.
- Optional WBS-style Gantt scheduling, Excel import and Kanban task tracking.
- Docker packaging with Python 3.11, Streamlit and Tesseract OCR.

## Roles and access

Access is checked against the authenticated database session and project
assignments:

- Students can access assigned projects and maintain project content, but
  cannot change project identity, mentor or team membership.
- Mentors can access assigned teams.
- Convenors can oversee Capstone projects.
- Administrators manage users, approved knowledge, monitoring, prompts,
  evaluations and feature settings.

Project data is isolated during retrieval. Audit and monitoring records store
bounded metadata and operational status rather than unnecessary document
content. Provider credentials are supplied through environment variables or
Streamlit secrets and are never committed to the repository.

## Project structure

| Path | Responsibility |
| --- | --- |
| `app.py` | Streamlit entry point and compatibility facade |
| `app_modules/database.py` | SQLite persistence and additive migrations |
| `app_modules/auth.py` and `access_control.py` | Sessions, authentication and authorisation |
| `app_modules/services/ai_client.py` | Agentaus requests, streaming and provider telemetry |
| `app_modules/vector_store.py` | Local embeddings and hybrid retrieval |
| `app_modules/monitoring.py` | AI, API and retrieval monitoring |
| `app_modules/gantt.py`, `kanban.py`, `milestones.py` | Project scheduling and task workflows |
| `app_modules/exporting.py` and `export_ui.py` | Response export generation and controls |
| `app_modules/ui/` | Shared UI and administrator pages |
| `scripts/manage.py` | Account and operational CLI tasks |
| `knowledge_base/` | Approved general Capstone documents |
| `knowledge_index/` | Generated general knowledge index |
| `project_data/` | SQLite database and project records |
| `project_knowledge/` | Project-specific uploads and indexes |
| `docs/` | Sprint and operational documentation |

## Requirements

- Python 3.11 or newer
- Tesseract OCR 5 for scanned PDFs
- Docker, if using the container workflow
- An Agentaus-compatible endpoint and API key

## Local setup

### 1. Install and configure

```bash
git clone <repository-url>
cd ai-assisted-capstone-pms
python -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install Tesseract separately if it is not already available, then create a
local `.env` file in the project root:

```dotenv
AGENTAUS_API_KEY=replace-with-your-api-key
API_ENDPOINT=https://your-agentaus-host/api/v1/chat/completions
```

Optional limits include `MAX_DOCUMENT_PAGES`, `OCR_PAGE_TIMEOUT_SECONDS`,
`MAX_PROJECT_PROFILE_CHARS`, `ENABLE_ANSWER_VALIDATION`, and the context-budget
settings documented in the application code.

### 2. Initialise an account and run

```bash
python scripts/manage.py init
python scripts/manage.py create-user --name "Local Administrator" \
  --username admin@example.org --role Administrator
streamlit run app.py
```

Open <http://localhost:8501>. Start Streamlit from the repository root so the
project configuration is loaded.

### 3. Run tests

```bash
python -m pip install -r requirements-dev.txt
pytest -q
```

The Sprint 5 verification run passed 111 tests.

## Docker setup

The Dockerfile builds a Python 3.11 slim image, installs Tesseract and the
runtime dependencies, then starts Streamlit on port `8501`.

```bash
docker build -t capstone-assistant .
docker run --rm -p 8501:8501 --env-file .env capstone-assistant
```

For data to survive container replacement, mount the runtime data directories:

```bash
docker run --rm -p 8501:8501 --env-file .env \
  -v "$(pwd)/project_data:/app/project_data" \
  -v "$(pwd)/project_knowledge:/app/project_knowledge" \
  capstone-assistant
```

The container health endpoint is `/_stcore/health`. The image contains the
application runtime, not production secrets or an external orchestration
configuration.

## Data and knowledge management

- `knowledge_base/` contains approved general source documents.
- `knowledge_index/index.json` is generated by the application; do not edit it
  manually.
- Administration uploads and deletes rebuild the general index.
- Project uploads are stored under `project_knowledge/<project-id>/` and use
  isolated indexes.
- SQLite is stored at `project_data/capstone.sqlite3`.
- Existing database migrations are additive and preserve users, assignments,
  projects and password hashes.
- Keep `.env` and `.streamlit/secrets.toml` private.

## AI and retrieval behaviour

Each request is planned, retrieved locally and sent to Agentaus with bounded
context. Hybrid retrieval combines lexical, fuzzy, latent-semantic and local
vector signals. Responses can undergo groundedness validation before they are
streamed to the UI. Retrieval selects context; Agentaus composes the
user-facing answer.

Administrators can review provider latency and failures, retrieval quality,
feedback, prompt versions and manual evaluations. Monitoring is designed to
retain only the information needed for operational review and evaluation.

## Sprint delivery history

The project is planned across seven sprints. Completed work is summarised below;
the detailed delivery records are in `docs/` and the release notes are in
[`CHANGELOG.md`](CHANGELOG.md).

| Sprint | Focus | Outcome |
| --- | --- | --- |
| 1 | General Capstone Assistant | General retrieval, Agentaus integration and knowledge-base administration |
| 2 | Project Workspace | Project records, uploads, isolated retrieval, meetings and milestones |
| 3 | Database, Login & User Access | SQLite persistence, authentication, roles and assignment-based access |
| 4 | AI & System Performance Dashboard | Monitoring, evaluation, vector retrieval, exports, scheduling and Tasks |
| 5 | Integration & Dockerisation | Integrated containerised prototype complete on 2026-10-09 |

### Sprint 5 scope

Sprint 5 ran from 2026-10-05 to 2026-10-09:

- Integrate modules and resolve integration defects: 2026-10-05 to 2026-10-07.
- Dockerise and configure the application: 2026-10-06 to 2026-10-08.
- Test, review and document the containerised prototype: 2026-10-08 to
  2026-10-09.
- Complete the integrated containerised prototype: 2026-10-09.

## Troubleshooting

**`streamlit` is not recognised**

Activate `.venv` and use `python -m streamlit run app.py`.

**OCR is unavailable**

Install Tesseract, verify `tesseract --version`, and restart the terminal.

**Agentaus requests fail**

Check `AGENTAUS_API_KEY` and `API_ENDPOINT`. Streamlit Cloud requires a
publicly reachable HTTPS endpoint configured in App settings → Secrets.

**The browser cannot connect**

Confirm the Streamlit process is running and use the port shown in the command.
The default is <http://localhost:8501>.

**An upload is rejected**

Use a supported, non-password-protected PDF, DOCX, XLSX, CSV, PPTX, TXT or MD
file within the configured size limit.

## Boundaries

The prototype does not include LMS integration, enterprise orchestration or
production hosting configuration. Local accounts, assignments and project
records remain the current source of truth. AI output supports users but does
not replace formal academic, mentor or stakeholder decisions.

For sprint-specific implementation details, see the Word records in `docs/`.
