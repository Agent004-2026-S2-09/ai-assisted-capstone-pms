# Changelog

Concise release history for the seven-sprint Capstone Assistant delivery plan.

## Version 5 — Sprint 5 — 2026-10-09

**Focus:** Integration & Dockerisation

**Status:** Complete

- Integrated the assistant, workspace, authentication, monitoring, retrieval,
  scheduling, Tasks and export modules behind the existing Streamlit entry point.
- Built a Python 3.11 slim Docker image with Tesseract OCR and all runtime
  dependencies.
- Configured Streamlit for container access on `0.0.0.0:8501`.
- Documented environment configuration, data mounts, image build and startup.
- Preserved SQLite and project-upload data as external runtime data.
- Added [`docs/sprint_5_integration_dockerisation.docx`](docs/sprint_5_integration_dockerisation.docx).

**Verification:** Docker image build succeeded, the container health endpoint
returned HTTP 200, and all 111 automated tests passed.

## Version 4 — Sprint 4 — 2026-10-04

**Focus:** AI & System Performance Dashboard

**Status:** Complete

- Added Administrator monitoring for Agentaus API health, retrieval quality,
  vector-index health, feedback, prompt intelligence and AI evaluation.
- Added prompt version management, grounded-response status and bounded
  response monitoring.
- Added SQLite vector embeddings and hybrid retrieval.
- Added Word, Excel, PDF and PowerPoint response exports.
- Added WBS Gantt scheduling, Excel import, Kanban synchronisation and guarded
  Kanban AI actions.
- Added feature toggles, account import, temporary-password workflows, team
  validation, date pickers and metadata-only audit logging.
- Preserved existing users, projects, assignments and deployment settings.

**Verification:** 98 tests passed at the Sprint 4 release point; Python
compilation, Streamlit navigation, database migration and deployment checks
completed successfully.

## Version 3 — Sprint 3

**Focus:** Database, Login & User Access

**Status:** Complete

- Added SQLite persistence for users, projects, assignments, sessions and
  application records.
- Added database-backed authentication, session expiry, password hashing,
  reset codes and first-login password changes.
- Added Student, Mentor, Convenor and Administrator access rules.
- Added assignment-based project isolation and Administrator-only controls.
- Added additive migrations that preserve existing identity and project data.

## Version 2 — Sprint 2 — 2026-09-14

**Focus:** Project Workspace

**Status:** Complete

- Added project creation, selection and profile management.
- Added team members, meetings, milestones and project documents.
- Added project-scoped storage, indexing and retrieval isolation.
- Added context budgeting, streamed responses and project question trends.
- Added upload validation, rollback behaviour and project-access checks.

## Version 1 — Sprint 1 — 2026-09-07

**Focus:** General Capstone Assistant

**Status:** Complete

- Added the Streamlit assistant and Agentaus integration.
- Added local ingestion and retrieval for PDF, DOCX, XLSX, CSV, PPTX,
  Markdown and text files.
- Added Tesseract OCR support for scanned PDFs.
- Added Administrator knowledge-base upload, delete and reindex workflows.
- Added initial regression coverage for ingestion, retrieval, provider errors
  and response handling.
