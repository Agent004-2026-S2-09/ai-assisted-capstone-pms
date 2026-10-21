## File: tests/test_project_comments.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing test project comments functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

import pytest

import app
from app_modules import auth
from app_modules import comments
from app_modules import access_control as access
from app_modules import notifications


PASSWORD = "a-long-test-password"
ADMIN_PASSWORD = "test-password-long"


def _sign_in(username, password=PASSWORD):
    """
    Function: _sign_in
    Purpose: Execute the  sign in operation.
    Inputs:
            username (value): Caller-provided input.
            password (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    assert auth.login(app.st.session_state, username, password)


def test_project_comments_are_persistent_and_threaded():
    """
    Function: test_project_comments_are_persistent_and_threaded
    Purpose: Execute the test project comments are persistent and threaded operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    project = app.create_project("Discussion project")
    admin_id = auth.current_user(app.st.session_state)["id"]
    mentor_id = auth.create_user(
        "Project Mentor", "mentor-comments@test.local", PASSWORD, "Mentor",
    )
    access.assign_project(app.st.session_state, mentor_id, project.id)

    first_id = comments.add_comment(app.st.session_state, project.id, "Please review the project scope.")
    reply_id = comments.add_comment(
        app.st.session_state, project.id, "I have reviewed it and added feedback.", parent_comment_id=first_id
    )
    assert [item["id"] for item in comments.list_comments(app.st.session_state, project.id)] == [first_id, reply_id]

    _sign_in("mentor-comments@test.local")
    discussion = comments.list_comments(app.st.session_state, project.id)
    assert discussion[0]["author_user_id"] == admin_id
    assert discussion[1]["parent_comment_id"] == first_id


def test_comment_edit_and_delete_are_limited_to_owner_or_moderator():
    """
    Function: test_comment_edit_and_delete_are_limited_to_owner_or_moderator
    Purpose: Execute the test comment edit and delete are limited to owner or moderator operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    project = app.create_project("Comment permissions")
    owner_id = auth.create_user("Comment Owner", "comment-owner@test.local", PASSWORD, "Mentor")
    access.assign_project(app.st.session_state, owner_id, project.id)
    _sign_in("comment-owner@test.local")
    comment_id = comments.add_comment(app.st.session_state, project.id, "Original message")

    comments.update_comment(app.st.session_state, comment_id, "Edited message")
    assert comments.list_comments(app.st.session_state, project.id)[0]["body"] == "Edited message"

    _sign_in("admin@test.local", ADMIN_PASSWORD)
    other_id = auth.create_user("Other Mentor", "other-mentor@test.local", PASSWORD, "Mentor")
    access.assign_project(app.st.session_state, other_id, project.id)
    _sign_in("other-mentor@test.local")
    with pytest.raises(access.AccessDenied):
        comments.update_comment(app.st.session_state, comment_id, "Not allowed")

    _sign_in("admin@test.local", ADMIN_PASSWORD)
    comments.delete_comment(app.st.session_state, comment_id)
    assert comments.list_comments(app.st.session_state, project.id) == []


def test_discussion_posts_broadcast_to_every_authorised_project_member():
    """
    Function: test_discussion_posts_broadcast_to_every_authorised_project_member
    Purpose: Execute the test discussion posts broadcast to every authorised project member operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    project = app.create_project("Notification project")
    mentor_id = auth.create_user("Mentioned Mentor", "mentioned-mentor@test.local", PASSWORD, "Mentor")
    other_id = auth.create_user("Other Mentor", "other-notified@test.local", PASSWORD, "Mentor")
    access.assign_project(app.st.session_state, mentor_id, project.id)
    access.assign_project(app.st.session_state, other_id, project.id)

    comment_id = comments.add_comment(
        app.st.session_state,
        project.id,
        "Please review this with the team.",
    )

    _sign_in("mentioned-mentor@test.local")
    mentor_notifications = notifications.list_notifications(app.st.session_state, unread_only=True)
    assert mentor_notifications[0]["comment_id"] == comment_id
    assert mentor_notifications[0]["kind"] == "discussion"
    assert "Team Discussion" in mentor_notifications[0]["message"]

    _sign_in("other-notified@test.local")
    other_notifications = notifications.list_notifications(app.st.session_state, unread_only=True)
    assert other_notifications[0]["comment_id"] == comment_id
    assert other_notifications[0]["kind"] == "discussion"

    notifications.mark_read(app.st.session_state, [other_notifications[0]["id"]])
    assert notifications.list_notifications(app.st.session_state, unread_only=True) == []
