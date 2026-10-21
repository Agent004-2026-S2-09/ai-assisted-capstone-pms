## File: app_modules/mentor_feedback.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Project-scoped mentor guidance attached to workspace items.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Project-scoped mentor guidance attached to workspace items."""

from datetime import datetime, timezone

from app_modules import access_control as access, auth, database, notifications


MAX_FEEDBACK_LENGTH = 10000
ALLOWED_TARGET_TYPES = {"overview", "milestone"}


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


def _validate_target(target_type, target_id):
    """
    Function: _validate_target
    Purpose: Execute the  validate target operation.
    Inputs:
            target_type (value): Caller-provided input.
            target_id (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    target_type = str(target_type or "").strip().casefold()
    target_id = str(target_id or "").strip()
    if target_type not in ALLOWED_TARGET_TYPES or not target_id or len(target_id) > 300:
        raise ValueError("The mentor guidance location is invalid.")
    return target_type, target_id


def get_feedback(state, project_id, target_type, target_id):
    """
    Function: get_feedback
    Purpose: Execute the get feedback operation.
    Inputs:
            state (value): Caller-provided input.
            project_id (value): Caller-provided input.
            target_type (value): Caller-provided input.
            target_id (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    access.require_project_content(state, project_id)
    target_type, target_id = _validate_target(target_type, target_id)
    with database.connect() as db:
        row = db.execute("""
            SELECT f.id, f.project_id, f.target_type, f.target_id, f.body,
                   f.author_user_id, f.created_at, f.updated_at,
                   u.name AS author_name
            FROM mentor_feedback f
            JOIN users u ON u.id = f.author_user_id
            WHERE f.project_id = ? AND f.target_type = ? AND f.target_id = ?
              AND f.deleted_at IS NULL
        """, (project_id, target_type, target_id)).fetchone()
    return dict(row) if row else None


def list_feedback(state, project_id):
    """
    Function: list_feedback
    Purpose: Return all active mentor guidance records for an authorised project.
    Inputs:
            state: Current application/session state used for authorization.
            project_id: Project identifier whose guidance should be returned.
    Returns:
            List of guidance records ordered by location and update time.
    Raises/side effects:
            Requires project-content access; performs a read-only database query.
    """
    access.require_project_content(state, project_id)
    with database.connect() as db:
        rows = db.execute("""
            SELECT f.id, f.project_id, f.target_type, f.target_id, f.body,
                   f.author_user_id, f.created_at, f.updated_at,
                   u.name AS author_name
            FROM mentor_feedback f
            JOIN users u ON u.id = f.author_user_id
            WHERE f.project_id = ? AND f.deleted_at IS NULL
            ORDER BY f.target_type, f.target_id, f.updated_at, f.id
        """, (project_id,)).fetchall()
    return [dict(row) for row in rows]


def save_feedback(state, project_id, target_type, target_id, body, *, target_label=None):
    """
    Function: save_feedback
    Purpose: Execute the save feedback operation.
    Inputs:
            state (value): Caller-provided input.
            project_id (value): Caller-provided input.
            target_type (value): Caller-provided input.
            target_id (value): Caller-provided input.
            body (value): Caller-provided input.
            target_label (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    actor = access.require_project_content(state, project_id)
    if auth.has_permission(actor, "Student"):
        raise access.AccessDenied("Only Mentors, Convenors and Administrators can add mentor guidance.")
    target_type, target_id = _validate_target(target_type, target_id)
    body = str(body or "").strip()
    if len(body) > MAX_FEEDBACK_LENGTH:
        raise ValueError(f"Mentor guidance must be {MAX_FEEDBACK_LENGTH} characters or fewer.")
    now = _now()
    with database.connect() as db:
        existing = db.execute("""
            SELECT id, body FROM mentor_feedback
            WHERE project_id = ? AND target_type = ? AND target_id = ? AND deleted_at IS NULL
        """, (project_id, target_type, target_id)).fetchone()
        if not body:
            if existing:
                db.execute("UPDATE mentor_feedback SET deleted_at = ?, updated_at = ? WHERE id = ?", (now, now, existing["id"]))
            return None
        if existing:
            if existing["body"] == body:
                return get_feedback(state, project_id, target_type, target_id)
            db.execute("UPDATE mentor_feedback SET body = ?, author_user_id = ?, updated_at = ? WHERE id = ?", (body, actor["id"], now, existing["id"]))
            feedback_id = existing["id"]
            action = "updated"
        else:
            cursor = db.execute("""
                INSERT INTO mentor_feedback(project_id, target_type, target_id, body, author_user_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (project_id, target_type, target_id, body, actor["id"], now, now))
            feedback_id = cursor.lastrowid
            action = "added"
        notifications.broadcast_project_notification(
            db,
            project_id=project_id,
            actor_user_id=actor["id"],
            actor_name=actor["name"],
            message=f"{actor['name']} {action} mentor guidance for {target_label or ('the ' + target_type)}",
        )
    access.record_audit(state, "mentor_guidance_saved", project_id=project_id, object_type=target_type, object_id=target_id)
    return get_feedback(state, project_id, target_type, target_id)
