## File: app_modules/notifications.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Persistent notifications for authorised project activity.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Persistent notifications for authorised project activity."""

from datetime import datetime, timezone

from app_modules import auth, database


MAX_NOTIFICATION_TEXT = 240


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


def _project_recipient_ids(db, project_id):
    """
    Function: _project_recipient_ids
    Purpose: Execute the  project recipient ids operation.
    Inputs:
            db (value): Caller-provided input.
            project_id (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    rows = db.execute("""
        SELECT DISTINCT u.id
        FROM users u
        LEFT JOIN assignments a ON a.user_id = u.id AND a.project_id = ?
        WHERE u.active = 1 AND (
            a.user_id IS NOT NULL OR instr(u.permissions, 'Administrator') > 0
            OR instr(u.permissions, 'Convenor') > 0
        )
        ORDER BY u.id
    """, (project_id,)).fetchall()
    return [row["id"] for row in rows]


def broadcast_project_notification(db, *, project_id, actor_user_id, actor_name, message, kind="discussion", comment_id=None):
    """Create one notification for every authorised member of a project."""
    recipients = _project_recipient_ids(db, project_id)
    if not recipients:
        return 0
    project = db.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    project_name = project["name"] if project else project_id
    message = f"{message} ({project_name})"[:MAX_NOTIFICATION_TEXT]
    now = _now()
    for recipient_id in recipients:
        db.execute("""
            INSERT INTO notifications(
                recipient_user_id, actor_user_id, project_id, comment_id,
                kind, message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (recipient_id, actor_user_id, project_id, comment_id, kind, message, now))
    return len(recipients)


def create_discussion_notifications(db, *, project_id, comment_id, actor_user_id, actor_name, body):
    """Create one broadcast notification per authorised project member."""
    recipients = _project_recipient_ids(db, project_id)
    if not recipients:
        return 0
    project = db.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    project_name = project["name"] if project else project_id
    preview = " ".join(str(body).split())[:MAX_NOTIFICATION_TEXT]
    now = _now()
    for recipient_id in recipients:
        message = f"{actor_name} posted in Team Discussion for {project_name}: {preview}"
        db.execute("""
            INSERT INTO notifications(
                recipient_user_id, actor_user_id, project_id, comment_id,
                kind, message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (recipient_id, actor_user_id, project_id, comment_id, "discussion", message, now))
    return len(recipients)


def list_notifications(state, *, unread_only=False, limit=50):
    """
    Function: list_notifications
    Purpose: Execute the list notifications operation.
    Inputs:
            state (value): Caller-provided input.
            unread_only (value): Caller-provided input.
            limit (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    user = auth.current_user(state)
    if not user:
        return []
    limit = max(1, min(int(limit), 200))
    where = "AND n.read_at IS NULL" if unread_only else ""
    with database.connect() as db:
        rows = db.execute(f"""
            SELECT n.id, n.project_id, n.comment_id, n.kind, n.message,
                   n.created_at, n.read_at, p.name AS project_name
            FROM notifications n
            LEFT JOIN projects p ON p.id = n.project_id
            WHERE n.recipient_user_id = ? {where}
            ORDER BY n.created_at DESC, n.id DESC
            LIMIT ?
        """, (user["id"], limit)).fetchall()
    return [dict(row) for row in rows]


def mark_read(state, notification_ids=None):
    """
    Function: mark_read
    Purpose: Execute the mark read operation.
    Inputs:
            state (value): Caller-provided input.
            notification_ids (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    user = auth.current_user(state)
    if not user:
        return
    with database.connect() as db:
        if notification_ids is None:
            db.execute("UPDATE notifications SET read_at = ? WHERE recipient_user_id = ? AND read_at IS NULL", (_now(), user["id"]))
            return
        ids = [int(item) for item in notification_ids]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            db.execute(
                f"UPDATE notifications SET read_at = ? WHERE recipient_user_id = ? AND id IN ({placeholders})",
                (_now(), user["id"], *ids),
            )
