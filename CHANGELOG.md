# Changelog

This file records notable features, fixes and documentation changes across the
project's seven-sprint delivery plan.

## Version 4 — Sprint 4 — 2026-10-04

**Sprint:** AI & System Performance Dashboard
**Status:** Complete

### Sprint commitments

- Define and implement AI monitoring and evaluation metrics.
- Develop the Administrator AI and System Performance Dashboard.
- Integrate and test dashboard, response feedback and prompt monitoring.
- Complete the performance dashboard while preserving existing workflows.

### Added

- Administrator-only AI and system performance dashboard.
- Privacy-conscious AI interaction monitoring with latency, success/failure,
  prompt-version and token metadata.
- Helpful / Not helpful response feedback with optional comments.
- Administrator prompt and topic intelligence, including trends and prompt
  exploration.
- Administrator prompt version management with active-version history.
- Administrator manual AI response evaluation for relevance, grounded accuracy
  usability, and hallucination detection.
- AI-formatted response exports to Word, Excel, PDF and PowerPoint.
- Native in-memory document generation with structured sections, bullets and
  tables.
- SQLite-backed document vector embeddings with automatic stale-index rebuilds.
- Configurable deployment-safe embedding model metadata and vector dimensions.
- Hybrid retrieval that combines SQLite vector similarity with lexical,
  fuzzy and latent-semantic ranking.
- API service telemetry covering provider latency, status, failures and token
  usage.
- Retrieval quality telemetry covering no-match rate, result counts, top-score
  quality and retrieval latency.
- Administrator dashboard panels for API health, retrieval quality and vector
  embedding index health.
- Explicit Administrator usability scoring for evaluated AI responses, with an
  additive SQLite migration that preserves existing evaluation records.
- Improved multi-stage response handling with bounded context, complete
  document reporting and grounded response validation.
- Project-aware AI context now includes authorized Gantt schedule records and
  Tasks board cards, in addition to project metadata, team, milestones,
  meetings, indexed files and SQLite vector retrieval.
- Project Workspace Gantt scheduling tab positioned immediately after Meetings.
- AI-enabled project Kanban task board positioned immediately after Gantt.
- Hierarchical Gantt task codes such as `1`, `1.1` and `1.2`.
- Transactional Excel Gantt import with validation, preview-ready template and
  automatic Kanban Backlog synchronisation.
- Administrator-downloadable Gantt and user-account Excel templates.
- Persistent Administrator feature toggles for Gantt, Kanban, Kanban AI,
  Excel import, backlog synchronisation and user creation.
- Expanded administrator user fields for username, first name, last name,
  email, role, temporary password and status.
- First-login temporary-password enforcement and authenticated in-app password
  changes.
- Project team selectors restricted to active Student accounts, mentor selectors
  restricted to active Mentor accounts, and a four-student project-team limit.
- Tasks board and Gantt presentation aligned with the project workspace visual
  design, including reference-style KPI, task-sheet and draggable-card layouts.
- Gantt schedule presented as a WBS task table without timeline drawings, with
  deterministic Kanban-stage synchronization from 0% to 100% completion.
- Added administrator user-account Excel preview/import with atomic validation,
  duplicate protection and first-login password enforcement.
- Kanban AI mutations now preserve a confirmation notice and refresh the board
  immediately after successful actions.
- Additive SQLite schema migration preserving existing users, projects and
  assignments.
- UC Canberra branding, visual theme and responsive layout applied throughout
  the application.

### Security and compatibility

- All dashboard, prompt, archive and evaluation reads and writes enforce live
  Administrator authorization.
- Existing users and password hashes are retained.
- Student write permissions are now enforced at the persistence boundary: students
  may maintain project content (meetings, milestones and documents) but cannot
  change project identity, profile, mentor or team membership.
- Project profile, document, schedule and Tasks-board changes now produce bounded
  metadata-only audit records; prompts, answers, document contents and passwords
  are not written to the audit trail.
- Streaming Agentaus connection and HTTP failures now record failed service
  telemetry before returning the existing safe user-facing error path.
- Grounded-response validation now exposes whether verification was completed,
  disabled or unavailable, rather than silently treating a validation outage as
  a verified answer.
- Added operational indexes for project audit queries through additive schema
  migration 7; no existing identity, project or assignment records are removed.
- Replaced free-text project milestone, meeting and Gantt schedule date fields
  with date pickers, including finish-date constraints and legacy date-format
  compatibility.
- Added Administrator-only captured AI response display to the evaluation page;
  completed responses are retained in bounded monitoring records through
  additive schema migration 8, while older interactions remain available with
  an explicit response-unavailable notice.
- Streamlit Cloud configuration and existing AgentAus settings are preserved.
- Added the `reportlab` runtime dependency for PDF generation.
- Updated repository rules so persistent SQLite, project-record and
  project-knowledge files remain deployable, while environment and Streamlit
  secret files remain excluded.

### Verification

- 98 automated tests pass, including monitoring, feedback, prompt authorization,
  project-scope isolation, vector retrieval, structured project AI context,
  database migration and Streamlit navigation checks.
- Python compilation succeeds.
- Streamlit starts successfully with the existing `app.py` entry point.
- Existing database identity counts remain unchanged after migration.

## Version 3 — Sprint 3

**Sprint:** Database, Login & User Access
**Status:** Complete

### Sprint commitments

- Design and implement the SQLite database.
- Implement user authentication.
- Implement Student, Mentor, Convenor and Administrator privileges.
- Test authentication and project access.
- Complete the database and access-control foundation.

### Completed

- SQLite persistence for users, projects, assignments, sessions and related
  application records.
- Database-backed user authentication with protected login sessions.
- Role-based Student, Mentor, Convenor and Administrator privileges.
- Assignment-based project access controls and administrator-wide oversight.
- Authentication, authorisation and project-access regression testing.

## Version 2 — Sprint 2 — 2026-09-14

**Sprint:** Project Workspace  
**Status:** Complete

### Sprint commitments

- Add project creation, editing, deletion and selection.
- Store project profiles, team members, milestones and meeting notes.
- Support project-specific document uploads and isolated project indexes.
- Restrict students and mentors to their assigned project teams.
- Use a two-step retrieval process for the 128K context-window limit: search
  first, then compress selected documents into query-relevant excerpts.
- Stream longer assistant responses progressively when processing takes longer.
- Index lecture-slide text, tables, notes and author-provided image or diagram
  descriptions.
- Let the assistant answer with selected-project context while preserving the
  Sprint 1 general assistant path.
- Capture question trends for mentor and administrator review.
- Test, review and document Sprint 2.

### Added

- Project workspace mode with project overview, team, milestone, meeting and
  document-management views.
- Prototype role selector with Student, Mentor, Convenor and Administrator
  project-access filtering.
- Local project records stored in `project_data/projects.json`.
- Local question trend logging stored under `project_data/` for mentor and
  administrator review.
- Project-specific uploads stored under `project_knowledge/<project-id>/`.
- Separate project knowledge indexes with stale-index detection and rebuilds.
- Project profile context for selected-project assistant conversations.
- Project-scoped retrieval so one project's documents are not returned for
  another selected project.
- Context-budget controls for the 128K model window, including compressed
  snippets and omission tracking when too many results are retrieved.
- Streaming response support with fallback to the existing complete-response
  path if the provider does not return a valid event stream.
- PowerPoint image and diagram alt text extraction for searchable slide context.
- Sidebar and Administration interface panels summarising the Sprint 2
  improvements requested after sponsor/mentor review.
- Streamlit Cloud troubleshooting guidance for unreachable AgentAus endpoints.

### Fixed

- AgentAus connection, timeout and HTTP failures now return safer actionable
  messages instead of leaking raw provider errors.
- Project document upload failures roll back files and index state.
- Project updates reject stale concurrent edits through revision checks.

### Security and reliability

- Added project identifier validation to prevent path traversal.
- Added assignment-based project access checks for student and mentor project
  selection.
- Added process and file locking around project record writes.
- Added `.gitignore` protection for local project data and project uploads.
- Project deletion removes associated project data and project knowledge
  folders transactionally.

### Verification

- All automated tests pass at the Sprint 2 release point.

## Version 1 — Sprint 1 — 2026-09-07

**Sprint:** General Capstone Assistant  
**Status:** Complete

### Sprint commitments

- Develop general Capstone knowledge processing and retrieval.
- Develop the Administrator knowledge-base feature.
- Integrate AgentAus AI and the general assistant interface.
- Test, review and document Sprint 1.
- General Capstone Assistant complete.

### Added

- General UC Canberra Capstone question-and-answer interface built with
  Streamlit.
- AgentAus AI integration for search planning, response generation and factual
  answer validation.
- LLM-driven interpretation of natural questions and conversation-aware
  follow-ups without requiring a fixed activation keyword.
- Local processing and indexing for PDF, DOCX, PPTX, XLSX, CSV, Markdown and
  text documents.
- Local Tesseract OCR support for scanned and image-only PDF pages.
- Hybrid document retrieval with exact project ID and title handling,
  structured catalogue records, lexical ranking and local semantic matching.
- Password-protected Administrator area for uploading, deleting and reindexing
  approved information.
- Administration ingestion reporting for extraction coverage, OCR usage,
  incomplete project records and duplicate project IDs.
- Responsive assistant interface, persistent guidance cards and accessibility
  styling.
- Automated regression tests for ingestion, retrieval, upload safety, project
  discovery, LLM answer generation and follow-up search planning.

### Fixed

- Newly uploaded documents are immediately rebuilt into the searchable index.
- Natural questions about uploaded information no longer require the word
  “Capstone” to reach document search.
- Follow-up requests can be resolved by the LLM using recent conversation
  history.
- Failed uploads and failed index rebuilds roll back without replacing valid
  existing documents.
- Source filenames, internal locations and page references are removed from
  student-facing answers.

### Security and reliability

- Added atomic document writes and transactional upload rollback.
- Added upload type, size and Office archive validation.
- Added knowledge-base signatures to detect stale indexes.
- Added `.gitignore` protection for `.env`, Streamlit secrets, virtual
  environments, caches, logs and editor files.
- Constrained generated factual answers to approved retrieved information.

### Verification

- Python compilation succeeds.
- All 20 automated tests pass at the Sprint 1 release point.
