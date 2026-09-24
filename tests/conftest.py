import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


import pytest
import auth
import database


class TestSession(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


@pytest.fixture(autouse=True)
def authenticated_test_database(tmp_path, monkeypatch, request):
    """Regression tests run as an explicit test admin against a disposable DB.

    Security tests log out or replace this identity; production has no bypass.
    """
    import app
    monkeypatch.setenv("CAPSTONE_DB_PATH", str(tmp_path / "test.sqlite3"))
    database.initialize(legacy_file=tmp_path / "no-legacy.json")
    state = TestSession(messages=[], suggested_project_keys=[], api_usage=[])
    if request.path.name != "test_sprint3_ui.py":
        monkeypatch.setattr(app.st, "session_state", state)
    auth.create_user("Test Administrator", "admin@test.local", "test-password-long", "Administrator")
    auth.login(state, "admin@test.local", "test-password-long")
    state.update(messages=[], suggested_project_keys=[], api_usage=[])
    # Never touch repository project files during tests, including security tests.
    data = tmp_path / "project_data"
    knowledge = tmp_path / "project_knowledge"
    data.mkdir()
    knowledge.mkdir()
    monkeypatch.setattr(app, "PROJECT_DATA_DIR", data)
    monkeypatch.setattr(app, "PROJECT_KNOWLEDGE_DIR", knowledge)
    monkeypatch.setattr(app, "PROJECTS_FILE", data / "projects.json")
    return state
