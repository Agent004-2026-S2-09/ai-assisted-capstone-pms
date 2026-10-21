## File: tests/test_project_directory.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing test project directory functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

import pytest
from plotly.io import to_json

import app
from app_modules import auth


PASSWORD = "directory-test-password"


def test_project_directory_filters_roles_and_limits_students():
    """
    Function: test_project_directory_filters_roles_and_limits_students
    Purpose: Execute the test project directory filters roles and limits students operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    student_ids = [
        auth.create_user(f"Student {index}", f"student-{index}", PASSWORD, "Student")
        for index in range(1, 6)
    ]
    mentor_id = auth.create_user("Mentor One", "mentor-one", PASSWORD, "Mentor")
    convenor_id = auth.create_user("Convenor One", "convenor-one", PASSWORD, "Convenor")

    assert {user["id"] for user in app._directory_users("Student")} == set(student_ids)
    assert {user["id"] for user in app._directory_users("Mentor")} == {mentor_id}
    assert convenor_id not in {user["id"] for user in app._directory_users("Mentor")}

    project = app.create_project("Directory Project", mentor_user_id=str(mentor_id))
    project.team = [
        {"id": str(student_id), "user_id": str(student_id), "name": "", "role": "Developer"}
        for student_id in student_ids[:4]
    ]
    app.update_project(project, allow_student_content=True)
    assert len(app.get_project(project.id).team) == 4

    project.team.append({"id": str(student_ids[4]), "user_id": str(student_ids[4]), "name": "", "role": "Developer"})
    with pytest.raises(ValueError, match="maximum of 4"):
        app.update_project(project, allow_student_content=True)

    project.team = [{"id": str(mentor_id), "user_id": str(mentor_id), "name": "", "role": "Mentor"}]
    with pytest.raises(ValueError, match="existing student"):
        app.update_project(project, allow_student_content=True)


def test_gantt_resources_are_searchable_existing_project_members_only():
    """
    Function: test_gantt_resources_are_searchable_existing_project_members_only
    Purpose: Execute the test gantt resources are searchable existing project members only operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    student_id = auth.create_user("Resource Student", "resource-student", PASSWORD, "Student")
    inactive_id = auth.create_user("Inactive Student", "inactive-student", PASSWORD, "Student", active=False)
    mentor_id = auth.create_user("Resource Mentor", "resource-mentor", PASSWORD, "Mentor")
    project = app.create_project("Resource Project", mentor_user_id=str(mentor_id))
    project.team = [
        {"id": str(student_id), "user_id": str(student_id), "name": "", "role": "Developer"},
    ]
    app.update_project(project, allow_student_content=True)
    project = app.get_project(project.id)
    project.team.append(
        {"id": str(inactive_id), "user_id": str(inactive_id), "name": "", "role": "Developer"}
    )

    entries = app._project_resource_entries(project)
    names = {entry["name"] for entry in entries}
    assert names == {"Resource Student"}
    assert {entry["label"] for entry in entries} == {
        "Resource Student · resource-student",
    }

    entries, options, defaults, by_id = app._resource_selection(project, "Resource Student")
    assert defaults == [next(entry["id"] for entry in entries if entry["name"] == "Resource Student")]
    assert app._resource_value(defaults, by_id) == "Resource Student"


def test_gantt_chart_uses_plotly_serializable_date_values(monkeypatch):
    """
    Function: test_gantt_chart_uses_plotly_serializable_date_values
    Purpose: Execute the test gantt chart uses plotly serializable date values operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    rendered = []
    monkeypatch.setattr(app.st, "plotly_chart", lambda figure, **kwargs: rendered.append(to_json(figure)))
    app._render_gantt_chart([
        {
            "id": "task-1",
            "code": "1.1",
            "name": "Implementation",
            "start": "2026-10-02",
            "finish": "2026-10-15",
            "progress": 25,
            "resource": "Student One",
            "predecessors": [],
            "milestone": False,
        }
    ])
    assert rendered
