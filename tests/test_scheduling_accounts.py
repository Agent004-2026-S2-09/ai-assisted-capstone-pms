import io
import zipfile

import pytest
import app
import auth
import database
import gantt
import kanban
import settings
import templates
import access_control as access
import openpyxl


def test_gantt_import_creates_idempotent_kanban_backlog_cards(monkeypatch):
    state = {}
    admin_id = auth.create_user("Schedule Admin", "schedule-admin", "schedule-admin-password", "Administrator")
    assert auth.login(state, "schedule-admin", "schedule-admin-password")
    database.write_projects([{"id": "schedule", "name": "Schedule", "profile": {"id": "schedule", "name": "Schedule"}}])
    workbook = gantt.template_bytes()
    plan = gantt.import_workbook(state, "schedule", workbook)
    assert len(plan["tasks"]) == 2
    board = kanban.get_board(state, "schedule")
    assert len(board["cards"]) == 2
    gantt.import_workbook(state, "schedule", workbook)
    assert len(kanban.get_board(state, "schedule")["cards"]) == 2
    assert admin_id


def test_kanban_stage_moves_update_linked_gantt_progress():
    state = {}
    auth.create_user("Progress Admin", "progress-admin", "progress-admin-password", "Administrator")
    assert auth.login(state, "progress-admin", "progress-admin-password")
    database.write_projects([{"id": "progress", "name": "Progress", "profile": {"id": "progress", "name": "Progress"}}])
    plan = gantt.add_task(state, "progress", {
        "code": "1",
        "name": "Linked milestone",
        "type": "Milestone",
        "start": "2026-10-02",
        "finish": "2026-10-02",
        "progress": 0,
        "resource": "",
        "predecessors": [],
        "details": "",
        "milestone": True,
    })
    board = kanban.get_board(state, "progress")
    card_id = next(iter(board["cards"]))
    expected = {"backlog": 0, "todo": 25, "progress": 50, "review": 75, "done": 100}
    for column_id, progress in expected.items():
        kanban.move_card(state, "progress", card_id, column_id)
        current = gantt.get_plan(state, "progress")
        assert current["tasks"][0]["progress"] == progress
    updated_board = kanban.get_board(state, "progress")
    assert "Progress:" not in updated_board["cards"][card_id]["details"]
    assert plan["tasks"]


def test_drag_style_board_saves_update_linked_gantt_progress_without_card_metadata():
    state = {}
    auth.create_user("Drag Progress Admin", "drag-progress-admin", "drag-progress-password", "Administrator")
    assert auth.login(state, "drag-progress-admin", "drag-progress-password")
    database.write_projects([{"id": "drag-progress", "name": "Drag Progress", "profile": {"id": "drag-progress", "name": "Drag Progress"}}])
    gantt.add_task(state, "drag-progress", {"code": "1", "name": "Drag task", "type": "Task", "start": "2026-10-02", "finish": "2026-10-05", "progress": 0, "resource": "", "predecessors": [], "details": "Short task detail", "milestone": False})
    expected = {"backlog": 0, "todo": 25, "progress": 50, "review": 75, "done": 100}
    card_id = next(iter(kanban.get_board(state, "drag-progress")["cards"]))
    for column_id, progress in expected.items():
        board = kanban.get_board(state, "drag-progress")
        for column in board["columns"]:
            column["cardIds"] = [value for value in column["cardIds"] if value != card_id]
        next(column for column in board["columns"] if column["id"] == column_id)["cardIds"].append(card_id)
        kanban.save_board(state, "drag-progress", board)
        assert gantt.get_plan(state, "drag-progress")["tasks"][0]["progress"] == progress
    assert "Progress:" not in kanban.get_board(state, "drag-progress")["cards"][card_id]["details"]


def test_feature_flags_are_admin_only():
    state = {}
    auth.create_user("Flag Admin", "flag-admin", "flag-admin-password", "Administrator")
    assert auth.login(state, "flag-admin", "flag-admin-password")
    settings.update_settings(state, {"feature_kanban": False})
    assert not settings.is_enabled("feature_kanban")
    assert not settings.is_enabled("feature_kanban_ai")
    assert not settings.is_enabled("feature_backlog_sync")


def test_tab_settings_control_all_child_capabilities():
    state = {}
    auth.create_user("Tab Admin", "tab-admin", "tab-admin-password", "Administrator")
    assert auth.login(state, "tab-admin", "tab-admin-password")
    settings.update_settings(state, {"feature_gantt": False, "feature_kanban": True})
    assert settings.is_enabled("feature_kanban")
    assert settings.is_enabled("feature_kanban_ai")
    assert not settings.is_enabled("feature_gantt_import")
    assert not settings.is_enabled("feature_backlog_sync")
    assert set(settings.all_settings(state)) == {"feature_gantt", "feature_kanban"}
    assert settings.is_enabled("feature_user_creation")


def test_task_assistant_history_is_scoped_to_the_selected_project():
    state = {}
    first_project_history = app._get_kanban_ai_history(state, "project-one")
    first_project_history.append({"question": "Create a research task", "response": "Completed."})

    assert app._get_kanban_ai_history(state, "project-one") == first_project_history
    assert app._get_kanban_ai_history(state, "project-two") == []


def test_profile_verified_login_password_change_and_templates():
    auth.create_user("Ada Lovelace", "ada", "temporary-password", "Student", email="ada@example.edu", first_name="Ada", last_name="Lovelace")
    auth.change_password_from_login("ada", "Ada Lovelace", "ada@example.edu", "replacement-password", "replacement-password")
    assert auth.authenticate("ada", "replacement-password")
    with zipfile.ZipFile(io.BytesIO(templates.user_template_bytes())) as archive:
        assert any(b"Temporary password" in archive.read(name) for name in archive.namelist() if name.endswith(".xml"))


def test_administrator_can_import_user_accounts_from_excel():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(templates.USER_HEADERS)
    sheet.append(["imported.student", "Imported", "Student", "imported@example.edu", "Student", "imported-password", "active"])
    content = io.BytesIO()
    workbook.save(content)
    rows = templates.parse_user_workbook(content.getvalue())
    state = {}
    assert auth.login(state, "admin@test.local", "test-password-long")
    created = access.import_users(state, rows)
    assert len(created) == 1
    imported = auth.authenticate("imported.student", "imported-password")
    assert imported["role"] == "Student"
    assert imported["must_change_password"] == 1


def test_user_import_rejects_duplicate_batch_without_partial_writes():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(templates.USER_HEADERS)
    sheet.append(["duplicate.one", "Duplicate", "One", "duplicate.one@example.edu", "Student", "duplicate-password", "active"])
    sheet.append(["duplicate.one", "Duplicate", "Two", "duplicate.two@example.edu", "Student", "duplicate-password", "active"])
    content = io.BytesIO()
    workbook.save(content)
    rows = templates.parse_user_workbook(content.getvalue())
    state = {}
    assert auth.login(state, "admin@test.local", "test-password-long")
    with pytest.raises(ValueError, match="duplicate username or email"):
        access.import_users(state, rows)
    assert auth.authenticate("duplicate.one", "duplicate-password") is None
