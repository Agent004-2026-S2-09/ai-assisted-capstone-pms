## File: app_modules/settings.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Administrator-managed feature flags and audit helpers.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Administrator-managed feature flags and audit helpers."""

import json
from datetime import datetime, timezone

from app_modules import access_control as access
from app_modules import database


FEATURES = {
    "feature_gantt": "Gantt scheduling",
    "feature_kanban": "Tasks",
}

DEFAULT_SUPPORT_EMAIL = "ITS-Capstone@canberra.edu.au"
TEXT_SETTINGS = {
    "support_email": "Capstone support email",
}

# Account administration is an administrator responsibility, not a workspace
# tab. It is therefore always available to administrators and is not exposed
# as a user-facing feature toggle.
ALWAYS_ENABLED = {"feature_user_creation"}

# These are intentionally not administrator-facing settings. They are
# capabilities owned by their parent workspace tab, so disabling a tab also
# disables every operation contained within it.
TAB_CAPABILITIES = {
    "feature_kanban_ai": ("feature_kanban",),
    "feature_gantt_import": ("feature_gantt",),
    "feature_backlog_sync": ("feature_gantt", "feature_kanban"),
}


def is_enabled(key: str) -> bool:
    """
    Function: is_enabled
    Purpose: Execute the is enabled operation.
    Inputs:
            key (str): Caller-provided input.
    Returns:
            A value of type bool.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    if key in ALWAYS_ENABLED:
        return True
    if key not in FEATURES and key not in TAB_CAPABILITIES:
        raise ValueError("Unsupported feature flag.")
    if key in TAB_CAPABILITIES:
        return all(is_enabled(parent) for parent in TAB_CAPABILITIES[key])
    with database.connect() as db:
        row = db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return bool(row and str(row["value"]).strip().lower() in {"1", "true", "yes", "on"})


def all_settings(state):
    """
    Function: all_settings
    Purpose: Execute the all settings operation.
    Inputs:
            state (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    access.require_admin(state)
    with database.connect() as db:
        rows = db.execute("SELECT key, value, updated_at FROM app_settings ORDER BY key").fetchall()
    return {row["key"]: dict(row) for row in rows if row["key"] in FEATURES}


def update_settings(state, values):
    """
    Function: update_settings
    Purpose: Execute the update settings operation.
    Inputs:
            state (value): Caller-provided input.
            values (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    actor = access.require_admin(state)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for key, value in values.items():
            if key not in FEATURES:
                raise ValueError("Unsupported feature flag.")
            db.execute(
                "INSERT INTO app_settings(key, value, updated_at, updated_by) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
                (key, "1" if bool(value) else "0", now, actor["id"]),
            )
        db.execute(
            "INSERT INTO project_audit_log(created_at, user_id, action, details) VALUES (?, ?, ?, ?)",
            (now, actor["id"], "feature_settings_updated", json.dumps({key: bool(value) for key, value in values.items()})),
        )


def get_text_setting(key, default=""):
    """
    Function: get_text_setting
    Purpose: Execute the get text setting operation.
    Inputs:
            key (value): Caller-provided input.
            default (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    if key not in TEXT_SETTINGS:
        raise ValueError("Unsupported text setting.")
    with database.connect() as db:
        row = db.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"]).strip() if row and str(row["value"]).strip() else default


def update_text_setting(state, key, value):
    """
    Function: update_text_setting
    Purpose: Execute the update text setting operation.
    Inputs:
            state (value): Caller-provided input.
            key (value): Caller-provided input.
            value (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    actor = access.require_admin(state)
    if key not in TEXT_SETTINGS:
        raise ValueError("Unsupported text setting.")
    value = str(value or "").strip()
    if key == "support_email":
        if not value or "@" not in value or len(value) > 320:
            raise ValueError("Enter a valid support email address.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with database.connect() as db:
        db.execute(
            "INSERT INTO app_settings(key, value, updated_at, updated_by) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (key, value, now, actor["id"]),
        )
        db.execute(
            "INSERT INTO project_audit_log(created_at, user_id, action, details) VALUES (?, ?, ?, ?)",
            (now, actor["id"], "text_setting_updated", json.dumps({key: value})),
        )
