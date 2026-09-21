# Changelog

This file records notable features, fixes and documentation changes across the
project's seven-sprint delivery plan.

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
