## File: tests/test_sprint3.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Database, login, role enforcement and private retrieval regression tests.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Database, login, role enforcement and private retrieval regression tests."""
import json
import sqlite3
import time

import pytest

import app
from app_modules import auth
from app_modules import database
from app_modules import access_control as access
from app_modules import notifications

PASSWORD = "a-long-test-password"


@pytest.fixture
def projects():
    """
    Function: projects
    Purpose: Execute the projects operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha = app.create_project("Alpha")
    beta = app.create_project("Beta")
    app.install_project_uploaded_files(alpha.id, [("alpha.txt", b"Alpha uses offline mobile caching.")])
    app.install_project_uploaded_files(beta.id, [("beta.txt", b"Beta secret satellite dashboard.")])
    return alpha, beta


def sign_in_role(role, project=None):
    """
    Function: sign_in_role
    Purpose: Execute the sign in role operation.
    Inputs:
            role (value): Caller-provided input.
            project (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    user_id = auth.create_user(f"Test {role}", f"{role}@test.local", PASSWORD, role)
    if project:
        access.assign_project(app.st.session_state, user_id, project.id)
    assert auth.login(app.st.session_state, f"{role}@test.local", PASSWORD)
    return user_id


def test_successful_login_and_hashed_password():
    """
    Function: test_successful_login_and_hashed_password
    Purpose: Execute the test successful login and hashed password operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    user_id = auth.create_user("Student", "Student@Example.org", PASSWORD, "Student")
    user = auth.authenticate("  STUDENT@example.org  ", PASSWORD)
    assert user["id"] == user_id
    assert "password_hash" not in user
    with database.connect() as db:
        encoded = db.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()[0]
    assert PASSWORD not in encoded
    assert auth.verify_password(PASSWORD, encoded)
    assert encoded != auth.hash_password(PASSWORD)


def test_browser_session_token_can_restore_after_streamlit_refresh():
    """
    Function: test_browser_session_token_can_restore_after_streamlit_refresh
    Purpose: Execute the test browser session token can restore after streamlit refresh operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    auth.create_user("Refresh Admin", "refresh-admin", PASSWORD, "Administrator")
    first_session = {}
    assert auth.login(first_session, "refresh-admin", PASSWORD)
    token = first_session["auth_token"]

    refreshed_session = {}
    assert auth.restore_session(refreshed_session, token)
    assert auth.current_user(refreshed_session)["username"] == "refresh-admin"

    auth.logout(first_session)
    revoked_session = {}
    assert not auth.restore_session(revoked_session, token)
    assert not revoked_session


@pytest.mark.parametrize("username,password", [("admin@test.local", "invalid"), ("unknown", PASSWORD)])
def test_invalid_login(username, password):
    """
    Function: test_invalid_login
    Purpose: Execute the test invalid login operation.
    Inputs:
            username (value): Caller-provided input.
            password (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    assert auth.authenticate(username, password) is None
    assert not auth.login(app.st.session_state, username, password)
    assert not app.st.session_state


@pytest.mark.parametrize("role", database.ROLES)
def test_role_access_and_direct_denial(role, projects):
    """
    Function: test_role_access_and_direct_denial
    Purpose: Execute the test role access and direct denial operation.
    Inputs:
            role (value): Caller-provided input.
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, beta = projects
    sign_in_role(role, alpha)
    assert app.get_project(alpha.id).name == "Alpha"
    assert app.load_project_index(alpha.id)
    if role in ("Administrator", "Convenor"):
        assert app.get_project(beta.id).name == "Beta"
        assert len(app.get_accessible_projects()) == 2
        if role == "Administrator":
            access.require_admin(app.st.session_state)
        else:
            with pytest.raises(access.AccessDenied):
                access.require_admin(app.st.session_state)
    else:
        assert [project.id for project in app.get_accessible_projects()] == [alpha.id]
        with pytest.raises(access.AccessDenied):
            access.require_admin(app.st.session_state)
        for operation in (app.get_project, app.load_project_index, app.list_project_documents,
                          app.get_project_knowledge_dir, app.get_project_index_file,
                          app.calculate_project_signature, app.rebuild_project_index):
            with pytest.raises(access.AccessDenied):
                operation(beta.id)
        with pytest.raises(access.AccessDenied):
            app.create_project("Forbidden")
        with pytest.raises(access.AccessDenied):
            app.delete_project(alpha.id)


def test_logout_clears_session_and_revokes_token(projects):
    """
    Function: test_logout_clears_session_and_revokes_token
    Purpose: Execute the test logout clears session and revokes token operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    sign_in_role("Student", projects[0])
    copied = dict(app.st.session_state)
    app.st.session_state.update(messages=[{"content": "private"}], selected_project_id="alpha", user_role="Administrator")
    auth.logout(app.st.session_state)
    assert dict(app.st.session_state) == {}
    assert auth.current_user(copied) is None
    with pytest.raises(access.AccessDenied):
        app.get_project("alpha")


def test_forged_role_and_name_do_not_grant_access(projects):
    """
    Function: test_forged_role_and_name_do_not_grant_access
    Purpose: Execute the test forged role and name do not grant access operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, beta = projects
    sign_in_role("Student", alpha)
    app.st.session_state.update(user_role="Administrator", user_name="Test Administrator", admin_authenticated=True)
    assert not app.can_access_project(beta, "Administrator", "Test Administrator")
    with pytest.raises(access.AccessDenied):
        access.require_admin(app.st.session_state)
    assert auth.current_user(app.st.session_state)["role"] == "Student"


def test_private_retrieval_and_assistant_reject_foreign_context(projects, monkeypatch):
    """
    Function: test_private_retrieval_and_assistant_reject_foreign_context
    Purpose: Execute the test private retrieval and assistant reject foreign context operation.
    Inputs:
            projects (value): Caller-provided input.
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, beta = projects
    alpha_docs, beta_docs = app.load_project_index(alpha.id), app.load_project_index(beta.id)
    sign_in_role("Student", alpha)
    calls = []
    monkeypatch.setattr(app, "call_agentaus", lambda *args, **kwargs: calls.append(args))
    assert app.retrieve_project_information("offline mobile caching", alpha_docs + beta_docs, alpha.id)
    assert "satellite" not in app.build_private_context(alpha_docs)
    for operation in (
        lambda: app.retrieve_project_information("secret", beta_docs, beta.id),
        lambda: app.execute_project_search_plan({"action": "out_of_scope"}, beta_docs, beta.id),
        lambda: app.retrieve_information("secret", beta_docs),
        lambda: app.execute_search_plan({"action": "search", "queries": ["secret"]}, beta_docs),
        lambda: app.plan_information_search("secret", beta_docs),
        lambda: app._structured_project_completion_context("list all completed tasks", beta),
        lambda: app.build_private_context(alpha_docs + beta_docs),
        lambda: app.build_project_profile(beta),
        lambda: app.generate_response("secret", beta_docs, project=alpha),
        lambda: list(app.generate_response_stream("secret", beta_docs, project=beta)),
        lambda: app.process_project_document(app.PROJECT_KNOWLEDGE_DIR / beta.id / "beta.txt", alpha.id),
        lambda: app.extract_text(app.PROJECT_KNOWLEDGE_DIR / beta.id / "beta.txt"),
    ):
        with pytest.raises(access.AccessDenied):
            operation()
    assert not calls


def test_student_cannot_mutate_projects_or_grant_assignments(projects):
    """
    Function: test_student_cannot_mutate_projects_or_grant_assignments
    Purpose: Execute the test student cannot mutate projects or grant assignments operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, beta = projects
    student_id = sign_in_role("Student", alpha)
    for operation in (
        lambda: app.update_project(alpha),
        lambda: app.install_project_uploaded_files(alpha.id, [("inject.txt", b"Injected")]),
        lambda: app.delete_project_document(alpha.id, "alpha.txt"),
        lambda: app.save_projects([alpha]),
        lambda: access.assign_project(app.st.session_state, student_id, beta.id),
        lambda: access.create_user(app.st.session_state, "Evil", "evil", PASSWORD, "Administrator"),
    ):
        with pytest.raises(access.AccessDenied):
            operation()


def test_student_can_update_meetings_milestones_and_project_documents(projects):
    """
    Function: test_student_can_update_meetings_milestones_and_project_documents
    Purpose: Execute the test student can update meetings milestones and project documents operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, _ = projects
    sign_in_role("Student", alpha)
    project = app.get_project(alpha.id)
    original_description = project.description
    original_team = list(project.team)
    project.description = "Student project overview update"
    project.team.append({"id": "student-member", "name": "Student member", "role": "Developer"})
    project.meetings.append({"id": "student-meeting", "title": "Student meeting"})
    project.milestones.append({"id": "student-milestone", "name": "Student milestone"})
    app.update_project(project, allow_student_content=True)
    app.install_project_uploaded_files(
        alpha.id,
        [("student-note.txt", b"Student project note")],
        allow_student_content=True,
    )
    saved = app.get_project(alpha.id)
    assert saved.description == original_description
    assert saved.team == original_team
    assert saved.meetings[0]["id"] == "student-meeting"
    assert saved.milestones[0]["id"] == "student-milestone"
    assert any(path.name == "student-note.txt" for path in app.list_project_documents(alpha.id))


def test_student_has_full_meeting_crud_only_in_assigned_project(projects):
    """
    Function: test_student_has_full_meeting_crud_only_in_assigned_project
    Purpose: Execute the test student has full meeting crud only in assigned project operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, beta = projects
    sign_in_role("Student", alpha)

    created = app.create_project_meeting(
        alpha.id,
        {
            "title": "Student planning meeting",
            "date": "2026-10-13",
            "attendees": "Project team",
            "discussion": "Reviewed the delivery plan.",
            "decisions": "Keep the current scope.",
            "actions": "Update the task board.",
        },
    )
    assert created["id"]
    updated = app.update_project_meeting(
        alpha.id,
        created["id"],
        {**created, "title": "Updated student planning meeting"},
    )
    assert updated["title"] == "Updated student planning meeting"
    assert app.get_project(alpha.id).meetings[0]["title"] == "Updated student planning meeting"

    app.delete_project_meeting(alpha.id, created["id"])
    assert all(meeting["id"] != created["id"] for meeting in app.get_project(alpha.id).meetings)
    with pytest.raises(access.AccessDenied):
        app.create_project_meeting(beta.id, {"title": "Should be denied"})


def test_mentor_comment_is_visible_to_students_but_student_read_only(projects):
    """
    Function: test_mentor_comment_is_visible_to_students_but_student_read_only
    Purpose: Execute the test mentor comment is visible to students but student read only operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, _ = projects
    student_id = auth.create_user("Test Student", "student-mentor-comment@test.local", PASSWORD, "Student")
    admin_state = {}
    assert auth.login(admin_state, "admin@test.local", "test-password-long")
    access.assign_project(admin_state, student_id, alpha.id)
    sign_in_role("Mentor", alpha)
    created = app.create_project_meeting(
        alpha.id,
        {
            "title": "Mentor feedback meeting",
            "date": "2026-10-20",
            "actions": "Student action",
            "mentor_comment": "Please include the approved evidence in the next draft.",
        },
    )
    assert created["mentor_comment"] == "Please include the approved evidence in the next draft."

    assert auth.login(app.st.session_state, "student-mentor-comment@test.local", PASSWORD)
    student_notifications = notifications.list_notifications(app.st.session_state, unread_only=True)
    assert any("added mentor guidance" in item["message"] for item in student_notifications)
    student_update = {**created, "mentor_comment": "Student attempted to overwrite this."}
    updated = app.update_project_meeting(alpha.id, created["id"], student_update)
    assert updated["mentor_comment"] == created["mentor_comment"]
    assert app.get_project(alpha.id).meetings[0]["mentor_comment"] == created["mentor_comment"]


def test_database_record_questions_use_deterministic_project_aggregates(projects):
    """
    Function: test_database_record_questions_use_deterministic_project_aggregates
    Purpose: Execute the test database record questions use deterministic project aggregates operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, _ = projects
    for code, name in (("5", "Sprint 1 – General Capstone Assistant"), ("6", "Sprint 2 – Project-Specific Assistant")):
        app.gantt.add_task(
            app.st.session_state,
            alpha.id,
            {
                "code": code,
                "name": name,
                "type": "Milestone",
                "start": "2026-09-07",
                "finish": "2026-09-07",
                "progress": 0,
                "status": "Planned",
                "resource": "",
                "predecessors": [],
                "details": "",
                "milestone": True,
            },
        )
    app.gantt.add_task(
        app.st.session_state,
        alpha.id,
        {
            "code": "5.1",
            "name": "Prepare sprint demonstration",
            "type": "Task",
            "start": "2026-09-07",
            "finish": "2026-09-07",
            "progress": 50,
            "status": "In Progress",
            "resource": "",
            "predecessors": [],
            "details": "",
            "milestone": False,
        },
    )
    profile = app.get_project(alpha.id)
    profile.team = [{"id": "member-1", "name": "Test Member", "role": "Developer"}]
    app.update_project(profile)
    app.create_project_meeting(
        alpha.id,
        {"title": "Sprint 1 Demo", "date": "2026-09-07", "attendees": "Test Student"},
    )
    app.create_project_meeting(
        alpha.id,
        {"title": "Planning Meeting", "date": "2026-09-08", "attendees": "Other person"},
    )
    sign_in_role("Student", alpha)

    sprint_answer = app._structured_project_database_answer("how many project sprints did we do?", app.get_project(alpha.id))
    assert "Scheduled project sprints: 2" in sprint_answer
    assert "Sprint demo meetings recorded: 1" in sprint_answer
    typo_answer = app._structured_project_database_answer("how many capstone sprinnts did we do?", app.get_project(alpha.id))
    assert "Scheduled project sprints: 2" in typo_answer

    attendance_answer = app._structured_project_database_answer("how many meetings did we attend?", app.get_project(alpha.id))
    assert "1 meeting(s) attended" in attendance_answer
    assert "Sprint 1 Demo" in attendance_answer

    list_answer = app._structured_project_database_answer("list all our meetings", app.get_project(alpha.id))
    assert "2 meeting(s)" in list_answer
    assert "Planning Meeting" in list_answer

    assert "1 team member(s)" in app._structured_project_database_answer("how many team members are there?", app.get_project(alpha.id))
    assert "2 milestone(s)" in app._structured_project_database_answer("how many milestones are recorded?", app.get_project(alpha.id))
    assert "1 matching schedule item(s)" in app._structured_project_database_answer("how many tasks are in progress?", app.get_project(alpha.id))
    assert "Project name: Alpha" in app._structured_project_database_answer("what is the project name?", app.get_project(alpha.id))


def test_natural_language_meeting_selection_uses_authoritative_date_order(projects):
    """
    Function: test_natural_language_meeting_selection_uses_authoritative_date_order
    Purpose: Execute the test natural language meeting selection uses authoritative date order operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, _ = projects
    alpha.meetings = [
        {
            "title": "Earlier planning session",
            "date": "2026-08-24",
            "discussion": "Initial scope discussion",
            "decisions": "Proceed with the assistant",
            "actions": "Prepare the project plan",
        },
        {
            "title": "Latest mentor session",
            "date": "2026-10-19",
            "discussion": "Final presentation planning",
            "decisions": "Prepare the handover",
            "actions": "Confirm the demonstration scope",
        },
    ]
    app.update_project(alpha)
    project = app.get_project(alpha.id)

    latest = app._structured_project_database_answer(
        "Could you write a detailed report of our most recent mentor session?",
        project,
    )
    first = app._structured_project_database_answer(
        "What happened in the first meeting?",
        project,
    )
    previous = app._structured_project_database_answer(
        "Please summarise the 2nd meeting and its decisions.",
        project,
    )

    assert "2026-10-19" in latest
    assert "Latest mentor session" in latest
    assert "Final presentation planning" in latest
    assert "2026-08-24" in first
    assert "Earlier planning session" in first
    assert "2026-10-19" in previous
    assert "Prepare the handover" in previous


@pytest.mark.parametrize(
    ("stored_value", "expected"),
    [("2026-10-13", "2026-10-13"), ("13 October 2026", "2026-10-13"), ("", "2026-01-01")],
)
def test_meeting_date_picker_handles_existing_date_formats(stored_value, expected):
    """
    Function: test_meeting_date_picker_handles_existing_date_formats
    Purpose: Execute the test meeting date picker handles existing date formats operation.
    Inputs:
            stored_value (value): Caller-provided input.
            expected (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    fallback = app._date_picker_value(stored_value, app.date(2026, 1, 1))
    assert fallback.isoformat() == expected


def test_student_can_only_be_assigned_to_one_project(projects):
    """
    Function: test_student_can_only_be_assigned_to_one_project
    Purpose: Execute the test student can only be assigned to one project operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, beta = projects
    admin_state = dict(app.st.session_state)
    student_id = auth.create_user("Student", "single-project-student", PASSWORD, "Student")
    access.assign_project(admin_state, student_id, alpha.id)
    with pytest.raises(ValueError, match="only one project"):
        access.assign_project(admin_state, student_id, beta.id)


def test_convenor_accesses_all_projects(projects):
    """
    Function: test_convenor_accesses_all_projects
    Purpose: Execute the test convenor accesses all projects operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, beta = projects
    admin_state = dict(app.st.session_state)
    convenor_id = auth.create_user("Convenor", "all-project-convenor", PASSWORD, "Convenor")
    access.assign_project(admin_state, convenor_id, alpha.id)
    convenor_state = {}
    auth.login(convenor_state, "all-project-convenor", PASSWORD)
    assert access.can_access_project(convenor_state, alpha.id)
    assert access.can_access_project(convenor_state, beta.id)
    assert {p["id"] for p in access.accessible_projects(convenor_state)} == {alpha.id, beta.id}


def test_administrator_can_view_assignment_summary(projects):
    """
    Function: test_administrator_can_view_assignment_summary
    Purpose: Execute the test administrator can view assignment summary operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, _ = projects
    admin_state = dict(app.st.session_state)
    student_id = auth.create_user("Summary Student", "summary-student", PASSWORD, "Student")
    convenor_id = auth.create_user("Summary Convenor", "summary-convenor", PASSWORD, "Convenor")
    access.assign_project(admin_state, student_id, alpha.id)
    access.assign_project(admin_state, convenor_id, alpha.id)

    summary = {row["Username"]: row for row in access.project_assignment_summary(admin_state)}
    assert summary["summary-student"]["Assignment count"] == 1
    assert "Alpha" in summary["summary-student"]["Assigned projects"]
    assert summary["summary-student"]["Effective access"] == summary["summary-student"]["Assigned projects"]
    assert summary["summary-convenor"]["Assignment count"] == 1
    assert summary["summary-convenor"]["Effective access"] == "All Capstone projects"


def test_administrator_can_view_selected_users_assignments(projects):
    """
    Function: test_administrator_can_view_selected_users_assignments
    Purpose: Execute the test administrator can view selected users assignments operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, beta = projects
    admin_state = dict(app.st.session_state)
    mentor_id = auth.create_user("Assigned Mentor", "assigned-mentor", PASSWORD, "Mentor")
    access.assign_project(admin_state, mentor_id, alpha.id)
    access.assign_project(admin_state, mentor_id, beta.id)
    assignments = access.user_project_assignments(admin_state, mentor_id)
    assert [(row["id"], row["name"]) for row in assignments] == [
        (alpha.id, alpha.name),
        (beta.id, beta.name),
    ]


@pytest.mark.parametrize("role", ["Mentor"])
def test_assigned_staff_can_update_but_cannot_update_unrelated_project(role, projects):
    """
    Function: test_assigned_staff_can_update_but_cannot_update_unrelated_project
    Purpose: Execute the test assigned staff can update but cannot update unrelated project operation.
    Inputs:
            role (value): Caller-provided input.
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, beta = projects
    sign_in_role(role, alpha)
    alpha.description = "Updated by assigned staff"
    app.update_project(alpha)
    assert app.get_project(alpha.id).description == alpha.description
    with pytest.raises(access.AccessDenied):
        app.update_project(beta)
    app.install_project_uploaded_files(alpha.id, [("new.txt", b"New staff guidance")])
    with pytest.raises(access.AccessDenied):
        app.install_project_uploaded_files(beta.id, [("new.txt", b"Forbidden")])


def test_revoked_assignment_and_disabled_user_take_effect_immediately(projects):
    """
    Function: test_revoked_assignment_and_disabled_user_take_effect_immediately
    Purpose: Execute the test revoked assignment and disabled user take effect immediately operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, _ = projects
    admin_state = dict(app.st.session_state)
    # Keep the independent administrator session alive.
    student_id = auth.create_user("Student", "student", PASSWORD, "Student")
    access.assign_project(admin_state, student_id, alpha.id)
    student_state = {}
    auth.login(student_state, "student", PASSWORD)
    assert access.can_access_project(student_state, alpha.id)
    access.assign_project(admin_state, student_id, alpha.id, assigned=False)
    with pytest.raises(access.AccessDenied):
        access.require_project(student_state, alpha.id)
    access.update_user(admin_state, student_id, "Student", False)
    assert auth.current_user(student_state) is None
    assert auth.authenticate("student", PASSWORD) is None


def test_expired_session_and_unauthenticated_direct_access(projects):
    """
    Function: test_expired_session_and_unauthenticated_direct_access
    Purpose: Execute the test expired session and unauthenticated direct access operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    with database.connect() as db:
        db.execute("UPDATE sessions SET expires_at = ?", (time.time() - 1,))
    assert auth.current_user(app.st.session_state) is None
    with pytest.raises(access.AccessDenied):
        app.load_project_index(projects[0].id)
    app.st.session_state.clear()
    with pytest.raises(access.AccessDenied):
        app.get_projects()


def test_analytics_only_include_authorised_projects(projects):
    """
    Function: test_analytics_only_include_authorised_projects
    Purpose: Execute the test analytics only include authorised projects operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, beta = projects
    app.record_question_analytics("Alpha question", alpha.id)
    app.record_question_analytics("Beta secret", beta.id)
    sign_in_role("Mentor", alpha)
    assert [record["question"] for record in app.load_question_analytics()] == ["Alpha question"]


def test_migration_is_repeatable_preserves_profiles_and_does_not_assign_by_name(tmp_path):
    """
    Function: test_migration_is_repeatable_preserves_profiles_and_does_not_assign_by_name
    Purpose: Execute the test migration is repeatable preserves profiles and does not assign by name operation.
    Inputs:
            tmp_path (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    legacy = tmp_path / "legacy.json"
    record = {"id": "existing", "name": "Existing", "revision": 7,
              "team": [{"name": "Student"}], "meetings": [{"discussion": "Preserve"}]}
    legacy.write_text(json.dumps([record]))
    before = legacy.read_bytes()
    path = tmp_path / "migration.sqlite3"
    database.initialize(path, legacy)
    database.initialize(path, legacy)
    with database.connect(path) as db:
        assert json.loads(db.execute("SELECT profile FROM projects").fetchone()[0]) == record
        assert db.execute("SELECT count(*) FROM assignments").fetchone()[0] == 0
        assert db.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION
    assert legacy.read_bytes() == before


def test_failed_migration_rolls_back_and_can_retry(tmp_path):
    """
    Function: test_failed_migration_rolls_back_and_can_retry
    Purpose: Execute the test failed migration rolls back and can retry operation.
    Inputs:
            tmp_path (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    legacy = tmp_path / "legacy.json"
    legacy.write_text('[{"id":"../bad","name":"Bad"}]')
    path = tmp_path / "retry.sqlite3"
    with pytest.raises(ValueError):
        database.initialize(path, legacy)
    legacy.write_text('[{"id":"valid","name":"Valid"}]')
    database.initialize(path, legacy)
    with database.connect(path) as db:
        assert db.execute("SELECT id FROM projects").fetchone()[0] == "valid"
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO assignments VALUES (999, 'valid')")


def test_admin_account_management_and_foreign_key_cleanup(projects):
    """
    Function: test_admin_account_management_and_foreign_key_cleanup
    Purpose: Execute the test admin account management and foreign key cleanup operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, _ = projects
    user_id = access.create_user(app.st.session_state, "Created", "created", PASSWORD, "Student")
    access.assign_project(app.st.session_state, user_id, alpha.id)
    access.update_user(app.st.session_state, user_id, "Mentor", True)
    assert auth.authenticate("created", PASSWORD)["role"] == "Mentor"
    app.delete_project(alpha.id)
    with database.connect() as db:
        assert db.execute("SELECT count(*) FROM assignments WHERE user_id = ?", (user_id,)).fetchone()[0] == 0
    with pytest.raises(ValueError):
        actor_id = auth.current_user(app.st.session_state)["id"]
        access.update_user(app.st.session_state, actor_id, "Student", True)


def test_profile_is_loaded_from_database_not_supplied_object(projects):
    """
    Function: test_profile_is_loaded_from_database_not_supplied_object
    Purpose: Execute the test profile is loaded from database not supplied object operation.
    Inputs:
            projects (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    alpha, _ = projects
    sign_in_role("Student", alpha)
    alpha.description = "FORGED PROFILE CONTENT"
    assert "FORGED PROFILE CONTENT" not in app.build_project_profile(alpha)


def test_demo_cli_is_idempotent_and_prints_only_new_random_passwords(monkeypatch, capsys):
    """
    Function: test_demo_cli_is_idempotent_and_prints_only_new_random_passwords
    Purpose: Execute the test demo cli is idempotent and prints only new random passwords operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
            capsys (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    from scripts import manage
    monkeypatch.setattr("sys.argv", ["scripts/manage.py", "seed-demo"])
    manage.main()
    output = capsys.readouterr().out
    assert "DEVELOPMENT / DEMO ONLY" in output
    for role in database.ROLES:
        username = f"{role.lower()}@demo.local"
        password = next(line.split()[1] for line in output.splitlines() if line.startswith(username))
        assert auth.authenticate(username, password)["role"] == role
    manage.main()
    assert "Skipped existing student@demo.local" in capsys.readouterr().out
    with database.connect() as db:
        assert db.execute("SELECT count(*) FROM users WHERE username LIKE '%@demo.local'").fetchone()[0] == 4
        assert db.execute("SELECT count(*) FROM assignments").fetchone()[0] == 3
