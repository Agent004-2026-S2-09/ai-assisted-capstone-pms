## File: tests/test_multi_permissions.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing test multi permissions functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

import pytest

from app_modules import access_control as access
from app_modules import auth, database


def _setup_db(tmp_path, monkeypatch):
    """
    Function: _setup_db
    Purpose: Execute the  setup db operation.
    Inputs:
            tmp_path (value): Caller-provided input.
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    path = tmp_path / "permissions.sqlite3"
    monkeypatch.setenv("CAPSTONE_DB_PATH", str(path))
    database.initialize(path=path)
    return path


def test_non_student_can_have_multiple_permissions_and_use_admin_access(tmp_path, monkeypatch):
    """
    Function: test_non_student_can_have_multiple_permissions_and_use_admin_access
    Purpose: Execute the test non student can have multiple permissions and use admin access operation.
    Inputs:
            tmp_path (value): Caller-provided input.
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _setup_db(tmp_path, monkeypatch)
    password = "A-secure-password-123"
    user_id = auth.create_user(
        "Mentor Admin", "mentor-admin", password, "Mentor",
        permissions=("Mentor", "Administrator"),
    )
    user = auth.authenticate("mentor-admin", password)

    assert user["id"] == user_id
    assert user["role"] == "Mentor"  # legacy primary role remains stable
    assert user["permissions"] == ["Mentor", "Administrator"]
    assert auth.has_permission(user, "Mentor")
    assert auth.has_permission(user, "Administrator")
    state = {}
    assert auth.login(state, "mentor-admin", password)
    assert access.require_admin(state)["id"] == user_id


def test_student_permissions_are_server_side_exclusive(tmp_path, monkeypatch):
    """
    Function: test_student_permissions_are_server_side_exclusive
    Purpose: Execute the test student permissions are server side exclusive operation.
    Inputs:
            tmp_path (value): Caller-provided input.
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _setup_db(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Students can only have"):
        auth.create_user(
            "Student User", "student", "A-secure-password-123", "Student",
            permissions=("Student", "Administrator"),
        )


def test_legacy_single_role_defaults_to_one_permission(tmp_path, monkeypatch):
    """
    Function: test_legacy_single_role_defaults_to_one_permission
    Purpose: Execute the test legacy single role defaults to one permission operation.
    Inputs:
            tmp_path (value): Caller-provided input.
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _setup_db(tmp_path, monkeypatch)
    auth.create_user("Mentor User", "mentor", "A-secure-password-123", "Mentor")
    user = auth.authenticate("mentor", "A-secure-password-123")
    assert user["permissions"] == ["Mentor"]
