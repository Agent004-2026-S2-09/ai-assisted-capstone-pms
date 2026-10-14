import pytest

import app
from app_modules import auth
from app_modules import comments
from app_modules import access_control as access


PASSWORD = "a-long-test-password"
ADMIN_PASSWORD = "test-password-long"


def _sign_in(username, password=PASSWORD):
    assert auth.login(app.st.session_state, username, password)


def test_project_comments_are_persistent_and_threaded():
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
