## File: app_modules/milestones.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Bidirectional project milestone records linked to explicit Gantt milestones.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Bidirectional project milestone records linked to explicit Gantt milestones."""

import json
import uuid
from datetime import date

from app_modules import access_control as access
from app_modules import database


def _duration(task):
    """Return a positive schedule weight for a task."""
    def parse(value):
        """
        Function: parse
        Purpose: Execute the parse operation.
        Inputs:
                value (value): Caller-provided input.
        Returns:
                The function result, or None where no value is returned.
        Raises/side effects:
                Existing validation, authorization, persistence, and error handling apply.
        """
        try:
            return date.fromisoformat(str(value or ""))
        except ValueError:
            return None
    start, finish = parse(task.get("start")), parse(task.get("finish"))
    if not start or not finish or finish < start:
        return 1
    return max(1, (finish - start).days + 1)


def recalculate_gantt_rollups(state, project_id, tasks):
    """Calculate milestone progress/status from explicitly linked child tasks.

    The Gantt rows remain authoritative. The project profile stores only a
    synchronized projection for the Milestones tab and AI context.
    """

    access.require_project_content(state, project_id)
    tasks = list(tasks or [])
    milestone_rows = {
        str(task.get("id")): task
        for task in tasks
        if str(task.get("type", "")).casefold() == "milestone"
    }
    code_to_id = {
        str(task.get("code")): str(task.get("id"))
        for task in milestone_rows.values()
        if task.get("code")
    }

    children = {key: [] for key in milestone_rows}
    for task in tasks:
        if str(task.get("type", "")).casefold() == "milestone":
            continue
        linked = str(task.get("milestone_id") or "").strip()
        if linked in code_to_id:
            linked = code_to_id[linked]
            task["milestone_id"] = linked
        if linked in children:
            children[linked].append(task)

    for milestone_id, milestone in milestone_rows.items():
        linked_tasks = children[milestone_id]
        total_weight = sum(_duration(task) for task in linked_tasks)
        completed_weight = sum(
            _duration(task) * max(0, min(100, int(task.get("progress", 0) or 0))) / 100
            for task in linked_tasks
        )
        progress = round((completed_weight / total_weight) * 100) if total_weight else 0
        if linked_tasks and all(int(task.get("progress", 0) or 0) >= 100 for task in linked_tasks):
            status = "Completed"
        elif any(str(task.get("status", "")).casefold() in {"blocked", "at risk"} for task in linked_tasks):
            status = "At Risk"
        elif progress > 0:
            status = "In Progress"
        else:
            status = "Planned"
        milestone["progress"] = progress
        milestone["status"] = status
        milestone["milestone"] = True
        milestone["type"] = "Milestone"
        milestone["linked_task_count"] = len(linked_tasks)
        milestone["completed_task_count"] = sum(
            int(int(task.get("progress", 0) or 0) >= 100) for task in linked_tasks
        )

    with database.connect() as db:
        row = db.execute("SELECT profile FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            raise ValueError("Project does not exist.")
        profile = json.loads(row["profile"])
        records = profile.get("milestones", [])
        by_gantt_id = {
            str(item.get("gantt_task_id")): item
            for item in records
            if isinstance(item, dict) and item.get("gantt_task_id")
        }
        changed = False
        for milestone_id, milestone in milestone_rows.items():
            record = by_gantt_id.get(milestone_id)
            if not record:
                continue
            updates = {
                "name": milestone.get("name", ""),
                "date": milestone.get("finish") or milestone.get("start", ""),
                "status": milestone.get("status", "Planned"),
                "progress": milestone.get("progress", 0),
                "linked_task_count": milestone.get("linked_task_count", 0),
                "completed_task_count": milestone.get("completed_task_count", 0),
            }
            if any(record.get(key) != value for key, value in updates.items()):
                record.update(updates)
                changed = True
        if changed:
            profile["revision"] = int(profile.get("revision", 0) or 0) + 1
            db.execute(
                "UPDATE projects SET profile = ? WHERE id = ?",
                (json.dumps(profile, ensure_ascii=False), project_id),
            )
    return tasks


def sync_gantt_milestone(state, project_id, task):
    """Create or refresh the milestone projection for one Gantt milestone."""
    access.require_project_content(state, project_id)
    if not isinstance(task, dict):
        return None
    if str(task.get("type", "")).strip().casefold() != "milestone":
        return None

    task_id = str(task.get("id") or "").strip()
    if not task_id:
        return None
    task_code = str(task.get("code") or "").strip()
    name = str(task.get("name") or "").strip()[:160]
    if not name:
        return None
    date = str(task.get("finish") or task.get("start") or "").strip()[:100]
    notes = str(task.get("details") or "").strip()[:10000]
    progress = max(0, min(100, int(task.get("progress", 0) or 0)))
    status = str(task.get("status") or "").strip()
    if status not in {"Planned", "In Progress", "Completed", "At Risk"}:
        status = "Completed" if progress >= 100 else "In Progress" if progress > 0 else "Planned"
    linked_id = str(task.get("project_milestone_id") or "").strip()
    changed = False
    created = False
    reopened = False

    with database.connect() as db:
        row = db.execute("SELECT profile FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            raise ValueError("Project does not exist.")
        profile = json.loads(row["profile"])
        milestones = profile.get("milestones", [])
        if not isinstance(milestones, list):
            milestones = []

        linked = next(
            (
                item for item in milestones
                if isinstance(item, dict)
                and (
                    (linked_id and item.get("id") == linked_id)
                    or item.get("gantt_task_id") == task_id
                )
            ),
            None,
        )

        if linked is None:
            linked = {
                "id": uuid.uuid4().hex,
                "name": name,
                "status": status,
                "date": date,
                "notes": notes,
                "source": "gantt",
                "gantt_task_id": task_id,
                "gantt_code": task_code,
            }
            milestones.append(linked)
            linked_id = linked["id"]
            changed = True
            created = True
        else:
            linked_id = str(linked.get("id") or linked_id or uuid.uuid4().hex)
            updates = {
                "id": linked_id,
                "name": name,
                "status": status,
                "date": date,
                "notes": notes,
                "source": "gantt",
                "gantt_task_id": task_id,
                "gantt_code": task_code,
            }
            reopened = status != "Completed" and linked.get("status") == "Completed"
            if any(linked.get(key) != value for key, value in updates.items()):
                linked.update(updates)
                changed = True

        if changed:
            profile["milestones"] = milestones
            try:
                profile["revision"] = int(profile.get("revision", 0)) + 1
            except (TypeError, ValueError):
                profile["revision"] = 1
            db.execute(
                "UPDATE projects SET name = ?, profile = ? WHERE id = ?",
                (profile.get("name", ""), json.dumps(profile, ensure_ascii=False), project_id),
            )

    if created:
        access.record_audit(
            state,
            "gantt_milestone_linked",
            project_id=project_id,
            details={"gantt_task_id": task_id, "gantt_code": task_code},
        )
    elif reopened:
        access.record_audit(
            state,
            "gantt_milestone_reopened",
            project_id=project_id,
            details={"gantt_task_id": task_id, "gantt_code": task_code},
        )
    return linked_id


def remove_orphaned_gantt_milestones(state, project_id, tasks):
    """Remove milestone projections whose explicit Gantt milestone was deleted or retyped."""
    valid_ids = {
        str(task.get("id")) for task in tasks
        if str(task.get("type", "")).strip().casefold() == "milestone"
    }
    changed = False
    with database.connect() as db:
        row = db.execute("SELECT profile FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return
        profile = json.loads(row["profile"])
        milestones = profile.get("milestones", [])
        kept = [
            item for item in milestones
            if item.get("source") != "gantt" or str(item.get("gantt_task_id")) in valid_ids
        ]
        if len(kept) != len(milestones):
            profile["milestones"] = kept
            profile["revision"] = int(profile.get("revision", 0) or 0) + 1
            db.execute("UPDATE projects SET profile = ? WHERE id = ?", (json.dumps(profile, ensure_ascii=False), project_id))
            changed = True
    if changed:
        access.record_audit(state, "gantt_milestone_unlinked", project_id=project_id)


def update_milestone(state, project_id, milestone_id, *, name, target_date, status, notes):
    """Update a milestone and propagate the change to its linked Gantt item."""
    access.require_project_content(state, project_id)
    name = str(name or "").strip()
    if not name:
        raise ValueError("Milestone name is required.")
    if status not in {"Planned", "In Progress", "Completed", "At Risk"}:
        raise ValueError("Choose a valid milestone status.")
    target_date = str(target_date or "").strip()
    if not target_date:
        raise ValueError("A target date is required.")
    notes = str(notes or "").strip()
    with database.connect() as db:
        row = db.execute("SELECT profile FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            raise ValueError("Project does not exist.")
        profile = json.loads(row["profile"])
    record = next((item for item in profile.get("milestones", []) if item.get("id") == milestone_id), None)
    if not record:
        raise ValueError("The milestone could not be found.")
    if record.get("source") != "gantt":
        record.update({"name": name[:160], "date": target_date, "status": status, "notes": notes[:10000]})
        profile["revision"] = int(profile.get("revision", 0) or 0) + 1
        database.write_projects([*filter(lambda item: item.get("id") != project_id, database.read_projects()), profile])
        return record
    from app_modules import gantt
    plan = gantt.get_plan(state, project_id)
    task = next((item for item in plan["tasks"] if item.get("id") == record.get("gantt_task_id")), None)
    if not task:
        raise ValueError("The linked Gantt milestone could not be found.")
    # Progress and status are calculated from linked child tasks. Editing a
    # milestone changes only its metadata and target date.
    task.update({"name": name[:160], "start": target_date, "finish": target_date, "details": notes[:3000], "milestone": True, "type": "Milestone"})
    gantt.update_task(state, project_id, task["id"], task)
    return task


def delete_milestone(state, project_id, milestone_id):
    """Delete a milestone and its linked Gantt/Kanban records as one operation."""
    access.require_project_content(state, project_id)
    with database.connect() as db:
        row = db.execute("SELECT profile FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            raise ValueError("Project does not exist.")
        profile = json.loads(row["profile"])
    record = next((item for item in profile.get("milestones", []) if item.get("id") == milestone_id), None)
    if not record:
        raise ValueError("The milestone could not be found.")
    if record.get("source") == "gantt" and record.get("gantt_task_id"):
        from app_modules import gantt
        return gantt.delete_task(state, project_id, record["gantt_task_id"])
    profile["milestones"] = [item for item in profile.get("milestones", []) if item.get("id") != milestone_id]
    profile["revision"] = int(profile.get("revision", 0) or 0) + 1
    database.write_projects([*filter(lambda item: item.get("id") != project_id, database.read_projects()), profile])
