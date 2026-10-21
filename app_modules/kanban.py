## File: app_modules/kanban.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Project-scoped Kanban boards and Gantt-to-backlog synchronisation.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Project-scoped Kanban boards and Gantt-to-backlog synchronisation."""

import json
import uuid
from datetime import datetime, timezone

from app_modules import access_control as access
from app_modules import database
from app_modules import settings


DEFAULT_COLUMNS = (("backlog", "Backlog"), ("todo", "To do"), ("progress", "In progress"), ("review", "Review"), ("done", "Done"))
COLUMN_PROGRESS = {"backlog": 0, "todo": 25, "progress": 50, "review": 75, "done": 100}


def _task_column(task):
    """
    Function: _task_column
    Purpose: Execute the  task column operation.
    Inputs:
            task (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    explicit = str(task.get("kanban_column") or "").strip().casefold()
    if explicit in COLUMN_PROGRESS:
        return explicit
    status = str(task.get("status") or "").strip().casefold()
    return {
        "done": "done", "complete": "done", "completed": "done",
        "review": "review", "for review": "review",
        "in progress": "progress", "progress": "progress",
    }.get(status, "backlog")


def empty_board():
    """
    Function: empty_board
    Purpose: Execute the empty board operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return {"columns": [{"id": key, "title": title, "cardIds": []} for key, title in DEFAULT_COLUMNS], "cards": {}}


def _normalise(board):
    """
    Function: _normalise
    Purpose: Execute the  normalise operation.
    Inputs:
            board (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    if not isinstance(board, dict) or not isinstance(board.get("columns"), list) or not isinstance(board.get("cards"), dict):
        return empty_board()
    valid = {key for key, _ in DEFAULT_COLUMNS}
    columns = []
    for column in board["columns"]:
        if not isinstance(column, dict) or column.get("id") not in valid:
            return empty_board()
        columns.append({"id": column["id"], "title": str(column.get("title") or "Column")[:32], "cardIds": [str(item) for item in column.get("cardIds", [])]})
    cards = {}
    for card_id, card in board["cards"].items():
        if isinstance(card, dict) and str(card.get("title", "")).strip():
            cards[str(card_id)] = {
                "id": str(card_id), "title": str(card["title"]).strip()[:160],
                "details": str(card.get("details", "")).strip()[:3000],
                "gantt_task_id": card.get("gantt_task_id"), "gantt_code": card.get("gantt_code"),
                "milestone_id": card.get("milestone_id"),
                "source": str(card.get("source", "manual"))[:40],
            }
    return {"columns": columns, "cards": cards}


def get_board(state, project_id):
    """
    Function: get_board
    Purpose: Execute the get board operation.
    Inputs:
            state (value): Caller-provided input.
            project_id (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    if not settings.is_enabled("feature_kanban"):
        raise PermissionError("Kanban task management is disabled by an Administrator.")
    access.require_project(state, project_id)
    with database.connect() as db:
        row = db.execute("SELECT board_json FROM kanban_boards WHERE project_id = ?", (project_id,)).fetchone()
        if row:
            return _normalise(json.loads(row["board_json"]))
        board = empty_board()
        db.execute("INSERT INTO kanban_boards(project_id, board_json, updated_at) VALUES (?, ?, ?)", (project_id, json.dumps(board), _now()))
        return board


def save_board(state, project_id, board):
    """
    Function: save_board
    Purpose: Execute the save board operation.
    Inputs:
            state (value): Caller-provided input.
            project_id (value): Caller-provided input.
            board (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    access.require_project(state, project_id)
    board = _normalise(board)
    with database.connect() as db:
        existing = db.execute("SELECT board_json FROM kanban_boards WHERE project_id = ?", (project_id,)).fetchone()
    previous = _normalise(json.loads(existing["board_json"])) if existing else empty_board()
    with database.connect() as db:
        db.execute("""INSERT INTO kanban_boards(project_id, board_json, updated_at)
                     VALUES (?, ?, ?) ON CONFLICT(project_id) DO UPDATE SET
                     board_json=excluded.board_json, updated_at=excluded.updated_at""",
                   (project_id, json.dumps(board, ensure_ascii=False), _now()))
    previous_locations = _card_locations(previous)
    current_locations = _card_locations(board)
    for card_id, column_id in current_locations.items():
        if previous_locations.get(card_id) != column_id:
            card = board["cards"].get(card_id)
            if card:
                _sync_linked_gantt_progress(state, project_id, card, column_id)
    access.record_audit(state, "kanban_board_saved", project_id=project_id,
                        details={"card_count": len(board["cards"])})
    return board


def _card_locations(board):
    """
    Function: _card_locations
    Purpose: Execute the  card locations operation.
    Inputs:
            board (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return {
        card_id: column["id"]
        for column in board.get("columns", [])
        for card_id in column.get("cardIds", [])
        if card_id in board.get("cards", {})
    }


def _sync_linked_gantt_progress(state, project_id, card, column_id):
    """Move a linked schedule task's completion with its Kanban workflow stage."""
    if not settings.is_enabled("feature_backlog_sync") or not settings.is_enabled("feature_gantt"):
        return
    task_id = card.get("gantt_task_id")
    task_code = card.get("gantt_code")
    if not task_id and not task_code:
        return
    from app_modules import gantt

    plan = gantt.get_plan(state, project_id)
    task = next(
        (
            item for item in plan["tasks"]
            if (task_id and item.get("id") == task_id)
            or (task_code and item.get("code") == task_code)
        ),
        None,
    )
    if not task:
        return
    task["progress"] = COLUMN_PROGRESS[column_id]
    task["status"] = "Completed" if column_id == "done" else "In Progress" if column_id in {"progress", "review"} else "Planned"
    gantt.save_plan(state, project_id, plan)


def _next_gantt_code(plan, milestone_id=None):
    """Return a collision-free WBS code, nested under a linked milestone when possible."""
    tasks = plan.get("tasks", [])
    milestone = next(
        (task for task in tasks
         if str(task.get("id")) == str(milestone_id)
         and str(task.get("type", "")).casefold() == "milestone"),
        None,
    )
    if milestone and str(milestone.get("code", "")).strip():
        prefix = str(milestone["code"]).strip()
        children = []
        for task in tasks:
            code = str(task.get("code", "")).strip()
            if code.startswith(prefix + "."):
                suffix = code[len(prefix) + 1:]
                if suffix.isdigit():
                    children.append(int(suffix))
        return f"{prefix}.{max(children, default=0) + 1}"
    top_level_codes = [
        int(str(task.get("code", "")).strip())
        for task in tasks
        if str(task.get("code", "")).strip().isdigit()
    ]
    return str(max(top_level_codes, default=0) + 1)


def add_card(state, project_id, title, details="", column_id="backlog", *, gantt_task_id=None, gantt_code=None, milestone_id=None, source="manual"):
    """
    Function: add_card
    Purpose: Execute the add card operation.
    Inputs:
            state (value): Caller-provided input.
            project_id (value): Caller-provided input.
            title (value): Caller-provided input.
            details (value): Caller-provided input.
            column_id (value): Caller-provided input.
            gantt_task_id (value): Caller-provided input.
            gantt_code (value): Caller-provided input.
            milestone_id (value): Caller-provided input.
            source (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    board = get_board(state, project_id)
    if column_id not in {column["id"] for column in board["columns"]}:
        raise ValueError("Choose a valid Kanban column.")
    title = str(title or "").strip()
    if not title:
        raise ValueError("Card title is required.")
    card_id = uuid.uuid4().hex
    card = {"id": card_id, "title": title[:160], "details": str(details or "").strip()[:3000], "gantt_task_id": gantt_task_id, "gantt_code": gantt_code, "milestone_id": milestone_id, "source": source}
    board["cards"][card_id] = card
    next(column for column in board["columns"] if column["id"] == column_id)["cardIds"].append(card_id)
    if (
        source in {"manual", "ai"}
        and not gantt_task_id
        and not gantt_code
        and settings.is_enabled("feature_backlog_sync")
    ):
        from app_modules import gantt
        plan = gantt.get_plan(state, project_id)
        code = _next_gantt_code(plan, milestone_id)
        task_plan = gantt.add_task(
            state,
            project_id,
            {
                "code": code,
                "name": card["title"],
                "type": "Task",
                "start": datetime.now(timezone.utc).date().isoformat(),
                "finish": datetime.now(timezone.utc).date().isoformat(),
                "progress": COLUMN_PROGRESS[column_id],
                "resource": "",
                "predecessors": [],
                "details": card["details"],
                "milestone": False,
                "milestone_id": milestone_id,
            },
            sync_kanban=False,
        )
        linked_task = next(task for task in task_plan["tasks"] if task.get("code") == code)
        card.update({"gantt_task_id": linked_task["id"], "gantt_code": code})
        linked_task["kanban_card_id"] = card_id
        gantt.save_plan(state, project_id, task_plan)
    save_board(state, project_id, board)
    return card_id


def sync_gantt_task(state, project_id, task):
    """Create or update exactly one Backlog card for a Gantt task."""
    if str(task.get("type", "")).casefold() == "milestone":
        return None
    if not settings.is_enabled("feature_backlog_sync") or not settings.is_enabled("feature_kanban"):
        return None
    board = get_board(state, project_id)
    matching = next((card for card in board["cards"].values() if card.get("gantt_task_id") == task.get("id") or (task.get("code") and card.get("gantt_code") == task.get("code"))), None)
    details = str(task.get("details") or "").strip()[:3000]
    target_column = _task_column(task)
    if matching:
        matching.update({"title": task["name"][:160], "details": details, "gantt_task_id": task.get("id"), "gantt_code": task.get("code"), "milestone_id": task.get("milestone_id"), "source": "gantt"})
        for column in board["columns"]:
            column["cardIds"] = [card_id for card_id in column["cardIds"] if card_id != matching["id"]]
        next(column for column in board["columns"] if column["id"] == target_column)["cardIds"].append(matching["id"])
        save_board(state, project_id, board)
        return matching["id"]
    card_id = uuid.uuid4().hex
    board["cards"][card_id] = {"id": card_id, "title": task["name"][:160], "details": details, "gantt_task_id": task.get("id"), "gantt_code": task.get("code"), "milestone_id": task.get("milestone_id"), "source": "gantt"}
    next(column for column in board["columns"] if column["id"] == target_column)["cardIds"].append(card_id)
    save_board(state, project_id, board)
    return card_id


def update_card(state, project_id, card_id, title, details, milestone_id=None):
    """
    Function: update_card
    Purpose: Execute the update card operation.
    Inputs:
            state (value): Caller-provided input.
            project_id (value): Caller-provided input.
            card_id (value): Caller-provided input.
            title (value): Caller-provided input.
            details (value): Caller-provided input.
            milestone_id (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    board = get_board(state, project_id)
    card = board["cards"].get(card_id)
    if not card or not str(title or "").strip():
        raise ValueError("The Kanban card could not be updated.")
    updated_title = str(title).strip()[:160]
    updated_details = str(details or "").strip()[:3000]
    if settings.is_enabled("feature_backlog_sync") and (card.get("gantt_task_id") or card.get("gantt_code")):
        from app_modules import gantt
        plan = gantt.get_plan(state, project_id)
        linked_task = next(
            (
                task for task in plan["tasks"]
                if (card.get("gantt_task_id") and task.get("id") == card.get("gantt_task_id"))
                or (card.get("gantt_code") and task.get("code") == card.get("gantt_code"))
            ),
            None,
        )
        if linked_task:
            linked_task["name"] = updated_title
            linked_task["details"] = updated_details
            if str(linked_task.get("type", "")).casefold() != "milestone":
                linked_task["milestone_id"] = milestone_id
            gantt.update_task(state, project_id, linked_task["id"], linked_task, sync_kanban=False)
    card["title"] = updated_title
    card["details"] = updated_details
    if card.get("gantt_task_id") or card.get("gantt_code"):
        card["milestone_id"] = milestone_id
    save_board(state, project_id, board)


def move_card(state, project_id, card_id, column_id):
    """
    Function: move_card
    Purpose: Execute the move card operation.
    Inputs:
            state (value): Caller-provided input.
            project_id (value): Caller-provided input.
            card_id (value): Caller-provided input.
            column_id (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    board = get_board(state, project_id)
    if card_id not in board["cards"] or column_id not in {column["id"] for column in board["columns"]}:
        raise ValueError("The card or destination column could not be found.")
    for column in board["columns"]:
        column["cardIds"] = [value for value in column["cardIds"] if value != card_id]
    next(column for column in board["columns"] if column["id"] == column_id)["cardIds"].append(card_id)
    save_board(state, project_id, board)


def delete_card(state, project_id, card_id, *, sync_gantt=True):
    """
    Function: delete_card
    Purpose: Execute the delete card operation.
    Inputs:
            state (value): Caller-provided input.
            project_id (value): Caller-provided input.
            card_id (value): Caller-provided input.
            sync_gantt (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    board = get_board(state, project_id)
    card = board["cards"].get(card_id)
    if sync_gantt and card and settings.is_enabled("feature_backlog_sync") and (card.get("gantt_task_id") or card.get("gantt_code")):
        from app_modules import gantt
        try:
            gantt.delete_task(state, project_id, card.get("gantt_task_id"), sync_kanban=False)
        except ValueError:
            plan = gantt.get_plan(state, project_id)
            linked_task = next(
                (
                    task for task in plan["tasks"]
                    if card.get("gantt_code") and task.get("code") == card.get("gantt_code")
                ),
                None,
            )
            if linked_task:
                gantt.delete_task(state, project_id, linked_task["id"], sync_kanban=False)
    board["cards"].pop(card_id, None)
    for column in board["columns"]:
        column["cardIds"] = [value for value in column["cardIds"] if value != card_id]
    save_board(state, project_id, board)


def delete_linked_card(state, project_id, *, gantt_task_id=None, gantt_code=None, sync_gantt=False):
    """
    Function: delete_linked_card
    Purpose: Execute the delete linked card operation.
    Inputs:
            state (value): Caller-provided input.
            project_id (value): Caller-provided input.
            gantt_task_id (value): Caller-provided input.
            gantt_code (value): Caller-provided input.
            sync_gantt (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    board = get_board(state, project_id)
    card_id = next(
        (
            card["id"] for card in board["cards"].values()
            if (gantt_task_id and card.get("gantt_task_id") == gantt_task_id)
            or (gantt_code and card.get("gantt_code") == gantt_code)
        ),
        None,
    )
    if card_id:
        delete_card(state, project_id, card_id, sync_gantt=sync_gantt)


def remove_orphaned_gantt_cards(state, project_id, tasks):
    """Remove linked cards whose Gantt tasks disappeared during replacement imports."""
    valid_ids = {task.get("id") for task in tasks}
    valid_codes = {task.get("code") for task in tasks if task.get("code")}
    board = get_board(state, project_id)
    orphan_ids = [
        card["id"] for card in board["cards"].values()
        if (card.get("gantt_task_id") or card.get("gantt_code"))
        and card.get("gantt_task_id") not in valid_ids
        and card.get("gantt_code") not in valid_codes
    ]
    for card_id in orphan_ids:
        delete_card(state, project_id, card_id, sync_gantt=False)


def apply_ai_action(state, project_id, action):
    """Apply a validated, project-scoped AI action."""
    access.require_project(state, project_id)
    kind = str(action.get("action", "")).lower()
    board = get_board(state, project_id)
    if kind == "create":
        return add_card(
            state,
            project_id,
            action.get("title"),
            action.get("details", ""),
            action.get("column_id", "backlog"),
            milestone_id=action.get("milestone_id"),
            source="ai",
        )
    title = str(action.get("title", "")).strip().casefold()
    matches = [card for card in board["cards"].values() if card.get("title", "").casefold() == title]
    if len(matches) != 1:
        raise ValueError("Please provide the exact task title so I can identify one card.")
    card = matches[0]
    if kind == "move":
        move_card(state, project_id, card["id"], action.get("column_id", "todo"))
    elif kind in {"edit", "update"}:
        update_card(state, project_id, card["id"], action.get("new_title") or card["title"], action.get("details", card.get("details", "")))
    elif kind == "delete":
        delete_card(state, project_id, card["id"])
    else:
        raise ValueError("Unsupported Kanban action.")
    return card["id"]


def _now():
    """
    Function: _now
    Purpose: Execute the  now operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
