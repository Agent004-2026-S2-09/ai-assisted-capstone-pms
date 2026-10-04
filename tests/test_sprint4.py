"""Sprint 4 monitoring, feedback, prompt and administrator-access tests."""

import pytest

import auth
import monitoring
import prompts
import access_control as access


PASSWORD = "a-long-test-password"


def test_admin_monitoring_feedback_and_evaluation_round_trip():
    state = {}
    auth.create_user("Sprint 4 Admin", "s4-admin", PASSWORD, "Administrator")
    assert auth.login(state, "s4-admin", PASSWORD)

    interaction_id = monitoring.log_interaction(
        user=state,
        project_id=None,
        assistant_mode="general",
        prompt_name="general",
        prompt_version=1,
        question="How do I plan a milestone?",
        response_text="Use the approved project guidance.",
        latency_ms=125,
        input_tokens=10,
        output_tokens=8,
        total_tokens=18,
    )
    monitoring.add_feedback(interaction_id, 1, "Clear answer", user=state)
    monitoring.add_evaluation(state, interaction_id, "Milestone answer", 5, 5, False, "Grounded", usability=4)

    metrics = monitoring.dashboard_metrics(state)
    assert metrics["requests"] == 1
    assert metrics["successful"] == 1
    assert metrics["helpful"] == 1
    assert metrics["evaluations"] == 1
    assert metrics["usability"] == 4
    assert monitoring.prompt_analytics(state)[0]["question_text"] == "How do I plan a milestone?"
    assert monitoring.recent_successful_interactions(state)[0]["response_text"] == "Use the approved project guidance."


def test_sprint4_reporting_and_prompt_writes_require_administrator():
    state = {}
    user_id = auth.create_user("Sprint 4 Student", "s4-student", PASSWORD, "Student")
    assert auth.login(state, "s4-student", PASSWORD)
    with pytest.raises(access.AccessDenied):
        monitoring.dashboard_metrics(state)
    with pytest.raises(access.AccessDenied):
        monitoring.prompt_analytics(state)
    with pytest.raises(access.AccessDenied):
        prompts.create_prompt_version("general", "Unsafe prompt change", state=state)

    admin_state = {}
    auth.create_user("Sprint 4 Administrator", "s4-admin-2", PASSWORD, "Administrator")
    assert auth.login(admin_state, "s4-admin-2", PASSWORD)
    version = prompts.create_prompt_version("general", "Administrator-managed prompt", state=admin_state)
    assert prompts.get_active_prompt("general")["version"] == version
    assert prompts.list_prompt_versions("general", state=admin_state)[0]["prompt_text"] == "Administrator-managed prompt"
    assert user_id


def test_existing_database_identity_counts_are_unchanged_after_sprint4_migration():
    import database

    with database.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 1
        assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
