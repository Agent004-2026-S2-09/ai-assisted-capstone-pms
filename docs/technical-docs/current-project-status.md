# Current project status

**Date:** 21 October 2026  
**Workspace:** `/home/cbah/projects/ai-assisted-capstone-pms`  
**Purpose:** Living status record for sponsor demonstration and final handover.

## Overall status

The application is demo-ready for a controlled sponsor and university-panel demonstration. The core project-management, authentication, role-boundary, knowledge-base, retrieval, monitoring, notification and mentor-feedback features are implemented and passing their current automated checks.

## Latest verification

| Check | Result |
| --- | --- |
| Full backend/application regression suite | **240 passed, 1 skipped** |
| Focused role/frontend and AI-outage suite | **20 passed** |
| Administrator login/navigation | **Passed** |
| Student login/navigation | **Passed** |
| Mentor and Convenor role visibility checks | **Passed** |
| Project workspace access and student read-only boundaries | **Passed** |
| AI error sanitisation and offline status behaviour | **Passed** |
| Local Streamlit health endpoint | **HTTP 200** |
| Local application root | **HTTP 200** |
| Python compilation | **Passed** |

The latest full-suite result is the authoritative current regression result. Older sprint and acceptance reports retain their original historical test counts and should not be interpreted as the current total.

## AI and retrieval runtime

- The current verified MVP embedding backend is `hashing-v1` with 384 dimensions.
- The system retains the optional BGE neural backend, but it has not been enabled automatically and must not be changed without an explicit decision and index rebuild.
- General and project retrieval continue to use the hybrid evidence architecture: structured records for exact facts, lexical/vector retrieval for documents, permission filtering and AI generation as the final conversational layer.
- The latest monitored questions were routed through the shared query-plan and retrieval pipeline with evidence sufficiency recorded.
- Query traces record intent, scope, entity, route, retrieval, provider stages, validation state and security-boundary checks for administrator review.

## Provider and validation status

The configured Agentaus endpoint is reachable through its health probe. Generation requests used by the recent student questions completed successfully, but the independent response-validation pass was unavailable for those interactions. This limits confidence scoring; it does not mean the retrieved evidence was absent. The application records this state as `validation_unavailable` and does not expose provider traceback or internal Python details to users.

When a real provider request fails, the AI service indicator is shown as offline/red and the user receives a safe explanatory message. Provider credentials remain outside the repository.

## Security and access status

- Student, Mentor, Convenor and Administrator paths have role-specific access checks.
- Project retrieval is restricted to the authorised project scope.
- General-area answers do not grant access to private project records.
- Notifications are project-scoped: assigned project users receive project activity, with administrator/convenor oversight according to the current access policy; unrelated project users are not broadcast recipients.
- Mentor comments are available in Project Overview, Meetings and Milestones as read-only content for students.

## Knowledge-base status

- General and project indexes were rebuilt and audited after recent document additions.
- Indexed documents and embeddings were checked for missing, orphaned, duplicate and malformed records.
- The current local runtime deliberately retains `hashing-v1`; changing embedding backend requires a controlled rebuild and verification.
- Historical test artefacts and reports remain in `docs/test/` and are not overwritten.

## Remaining limitations and handover actions

1. Restore or confirm provider quota/availability before relying on independent AI validation or running a large adjudication batch.
2. Repeat literal Chromium browser testing from an environment with the required browser dependencies. AppTest and local HTTP checks currently pass.
3. Use deterministic database evidence for exact dates, counts, statuses, names and relationships during the demonstration.
4. Rehearse the final demonstration with prepared general and project questions, including one safe AI-outage scenario.
5. Preserve the current corpus, SQLite database, index files and embedding backend as the demo baseline; make future model or corpus changes only through a controlled rebuild and full regression run.

## Handover interpretation

This is an MVP/prototype suitable for controlled demonstration and supervised use. It is not a replacement for official Canvas records, sponsor decisions, academic-integrity judgement or production operational governance.
