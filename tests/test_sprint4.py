"""Sprint 4 monitoring, feedback, prompt and administrator-access tests."""

import pytest

from app_modules import auth
from app_modules import monitoring
from app_modules import prompts
from app_modules import rag_quality
from app_modules import access_control as access


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


def test_rag_diagnostic_classifies_and_reports_retrieval_failures():
    state = {}
    auth.create_user("RAG Admin", "rag-admin", PASSWORD, "Administrator")
    assert auth.login(state, "rag-admin", PASSWORD)
    diagnostic = rag_quality.build_diagnostic("What is the milestone date?", [], answer="")
    assert diagnostic["failure_class"] == "retrieval_failure"

    interaction_id = monitoring.log_interaction(
        user=state,
        project_id=None,
        assistant_mode="general",
        prompt_name="general",
        prompt_version=1,
        question="What is the milestone date?",
        response_text="I could not find that in the approved information.",
    )
    monitoring.log_rag_diagnostic(interaction_id, diagnostic)
    metrics = monitoring.rag_quality_metrics(state)
    assert metrics["diagnostics"] == 1
    assert metrics["classes"][0]["failure_class"] == "retrieval_failure"
    assert monitoring.recent_rag_diagnostics(state)[0]["result_count"] == 0


def test_rag_diagnostic_does_not_classify_grounded_caveats_as_generation_failure():
    diagnostic = rag_quality.build_diagnostic(
        "What is the delivery risk?",
        [{
            "text": "The approved record specifies the delivery risk but not the "
                    "owner. Confirm the owner with the project team.",
            "source": "risk-register.txt",
            "score": 0.8,
        }],
        answer=(
            "The approved record identifies a delivery risk. The owner is not "
            "specified, so confirm that detail with the project team."
        ),
        validation_status="validated",
    )

    assert diagnostic["failure_class"] == "none"


def test_rag_diagnostic_reports_grounding_confidence_signals():
    diagnostic = rag_quality.build_diagnostic(
        "What is the delivery date and owner?",
        [{
            "text": "The delivery date is 2026-10-20. The owner is Alex.",
            "source": "schedule.txt",
            "score": 0.9,
        }],
        answer="The delivery date is 2026-10-20 and the owner is Alex.",
        validation_status="validated",
    )

    assert diagnostic["confidence_band"] == "high"
    assert diagnostic["question_term_coverage"] > 0
    assert diagnostic["answer_evidence_overlap"] >= 3


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
    from app_modules import database

    with database.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 1
        assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0


def test_prompt_topics_are_grouped_into_explainable_intents():
    rows = [
        {"question_text": "How do I update my Gantt schedule?"},
        {"question_text": "What is the deadline for the proposal?"},
        {"question_text": "How do I update my Gantt schedule?"},
        {"question_text": "Where can I upload a project document?"},
    ]
    topics = monitoring.summarise_prompt_topics(rows)
    assert topics[0]["Topic"] == "Project planning and scheduling"
    assert topics[0]["Questions"] == 3
    assert topics[0]["Share"] == "75.0%"
    assert topics[0]["Example question"]
