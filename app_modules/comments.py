## File: app_modules/comments.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Persistent, project-scoped discussion threads.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Persistent, project-scoped discussion threads."""

from datetime import datetime, timezone

from app_modules import access_control as access
from app_modules import auth, database, notifications

MAX_COMMENT_LENGTH = 10000


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


def _clean_body(body):
    """
    Function: _clean_body
    Purpose: Execute the  clean body operation.
    Inputs:
            body (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    body = str(body or "").strip()
    if not body:
        raise ValueError("Write a comment before posting.")
    if len(body) > MAX_COMMENT_LENGTH:
        raise ValueError(f"Comments must be {MAX_COMMENT_LENGTH} characters or fewer.")
    return body


def list_comments(state, project_id):
    """Return active comments after verifying project access."""
    access.require_project_content(state, project_id)
    with database.connect() as db:
        rows = db.execute("""
            SELECT c.id, c.project_id, c.author_user_id, c.parent_comment_id,
                   c.body, c.created_at, c.updated_at,
                   u.name AS author_name, u.username AS author_username,
                   u.role AS author_role, u.permissions AS author_permissions
            FROM project_comments c
            JOIN users u ON u.id = c.author_user_id
            WHERE c.project_id = ? AND c.deleted_at IS NULL
            ORDER BY c.created_at, c.id
        """, (project_id,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["author_permissions"] = auth.permission_list({
            "role": item.get("author_role"),
            "permissions": item.get("author_permissions"),
        })
        result.append(item)
    return result


def _author_can_moderate(user):
    """
    Function: _author_can_moderate
    Purpose: Execute the  author can moderate operation.
    Inputs:
            user (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return auth.has_permission(user, "Administrator") or auth.has_permission(user, "Convenor")


def add_comment(state, project_id, body, *, parent_comment_id=None):
    """
    Function: add_comment
    Purpose: Execute the add comment operation.
    Inputs:
            state (value): Caller-provided input.
            project_id (value): Caller-provided input.
            body (value): Caller-provided input.
            parent_comment_id (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    user = access.require_project_content(state, project_id)
    body = _clean_body(body)
    now = _now()
    with database.connect() as db:
        if parent_comment_id is not None:
            parent = db.execute(
                "SELECT id FROM project_comments WHERE id = ? AND project_id = ? AND deleted_at IS NULL",
                (parent_comment_id, project_id),
            ).fetchone()
            if not parent:
                raise ValueError("The comment you are replying to no longer exists.")
        cursor = db.execute("""
            INSERT INTO project_comments(project_id, author_user_id, parent_comment_id,
                                         body, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project_id, user["id"], parent_comment_id, body, now, now))
        comment_id = cursor.lastrowid
        notifications.create_discussion_notifications(
            db,
            project_id=project_id,
            comment_id=comment_id,
            actor_user_id=user["id"],
            actor_name=user["name"],
            body=body,
        )
    access.record_audit(state, "project_comment_created", project_id=project_id,
                        object_type="project_comment", object_id=comment_id,
                        details={"parent_comment_id": parent_comment_id})
    return comment_id


def update_comment(state, comment_id, body):
    """
    Function: update_comment
    Purpose: Execute the update comment operation.
    Inputs:
            state (value): Caller-provided input.
            comment_id (value): Caller-provided input.
            body (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    user = access.require_user(state)
    body = _clean_body(body)
    now = _now()
    with database.connect() as db:
        row = db.execute("""
            SELECT id, project_id, author_user_id FROM project_comments
            WHERE id = ? AND deleted_at IS NULL
        """, (comment_id,)).fetchone()
        if not row:
            raise ValueError("The comment no longer exists.")
        if row["author_user_id"] != user["id"] and not _author_can_moderate(user):
            raise access.AccessDenied("You can only edit your own comments.")
        db.execute("UPDATE project_comments SET body = ?, updated_at = ? WHERE id = ?", (body, now, comment_id))
    access.record_audit(state, "project_comment_updated", project_id=row["project_id"],
                        object_type="project_comment", object_id=comment_id)


def delete_comment(state, comment_id):
    """
    Function: delete_comment
    Purpose: Execute the delete comment operation.
    Inputs:
            state (value): Caller-provided input.
            comment_id (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    user = access.require_user(state)
    now = _now()
    with database.connect() as db:
        row = db.execute("""
            SELECT id, project_id, author_user_id FROM project_comments
            WHERE id = ? AND deleted_at IS NULL
        """, (comment_id,)).fetchone()
        if not row:
            raise ValueError("The comment no longer exists.")
        if row["author_user_id"] != user["id"] and not _author_can_moderate(user):
            raise access.AccessDenied("You can only delete your own comments.")
        db.execute("UPDATE project_comments SET deleted_at = ?, updated_at = ? WHERE id = ?", (now, now, comment_id))
    access.record_audit(state, "project_comment_deleted", project_id=row["project_id"],
                        object_type="project_comment", object_id=comment_id)
