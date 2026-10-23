# Capstone Assistant

AI-assisted project management and knowledge retrieval for UC Canberra Capstone projects.

**Current release:** Version 7 — Sprint 7 complete; final demo-readiness verification recorded 21 October 2026
**Application:** Streamlit
**Sponsor:** Trellis Data — Agentaus AI

Capstone Assistant gives authorised students, mentors, convenors and administrators one place to manage Capstone project information, ask evidence-based questions, and monitor project activity. It combines local document retrieval, Agentaus AI, SQLite persistence, role-based access control and project-management workflows.

## Handover status

The prototype has completed the seven-sprint delivery plan. Sprint 6 covered system testing and User Acceptance Testing. Sprint 7 covered priority defect resolution, refinement, deployment preparation and post-deployment verification.

The current verification baseline is recorded in [Current project status](docs/technical-docs/current-project-status.md).

The current sponsor-review deployment is the Streamlit Community Cloud instance. The repository is also ready for local setup and handover using Docker.

## Current deployment

| Environment | Status | Entry point | Purpose |
| --- | --- | --- | --- |
| Streamlit Community Cloud | Current deployed instance | `app.py` | Sponsor demonstration, review and UAT |
| Docker | Supported local deployment | `app.py` | Reproducible handover and persistent local operation |

The Streamlit Community Cloud instance uses the repository's `app.py` entry point and configured Streamlit secrets. Its access URL and deployment credentials should be shared with authorised reviewers separately; they are not stored in this repository.

Docker remains the recommended setup when a reproducible local environment or persistent local data is required.

## Full system functionality

### AI assistant and knowledge retrieval

- Answers general Capstone questions from the approved general knowledge base.
- Answers project-specific questions from authorised project documents and structured project records.
- Supports questions about project identity, sponsors, mentors, teams, meetings, decisions, actions, milestones, schedules, Gantt tasks, Kanban tasks, requirements, dates and project knowledge.
- Supports follow-up questions using the current conversation context.
- Supports summaries, comparisons, report-style answers, table-style answers and broad information requests.
- Uses hybrid retrieval combining lexical, fuzzy, semantic and local vector signals.
- Supports `BAAI/bge-small-en-v1.5` neural embeddings when the optional neural dependencies are installed, with the retained deterministic `hashing-v1` backend for the current MVP/offline runtime.
- Builds bounded evidence context instead of sending the entire knowledge base with every request.
- Streams responses to the interface and records provider, latency, usage and failure metadata for administration.
- Performs grounded-response checks and provides safe fallback responses when information is missing, unsupported or unavailable.
- Detects export requests and prepares downloadable reports without adding unsupported facts.

### Document ingestion and knowledge management

- Supports PDF, DOCX, XLSX, CSV, PPTX, Markdown and plain-text files.
- Uses Tesseract OCR for scanned PDFs.
- Validates filenames, file types, duplicate uploads and extraction results before applying changes.
- Supports administrator-managed general knowledge uploads, deletion and reindexing.
- Supports project-scoped document uploads, replacement, deletion and isolated indexing.
- Uses atomic upload and index-rebuild behaviour so failed ingestion does not leave partial changes.
- Handles projects with structured records but no project documents safely.
- Detects knowledge changes and keeps generated indexes aligned with their source files.

### Project workspaces

- Provides project selection and project overview pages.
- Stores project identity, code, description, sponsor, mentor, team members and project metadata.
- Provides project-specific Knowledge, Meetings, Milestones, Gantt/Tasks and Team Discussion areas.
- Allows authorised users to create, edit and delete meetings, including dates, attendees, discussion, decisions and actions.
- Allows authorised users to manage milestones, target dates, status and notes.
- Derives milestone progress from authoritative linked Gantt task relationships.
- Provides persistent Team Discussion messages and replies with safe editing, deletion, access checks and audit logging.
- Provides date pickers and bounded fields for structured project records.

### Scheduling and task management

- Provides WBS-style Gantt scheduling with milestones, tasks, codes, dates, owners, status, progress and relationships.
- Supports task and milestone creation, editing and deletion.
- Supports Excel workbook import for schedule data, including controlled replacement workflows.
- Provides Kanban task boards with cards, details, columns and milestone links.
- Synchronises linked Gantt tasks and Kanban cards using authoritative task IDs and WBS codes.
- Keeps milestone progress, Gantt schedules and Kanban task status aligned where the relevant administrator feature flags are enabled.
- Provides guarded AI-assisted task actions where enabled by an Administrator.

### Authentication, authorisation and administration

- Provides database-backed login, logout and session restoration after browser refresh.
- Supports session expiry, password hashing, password reset and first-login password changes.
- Supports Student, Mentor, Convenor and Administrator permissions.
- Enforces assignment-based project access and prevents unauthorised cross-project retrieval.
- Allows non-student users to hold multiple permissions while keeping Student access exclusive.
- Allows administrators to create, edit, activate, disable and import user accounts.
- Supports account status, role, permission, profile and project-assignment administration.
- Provides operator password reset and safe account-management CLI commands.
- Provides administrator controls for approved knowledge, prompt versions, feature flags and support contact settings.

### Monitoring, evaluation and exports

- Provides API health, provider latency, request status, usage and failure monitoring.
- Provides retrieval-quality and vector-index health views.
- Provides response feedback capture and review.
- Provides RAG diagnostic quality and groundedness evaluation views.
- Provides prompt and topic intelligence, including question themes, trends, role breakdowns, general-versus-project usage and prompt exploration.
- Provides administrator prompt version management.
- Exports assistant responses to Word, Excel, PDF and PowerPoint.
- Preserves structured tables and readable report formatting in supported exports.

### Security, persistence and operations

- Stores application data in SQLite with additive migrations.
- Persists users, projects, assignments, sessions, meetings, milestones, tasks, comments, monitoring records and audit metadata.
- Uses project-scoped storage for uploaded documents and indexes.
- Records bounded operational metadata rather than unnecessary document content.
- Keeps provider credentials in environment variables or Streamlit secrets.
- Supports Docker deployment with Python 3.11, Streamlit and Tesseract OCR.
- Provides a Streamlit Community Cloud deployment for hosted review and a Docker workflow for reproducible local operation.

## AI models and retrieval architecture

The system separates document retrieval from answer generation. This means the local application selects relevant evidence first, and the external Agentaus service then generates the user-facing response from that bounded evidence.

### In plain English

- **BGE** is the system's search assistant. It converts documents and questions into a form that helps the application find information with similar meaning, even when different words are used.
- **Agentaus** is the system's writing assistant. It uses the question and the information found by BGE to write the final answer, summary or report.
- **Hashing** is a lightweight backup search method used when the BGE search model is unavailable or when the system is running in offline test mode.

### 1. Optional local neural embedding model: `BAAI/bge-small-en-v1.5`

**Function:** Converts document chunks and user questions into numerical vectors so semantically related content can be found even when the wording does not exactly match. These vectors support the local vector-similarity component of the hybrid retrieval pipeline.

**Runtime behaviour:**

- This is the optional neural embedding model when `sentence-transformers` is installed. It is not being enabled automatically for the current MVP baseline.
- It is used for both indexed document embeddings and query embeddings; the application does not run separate document and query models.
- Query embeddings use the model's query encoding method when available, with a search-instruction prefix for compatible versions.
- Embeddings are normalised and stored in the SQLite `document_embeddings` table.
- The application records the model name and vector dimensions with each embedding run.
- If the model name, vector dimensions or source content changes, stale vectors are automatically rebuilt.

**Code locations:**

- Model default and backend selection: [`app_modules/vector_store.py`](app_modules/vector_store.py), `DEFAULT_NEURAL_MODEL`, `backend_name()` and `model_name()`.
- Model loading and caching: [`app_modules/vector_store.py`](app_modules/vector_store.py), `_sentence_model()`.
- Document and query encoding: [`app_modules/vector_store.py`](app_modules/vector_store.py), `embed_texts()`.
- Embedding creation and refresh: [`app_modules/vector_store.py`](app_modules/vector_store.py), `rebuild_embeddings()` and `ensure_embeddings()`.
- Vector similarity scoring: [`app_modules/vector_store.py`](app_modules/vector_store.py), `score_documents()`.
- Embedding persistence schema: [`app_modules/database.py`](app_modules/database.py), the `document_embeddings` and `embedding_runs` tables.
- Neural embedding dependencies: [`requirements.txt`](requirements.txt), `torch` and `sentence-transformers`.

### 2. External answer-generation model: Agentaus

**Function:** Receives the system instructions, the user's question, conversation context and retrieved evidence, then generates the final answer. It is responsible for natural-language responses, summaries, comparisons, tables and report-style output.

**Runtime behaviour:**

- The application communicates with Agentaus through an OpenAI-compatible chat-completions endpoint.
- Agentaus is used for search planning, response generation, response validation and export formatting where those workflows require AI assistance.
- Responses can be streamed to the user interface.
- API latency, status, token usage and failures are recorded for administrator monitoring.
- The exact underlying generation model is selected by the Agentaus service and is not hard-coded in this repository.
- The application does not send the entire knowledge base to the provider. It sends bounded, retrieved evidence together with the relevant project context and conversation history.

**Code locations:**

- Provider endpoint and credential configuration: [`app.py`](app.py), `HOST_NAME`, `AGENTAUS_API_KEY` and `API_ENDPOINT`.
- Provider requests, streaming and error handling: [`app_modules/services/ai_client.py`](app_modules/services/ai_client.py), `call()` and `stream()`.
- Prompt and message construction: [`app.py`](app.py), `build_api_messages()` and the response-generation workflow.
- Evidence and context budgeting: [`app.py`](app.py), `build_bounded_model_context()` and the `MODEL_*_TOKENS` settings.
- Provider telemetry: [`app_modules/monitoring.py`](app_modules/monitoring.py) and the AI performance page in [`app_modules/ui/pages/performance.py`](app_modules/ui/pages/performance.py).

### 3. Offline embedding fallback: `hashing-v1`

**Function:** Provides a deterministic, dependency-light vector representation when the neural embedding stack is unavailable or when offline operation is required.

**Runtime behaviour:**

- It is not a second model running alongside BGE.
- It is selected automatically when `sentence-transformers` is unavailable, or explicitly with:

```dotenv
EMBEDDING_BACKEND=hashing
```

- It uses scikit-learn's `HashingVectorizer` with word and word-pair features.
- Automated tests use this backend so tests remain repeatable and do not download a neural model.
- The retrieval contract and SQLite storage remain the same when switching between BGE and `hashing-v1`; model metadata causes stale vectors to be rebuilt.

**Code locations:**

- Fallback selection: [`app_modules/vector_store.py`](app_modules/vector_store.py), `DEFAULT_HASHING_MODEL` and `backend_name()`.
- Hashing vectoriser: [`app_modules/vector_store.py`](app_modules/vector_store.py), `_vectorizer()`.
- Test configuration: [`tests/conftest.py`](tests/conftest.py), which sets `EMBEDDING_BACKEND=hashing`.

### Model count at runtime

The architecture has two model responsibilities:

1. One local embedding backend. The current verified MVP runtime uses `hashing-v1`; BGE remains an optional, explicitly selected alternative.
2. One external Agentaus answer-generation model, whose exact provider-side name is not exposed by this repository.

`hashing-v1` is an alternative embedding backend, not an additional concurrently running model. The system does not contain a second local language model or a separate reranking model.

## Roles and access

Access is enforced using the authenticated database session, role and project assignments.

| Role | Access summary |
| --- | --- |
| Student | Accesses assigned projects and maintains permitted project content. |
| Mentor | Accesses assigned project teams. |
| Convenor | Oversees Capstone projects. |
| Administrator | Manages users, approved knowledge, monitoring, prompts, evaluations and settings. |

Project-specific retrieval is isolated to the authorised project selected by the user. Provider credentials are supplied through environment variables or Streamlit secrets and must never be committed to the repository.

## Quick start with Docker

### Prerequisites

Install:

- Docker Desktop or Docker Engine with the Docker CLI.
- Git.
- An Agentaus-compatible API endpoint and API key.

### 1. Clone the repository

```bash
git clone <repository-url>
cd ai-assisted-capstone-pms
```

### 2. Create the local environment file

Create a file named `.env` in the repository root. Replace the placeholder values with the credentials supplied for the deployment environment.

```dotenv
AGENTAUS_API_KEY=replace-with-your-api-key
API_ENDPOINT=https://your-agentaus-host/api/v1/chat/completions
```

Do not commit `.env`, API keys, passwords or Streamlit secrets. The repository `.gitignore` already excludes these files.

### 3. Build the Docker image

```bash
docker build -t capstone-assistant .
```

The image installs Python dependencies and Tesseract OCR. The application listens on port `8501` inside the container.

### 4. Initialise the database

Run the database initialisation once. The mounted directories ensure the database and uploaded project data remain on the host.

```bash
docker run --rm \
  --env-file .env \
  -v "$(pwd)/project_data:/app/project_data" \
  -v "$(pwd)/project_knowledge:/app/project_knowledge" \
  capstone-assistant \
  python scripts/manage.py init
```

### 5. Create the first administrator account

The command prompts for the administrator password and does not display or store it in the terminal history.

```bash
docker run --rm -it \
  --env-file .env \
  -v "$(pwd)/project_data:/app/project_data" \
  -v "$(pwd)/project_knowledge:/app/project_knowledge" \
  capstone-assistant \
  python scripts/manage.py create-user \
  --name "Local Administrator" \
  --username admin@example.org \
  --role Administrator
```

Use a password of at least 12 characters when prompted.

### 6. Start the application

```bash
docker run --rm \
  --name capstone-assistant \
  -p 8501:8501 \
  --env-file .env \
  -v "$(pwd)/project_data:/app/project_data" \
  -v "$(pwd)/project_knowledge:/app/project_knowledge" \
  capstone-assistant
```

Open [http://localhost:8501](http://localhost:8501) in a browser and sign in with the administrator account created above.

The container health endpoint is [http://localhost:8501/_stcore/health](http://localhost:8501/_stcore/health). A healthy container returns HTTP 200.

To stop the application, press `Ctrl+C` in the terminal running the container.

## Data persistence

The Docker commands above mount the runtime directories on the host:

| Directory | Contents | Keep backed up? |
| --- | --- | --- |
| `project_data/` | SQLite database, project records, accounts, sessions and logs | Yes |
| `project_knowledge/` | Project-specific uploaded documents and indexes | Yes |
| `knowledge_base/` | Approved general Capstone source documents | Yes |
| `knowledge_index/` | Generated general-knowledge retrieval index | Rebuildable |

Do not edit `knowledge_index/index.json` manually. Uploading or removing approved knowledge through the application rebuilds the relevant index. SQLite migrations are additive and preserve existing users, assignments and project records.

## Local Python setup without Docker

Docker is the recommended handover path. For development without Docker, use Python 3.11 or newer and install Tesseract OCR separately.

```bash
python -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/manage.py init
python scripts/manage.py create-user --name "Local Administrator" \
  --username admin@example.org --role Administrator
python -m streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501). Start Streamlit from the repository root so the project paths and configuration are loaded correctly.

## Verification and testing

Run the full automated suite from the repository root:

```bash
pytest -q
python -m compileall -q app.py app_modules tools
python -m pip check
```

Verification records and historical test artefacts are retained in `docs/test/`.

For the offline retrieval benchmark:

```bash
python tools/qa_benchmark.py
```

The merged test-question index is stored in `docs/test/`. It contains questions and classification metadata only; do not add secrets, passwords, session tokens or private document contents to future test artefacts.

## Configuration

Required environment variables:

| Variable | Purpose |
| --- | --- |
| `AGENTAUS_API_KEY` | API credential for Agentaus requests. |
| `API_ENDPOINT` | Agentaus-compatible chat-completions endpoint. |

Optional configuration includes document-page limits, OCR timeouts, project-profile limits, answer validation and context-budget settings. The application can use `BAAI/bge-small-en-v1.5` for neural embeddings. Set `EMBEDDING_BACKEND=hashing` for an offline, dependency-light fallback.

## Repository structure

| Path | Responsibility |
| --- | --- |
| `app.py` | Streamlit entry point and application facade |
| `app_modules/database.py` | SQLite persistence and additive migrations |
| `app_modules/auth.py` and `access_control.py` | Authentication, sessions and authorisation |
| `app_modules/services/ai_client.py` | Agentaus requests and provider telemetry |
| `app_modules/vector_store.py` | Local embeddings and hybrid retrieval |
| `app_modules/monitoring.py` | AI, API and retrieval monitoring |
| `app_modules/gantt.py`, `kanban.py`, `milestones.py` | Scheduling and task workflows |
| `app_modules/exporting.py` and `export_ui.py` | Response export generation |
| `app_modules/ui/` | Shared UI and administrator pages |
| `scripts/manage.py` | Account and database administration CLI |
| `knowledge_base/` | Approved general Capstone documents |
| `knowledge_index/` | Generated general retrieval index |
| `project_data/` | SQLite database and project records |
| `project_knowledge/` | Project-specific uploads and indexes |
| `docs/test/` | Generated test reports, checkpoints and verification results |
| `docs/technical-docs/` | Technical guides and operational documentation |
| `docs/sprints/` | Sprint delivery records |

## Sprint delivery history

| Sprint | Delivery focus | Completed outcomes | Status |
| --- | --- | --- | --- |
| 1 | General Capstone Assistant | Developed general Capstone knowledge processing and retrieval, the administrator knowledge-base feature, and the Agentaus AI general assistant interface. | Complete |
| 2 | Project-Specific Assistant | Developed project workspaces and project knowledge bases; implemented project-specific and combined retrieval; added teams, meetings and milestones. | Complete |
| 3 | Database, Login & User Access | Implemented SQLite persistence, authentication, Student/Mentor/Convenor/Administrator privileges, project assignments and access-boundary testing. | Complete |
| 4 | AI & System Performance Dashboard | Defined AI monitoring and evaluation metrics; developed the administrator AI/system performance dashboard; integrated feedback and prompt monitoring. | Complete |
| 5 | Integration & Dockerisation | Integrated modules and resolved integration defects; Dockerised and configured the application; tested and documented the containerised prototype. | Complete |
| 6 | System Testing & UAT | Conducted functional, AI, access-control and performance testing; completed User Acceptance Testing; recorded and resolved priority defects identified during verification. | Complete |
| 7 | Refinement & Prototype Deployment | Refined the prototype, prepared the deployment environment, deployed the current Streamlit Community Cloud instance and completed post-deployment verification. | Complete |

The sprint plan is complete. The current handover baseline is the Sprint 7 application: Streamlit Community Cloud for hosted sponsor review, with Docker available for reproducible local operation.

See the [Sprint delivery records](docs/sprints/) and [technical documentation](docs/technical-docs/) for the detailed release and handover material.

## Troubleshooting

**The browser cannot connect**
Confirm the container is running and that port `8501` is available. Check the health endpoint and run `docker logs capstone-assistant` if the container was started with `--name capstone-assistant`.

**Agentaus requests fail**
Check `AGENTAUS_API_KEY` and `API_ENDPOINT` in `.env`. Do not put credentials directly in source files.

If an AI request fails, the application shows a safe user-facing message, records the failure for administrators and changes the AI service indicator to offline/red. A reachable health probe does not guarantee that every provider generation or validation request is available.

**OCR is unavailable**
The Docker image installs Tesseract. For a non-Docker setup, install Tesseract separately and verify it with `tesseract --version`.

**The database or uploaded documents disappear after restart**
Start the container with the `project_data` and `project_knowledge` volume mounts shown above. Without these mounts, data inside a removed container is not retained.

**An upload is rejected**
Use a supported, non-password-protected PDF, DOCX, XLSX, CSV, PPTX, TXT or MD file within the configured upload limit.

## Scope and limitations

This is a prototype and does not include LMS integration, enterprise orchestration or production hosting configuration. Local accounts, assignments and project records remain the current source of truth. AI output supports formal academic, mentor and stakeholder decisions; it does not replace them.

The current MVP uses `hashing-v1` for deterministic local embeddings unless the neural backend is explicitly installed and selected. Independent AI response validation depends on the provider being available. A real Chromium browser run remains an environment-dependent check; browser-level verification should be repeated from a machine with a working Chromium installation before a production deployment.
