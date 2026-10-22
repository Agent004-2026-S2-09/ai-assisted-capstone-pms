## File: tests/test_scheduling_accounts.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing test scheduling accounts functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

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


def test_gantt_import_creates_idempotent_task_cards_but_not_milestone_cards(monkeypatch):
    """
    Function: test_gantt_import_creates_idempotent_task_cards_but_not_milestone_cards
    Purpose: Execute the test gantt import creates idempotent task cards but not milestone cards operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    state = {}
    admin_id = auth.create_user("Schedule Admin", "schedule-admin", "schedule-admin-password", "Administrator")
    assert auth.login(state, "schedule-admin", "schedule-admin-password")
    database.write_projects([{"id": "schedule", "name": "Schedule", "profile": {"id": "schedule", "name": "Schedule"}}])
    workbook = gantt.template_bytes()
    plan = gantt.import_workbook(state, "schedule", workbook)
    assert len(plan["tasks"]) == 2
    board = kanban.get_board(state, "schedule")
    assert len(board["cards"]) == 1
    assert next(iter(board["cards"].values()))["milestone_id"] == plan["tasks"][0]["id"]
    gantt.import_workbook(state, "schedule", workbook)
    assert len(kanban.get_board(state, "schedule")["cards"]) == 1
    assert admin_id


def test_simple_gantt_sheet_maps_statuses_to_kanban_columns():
    """
    Function: test_simple_gantt_sheet_maps_statuses_to_kanban_columns
    Purpose: Execute the test simple gantt sheet maps statuses to kanban columns operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    state = {}
    password = "simple-import-admin-password"
    auth.create_user("Simple Import Admin", "simple-import-admin", password, "Administrator")
    assert auth.login(state, "simple-import-admin", password)
    database.write_projects([{"id": "simple-import", "name": "Simple Import", "milestones": []}])
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["WBS", "Task / Sub-task", "Start", "Finish", "days", "Status"])
    sheet.append(["1", "Initiation", "2026-08-10", "2026-08-16", 7, "Done"])
    sheet.append(["1.1", "Form team", "2026-08-10", "2026-08-10", 1, "Done"])
    sheet.append(["1.2", "Review options", "2026-08-10", "2026-08-12", 3, "Review"])
    sheet.append(["1.3", "Prepare EOI", "2026-08-10", "2026-08-12", 3, "To Do"])
    stream = io.BytesIO()
    workbook.save(stream)

    plan = gantt.import_workbook(state, "simple-import", stream.getvalue(), replace=True)
    assert len(plan["tasks"]) == 4
    milestone = next(task for task in plan["tasks"] if task["code"] == "1")
    assert milestone["type"] == "Milestone"
    board = kanban.get_board(state, "simple-import")
    cards_by_title = {card["title"]: card for card in board["cards"].values()}
    assert set(cards_by_title) == {"Form team", "Review options", "Prepare EOI"}
    locations = {
        card["title"]: column["id"]
        for column in board["columns"]
        for card_id in column["cardIds"]
        for card in [board["cards"].get(card_id)]
        if card
    }
    assert locations == {"Form team": "done", "Review options": "review", "Prepare EOI": "todo"}
    assert all(card["milestone_id"] == milestone["id"] for card in cards_by_title.values())


def test_kanban_stage_moves_update_linked_gantt_progress():
    """
    Function: test_kanban_stage_moves_update_linked_gantt_progress
    Purpose: Execute the test kanban stage moves update linked gantt progress operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    assert not board["cards"]
    assert gantt.get_plan(state, "progress")["tasks"][0]["progress"] == 0
    assert plan["tasks"]


def test_drag_style_board_saves_update_linked_gantt_progress_without_card_metadata():
    """
    Function: test_drag_style_board_saves_update_linked_gantt_progress_without_card_metadata
    Purpose: Execute the test drag style board saves update linked gantt progress without card metadata operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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


def test_kanban_round_trip_keeps_gantt_status_and_progress_in_sync():
    """Moving a linked task through the board updates every workflow field."""
    state = {}
    password = "round-trip-admin-password"
    auth.create_user("Round Trip Admin", "round-trip-admin", password, "Administrator")
    assert auth.login(state, "round-trip-admin", password)
    database.write_projects([{"id": "round-trip", "name": "Round Trip", "milestones": []}])

    gantt.add_task(state, "round-trip", {
        "code": "1", "name": "Round-trip task", "type": "Task",
        "start": "2026-10-02", "finish": "2026-10-05", "progress": 0,
        "status": "Planned", "resource": "", "predecessors": [],
        "details": "", "milestone": False,
    })
    card_id = next(iter(kanban.get_board(state, "round-trip")["cards"]))
    task_id = gantt.get_plan(state, "round-trip")["tasks"][0]["id"]

    expected = [
        ("done", 100, "Completed"),
        ("backlog", 0, "Planned"),
        ("review", 75, "In Progress"),
        ("progress", 50, "In Progress"),
        ("backlog", 0, "Planned"),
    ]
    for column_id, progress, status in expected:
        kanban.move_card(state, "round-trip", card_id, column_id)
        task = gantt.get_plan(state, "round-trip")["tasks"][0]
        assert task["id"] == task_id
        assert task["progress"] == progress
        assert task["status"] == status
        assert task["kanban_column"] == column_id


def test_gantt_and_kanban_crud_stays_bidirectionally_synchronised():
    """
    Function: test_gantt_and_kanban_crud_stays_bidirectionally_synchronised
    Purpose: Execute the test gantt and kanban crud stays bidirectionally synchronised operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    """
    Function: test_gantt_milestones_are_linked_without_replacing_manual_records
    Purpose: Execute the test gantt milestones are linked without replacing manual records operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    assert not kanban.get_board(state, "milestone-link")["cards"]
    records = next(item for item in database.read_projects() if item["id"] == "milestone-link")["milestones"]
    assert [item["id"] for item in records if item["id"] == "manual-1"] == ["manual-1"]
    linked = next(item for item in records if item.get("source") == "gantt")
    assert linked["status"] == "Planned"

    records = next(item for item in database.read_projects() if item["id"] == "milestone-link")["milestones"]
    assert [item["id"] for item in records if item.get("source") != "gantt"] == ["manual-1"]
    linked = next(item for item in records if item.get("source") == "gantt")
    assert linked["name"] == "Prototype accepted"
    assert linked["status"] == "Planned"
    assert linked["gantt_code"] == "1"


def test_milestone_edits_and_deletes_propagate_to_gantt_without_task_card():
    """
    Function: test_milestone_edits_and_deletes_propagate_to_gantt_without_task_card
    Purpose: Execute the test milestone edits and deletes propagate to gantt without task card operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    assert task["name"] == "Updated checkpoint"
    assert task["finish"] == "2026-10-12"
    assert task["progress"] == 0
    assert task["status"] == "Planned"
    assert not kanban.get_board(state, "milestone-crud")["cards"]

    milestones.delete_milestone(state, "milestone-crud", record["id"])
    assert not gantt.get_plan(state, "milestone-crud")["tasks"]
    assert not kanban.get_board(state, "milestone-crud")["cards"]


def test_only_explicit_gantt_milestones_sync_to_milestones_tab():
    """
    Function: test_only_explicit_gantt_milestones_sync_to_milestones_tab
    Purpose: Execute the test only explicit gantt milestones sync to milestones tab operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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


def test_milestone_progress_is_weighted_from_explicit_child_tasks():
    """
    Function: test_milestone_progress_is_weighted_from_explicit_child_tasks
    Purpose: Execute the test milestone progress is weighted from explicit child tasks operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    state = {}
    password = "rollup-admin-password"
    auth.create_user("Rollup Admin", "rollup-admin", password, "Administrator")
    assert auth.login(state, "rollup-admin", password)
    database.write_projects([{"id": "rollup", "name": "Rollup", "milestones": []}])

    milestone_plan = gantt.add_task(state, "rollup", {
        "code": "1", "name": "Build", "type": "Milestone", "start": "2026-10-01",
        "finish": "2026-10-01", "progress": 0, "status": "Planned", "resource": "",
        "predecessors": [], "details": "", "milestone": True,
    })
    milestone_id = milestone_plan["tasks"][0]["id"]
    gantt.add_task(state, "rollup", {
        "code": "1.1", "name": "Long task", "type": "Task", "start": "2026-10-01",
        "finish": "2026-10-05", "progress": 50, "status": "In Progress", "resource": "",
        "predecessors": [], "details": "", "milestone": False, "milestone_id": milestone_id,
    })
    plan = gantt.add_task(state, "rollup", {
        "code": "1.2", "name": "Short task", "type": "Task", "start": "2026-10-06",
        "finish": "2026-10-06", "progress": 100, "status": "Completed", "resource": "",
        "predecessors": [], "details": "", "milestone": False, "milestone_id": milestone_id,
    })
    milestone = next(task for task in plan["tasks"] if task["id"] == milestone_id)
    assert milestone["milestone_id"] is None
    assert milestone["progress"] == 58
    assert milestone["status"] == "In Progress"
    assert milestone["linked_task_count"] == 2
    assert milestone["completed_task_count"] == 1

    project = next(item for item in database.read_projects() if item["id"] == "rollup")
    projection = next(item for item in project["milestones"] if item.get("gantt_task_id") == milestone_id)
    assert projection["progress"] == 58
    assert projection["linked_task_count"] == 2

    # The UI loads profiles through Project.from_dict; calculated roll-up
    # fields must survive that sanitisation boundary.
    loaded_project = app.Project.from_dict(project)
    loaded_projection = next(
        item for item in loaded_project.milestones
        if item.get("gantt_task_id") == milestone_id
    )
    assert loaded_projection["progress"] == 58
    assert loaded_projection["linked_task_count"] == 2
    assert loaded_projection["completed_task_count"] == 1

    plan["tasks"][1]["progress"] = 100
    plan["tasks"][1]["status"] = "Completed"
    plan = gantt.save_plan(state, "rollup", plan)
    milestone = next(task for task in plan["tasks"] if task["id"] == milestone_id)
    assert milestone["progress"] == 100
    assert milestone["status"] == "Completed"


def test_linked_milestone_cannot_be_deleted_until_children_are_reassigned():
    """
    Function: test_linked_milestone_cannot_be_deleted_until_children_are_reassigned
    Purpose: Execute the test linked milestone cannot be deleted until children are reassigned operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    state = {}
    password = "delete-rollup-admin-password"
    auth.create_user("Delete Rollup Admin", "delete-rollup-admin", password, "Administrator")
    assert auth.login(state, "delete-rollup-admin", password)
    database.write_projects([{"id": "delete-rollup", "name": "Delete Rollup", "milestones": []}])
    plan = gantt.add_task(state, "delete-rollup", {
        "code": "1", "name": "Checkpoint", "type": "Milestone", "start": "2026-10-01",
        "finish": "2026-10-01", "progress": 0, "resource": "", "predecessors": [],
        "details": "", "milestone": True,
    })
    milestone_id = plan["tasks"][0]["id"]
    plan = gantt.add_task(state, "delete-rollup", {
        "code": "1.1", "name": "Child", "type": "Task", "start": "2026-10-01",
        "finish": "2026-10-01", "progress": 0, "resource": "", "predecessors": [],
        "details": "", "milestone": False, "milestone_id": milestone_id,
    })
    with pytest.raises(ValueError, match="linked task"):
        gantt.delete_task(state, "delete-rollup", milestone_id)


def test_feature_flags_are_admin_only():
    """
    Function: test_feature_flags_are_admin_only
    Purpose: Execute the test feature flags are admin only operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    state = {}
    auth.create_user("Flag Admin", "flag-admin", "flag-admin-password", "Administrator")
    assert auth.login(state, "flag-admin", "flag-admin-password")
    settings.update_settings(state, {"feature_kanban": False})
    assert not settings.is_enabled("feature_kanban")
    assert not settings.is_enabled("feature_kanban_ai")
    assert not settings.is_enabled("feature_backlog_sync")


def test_tab_settings_control_all_child_capabilities():
    """
    Function: test_tab_settings_control_all_child_capabilities
    Purpose: Execute the test tab settings control all child capabilities operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    """
    Function: test_task_assistant_history_is_scoped_to_the_selected_project
    Purpose: Execute the test task assistant history is scoped to the selected project operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    state = {}
    first_project_history = app._get_kanban_ai_history(state, "project-one")
    first_project_history.append({"question": "Create a research task", "response": "Completed."})

    assert app._get_kanban_ai_history(state, "project-one") == first_project_history
    assert app._get_kanban_ai_history(state, "project-two") == []


def test_profile_verified_login_password_change_and_templates():
    """
    Function: test_profile_verified_login_password_change_and_templates
    Purpose: Execute the test profile verified login password change and templates operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    auth.create_user("Ada Lovelace", "ada", "temporary-password", "Student", email="ada@example.edu", first_name="Ada", last_name="Lovelace")
    auth.change_password_from_login("ada", "Ada Lovelace", "ada@example.edu", "replacement-password", "replacement-password")
    assert auth.authenticate("ada", "replacement-password")
    with zipfile.ZipFile(io.BytesIO(templates.user_template_bytes())) as archive:
        assert any(b"Temporary password" in archive.read(name) for name in archive.namelist() if name.endswith(".xml"))


def test_administrator_can_import_user_accounts_from_excel():
    """
    Function: test_administrator_can_import_user_accounts_from_excel
    Purpose: Execute the test administrator can import user accounts from excel operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    """
    Function: test_user_import_rejects_duplicate_batch_without_partial_writes
    Purpose: Execute the test user import rejects duplicate batch without partial writes operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
