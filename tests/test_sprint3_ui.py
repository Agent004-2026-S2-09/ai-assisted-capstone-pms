"""Exercise real Streamlit session state and forms without a live API call."""
import pytest
from streamlit.testing.v1 import AppTest

import app
import auth
import database


@pytest.mark.parametrize("role", database.ROLES)
def test_login_navigation_project_visibility_and_logout(role, monkeypatch):
    # AppTest runs main against the same isolated services and actual Streamlit state.
    database.write_projects([{"id": "alpha", "name": "Alpha"}, {"id": "beta", "name": "Beta"}])
    user_id = auth.create_user("UI User", "ui@example.org", "ui-test-password", role)
    with database.connect() as db:
        db.execute("INSERT INTO assignments VALUES (?, 'alpha')", (user_id,))
    monkeypatch.setattr(app, "ensure_index_is_current", lambda: [])
    at = AppTest.from_string("import app\napp.main()", default_timeout=15).run()
    assert not at.exception
    assert len(at.text_input) == 2
    assert not at.radio
    at.text_input[0].input("ui@example.org")
    at.text_input[1].input("invalid")
    at.button[0].click().run()
    assert at.error
    assert not at.radio
    at.text_input[0].input("ui@example.org")
    at.text_input[1].input("ui-test-password")
    at.button[0].click().run()
    assert not at.exception
    assert not any(widget.label == "Prototype role" for widget in at.selectbox)
    projects = next(widget for widget in at.selectbox if widget.label == "Current project")
    assert any("Alpha" in value for value in projects.options)
    assert any("Beta" in value for value in projects.options) == (role in ("Administrator", "Convenor"))
    assert projects.value == ("General Capstone" if role in ("Administrator", "Convenor") else "Alpha (alpha)")
    # Auto-selection happens at login only: General Capstone remains selectable.
    if role not in ("Administrator", "Convenor"):
        projects.select("General Capstone").run()
        projects = next(widget for widget in at.selectbox if widget.label == "Current project")
        assert projects.value == "General Capstone"
    navigation = next(widget for widget in at.radio if widget.label == "Go to")
    assert "🔐 Change password" not in navigation.options
    assert sum(widget.label == "Change password" for widget in at.button) == 1
    assert ("⚙️ Administration" in navigation.options) == (role == "Administrator")
    projects.select("Alpha (alpha)").run()
    navigation = next(widget for widget in at.radio if widget.label == "Go to")
    navigation.set_value("📁 Project Workspace").run()
    assert not at.exception
    save = next(widget for widget in at.button if widget.label == "Save Project")
    assert save.disabled == (role == "Student")
    if role == "Administrator":
        next(widget for widget in at.radio if widget.label == "Go to").set_value("⚙️ Administration").run()
        assert not at.exception
        assert any(widget.label == "Manage account" for widget in at.selectbox)
    next(widget for widget in at.button if widget.label == "Log out").click().run()
    assert not at.exception
    assert len(at.text_input) == 2
    assert not at.radio
    assert "auth_token" not in at.session_state
    assert "selected_project_id" not in at.session_state
