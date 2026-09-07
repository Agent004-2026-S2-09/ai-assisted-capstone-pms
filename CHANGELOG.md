# Changelog

This file records notable features, fixes and documentation changes across the
project's seven-sprint delivery plan.

## Unreleased

Changes for Sprint 2 will be recorded here as development begins.

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
