import io
import zipfile

import pytest
import app
from app_modules import auth
from app_modules import database
from app_modules import gantt
from app_modules import kanban
from app_modules import milestones
from app_modules import settings
from app_modules import templates
from app_modules import access_control as access
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


def test_gantt_and_kanban_crud_stays_bidirectionally_synchronised():
    state = {}
    password = "bidirectional-admin-password"
    auth.create_user("Bidirectional Admin", "bidirectional-admin", password, "Administrator")
    assert auth.login(state, "bidirectional-admin", password)
    database.write_projects([{"id": "bidirectional", "name": "Bidirectional", "profile": {"id": "bidirectional", "name": "Bidirectional"}}])

    gantt.add_task(state, "bidirectional", {
        "code": "1",
        "name": "Initial schedule task",
        "type": "Task",
        "start": "2026-10-02",
        "finish": "2026-10-05",
        "progress": 0,
        "resource": "",
        "predecessors": [],
        "details": "Initial details",
        "milestone": False,
    })
    board = kanban.get_board(state, "bidirectional")
    linked_card_id = next(iter(board["cards"]))
    gantt_task_id = gantt.get_plan(state, "bidirectional")["tasks"][0]["id"]

    gantt.update_task(
        state,
        "bidirectional",
        gantt_task_id,
        {**gantt.get_plan(state, "bidirectional")["tasks"][0], "name": "Renamed schedule task", "details": "Updated details"},
    )
    updated_card = kanban.get_board(state, "bidirectional")["cards"][linked_card_id]
    assert updated_card["title"] == "Renamed schedule task"
    assert updated_card["details"] == "Updated details"

    gantt.delete_task(state, "bidirectional", gantt_task_id)
    assert not kanban.get_board(state, "bidirectional")["cards"]

    manual_card_id = kanban.add_card(state, "bidirectional", "Manual task", "Manual details")
    plan = gantt.get_plan(state, "bidirectional")
    assert len(plan["tasks"]) == 1
    linked_task = plan["tasks"][0]
    assert linked_task["name"] == "Manual task"

    kanban.update_card(state, "bidirectional", manual_card_id, "Edited manual task", "Edited details")
    linked_task = gantt.get_plan(state, "bidirectional")["tasks"][0]
    assert linked_task["name"] == "Edited manual task"
    assert linked_task["details"] == "Edited details"

    kanban.move_card(state, "bidirectional", manual_card_id, "done")
    assert gantt.get_plan(state, "bidirectional")["tasks"][0]["progress"] == 100
    kanban.delete_card(state, "bidirectional", manual_card_id)
    assert not gantt.get_plan(state, "bidirectional")["tasks"]


def test_gantt_milestones_are_linked_without_replacing_manual_records():
    state = {}
    password = "milestone-link-admin-password"
    auth.create_user("Milestone Link Admin", "milestone-link-admin", password, "Administrator")
    assert auth.login(state, "milestone-link-admin", password)
    database.write_projects([{"id": "milestone-link", "name": "Milestone Link", "milestones": [{"id": "manual-1", "name": "Sponsor decision", "status": "Completed", "date": "2026-10-01", "notes": "Manual record"}]}])

    gantt.add_task(state, "milestone-link", {
        "code": "1",
        "name": "Prototype accepted",
        "type": "Milestone",
        "start": "2026-10-02",
        "finish": "2026-10-02",
        "progress": 0,
        "resource": "",
        "predecessors": [],
        "details": "Acceptance recorded by the project team.",
        "milestone": True,
    })
    card_id = next(iter(kanban.get_board(state, "milestone-link")["cards"]))
    records = next(item for item in database.read_projects() if item["id"] == "milestone-link")["milestones"]
    assert [item["id"] for item in records if item["id"] == "manual-1"] == ["manual-1"]
    linked = next(item for item in records if item.get("source") == "gantt")
    assert linked["status"] == "Planned"

    kanban.move_card(state, "milestone-link", card_id, "done")
    records = next(item for item in database.read_projects() if item["id"] == "milestone-link")["milestones"]
    assert [item["id"] for item in records if item.get("source") != "gantt"] == ["manual-1"]
    linked = next(item for item in records if item.get("source") == "gantt")
    assert linked["name"] == "Prototype accepted"
    assert linked["status"] == "Completed"
    assert linked["gantt_code"] == "1"

    kanban.move_card(state, "milestone-link", card_id, "progress")
    records = next(item for item in database.read_projects() if item["id"] == "milestone-link")["milestones"]
    assert next(item for item in records if item.get("source") == "gantt")["status"] == "In Progress"


def test_milestone_edits_and_deletes_propagate_to_gantt_and_kanban():
    state = {}
    password = "milestone-crud-admin-password"
    auth.create_user("Milestone CRUD Admin", "milestone-crud-admin", password, "Administrator")
    assert auth.login(state, "milestone-crud-admin", password)
    database.write_projects([{"id": "milestone-crud", "name": "Milestone CRUD", "profile": {"id": "milestone-crud", "name": "Milestone CRUD", "milestones": []}}])

    gantt.add_task(state, "milestone-crud", {
        "code": "1", "name": "Initial checkpoint", "type": "Milestone",
        "start": "2026-10-02", "finish": "2026-10-02", "progress": 0,
        "status": "Planned", "resource": "", "predecessors": [],
        "details": "Initial notes", "milestone": True,
    })
    record = next(item for item in database.read_projects()[0]["milestones"] if item.get("source") == "gantt")
    milestones.update_milestone(
        state, "milestone-crud", record["id"], name="Updated checkpoint",
        target_date="2026-10-12", status="Completed", notes="Approved by sponsor",
    )
    task = gantt.get_plan(state, "milestone-crud")["tasks"][0]
    card = next(iter(kanban.get_board(state, "milestone-crud")["cards"].values()))
    assert task["name"] == "Updated checkpoint"
    assert task["finish"] == "2026-10-12"
    assert task["progress"] == 100
    assert card["title"] == "Updated checkpoint"
    assert card["details"] == "Approved by sponsor"

    milestones.delete_milestone(state, "milestone-crud", record["id"])
    assert not gantt.get_plan(state, "milestone-crud")["tasks"]
    assert not kanban.get_board(state, "milestone-crud")["cards"]


def test_only_explicit_gantt_milestones_sync_to_milestones_tab():
    state = {}
    password = "explicit-milestone-admin-password"
    auth.create_user("Explicit Milestone Admin", "explicit-milestone-admin", password, "Administrator")
    assert auth.login(state, "explicit-milestone-admin", password)
    database.write_projects([{"id": "explicit-milestone", "name": "Explicit Milestone", "milestones": []}])
    gantt.add_task(state, "explicit-milestone", {
        "code": "1", "name": "Normal task", "type": "Task", "start": "2026-10-02",
        "finish": "2026-10-05", "progress": 0, "resource": "", "predecessors": [],
        "details": "", "milestone": False,
    })
    assert not database.read_projects()[0]["milestones"]


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
