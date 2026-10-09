"""Bidirectional project milestone records linked to explicit Gantt milestones."""

import json
import uuid

from app_modules import access_control as access
from app_modules import database


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
    progress = {"Planned": 0, "In Progress": 50, "Completed": 100}.get(status, task.get("progress", 0))
    task.update({"name": name[:160], "start": target_date, "finish": target_date, "details": notes[:3000], "status": status, "progress": progress, "milestone": True, "type": "Milestone"})
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
