"""Administrator-managed feature flags and audit helpers."""

import json
from datetime import datetime, timezone

import access_control as access
import database


FEATURES = {
    "feature_gantt": "Gantt scheduling",
    "feature_kanban": "Tasks",
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
    access.require_admin(state)
    with database.connect() as db:
        rows = db.execute("SELECT key, value, updated_at FROM app_settings ORDER BY key").fetchall()
    return {row["key"]: dict(row) for row in rows if row["key"] in FEATURES}


def update_settings(state, values):
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
