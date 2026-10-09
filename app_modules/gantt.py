"""Project schedule persistence, validation and Excel import/template support."""

import io
import json
import re
import uuid
from datetime import datetime, date, timezone

import openpyxl

from app_modules import access_control as access
from app_modules import database
from app_modules import settings


CODE_RE = re.compile(r"^\d+(?:\.\d+)*$")
HEADERS = ["Code", "Task / milestone name", "Type", "Start date", "Finish date", "Progress", "Resource / owner", "Predecessor codes", "Details"]


def empty_plan():
    return {"tasks": []}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _normalise(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        return empty_plan()
    tasks = []
    for raw in plan["tasks"]:
        if not isinstance(raw, dict) or not str(raw.get("name", "")).strip():
            continue
        start = _date(raw.get("start"))
        finish = _date(raw.get("finish")) or start
        try:
            progress = max(0, min(100, int(raw.get("progress", 0))))
        except (TypeError, ValueError):
            progress = 0
        code = str(raw.get("code", "")).strip()
        type_name = str(raw.get("type") or "").strip()
        milestone = type_name.casefold() == "milestone" or (not type_name and bool(raw.get("milestone")))
        progress_status = "Completed" if progress >= 100 else "In Progress" if progress > 0 else "Planned"
        status = str(raw.get("status") or "").strip()
        if status not in {"Planned", "In Progress", "Completed", "At Risk"}:
            status = progress_status
        tasks.append({
            "id": str(raw.get("id") or uuid.uuid4().hex), "code": code[:40],
            "name": str(raw["name"]).strip()[:160], "type": str(raw.get("type") or ("Milestone" if milestone else "Task"))[:20],
            "start": start.isoformat() if start else "", "finish": (start if milestone else finish).isoformat() if (start if milestone else finish) else "",
            "progress": progress, "resource": str(raw.get("resource") or "").strip()[:240],
            "predecessors": [str(value).strip() for value in raw.get("predecessors", []) if str(value).strip()],
            "details": str(raw.get("details") or "").strip()[:3000], "milestone": milestone,
            "status": status,
            "summary": bool(raw.get("summary")), "kanban_card_id": raw.get("kanban_card_id"),
            "project_milestone_id": raw.get("project_milestone_id") if milestone else None,
        })
    return {"tasks": tasks}


def _validate(plan):
    tasks = plan["tasks"]
    codes = [task.get("code", "") for task in tasks if task.get("code")]
    if len(codes) != len(set(codes)):
        raise ValueError("Gantt task codes must be unique.")
    code_set = set(codes)
    ids = {task["id"] for task in tasks}
    for task in tasks:
        code = task.get("code", "")
        if code and not CODE_RE.fullmatch(code):
            raise ValueError(f"Invalid task code: {code}")
        if code and "." in code and code.rsplit(".", 1)[0] not in code_set:
            raise ValueError(f"Task {code} must have a valid parent milestone or summary code.")
        start, finish = _date(task.get("start")), _date(task.get("finish"))
        if start and finish and finish < start:
            raise ValueError(f"Finish date cannot be before start date for {task['name']}.")
        for predecessor in task.get("predecessors", []):
            if predecessor not in code_set and predecessor not in ids:
                raise ValueError(f"Unknown predecessor: {predecessor}")
    # Imports use human-readable task codes while persisted edits may use IDs.
    # Resolve both forms before checking for cycles so Excel schedules cannot
    # introduce a circular dependency by referring to codes.
    id_by_code = {task.get("code"): task["id"] for task in tasks if task.get("code")}
    graph = {
        task["id"]: [id_by_code.get(value, value) for value in task.get("predecessors", [])]
        for task in tasks
    }
    visiting, visited = set(), set()
    def visit(node):
        if node in visiting:
            raise ValueError("Gantt predecessors contain a circular dependency.")
        if node in visited:
            return
        visiting.add(node)
        for predecessor in graph.get(node, []):
            visit(predecessor)
        visiting.remove(node)
        visited.add(node)
    for node in graph:
        visit(node)


def get_plan(state, project_id, seed_tasks=None):
    if not settings.is_enabled("feature_gantt"):
        raise PermissionError("Gantt scheduling is disabled by an Administrator.")
    access.require_project(state, project_id)
    with database.connect() as db:
        row = db.execute("SELECT plan_json FROM gantt_plans WHERE project_id = ?", (project_id,)).fetchone()
        if row:
            return _normalise(json.loads(row["plan_json"]))
        plan = _normalise({"tasks": seed_tasks or []})
        db.execute("INSERT INTO gantt_plans(project_id, plan_json, updated_at) VALUES (?, ?, ?)", (project_id, json.dumps(plan), _now()))
        return plan


def next_top_level_code(state, project_id):
    """Return the next available top-level WBS code for a new milestone."""
    plan = get_plan(state, project_id)
    values = [
        int(str(task.get("code")).strip())
        for task in plan["tasks"]
        if str(task.get("code", "")).strip().isdigit()
    ]
    return str(max(values, default=0) + 1)


def save_plan(state, project_id, plan):
    access.require_project(state, project_id)
    plan = _normalise(plan)
    _validate(plan)
    from app_modules import milestones
    for task in plan["tasks"]:
        milestone_id = milestones.sync_gantt_milestone(state, project_id, task)
        if milestone_id:
            task["project_milestone_id"] = milestone_id
    with database.connect() as db:
        db.execute("""INSERT INTO gantt_plans(project_id, plan_json, updated_at) VALUES (?, ?, ?)
                     ON CONFLICT(project_id) DO UPDATE SET plan_json=excluded.plan_json, updated_at=excluded.updated_at""", (project_id, json.dumps(plan, ensure_ascii=False), _now()))
    access.record_audit(state, "gantt_plan_saved", project_id=project_id,
                        details={"task_count": len(plan["tasks"])})
    milestones.remove_orphaned_gantt_milestones(state, project_id, plan["tasks"])
    return plan


def add_task(state, project_id, task, *, sync_kanban=True):
    plan = get_plan(state, project_id)
    item = dict(task)
    item["id"] = uuid.uuid4().hex
    plan["tasks"].append(item)
    plan = save_plan(state, project_id, plan)
    if sync_kanban and settings.is_enabled("feature_backlog_sync"):
        from app_modules import kanban
        for saved in plan["tasks"][-1:]:
            saved["kanban_card_id"] = kanban.sync_gantt_task(state, project_id, saved)
        save_plan(state, project_id, plan)
    return plan


def update_task(state, project_id, task_id, task, *, sync_kanban=True):
    plan = get_plan(state, project_id)
    for index, current in enumerate(plan["tasks"]):
        if current["id"] == task_id:
            item = dict(task)
            item["id"] = task_id
            plan["tasks"][index] = item
            plan = save_plan(state, project_id, plan)
            if sync_kanban and settings.is_enabled("feature_backlog_sync"):
                from app_modules import kanban
                item["kanban_card_id"] = kanban.sync_gantt_task(state, project_id, item)
                plan["tasks"][index] = item
                save_plan(state, project_id, plan)
            return plan
    raise ValueError("The schedule task could not be found.")


def delete_task(state, project_id, task_id, *, sync_kanban=True):
    plan = get_plan(state, project_id)
    target = next((task for task in plan["tasks"] if task["id"] == task_id), None)
    if not target:
        raise ValueError("The schedule task could not be found.")
    plan["tasks"] = [task for task in plan["tasks"] if task["id"] != task_id]
    for task in plan["tasks"]:
        task["predecessors"] = [value for value in task.get("predecessors", []) if value not in {task_id, target.get("code")}]
    save_plan(state, project_id, plan)
    access.record_audit(state, "gantt_task_deleted", project_id=project_id,
                        details={"task_id": task_id, "code": target.get("code", "")})
    if sync_kanban and settings.is_enabled("feature_backlog_sync"):
        from app_modules import kanban
        kanban.delete_linked_card(
            state,
            project_id,
            gantt_task_id=target.get("id"),
            gantt_code=target.get("code"),
            sync_gantt=False,
        )
    return plan


def import_workbook(state, project_id, content, *, replace=False):
    if not settings.is_enabled("feature_gantt_import"):
        raise PermissionError("Excel Gantt import is disabled by an Administrator.")
    access.require_project(state, project_id)
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
    except Exception as error:
        raise ValueError(f"The Excel schedule could not be read: {error}") from error
    if not rows:
        raise ValueError("The Excel template is empty.")
    headers = [str(value or "").strip() for value in rows[0]]
    if headers[:len(HEADERS)] != HEADERS:
        raise ValueError("Use the official Gantt template with the required columns in order.")
    existing = {} if replace else {task.get("code"): task for task in get_plan(state, project_id)["tasks"] if task.get("code")}
    imported = []
    for number, row in enumerate(rows[1:], start=2):
        if not any(value not in (None, "") for value in row):
            continue
        values = list(row) + [None] * (len(HEADERS) - len(row))
        code, name, kind, start, finish, progress, resource, predecessors, details = values[:9]
        code, name = str(code or "").strip(), str(name or "").strip()
        if not code or not name:
            raise ValueError(f"Row {number}: Code and Task / milestone name are required.")
        start_date, finish_date = _date(start), _date(finish) or _date(start)
        if not start_date or not finish_date:
            raise ValueError(f"Row {number}: valid start and finish dates are required.")
        try:
            progress_value = int(progress or 0)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Row {number}: Progress must be a whole number from 0 to 100.") from error
        if not 0 <= progress_value <= 100:
            raise ValueError(f"Row {number}: Progress must be between 0 and 100.")
        milestone = str(kind or "").strip().casefold() == "milestone"
        predecessor_values = [item.strip() for item in re.split(r"[,;]", str(predecessors or "")) if item.strip()]
        imported.append({"id": existing.get(code, {}).get("id") or uuid.uuid4().hex, "code": code, "name": name, "type": str(kind or ("Milestone" if milestone else "Task")), "start": start_date.isoformat(), "finish": (start_date if milestone else finish_date).isoformat(), "progress": progress_value, "resource": str(resource or ""), "predecessors": predecessor_values, "details": str(details or ""), "milestone": milestone, "summary": str(kind or "").casefold() == "summary"})
    plan = {"tasks": imported if replace else [*existing.values(), *[item for item in imported if item.get("code") not in existing]]}
    if not replace:
        by_code = {task.get("code"): task for task in plan["tasks"]}
        for item in imported:
            by_code[item["code"]] = item
        plan["tasks"] = list(by_code.values())
    plan = save_plan(state, project_id, plan)
    if settings.is_enabled("feature_backlog_sync"):
        from app_modules import kanban
        kanban.remove_orphaned_gantt_cards(state, project_id, plan["tasks"])
        for task in plan["tasks"]:
            task["kanban_card_id"] = kanban.sync_gantt_task(state, project_id, task)
        plan = save_plan(state, project_id, plan)
    return plan


def preview_workbook(content, limit=100):
    """Read the first rows for an administrator confirmation preview."""
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
    except Exception as error:
        raise ValueError(f"The Excel schedule could not be previewed: {error}") from error
    if not rows:
        raise ValueError("The Excel template is empty.")
    headers = [str(value or "").strip() for value in rows[0]]
    if headers[:len(HEADERS)] != HEADERS:
        raise ValueError("Use the official Gantt template with the required columns in order.")
    return [dict(zip(HEADERS, list(row)[:len(HEADERS)] + [None] * max(0, len(HEADERS) - len(row)))) for row in rows[1:limit + 1] if any(value not in (None, "") for value in row)]


def template_bytes():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Gantt import"
    sheet.append(HEADERS)
    sheet.append(["1", "Project milestone", "Milestone", "2026-10-01", "2026-10-01", 0, "", "", "Major delivery point"])
    sheet.append(["1.1", "Example task", "Task", "2026-10-02", "2026-10-15", 0, "Project team", "1", "Task linked to milestone 1"])
    for cell in sheet[1]:
        cell.font = openpyxl.styles.Font(bold=True, color="FFFFFF")
        cell.fill = openpyxl.styles.PatternFill("solid", fgColor="001B2F")
    sheet.freeze_panes = "A2"
    instructions = workbook.create_sheet("Instructions")
    instructions.append(["Gantt import instructions"])
    instructions.append(["Use codes such as 1 for milestones and 1.1, 1.2 for tasks."])
    instructions.append(["Dates use YYYY-MM-DD. Progress must be between 0 and 100."])
    instructions.append(["Separate multiple predecessor codes with commas."])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
