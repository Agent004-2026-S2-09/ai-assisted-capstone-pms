# Mentor, Convenor and Administrator acceptance test

**Date:** 20 October 2026  
**Environment:** Local Ubuntu/WSL instance, Streamlit app on `http://127.0.0.1:8501`  
**Scope:** Mentor, Convenor and Administrator permissions and CRUD operations. No GitHub push was performed.

## Executive result

All three role-specific acceptance runs passed against an isolated temporary project and temporary accounts. Existing projects, users, documents, indexes, embeddings and production records were not used as mutation targets.

The test also confirmed the intended permission boundary: Mentor, Convenor and Administrator accounts can update project profile data; Students remain blocked from that operation.

## Features tested for each role

For Mentor, Convenor and Administrator accounts, the test performed:

- authentication, role resolution and project access;
- project overview read access;
- meeting create, read, update and delete;
- Gantt task create, read, update and delete;
- Gantt-to-Kanban synchronisation;
- linked Kanban task movement;
- standalone Kanban card create, read, update, move and delete;
- team discussion comment create, read, update and delete;
- project document upload, extraction, indexing, read-back, deletion and re-indexing;
- project profile update followed by restoration of the original profile.

## Administrator-only operations tested

The temporary Administrator account also completed:

- temporary user account create and read;
- managed user profile/role update and read-back;
- project assignment create, read and delete;
- prompt-version create and read.

The administrator-created project itself was removed through the cleanup transaction after testing.

## Results summary

| Role | Result | Notes |
|---|---|---|
| Mentor | PASS | Assigned-project access and all project content/profile CRUD operations succeeded. |
| Convenor | PASS | Cross-project permission path and all project content/profile CRUD operations succeeded. |
| Administrator | PASS | Full tested project/content CRUD plus account, assignment and prompt-management operations succeeded. |
| Student protection check | EXPECTED DENIAL | Student profile/team write raised `AccessDenied`, confirming the boundary remains intact. |

## Regression tests

The relevant existing automated suites completed successfully: **59 passed** across scheduling/accounts, multi-permission, project-directory, Sprint 3, comments and Streamlit UI-smoke coverage.

## Browser limitation

As in the student test, a real Playwright browser session could not be started in this WSL environment because the installed Chromium binary is missing `libnspr4.so`. This prevented a literal browser-rendered login test. Authentication and role permissions were instead exercised through authenticated application session state, and the Streamlit UI-smoke tests passed.

This is an environment limitation, not a detected application failure. A browser-level pass should be run after the WSL Chromium dependencies are installed or from a machine with a working Chromium installation.

## Cleanup verification

The temporary accounts, managed account, project, assignments, project documents, embeddings, comments, Gantt plan and Kanban board were removed. Final counts for the temporary project identifier were all zero:

- projects: 0
- assignments: 0
- embeddings: 0
- project comments: 0
- Gantt plans: 0
- Kanban boards: 0

## Conclusion

No application defect was found in the tested Mentor, Convenor or Administrator role paths. The local system was left without the temporary test data, and no remote repository changes were made.
