# Student feature CRUD acceptance test

**Date:** 20 October 2026  
**Environment:** Local Ubuntu/WSL instance, Streamlit app on `http://127.0.0.1:8501`  
**Scope:** Student-authorised features only. No GitHub push was performed.

## Executive result

The authenticated student service-layer acceptance test passed for all student-writable features tested. Student profile/team writes were correctly rejected. Existing application data was not used as a mutation target.

The test used a temporary student account and a temporary assigned project. All temporary records, files, indexes, embeddings, comments, schedules, boards, audit rows and sessions were removed after the test. A post-clean-up database check reported zero remaining test users, projects, assignments, embeddings, comments, Gantt plans and Kanban boards.

## Test method

1. Created a dedicated temporary Student account and assigned it to a temporary project.
2. Authenticated that account through the application authentication service and verified the Student role and project assignment.
3. Performed create, read, update and delete operations against test-owned records.
4. Verified cross-feature synchronisation, especially Gantt-to-Kanban behaviour and document indexing.
5. Verified that a Student cannot modify project profile/team data.
6. Removed the temporary test scope and checked for leftovers.
7. Ran the existing relevant automated suites: **33 passed** (`tests/test_sprint3.py`, `tests/test_project_comments.py`, and `tests/test_ui_smoke.py`).

## Results

| Feature | Result | Evidence covered |
|---|---|---|
| Authentication and project access | PASS | Student login, role resolution and assigned-project access succeeded. |
| Project overview/read access | PASS | Temporary project was read through the authenticated student scope. |
| Project profile/team protection | PASS | Profile write raised the expected `AccessDenied`; student cannot change profile or team assignments. |
| Meetings | PASS | Create, read, update and delete all succeeded. |
| Milestones | PASS | Created, read, updated and deleted through the authoritative Gantt schedule. |
| Gantt schedule | PASS | Task create, read, update and delete succeeded. |
| Gantt/Kanban synchronisation | PASS | A Gantt task produced a linked Kanban card; updating the task updated the linked card; deleting the task removed the linked card. |
| Kanban tasks | PASS | Standalone card create, read, update, move and delete succeeded. |
| Team discussion | PASS | Comment create, read, update and delete succeeded for the student’s own comment. |
| Project knowledge | PASS | Student document upload, extraction/indexing, read-back and delete/re-index succeeded. |
| General assistant access | Not destructively tested | The assistant is an external AI operation and was not invoked as part of a CRUD mutation test. Existing RAG tests remain separate. |
| Account/password controls | Not mutated | No password was changed so the temporary account could be removed deterministically. |

## Browser limitation

A real Playwright browser session could not be started in this WSL environment because the installed Chromium binary is missing the system shared library `libnspr4.so`. This prevented a literal browser-rendered login test. The application authentication and permission paths were therefore exercised using the same authenticated application session state used by the app’s UI functions, and the existing Streamlit UI-smoke tests passed.

This is an environment limitation, not an application failure. A browser-level pass should be run after the WSL browser dependencies are installed or from a machine with a working Chromium installation.

## Cleanup verification

The temporary scope was removed successfully. Final counts for the test identifiers were all zero:

- users: 0
- projects: 0
- assignments: 0
- embeddings: 0
- project comments: 0
- Gantt plans: 0
- Kanban boards: 0

## Conclusion

No application defect was found in the student CRUD paths covered by this acceptance test. The remaining validation gap is browser-level interaction, blocked by the local Chromium dependency. The local application and repository were left without the temporary test data, and no remote repository changes were made.
