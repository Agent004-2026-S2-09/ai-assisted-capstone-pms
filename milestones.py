"""Project milestone records derived from completed Gantt milestones."""

import json
import uuid

import access_control as access
import database


def sync_gantt_milestone(state, project_id, task):
    """Create or refresh a project milestone for one scheduled Gantt milestone.

    Manual milestone records are never matched or changed. A linked Gantt
    milestone is created only after the schedule item reaches 100% and is
    marked In Progress again if the item is later reopened.
    """
    access.require_project_content(state, project_id)
    if not isinstance(task, dict):
        return None
    if not (task.get("milestone") or str(task.get("type", "")).casefold() == "milestone"):
        return task.get("project_milestone_id")

    task_id = str(task.get("id") or "").strip()
    if not task_id:
        return None
    task_code = str(task.get("code") or "").strip()
    name = str(task.get("name") or "").strip()[:160]
    if not name:
        return None
    date = str(task.get("finish") or task.get("start") or "").strip()[:100]
    notes = str(task.get("details") or "").strip()[:10000]
    completed = int(task.get("progress", 0) or 0) >= 100
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

        if not completed and linked is None:
            return None

        if linked is None:
            linked = {
                "id": uuid.uuid4().hex,
                "name": name,
                "status": "Completed",
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
            desired_status = "Completed" if completed else "In Progress"
            updates = {
                "id": linked_id,
                "name": name,
                "status": desired_status,
                "date": date,
                "notes": notes,
                "source": "gantt",
                "gantt_task_id": task_id,
                "gantt_code": task_code,
            }
            reopened = not completed and linked.get("status") == "Completed"
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
            "gantt_milestone_completed",
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
