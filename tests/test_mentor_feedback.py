## File: tests/test_mentor_feedback.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing test mentor feedback functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

import app
from app_modules import access_control as access
from app_modules import auth, comments, mentor_feedback, notifications


PASSWORD = "a-long-test-password"


def test_mentor_guidance_is_reusable_and_notifies_authorised_project_team():
    """
    Function: test_mentor_guidance_is_reusable_and_notifies_authorised_project_team
    Purpose: Execute the test mentor guidance is reusable and notifies authorised project team operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    project = app.create_project("Mentor guidance project")
    student_id = auth.create_user("Guidance Student", "guidance-student@test.local", PASSWORD, "Student")
    mentor_id = auth.create_user("Guidance Mentor", "guidance-mentor@test.local", PASSWORD, "Mentor")
    access.assign_project(app.st.session_state, student_id, project.id)
    access.assign_project(app.st.session_state, mentor_id, project.id)
    assert auth.login(app.st.session_state, "guidance-mentor@test.local", PASSWORD)

    targets = (("overview", "overview", "the project overview"), ("milestone", "m1", "milestone 'M1'"))
    for target_type, target_id, target_label in targets:
        saved = mentor_feedback.save_feedback(
            app.st.session_state,
            project.id,
            target_type,
            target_id,
            f"Review the {target_type} evidence before the next check-in.",
            target_label=target_label,
        )
        assert saved["target_type"] == target_type

    assert auth.login(app.st.session_state, "guidance-student@test.local", PASSWORD)
    student_notifications = notifications.list_notifications(app.st.session_state, unread_only=True)
    assert len(student_notifications) == 2
    assert all("mentor guidance" in item["message"] for item in student_notifications)
    assert {"the project overview", "milestone 'M1'"} <= {
        item["message"].split(" for ", 1)[-1].split(" (", 1)[0]
        for item in student_notifications
    }


def test_ai_workspace_context_covers_activity_and_is_project_scoped():
    """
    Function: test_ai_workspace_context_covers_activity_and_is_project_scoped
    Purpose: Verify AI workspace evidence includes activity records without
             exposing records from another authorised project.
    Inputs:
            None.
    Returns:
            None; pytest raises an assertion on failure.
    Raises/side effects:
            Creates isolated test users, projects, comments, guidance, and
            notifications in the test database.
    """
    project = app.create_project("Workspace context project")
    other_project = app.create_project("Other workspace project")
    student_id = auth.create_user("Context Student", "context-student@test.local", PASSWORD, "Student")
    mentor_id = auth.create_user("Context Mentor", "context-mentor@test.local", PASSWORD, "Mentor")
    access.assign_project(app.st.session_state, student_id, project.id)
    for project_id in (project.id, other_project.id):
        access.assign_project(app.st.session_state, mentor_id, project_id)

    assert auth.login(app.st.session_state, "context-student@test.local", PASSWORD)
    comments.add_comment(app.st.session_state, project.id, "Project discussion evidence")

    assert auth.login(app.st.session_state, "context-mentor@test.local", PASSWORD)
    comments.add_comment(app.st.session_state, other_project.id, "Other project must stay out")
    mentor_feedback.save_feedback(
        app.st.session_state,
        project.id,
        "overview",
        "overview",
        "Mentor overview guidance evidence",
        target_label="the project overview",
    )

    assert auth.login(app.st.session_state, "context-student@test.local", PASSWORD)
    context = app._build_project_workspace_activity_context(
        project,
        "show the discussion, mentor comments, and notifications",
    )
    assert "Project discussion evidence" in context
    assert "Mentor overview guidance evidence" in context
    assert "Other project must stay out" not in context
    assert app._structured_project_database_answer(
        "what mentor comments are recorded?", project
    ) is None

