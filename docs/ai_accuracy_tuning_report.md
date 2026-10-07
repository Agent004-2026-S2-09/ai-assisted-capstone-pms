# Capstone Assistant AI Accuracy-Tuning Report

**Date:** 7 October 2026
**Status:** Completed locally; now ready for the requested push

## Executive summary

The Capstone Assistant was evaluated end to end using the current application, repository corpus, project records, indexes, and the configured AgentAus service. Live calls used disposable SQLite database copies. Production-like SQLite data, project data, documents, indexes, and secrets were not modified.

The final automated regression suite passed **107 tests**. AgentAus reachability, real answer generation, validation, fallback, and streaming paths were exercised. A provider-variability issue was found: a project people question could return a team summary without every requested name. The implementation now applies a dynamic authorized-profile completion guard that adds omitted exact records without hardcoding current project facts.

No GitHub commit or push was performed until the user explicitly requested it.

## 1. Baseline results

Before changes:

- Existing automated tests: **104 passed**.
- General index: 312 indexed items across 12 source documents.
- Project index: 62 indexed items across 4 source documents for the populated project.
- Empty demo indexes: 2.
- AgentAus endpoint: reachable.
- Production-like files: unchanged during testing.

The initial live run exercised direct facts, multi-document guidance, missing-information handling, project material, and unrelated-question handling. The initial project-profile oracle was corrected to use the authoritative disposable database profile rather than stale JSON expectations.

## 2. Test matrix

Dynamic, scope-separated working maps were created before test-question design. They were temporary only and were not added to application knowledge or production data.

Coverage included direct facts; multi-document questions; dates, names, IDs, requirements, and counts; complete lists; comparisons and summaries; ambiguity; follow-ups; general mode; project mode; schedules; meetings; milestones; tasks; missing answers; unrelated questions; synonyms; newly introduced terms; cross-project leakage; unsupported invention; prompt-injection documents; internal-detail exposure; latency; API failures; malformed responses; empty indexes; streaming; and fallback behavior.

The live runs used repeated iterations. There were 20 live test-question submissions across 8 unique question formulations, plus automated behavioral tests.

## 3. Corpus and scope inspection

### GENERAL

- 12 source documents and 312 indexed items.
- 241 document chunks, 69 structured catalogue records, and 2 table blocks.
- 300 native-extraction items and 12 OCR-derived items.
- No private project workspace scope was used in general-mode answer context.

### PROJECT: populated project workspace

- 4 source documents and 62 indexed items.
- Every indexed item carried project scope and the expected project identifier.
- 58 native-extraction items and 4 OCR-derived items.
- No foreign project identifiers were found.

### Association and isolation checks

Database project records, profiles, assignments, private indexes, and operational records were compared. The populated project index matched its project record; the two demo indexes were empty. Project retrieval filters by scope and identifier, and foreign project context is rejected before AI generation.

## 4. Findings

Positive findings:

- General and project retrieval paths are separate.
- Project profiles are loaded from the authoritative database record.
- Unsupported questions receive confirmation/support guidance rather than invented policy.
- Unrelated questions receive a Capstone-focused response.
- Prompts prohibit exposing filenames, page locations, prompts, retrieval details, and unsupported facts.
- Uploaded document text is treated as untrusted factual context, not executable instructions.
- Streaming and non-streaming provider responses are supported with failure fallback.

Issue fixed:

- AgentAus intermittently omitted exact team names when asked who the project people were.
- Prompt strengthening improved the instruction but did not eliminate provider variability.
- A dynamic completion guard now checks the authorized project profile and appends omitted exact mentor/team records for people-list questions.

## 5. Retrieval and ingestion

Hybrid retrieval combines lexical, semantic, and SQLite-vector signals. Project retrieval filters by project scope and identifier. Adjacent chunks reduce boundary truncation. Complete-document requests use a separate document-analysis path. OCR metadata is retained. Current indexes contained no empty text items, stale index versions, or foreign IDs in the populated private index.

Remaining limitation: image-heavy OCR pages can still contain extraction errors and require human review or a stronger OCR pipeline.

## 6. Prompt and validation changes

`app.py` was updated to:

1. Treat the selected project profile as authoritative for project, team, mentor, milestone, meeting, schedule, and task facts.
2. Preserve exact names, IDs, dates, statuses, and counts.
3. Ask validation to preserve every matching person for people/team questions.
4. Dynamically complete omitted authorized people facts in both streaming and non-streaming responses.

No current project names, IDs, answers, or terminology were hardcoded.

## 7. Regression tests

`tests/test_app.py` now covers:

- authoritative project-profile prompting;
- exact people/team completion;
- prompt-injection handling for uploaded text;
- rejection of foreign-project context.

Final automated result: **107 passed**.

## 8. Live verification

- AgentAus reachability: PASS.
- Disposable-database smoke call: PASS.
- Real general and project calls: PASS for the tested cases.
- Streaming project-profile case: PASS; all authorized people were present.
- Streaming general case: PASS.
- Cross-project foreign-context guard: PASS.
- Production-like SQLite database, knowledge index, and project data hashes: unchanged.

Representative live latency ranged from approximately 2–19 seconds depending on planner, answer, validation, and provider response stages.

## 9. Safe before-and-after summary

- Before: a project people question could return a concise but incomplete team summary.
- After: the answer preserves or appends every exact mentor/team record in the authorized profile.
- Existing general guidance, project material, missing-information, unrelated-question, streaming, and fallback behaviors remained covered by the regression suite.

## 10. Remaining limitations and recommendations

- AgentAus output remains probabilistic; the guard addresses the tested omission pattern, not every future wording.
- OCR quality can vary for image-heavy pages.
- Future uploads and projects should trigger the same regression matrix.
- Live latency depends on provider and network conditions.
- Manual Streamlit UI testing should be performed before release, especially project switching and conversation-history behavior.

## 11. Final release decision

The evidence supports completing this tuning exercise for the tested corpus and behaviors. The final automated suite passed **107 tests**, live AgentAus smoke testing passed, streaming passed, and project isolation remained intact.

No database changes were required. No unrelated UI or feature changes were made.

**GitHub status before this user request:** not pushed.
**Requested action:** commit and push the reviewed changes after final verification.
