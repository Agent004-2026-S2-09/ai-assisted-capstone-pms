# Capstone Assistant — Handover Status

**Date:** 21 October 2026  
**Workspace:** `/home/cbah/projects/ai-assisted-capstone-pms`  
**Purpose:** Preserve the current testing state before shutdown.

> **Living-status note — 21 October 2026:** The current status is maintained in [`current-project-status.md`](current-project-status.md). The latest regression result is 240 passed and 1 skipped, with 20 focused role/frontend and outage tests passed. The local Streamlit health endpoint and application root returned HTTP 200. The current MVP runtime uses only deterministic `hashing-v1` embeddings. Recent Agentaus generation requests completed, but independent response validation was unavailable. Historical results below are preserved as historical records.

## Completed browser test

The real Chromium student-facing test completed all **610 questions**:

- 45 general Capstone documents × 10 questions = 450 questions
- 6 project sections × 10 questions = 60 questions
- 100 multi-document questions
- All questions were submitted through the student UI.
- 608 responses completed successfully through Agentaus.
- 2 project cross-document questions failed before generation with `AccessDenied`.
- No fallback responses were recorded in this run.

The primary browser report was a temporary JSON test artifact and is not retained in the repository.

The browser checkpoint is:

The temporary browser-test checkpoint was archived outside the repository after the run completed.

## Answer verification status

The first Agentaus adjudication pass checked all 610 rows, but the provider became unavailable during the run. Its provisional results were:

- Correct: 47
- Partially correct: 167
- Incorrect: 101
- Unverifiable: 295, primarily due to provider timeouts

The 47 currently classified as correct were all general, single-document questions. No project-specific or multi-document answer was independently confirmed in that pass.

The adjudication report was a temporary JSON test artifact and is not retained in the repository.

A retry was started for the timeout cases. It was stopped after the provider health check returned **HTTP 402 — Payment Required**. This indicates quota, credit or billing restriction; it does not establish that Agentaus is permanently offline.

Retry checkpoint:

The temporary adjudication retry checkpoint was archived outside the repository after the run completed.

## Current Agentaus finding

The Agentaus endpoint is reachable but currently rejects requests with HTTP 402. Do not continue bulk adjudication until Agentaus account quota/credit/billing is restored.

The application code was not changed as part of the adjudication or retry work.

## Important interpretation

The 47 figure is not proof that only 47 answers were correct. It is the number independently classified as correct before the validator became unavailable. The remaining answers require re-adjudication or deterministic/human review when the provider is available.

The strongest next evaluation approach is:

1. Use deterministic checks for exact names, dates, numbers, statuses, counts and project records.
2. Use an independent semantic review for paraphrases, omissions and unsupported claims.
3. Review project and multi-document cases separately.
4. Reproduce and isolate the two `AccessDenied` cases before changing code.

## Safe handover recommendation

Do not rename the whole document corpus or migrate from SQLite before handover. Those changes could invalidate indexes, embeddings, source references and regression results. SQLite is acceptable for the current MVP scale. Freeze the current corpus and make any future naming or storage change only through a controlled A/B test and full index rebuild.

