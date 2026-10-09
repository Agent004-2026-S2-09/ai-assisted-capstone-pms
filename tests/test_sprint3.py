"""Database, login, role enforcement and private retrieval regression tests."""
import json
import sqlite3
import time

import pytest

import app
from app_modules import auth
from app_modules import database
from app_modules import access_control as access

PASSWORD = "a-long-test-password"


@pytest.fixture
def projects():
    alpha = app.create_project("Alpha")
    beta = app.create_project("Beta")
    app.install_project_uploaded_files(alpha.id, [("alpha.txt", b"Alpha uses offline mobile caching.")])
    app.install_project_uploaded_files(beta.id, [("beta.txt", b"Beta secret satellite dashboard.")])
    return alpha, beta


def sign_in_role(role, project=None):
    user_id = auth.create_user(f"Test {role}", f"{role}@test.local", PASSWORD, role)
    if project:
        access.assign_project(app.st.session_state, user_id, project.id)
    assert auth.login(app.st.session_state, f"{role}@test.local", PASSWORD)
    return user_id


def test_successful_login_and_hashed_password():
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
    assert auth.authenticate(username, password) is None
    assert not auth.login(app.st.session_state, username, password)
    assert not app.st.session_state


@pytest.mark.parametrize("role", database.ROLES)
def test_role_access_and_direct_denial(role, projects):
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
    sign_in_role("Student", projects[0])
    copied = dict(app.st.session_state)
    app.st.session_state.update(messages=[{"content": "private"}], selected_project_id="alpha", user_role="Administrator")
    auth.logout(app.st.session_state)
    assert dict(app.st.session_state) == {}
    assert auth.current_user(copied) is None
    with pytest.raises(access.AccessDenied):
        app.get_project("alpha")


def test_forged_role_and_name_do_not_grant_access(projects):
    alpha, beta = projects
    sign_in_role("Student", alpha)
    app.st.session_state.update(user_role="Administrator", user_name="Test Administrator", admin_authenticated=True)
    assert not app.can_access_project(beta, "Administrator", "Test Administrator")
    with pytest.raises(access.AccessDenied):
        access.require_admin(app.st.session_state)
    assert auth.current_user(app.st.session_state)["role"] == "Student"


def test_private_retrieval_and_assistant_reject_foreign_context(projects, monkeypatch):
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


def test_student_can_only_be_assigned_to_one_project(projects):
    alpha, beta = projects
    admin_state = dict(app.st.session_state)
    student_id = auth.create_user("Student", "single-project-student", PASSWORD, "Student")
    access.assign_project(admin_state, student_id, alpha.id)
    with pytest.raises(ValueError, match="only one project"):
        access.assign_project(admin_state, student_id, beta.id)


def test_convenor_accesses_all_projects(projects):
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
    with database.connect() as db:
        db.execute("UPDATE sessions SET expires_at = ?", (time.time() - 1,))
    assert auth.current_user(app.st.session_state) is None
    with pytest.raises(access.AccessDenied):
        app.load_project_index(projects[0].id)
    app.st.session_state.clear()
    with pytest.raises(access.AccessDenied):
        app.get_projects()


def test_analytics_only_include_authorised_projects(projects):
    alpha, beta = projects
    app.record_question_analytics("Alpha question", alpha.id)
    app.record_question_analytics("Beta secret", beta.id)
    sign_in_role("Mentor", alpha)
    assert [record["question"] for record in app.load_question_analytics()] == ["Alpha question"]


def test_migration_is_repeatable_preserves_profiles_and_does_not_assign_by_name(tmp_path):
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
    alpha, _ = projects
    sign_in_role("Student", alpha)
    alpha.description = "FORGED PROFILE CONTENT"
    assert "FORGED PROFILE CONTENT" not in app.build_project_profile(alpha)


def test_demo_cli_is_idempotent_and_prints_only_new_random_passwords(monkeypatch, capsys):
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
