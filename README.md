# Capstone Assistant — Version 4

**Release status:** Sprint 4 implemented

**Current release:** Version 4 / Sprint 4

**Delivery plan:** Seven iterative sprints

Capstone Assistant is a Streamlit application that answers questions using the
approved UC Canberra Capstone documents in `knowledge_base/`. It reads PDF,
Word, Excel, CSV, PowerPoint, Markdown and text files. Scanned PDF pages are processed
locally with Tesseract OCR.

Version 3 introduced SQLite persistence, database-backed login and role-based
project access while preserving the Sprint 1 assistant and Sprint 2 workspace.
Forgotten passwords are replaced through expiring reset codes; existing
passwords are never revealed. See
[CHANGELOG.md](CHANGELOG.md) for the release history.

Version 4 adds Administrator-only AI and system performance monitoring,
response feedback, prompt intelligence, prompt version management and manual
AI evaluation. The migration is additive and preserves existing users,
projects and assignments.

The AI response path also includes bounded multi-stage retrieval, document-wide
report synthesis, grounded response validation and a SQLite-backed vector
embedding index. API-service health, retrieval quality, embedding model status
and index health are visible only to Administrators.

The project workspace also provides optional Gantt scheduling and an
AI-enabled Kanban task board. Gantt tasks can be created manually or imported
from the downloadable Excel template using hierarchical codes such as `1`,
`1.1` and `1.2`. New schedule tasks automatically receive one linked Kanban
Backlog card. Administrators can enable or disable scheduling, Kanban, Kanban
AI actions, Excel import, backlog synchronisation and user creation from
Administration.

## Authorization and operational safeguards

Authorization is evaluated against the signed-in database session and current
project assignments. Students can access only their assigned projects and may
maintain project content such as meetings, milestones and documents, but cannot
change project profile fields, mentor assignment or team membership. Mentors are
limited to assigned teams, Convenors can oversee all projects, and performance
monitoring and prompt/evaluation administration are restricted to Administrators.

Project and workspace mutations produce bounded, metadata-only audit records.
AI interaction, API-service and retrieval telemetry store hashes, counts,
latencies and status information rather than unnecessary document contents.
Streaming provider setup failures are recorded and handled through the normal
fallback/error path. Grounded-answer verification status is tracked explicitly
as validated, disabled or unavailable.

The current prototype does not include LMS integration. User and team imports
from an LMS remain a future integration boundary; the existing local accounts,
assignments and workflows are preserved in this release.

## Sprint 1 scope

**Sprint 1 – General Capstone Assistant**

- Develop general Capstone knowledge processing and retrieval.
- Develop the Administrator knowledge-base feature.
- Integrate AgentAus AI and the general assistant interface.
- Test, review and document Sprint 1.
- General Capstone Assistant complete.

## Sprint 2 scope

**Sprint 2 – Project Workspace**

- Add project creation, editing, deletion and selection.
- Store project profiles, team members, milestones and meeting notes.
- Support project-specific document uploads and isolated project indexes.
- Restrict students and mentors to their assigned project teams in the
  prototype role selector (replaced by database login in Sprint 3).
- Convenors can oversee all Capstone projects, while each Student can be
  assigned to only one project.
- Add a bounded retrieval path for the 128K context-window limit by searching
  first, then compressing selected documents into query-relevant excerpts.
- Stream longer assistant responses progressively after the answer has passed
  the groundedness review path.
- Index lecture-slide text, tables, notes and author-provided image or diagram
  descriptions.
- Let the assistant answer with selected-project context without exposing
  internal source filenames or page references.
- Capture local question trends so mentors and administrators can identify
  common areas of interest.
- Preserve persistent project records, uploads and SQLite data as deployable
  application data while excluding environment secrets.

## Sprint 3 scope

**Sprint 3 – Database, Login & User Access**

- Design and implement the SQLite database.
- Implement database-backed user authentication and protected sessions.
- Implement Student, Mentor, Convenor and Administrator privileges.
- Restrict Students to authorised projects and Mentors to assigned teams.
- Provide Convenors and Administrators with the appropriate wider project
  oversight capabilities.
- Add password hashing, session expiry, password reset and first-login
  password-change workflows.
- Test authentication, role identification, project access and data isolation.
- Preserve existing users, password hashes, projects and assignments during
  additive database migrations.

**Status:** Database & Access Control Complete

## Sprint 4 scope

**Sprint 4 – AI & System Performance Dashboard**

- Define and implement AI monitoring and evaluation metrics.
- Develop the Administrator AI and System Performance Dashboard.
- Integrate and test API monitoring, retrieval-quality monitoring, response
  feedback, prompt monitoring and structured AI evaluation.
- Add prompt version management for general and project-specific assistance.
- Add SQLite vector embeddings, embedding-model metadata and hybrid retrieval.
- Add Administrator evaluation of response relevance, grounded accuracy,
  usability and hallucination occurrence.
- Add Word, Excel, PDF and PowerPoint response exports.
- Add WBS-style Gantt scheduling, Excel schedule import and automatic
  Gantt-to-Tasks backlog synchronisation.
- Add the AI-enabled Tasks board with CRUD operations and guarded AI actions.
- Add Administrator feature toggles for project-specific scheduling and Tasks
  capabilities.
- Add team-member directory validation, mentor/student role filtering and the
  four-student project-team limit.
- Add date pickers for milestones, meetings and Gantt schedule dates.
- Add metadata-only audit logging, response-verification status and robust
  Agentaus failure handling.
- Preserve GitHub and Streamlit Cloud deployment configuration and existing
  persistent application data.

**Status:** Performance Dashboard Complete

LMS integration is intentionally not included because the external LMS service
is not yet available. Existing local users, assignments, project records and
project documents remain the current source of truth.

## Development roadmap

The project will be developed over seven sprints. Version 4 / Sprint 4 is the
current implementation. Each subsequent sprint will add features, address
identified defects and receive a new entry in `CHANGELOG.md`.

## Current interface

- The dark-blue sidebar provides Assistant and Administration navigation.
- The sidebar can switch between General Capstone mode and a selected project.
- Project Workspace manages project overview, team members, milestones,
  meetings and project-specific documents.
- The assistant can answer with selected-project context while keeping project
  documents isolated from other projects.
- Administrators can open AI and system performance, prompt intelligence,
  prompt management and AI evaluation views.
- Assistant responses support Helpful / Not helpful feedback with optional
  comments; administrators can review monitoring and feedback data.
- Completed responses can be formatted and downloaded as Word, Excel, PDF or
  PowerPoint files.
- The three guidance cards remain visible above the conversation at all times.
- Assistant responses appear below the guidance cards.
- Source filenames, document locations and page references remain internal and
  are not displayed in assistant responses.
- Every page displays `Powered by Trellis Data (agentaus AI)` in the footer.
- The layout adapts to desktop and narrow screens and includes keyboard focus
  and reduced-motion accessibility styling.
- Project Workspace places Gantt immediately after Meetings and Tasks after
  Gantt when those features are enabled.
- Project milestones, meetings and Gantt schedule dates use date pickers;
  schedule finish dates cannot precede their start dates.
- Project mentors are selected from active Mentor accounts, while project team
  members are selected from active Student accounts. A project supports a
  maximum of four students.
- Administrators can download Gantt and user-account Excel templates.
- Administrators can preview and atomically import user accounts from the
  user-account Excel template; imported accounts must change their temporary
  passwords at first login.
- Newly created accounts support first-login temporary-password enforcement.
- Users can change passwords inside the authenticated app. Password recovery is
  handled through the administrator-issued reset-code workflow.

## What you need

- Windows 10/11 or a currently supported version of macOS
- Python 3.11 or newer
- Git, if cloning the repository
- Tesseract OCR 5
- An AgentAus API endpoint and API key
- A database account created with `manage.py`

## 1. Get the project

Clone the repository if it is available through Git:

```bash
git clone <repository-url>
cd ai-assisted-capstone-pms
```

If you received the project as a ZIP file, extract it and open a terminal in the
`ai-assisted-capstone-pms` folder.

## 2. Install Python

Download Python from <https://www.python.org/downloads/>. On Windows, select
**Add Python to PATH** in the installer.

Verify the installation:

```bash
python --version
```

On macOS, use `python3 --version` if `python` is not available.

## 3. Install Tesseract OCR

Tesseract is required for scanned and image-only PDFs. Digital PDFs can still be
read without OCR.

### Windows

Tesseract does not provide an official current Windows installer. The Tesseract
documentation lists the UB Mannheim builds as the commonly used Windows
installer: <https://tesseract-ocr.github.io/tessdoc/Installation.html#windows>.

1. Download and run the 64-bit Tesseract installer linked there.
2. Install the English language data when prompted.
3. Add the installation directory to the Windows `Path`. The usual directory is:

   ```text
   C:\Program Files\Tesseract-OCR
   ```

4. Close and reopen PowerShell, then verify:

   ```powershell
   tesseract --version
   tesseract --list-langs
   ```

The language list should include `eng`.

### macOS

Install Homebrew first if it is not already available: <https://brew.sh/>.
Then run:

```bash
brew install tesseract
tesseract --version
tesseract --list-langs
```

The language list should include `eng`.

## 4. Create a virtual environment

Using a virtual environment keeps this project's packages separate from other
Python projects.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell blocks activation, run this once in the current terminal and then
activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### macOS Terminal

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

## 5. Install the Python packages

With the virtual environment active:

```bash
python -m pip install -r requirements.txt
```

## 6. Configure the application

Create a local `.env` file in the project root, next to `app.py`, and add your
private configuration values:

```dotenv
AGENTAUS_API_KEY=replace-with-your-api-key
API_ENDPOINT=https://your-agentaus-host/api/v1/chat/completions
```

Do not commit or share `.env`. Ask the project owner for the test endpoint and
API key through an approved private channel.

Uploads are limited to 25 MB per file. Optional document-processing limits can
also be set:

```dotenv
MAX_DOCUMENT_PAGES=500
OCR_PAGE_TIMEOUT_SECONDS=30
MAX_PROJECT_PROFILE_CHARS=8000
```

## 7. Verify the setup

Confirm that Python can see Tesseract and load the application:

### Windows PowerShell

```powershell
python -c "import shutil; print(shutil.which('tesseract'))"
python -m py_compile app.py
```

### macOS Terminal

```bash
python -c "import shutil; print(shutil.which('tesseract'))"
python -m py_compile app.py
```

The first command should print a path rather than `None`.

### Run the automated tests

Install the development dependencies and run the regression suite:

```bash
python -m pip install -r requirements-dev.txt
pytest -q
```

## Password reset

For forgotten passwords, contact an administrator for a single-use reset code,
then choose **Forgot password?** on the sign-in page.

Existing installations upgrade safely to schema version 8 on startup. Existing
users, assignments, projects and password hashes are retained. The migration
does not import accounts or data from any other project.

## 8. Initialize accounts and start Capstone Assistant

SQLite initializes automatically, but an initial account must be created locally:

```bash
python manage.py init
python manage.py create-user --name "Local Administrator" --username admin@example.org --role Administrator
streamlit run app.py
```

Streamlit normally opens <http://localhost:8501> automatically. Keep the terminal
open while testing. Stop the application with `Ctrl+C`.

Always start Streamlit from the project root so it loads
`.streamlit/config.toml`. This file controls the dark-blue sidebar. If a theme
change does not appear, stop Streamlit completely, start it again from this
folder, and hard-refresh the browser.

Runtime project records are stored in SQLite at `project_data/capstone.sqlite3`, and project-specific
uploads are stored in `project_knowledge/<project-id>/`. These persistent data
folders are intentionally included in the repository so the deployed
application can initialise with its existing users and records. Review private
data carefully before sharing the repository. Environment files and
`.streamlit/secrets.toml` remain excluded from Git.

## 9. Suggested test procedure

1. Open **Assistant** and ask a general Capstone question.
2. Ask the same question using different wording—for example, use both “due” and
   “deadline”—and compare the answers.
3. Ask a short follow-up question to check conversation handling.
4. Sign in with an Administrator database account and open **Administration**.
5. Upload a small PDF, DOCX or XLSX document containing a unique test fact.
6. For OCR, upload a scanned/image-only PDF with clear printed English text.
7. Ask a question whose answer appears only in that uploaded file.
8. Remove test documents when finished.
9. Confirm that the three guidance cards remain visible after sending messages.
10. Confirm that the sidebar is dark blue and the footer says
    `Powered by Trellis Data (agentaus AI)`.
11. Submit Helpful or Not helpful feedback on a completed answer.
12. As an Administrator, open **AI Performance**, **Prompt Intelligence**,
    **Prompt Management** and **AI Evaluation** and confirm that empty and
    populated monitoring views render correctly.

The application deliberately does not show source filenames or page numbers to
end users.

## Knowledge files and indexing

- `knowledge_base/` contains the approved source documents.
- `knowledge_index/index.json` is the generated search index.
- Uploading or deleting a document through Administration rebuilds the index.
- The application also rebuilds a stale index when source files change.
- Each request first goes to an AgentAus LLM search planner. The planner uses
  recent conversation context to resolve natural questions and follow-ups into
  one or more standalone searches. Students do not need to say `Capstone`, use
  fixed keywords or know which document contains the answer.
- The planner can route clearly unrelated requests out of scope. Questions that
  could concern approved information—including terminology introduced by a new
  upload—are searched rather than rejected by a hard-coded keyword gate.
- Long project catalogues are indexed as complete project records as well as
  page chunks, so project IDs, titles, descriptions, scope and skills stay
  together across page breaks.
- General PDFs are retained by page, Word files by heading and table row,
  PowerPoint files by slide and table row, and Excel/CSV files in row-aware
  blocks with their column headers repeated. Text and Markdown files retain
  paragraph-aware overlapping context.
- Exact project IDs and titles bypass fuzzy ranking. Questions asking for all
  projects, lists or counts search the complete record set instead of a fixed
  top-k sample.
- Retrieval only selects and organises supporting context. Every user-facing
  assistant answer—including exact IDs, lists, counts, out-of-scope questions
  and questions with no retrieval matches—is composed through the AgentAus LLM
  API. There are no hardcoded assistant-answer fallbacks.
- Numbered project suggestions are randomly sampled from matching catalogue
  records. Within a user's current session, follow-ups such as "suggest 5 more"
  exclude projects already suggested, while the AgentAus LLM still composes the
  complete user-facing response from the newly selected records.
- The Administration page reports page coverage, OCR use, duplicate project
  IDs and incomplete project records after ingestion.
- Generated factual answers receive a groundedness review pass by default.
  Set `ENABLE_ANSWER_VALIDATION=false` only if reduced API usage is preferred
  over the additional verification step.
- Do not manually edit `knowledge_index/index.json`.

### SQLite vector retrieval

Each indexed information item is embedded and stored in the application SQLite
database. The default deployment-safe model is `hashing-v1`, a deterministic
384-dimensional local embedding model using word and phrase features. SQLite
stores the vector bytes, model name, dimensions and content hash; retrieval
combines these vector cosine scores with BM25, fuzzy matching and latent
semantic scores. This keeps document contents and embeddings local and avoids a
mandatory external model download on Streamlit Cloud.

The model can be configured with `EMBEDDING_MODEL_NAME` and the vector size with
`EMBEDDING_DIMENSIONS`. Re-indexing occurs automatically after document changes
or when the model configuration changes.

### API and retrieval monitoring

Administrators can inspect provider-call counts, success rates, latency,
failures, token usage, retrieval no-match rate, result counts, top scores,
retrieval latency and daily retrieval trends. The telemetry stores hashes and
metadata rather than question or response content in operational event tables.

## Retrieval, context budgeting and response streaming

The application does not send every uploaded file to AgentAus. Each student
request uses a bounded retrieval and compression pipeline:

1. AgentAus converts the request and recent conversation into one to four
   standalone search queries.
2. Local BM25, fuzzy matching and latent-semantic ranking select relevant
   indexed chunks. Neighbouring prose chunks are added when useful.
3. Large result sets are compressed to identifiers, titles and
   query-relevant excerpts before they enter the prompt.
4. The assistant creates a draft from the bounded internal context.
5. A groundedness pass checks the draft and streams the checked answer to the
   Streamlit chat interface.

The default model context window is treated as 128,000 tokens. Document context
is limited to an estimated 26,000 tokens, with separate reserves for system
instructions, conversation history and model output. The estimate deliberately
uses a conservative three UTF-8 bytes per token because AgentAus does not expose
its tokenizer. If retrieved items do not fit, the app records the omission and
instructs the model not to describe the response as complete. Conversation
history and the planner's filename inventory also have independent budgets.

PowerPoint slide text, tables, speaker notes and author-provided image or
diagram alt text are indexed. Image-heavy PDFs are processed through local OCR
when Tesseract is available. Diagrams without readable text or alt text should
be accompanied by a short written description before upload.

These values can be configured through `.env` locally or Streamlit secrets in
Community Cloud:

```dotenv
MODEL_CONTEXT_WINDOW_TOKENS=128000
MODEL_OUTPUT_TOKEN_RESERVE=8192
MODEL_PROMPT_TOKEN_RESERVE=12000
MAX_PRIVATE_CONTEXT_TOKENS=26000
MAX_CONVERSATION_HISTORY_TOKENS=6000
MAX_SOURCE_INVENTORY_TOKENS=2000
```

Search planning remains non-streaming because it returns a small JSON object.
For an in-scope answer, the draft is also kept hidden; only the factual-review
pass is streamed, preventing an unvalidated draft from appearing in the UI. If
answer validation is disabled, the initial answer is streamed directly. If the
AgentAus endpoint does not provide a valid event stream, the app falls back to
the existing complete JSON response before showing any text.

Authenticated administrators can open **AI Performance** to view **Recent AI
usage**, including token counts returned by AgentAus and the estimated document-context
budget for the most recent answer. These diagnostics are session-local and do
not contain prompts, document text, API keys or passwords.

## AI monitoring and evaluation

Version 4 records privacy-conscious operational metrics in SQLite, including
request timing, success or failure, assistant mode, prompt version, response
length and provider token usage when returned. Full submitted questions and
bounded completed response text are kept in restricted Administrator
monitoring records for evaluation and documentation analysis. Response text is
not exposed to ordinary users through the monitoring interface.

Only Administrators can access the performance dashboard, prompt intelligence,
prompt management, prompt archive and manual AI evaluation pages. Users may
submit feedback on their own completed responses, while Administrators can
review the resulting metrics and comments.

The monitoring and performance migrations add `prompt_versions`,
`ai_interactions`, `ai_prompt_archive`, `response_feedback`,
`ai_evaluations`, `api_service_events`, `retrieval_events`,
`document_embeddings`, `embedding_runs`, `gantt_plans`, `kanban_boards`,
`app_settings` and `project_audit_log` tables. Completed response text is
retained in a bounded Administrator-only monitoring field for evaluation. The
migrations do not replace the existing SQLite database or user records.

## Scheduling, Kanban and account lifecycle

Gantt schedules are project-scoped and validate hierarchical codes, dates,
progress, predecessor references and circular dependencies before saving.
Excel imports are transactional and can add/update tasks by code or replace a
schedule after confirmation. Imported and manually created tasks synchronise
to one Kanban Backlog card using the Gantt task ID or code as the stable link.
The schedule is displayed as a ProjectLibre/Microsoft Project-style task table
with WBS, duration, dates, dependencies, resources and completion percentage.
Moving a linked task through the Tasks workflow updates its schedule completion
from 0% in Backlog to 100% in Done.

The Kanban assistant accepts structured natural-language actions for creating,
moving and updating cards. It is restricted to the selected project and does
not execute ambiguous destructive actions through AI. Successful AI task-board
actions immediately refresh the current Tasks view.

Administrators can create accounts with username, first name, last name,
email, role, temporary password and status. New administrator-created users
must change their temporary password at first login. Existing users can change
their password from the authenticated workspace. Passwords are hashed and are
never stored in plain text.

## Response exports

Each completed assistant response includes an **Export this answer** control.
Agentaus first organises the response into a structured title, summary,
sections, bullets and tables without adding facts. The result can then be
downloaded as Word (`.docx`), Excel (`.xlsx`), PDF (`.pdf`) or PowerPoint
(`.pptx`).

Export files are generated in memory and are not stored in the local database
or uploaded to the repository.

## Troubleshooting

### `streamlit` is not recognised

Activate `.venv` and run:

```bash
python -m streamlit run app.py
```

### OCR is unavailable

Run `tesseract --version`. If it is not found, reinstall Tesseract or add its
installation directory to `Path`, then restart the terminal.

### `AGENTAUS_API_KEY` or `API_ENDPOINT` is not configured

Confirm that `.env` is next to `app.py`, contains the required values, and is
named exactly `.env` rather than `.env.txt`.

### Streamlit Cloud reports an API fetch failure

In Streamlit Community Cloud, open **App settings → Secrets** and set the
production values as TOML:

```toml
AGENTAUS_API_KEY = "your-api-key"
API_ENDPOINT = "https://your-public-agentaus-host/api/v1/chat/completions"
```

`API_ENDPOINT` takes precedence over `HOST_NAME`, so remove a stale endpoint or
replace it with the correct public HTTPS endpoint. The hostname must resolve
from the public internet; an internal, VPN-only, local, or misspelled hostname
cannot be reached by Streamlit Cloud. Save the secrets, reboot the app, and
check its logs for the reported HTTP status if the provider still rejects the
request.

### The browser cannot connect

Check that the terminal still shows Streamlit running and open
<http://localhost:8501>. If port 8501 is occupied:

```bash
streamlit run app.py --server.port 8502
```

### The sidebar is grey instead of dark blue

Stop the server with `Ctrl+C`, change into the project root, and restart it:

```bash
cd ai-assisted-capstone-pms
streamlit run app.py
```

The native sidebar theme is loaded only when Streamlit starts. Also confirm that
`.streamlit/config.toml` exists and hard-refresh the browser after restarting.

### A document is rejected

Confirm that it is a genuine `.pdf`, `.docx`, `.xlsx`, `.csv`, `.pptx`, `.txt`
or `.md` file, is within the configured size limit, and is not
password-protected.

## Privacy

Uploaded files may contain sensitive information. Use test documents without
personal or confidential data unless the deployment and AgentAus environment
have been approved for that data.
