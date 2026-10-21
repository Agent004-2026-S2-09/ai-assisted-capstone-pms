# System-wide engineering principles

These principles are part of the project maintenance context and must be
consulted before future fixes or feature work.

## Core rule

When a user reports an incorrect answer or asks for a solution, treat the
problem as a system-wide engineering problem. Do not implement a response
that only recognises the exact wording, record, document or example reported
by the user.

## Open-ended student language

Students can ask an effectively unlimited range of natural-language questions,
including paraphrases, typos, follow-ups, implicit references, comparisons,
summaries and requests that combine documents with structured project records.
The assistant must therefore improve its general intent, entity, filter,
reference-resolution and evidence-selection capabilities. A new student
wording must not require a new hardcoded phrase, question template or
document-specific branch.

## Required approach

1. Identify the complete failure class and the shared architectural boundary.
2. Prefer reusable routing, schema-aware logic and authoritative data access
   over prompt-only changes or keyword patches.
3. Treat database-backed facts as authoritative for counts, lists, statuses,
   dates, relationships, permissions and workflow state.
4. Keep document/RAG retrieval for document-grounded questions; do not ask a
   language model to calculate deterministic database results from context.
5. Test the reported wording, unseen paraphrases, misspellings, neighbouring
   record types, multi-source requests, follow-ups and permission boundaries.
6. Run the full regression suite before declaring the work complete.
7. Never claim a complete fix when coverage remains narrow; state the gap.
8. Preserve existing work, use isolated test data for mutations and do not
   push to GitHub unless the user explicitly authorises it.

## Acceptance standard

A fix is complete only when it addresses the reusable failure class, has
regression coverage for related unseen inputs, preserves existing behaviour,
and has been verified against the full test suite.
