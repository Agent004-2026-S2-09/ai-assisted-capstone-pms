"""Project-scoped Kanban boards and Gantt-to-backlog synchronisation."""

import json
import uuid
from datetime import datetime, timezone

import access_control as access
import database
import settings


DEFAULT_COLUMNS = (("backlog", "Backlog"), ("todo", "To do"), ("progress", "In progress"), ("review", "Review"), ("done", "Done"))
COLUMN_PROGRESS = {"backlog": 0, "todo": 25, "progress": 50, "review": 75, "done": 100}


def empty_board():
    return {"columns": [{"id": key, "title": title, "cardIds": []} for key, title in DEFAULT_COLUMNS], "cards": {}}


def _normalise(board):
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
                "source": str(card.get("source", "manual"))[:40],
            }
    return {"columns": columns, "cards": cards}


def get_board(state, project_id):
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
    import gantt

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
    gantt.save_plan(state, project_id, plan)


def add_card(state, project_id, title, details="", column_id="backlog", *, gantt_task_id=None, gantt_code=None, source="manual"):
    board = get_board(state, project_id)
    if column_id not in {column["id"] for column in board["columns"]}:
        raise ValueError("Choose a valid Kanban column.")
    title = str(title or "").strip()
    if not title:
        raise ValueError("Card title is required.")
    card_id = uuid.uuid4().hex
    board["cards"][card_id] = {"id": card_id, "title": title[:160], "details": str(details or "").strip()[:3000], "gantt_task_id": gantt_task_id, "gantt_code": gantt_code, "source": source}
    next(column for column in board["columns"] if column["id"] == column_id)["cardIds"].append(card_id)
    save_board(state, project_id, board)
    return card_id


def sync_gantt_task(state, project_id, task):
    """Create or update exactly one Backlog card for a Gantt task."""
    if not settings.is_enabled("feature_backlog_sync") or not settings.is_enabled("feature_kanban"):
        return None
    board = get_board(state, project_id)
    matching = next((card for card in board["cards"].values() if card.get("gantt_task_id") == task.get("id") or (task.get("code") and card.get("gantt_code") == task.get("code"))), None)
    details = str(task.get("details") or "").strip()[:3000]
    if matching:
        matching.update({"title": task["name"][:160], "details": details, "gantt_task_id": task.get("id"), "gantt_code": task.get("code"), "source": "gantt"})
        save_board(state, project_id, board)
        return matching["id"]
    card_id = uuid.uuid4().hex
    board["cards"][card_id] = {"id": card_id, "title": task["name"][:160], "details": details, "gantt_task_id": task.get("id"), "gantt_code": task.get("code"), "source": "gantt"}
    next(column for column in board["columns"] if column["id"] == "backlog")["cardIds"].append(card_id)
    save_board(state, project_id, board)
    return card_id


def update_card(state, project_id, card_id, title, details):
    board = get_board(state, project_id)
    card = board["cards"].get(card_id)
    if not card or not str(title or "").strip():
        raise ValueError("The Kanban card could not be updated.")
    card["title"] = str(title).strip()[:160]
    card["details"] = str(details or "").strip()[:3000]
    save_board(state, project_id, board)


def move_card(state, project_id, card_id, column_id):
    board = get_board(state, project_id)
    if card_id not in board["cards"] or column_id not in {column["id"] for column in board["columns"]}:
        raise ValueError("The card or destination column could not be found.")
    for column in board["columns"]:
        column["cardIds"] = [value for value in column["cardIds"] if value != card_id]
    next(column for column in board["columns"] if column["id"] == column_id)["cardIds"].append(card_id)
    save_board(state, project_id, board)


def delete_card(state, project_id, card_id):
    board = get_board(state, project_id)
    board["cards"].pop(card_id, None)
    for column in board["columns"]:
        column["cardIds"] = [value for value in column["cardIds"] if value != card_id]
    save_board(state, project_id, board)


def apply_ai_action(state, project_id, action):
    """Apply a validated, project-scoped AI action."""
    access.require_project(state, project_id)
    kind = str(action.get("action", "")).lower()
    board = get_board(state, project_id)
    if kind == "create":
        return add_card(state, project_id, action.get("title"), action.get("details", ""), action.get("column_id", "backlog"), source="ai")
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
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
