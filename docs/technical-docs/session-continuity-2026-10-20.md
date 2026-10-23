# Capstone assistant — session continuity record

**Date:** 20 October 2026  
**Workspace:** /home/cbah/projects/ai-assisted-capstone-pms  
**Purpose:** Preserve the complete working context so a future session can resume without repeating the investigation.

## User requirements and operating constraints

- The application must support an effectively unlimited range of student natural-language questions.
- Fixes must be system-wide and reusable, not question-specific, document-specific or record-specific patches.
- Database-backed facts must remain authoritative for exact project facts, counts, dates, statuses, relationships and workflow state.
- General Capstone questions must use natural-language document retrieval.
- Project questions must use authorised project records and project documents without leaking data across projects.
- Follow-up questions, paraphrases, typos, implicit references and multi-document questions must be supported.
- Do not add more documents until the system is stable.
- Do not push to GitHub unless the user explicitly authorises it. No GitHub push was made during this work.
- Preserve existing work and avoid destructive broad commands.
- When a reported failure is fixed, test unseen variations and the neighbouring failure class.

The permanent engineering principles are in:

docs/technical-docs/system-wide-engineering-principles.md

## Main problem identified

The core issue was not a single missing document or a single bad prompt. The application had several routing boundaries:

1. Natural-language document questions use the Agentaus search planner and local hybrid retrieval.
2. Exact project facts use structured project records.
3. Project profile context was previously activated mainly by keyword patterns.
4. Meeting selection such as “first meeting” or “last meeting” was not resolved deterministically from dates.
5. Questions that included words such as “report” could be classified as document questions before the relevant project record was considered.

This caused the application to:

- retrieve an older meeting for “last meeting”;
- ask for clarification when “first meeting” was already determinable;
- rely on the model to infer database ordering from context;
- make a system intended for arbitrary student language depend too heavily on lexical triggers.

The data existed. The failure was query interpretation and routing.

## RAG and tokenisation findings

The current RAG pipeline:

- extracts documents into plain text;
- preserves structured table blocks and project catalogue records;
- splits prose using character-based chunks with overlap;
- embeds indexed chunks using the deterministic hashing backend;
- stores original chunk text, metadata, content hashes and embedding bytes in SQLite;
- performs local lexical retrieval with token normalisation/stemming;
- performs vector similarity retrieval;
- uses Agentaus for search planning and answer generation;
- uses a validation pass when enabled.

Important distinction:

- Text is tokenized internally by embedding and language models.
- SQLite does not store token IDs for every document/database field.
- Chunk boundaries are character-based rather than exact provider-token-based.
- Context budgeting uses a conservative byte-based estimate because the Agentaus tokenizer is not exposed locally.

Token-aware chunking could improve budget predictability, but it is not sufficient by itself. Reliability depends more heavily on authoritative source selection, structured-record routing, retrieval coverage, conflict handling and answer validation.

## Knowledge-base cleanup completed

The active knowledge folders were inspected before cleanup.

Verified:

- The exact hidden backup teaching-weeks file was already absent.
- The duplicate project-list PDF was already absent.
- The general CSV versions that had been converted to PDFs were already absent.
- The project-specific obsolete file below was removed from the active knowledge folder:

project_knowledge/ai-assisted-capstone-project-assistant/Assessments_S2_2026.csv

For recoverability, it was moved to:

/tmp/capstone-removed-20261020/Assessments_S2_2026.csv

A database backup made before the project-index rebuild is also in that quarantine directory:

/tmp/capstone-removed-20261020/capstone.sqlite3.before-index-rebuild

The project index was rebuilt successfully:

- indexed documents: 84
- parser errors: none
- CSV references in the project index: none

The general index was checked:

- indexed documents: 874
- CSV sources: none
- old duplicate project-list source: none

SQLite integrity check passed:

PRAGMA integrity_check = ok

The teaching-weeks DOCX files were deliberately not blindly deleted. The remaining copies are not byte-identical and contain different calendar text. Deleting one without resolving which calendar is authoritative would be unsafe.

## Query-layer work completed

### Natural-language meeting selection

The structured project query path now resolves meeting records by meaning and date order rather than relying on one complete sentence.

Supported examples include:

- “write a detailed report of our most recent mentor session”
- “what happened in the first meeting?”
- “summarise the 2nd meeting”
- “what did we agree in the previous session?”

The resolver:

- identifies meeting/session/minutes-style entities;
- sorts authorised meeting records by date;
- resolves first/earliest/initial/opening;
- resolves last/latest/most recent/newest/current/previous/prior;
- resolves numeric ordinals such as 2nd;
- returns the selected record’s date, title, attendees, discussion, decisions, actions and mentor comment where present;
- refuses to invent a meeting when the requested selection has no matching record.

This is schema-driven record selection, not a hardcoded answer for a specific meeting.

### Broad project context

The project profile context path was changed so a selected project is treated as an authorised information scope rather than being activated only when the question contains terms such as “meeting,” “team” or “milestone.”

For non-document project questions, the bounded authoritative project profile is now supplied to the answer planner. This supports indirect natural language such as:

- “what did we agree last time?”
- “who is responsible for this?”
- “what is happening with our project?”

The profile includes the selected project’s authorised records. Document-specific questions remain on the project-document retrieval path, so the project profile is not used as a substitute for a proposal, charter, assessment file or other document.

### General Capstone area

The general Capstone path already uses an Agentaus natural-language search planner. Its contract instructs the planner to:

- understand paraphrases without requiring the word “Capstone”;
- resolve follow-up references from recent user questions;
- use synonyms;
- preserve exact IDs, dates, quantities and names;
- search approved content rather than depend on filenames;
- keep multi-document and complete-list requests bounded and auditable.

The general retrieval path also has a local fallback search for the original question so a weak planner synonym does not automatically eliminate relevant evidence.

## Tests and verification

Added regression coverage for natural-language meeting selection, including:

- most recent meeting;
- first meeting;
- numeric second meeting;
- date-ordered authoritative selection;
- report/detail output.

Verification completed:

- Python compilation passed.
- tests/test_app.py and tests/test_sprint3.py: 132 passed, 1 skipped.
- The prior targeted query tests passed.
- SQLite integrity passed after index rebuild.

## Files changed or relevant

- app.py
  - project structured-query routing;
  - natural-language meeting selection;
  - broader project profile context;
  - existing extraction, RAG and project-record logic remains in the same entry point.
- tests/test_sprint3.py
  - natural-language meeting selection regression tests.
- docs/technical-docs/system-wide-engineering-principles.md
  - permanent no-bandaid and open-ended-language requirements.
- docs/technical-docs/session-continuity-2026-10-20.md
  - this handover record.
- knowledge_index/index.json
  - rebuilt/updated knowledge index state.
- project_data/ai-assisted-capstone-project-assistant/index.json
  - rebuilt project index state.
- project_data/capstone.sqlite3
  - rebuilt embedding state and project-index records.

## Important limitations still to address

This work improves the shared routing boundary but should not be described as proof that every possible student question is solved.

Remaining maturity work:

1. Replace remaining scattered lexical entity/operation checks with one validated query representation shared by project records and document retrieval.
2. Add structured natural-language planning for project database operations beyond meetings, including team, milestones, tasks, Kanban, Gantt and project fields.
3. Improve follow-up resolution when a question combines a previous document answer with a current project record.
4. Add date parsing and explicit filters for natural phrases such as “before the break,” “during Week 10,” “the meeting after the proposal” and “the task linked to that milestone.”
5. Add unseen-paraphrase benchmarks for both general and project areas.
6. Add conflict tests where database records and documents disagree.
7. Verify the running Streamlit application manually after restarting or refreshing it; unit tests do not replace browser-level role and UI checks.
8. Reconsider exact provider-token budgeting once the Agentaus tokenizer or token-usage contract is available.
9. Run the complete repository test suite before calling the full query overhaul complete.

## Recommended next-session starting point

1. Read this file and system-wide-engineering-principles.md.
2. Inspect git status; do not discard existing user changes.
3. Run the affected tests before editing.
4. Build the shared structured query-plan abstraction for all project record types.
5. Add paraphrase, typo, follow-up, cross-source and permission-boundary tests.
6. Run the complete test suite.
7. Do not push to GitHub without explicit user approval.

## Explicit status

The application has not been pushed to GitHub by this session. The current work is local only.

## Saved decision: hybrid evidence architecture

The agreed direction is not to replace or destroy the existing RAG system.
Vector embeddings, the vector store, lexical retrieval, query planning,
follow-up resolution, evidence validation, conflict detection, permission
checks and monitoring all remain part of the application.

The AI should remain the final conversational response layer so answers do not
look like raw database output. The intended flow is:

1. Resolve the user’s intent, project scope, entities, filters and permissions.
2. Retrieve authoritative structured records, approved documents, or both.
3. Validate completeness, authority, permissions, dates, names, numbers and conflicts.
4. Pass only the verified evidence to the AI.
5. Let the AI explain, summarise, compare and present the result naturally.

Use each evidence mechanism for the job it handles best:

- Database queries for exact current facts such as IDs, dates, statuses, counts, names and relationships.
- Vector embeddings for unstructured project documents, reports, meeting notes, policies and guidance.
- Lexical matching for exact identifiers, names, document titles and unusual terms.
- The AI for conversational explanation, synthesis, follow-ups and clearly labelled recommendations.

The AI must format and explain verified evidence, not invent facts or decide
which private records are in scope. Exact database routing is additive and must
not remove the existing semantic retrieval path.

## Natural-language robustness decision

Natural-language support must be system-wide and multi-user, not patched for a
single question or project. A shared normalization boundary was added in
`app_modules/query_planning.py` and applied to planning and retrieval. It now
normalizes Unicode punctuation, non-breaking spaces, mobile/document hyphens,
and zero-width characters before routing. This supports copied questions such
as `2026‑S2‑21` as well as ordinary ASCII identifiers without changing the
question displayed to the user.

Project-ID recognition was expanded across catalogue parsing, project lookup,
general retrieval, broad retrieval and project retrieval. Regression tests cover
mobile/document punctuation and the complete suite currently passes with 217
tests passed and 1 skipped.

The same system-wide standard should be applied in future to names, titles,
dates, statuses, owners, meeting references, milestone references, document
references, indirect wording and long conversational context. Do not add
question-specific answer patches.

## Reliability priorities for the next session

1. Add a canonical entity resolver for project IDs, project names, meetings, milestones, tasks, owners, dates and documents.
2. Apply authorization and metadata filters before vector or lexical retrieval.
3. Add query-specific retrieval strategies for counts, exact facts, exhaustive lists, summaries and comparisons.
4. Make evidence checks deterministic for numbers, dates, names, counts and completeness; keep LLM validation supplementary.
5. Add explicit abstention for ambiguity, incomplete evidence, authority conflicts and unavailable validation.
6. Expand permission-boundary tests through follow-ups, summaries, comparisons, exports and cached results.
7. Track structured failure reasons such as `entity_not_resolved`, `wrong_scope`, `missing_evidence`, `incomplete_list`, `authority_conflict` and `validation_unavailable`.

Do not make cosmetic changes as a substitute for these reliability controls.

