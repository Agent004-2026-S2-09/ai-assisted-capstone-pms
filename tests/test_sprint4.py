## File: tests/test_sprint4.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Sprint 4 monitoring, feedback, prompt and administrator-access tests.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Sprint 4 monitoring, feedback, prompt and administrator-access tests."""

import pytest

from app_modules import auth
from app_modules import monitoring
from app_modules import prompts
from app_modules import rag_quality
from app_modules import access_control as access


PASSWORD = "a-long-test-password"


def test_admin_monitoring_feedback_and_evaluation_round_trip():
    """
    Function: test_admin_monitoring_feedback_and_evaluation_round_trip
    Purpose: Execute the test admin monitoring feedback and evaluation round trip operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    """
    Function: test_rag_diagnostic_classifies_and_reports_retrieval_failures
    Purpose: Execute the test rag diagnostic classifies and reports retrieval failures operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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


def test_admin_query_trace_round_trip_is_structured_and_access_controlled():
    """
    Function: test_admin_query_trace_round_trip_is_structured_and_access_controlled
    Purpose: Verify query traces persist plan, evidence, route and timeline
             metadata and remain administrator-only.
    Inputs:
            None.
    Returns:
            None; pytest raises an assertion on failure.
    Raises/side effects:
            Creates one isolated interaction and query trace in the test DB.
    """
    admin_state = {}
    auth.create_user("Trace Admin", "trace-admin", PASSWORD, "Administrator")
    assert auth.login(admin_state, "trace-admin", PASSWORD)
    interaction_id = monitoring.log_interaction(
        user=admin_state,
        project_id=None,
        assistant_mode="general",
        prompt_name="general",
        prompt_version=1,
        question="What is the assessment deadline?",
        response_text="The approved schedule records the deadline.",
    )
    monitoring.log_query_trace(interaction_id, {
        "route": {"source": "general_documents", "filter": "query_plan_retrieval", "response_mode": "ai"},
        "final_status": "success",
        "query_plan": {"intent": "lookup", "entity": "assessment"},
        "evidence": {"item_count": 2, "complete": True},
        "retrieval": {"result_count": 2, "top_score": 0.91},
        "timeline": [{"stage": "query_plan", "elapsed_ms": 4.2}],
        "security": {"scope": "general", "access_boundary_checked": True},
    })
    traces = monitoring.recent_query_traces(admin_state)
    assert traces[0]["interaction_id"] == interaction_id
    assert traces[0]["route_source"] == "general_documents"
    assert '"assessment"' in traces[0]["query_plan_json"]
    assert '"query_plan"' in traces[0]["timeline_json"]

    student_state = {}
    auth.create_user("Trace Student", "trace-student", PASSWORD, "Student")
    assert auth.login(student_state, "trace-student", PASSWORD)
    with pytest.raises(access.AccessDenied):
        monitoring.recent_query_traces(student_state)


def test_rag_diagnostic_does_not_classify_grounded_caveats_as_generation_failure():
    """
    Function: test_rag_diagnostic_does_not_classify_grounded_caveats_as_generation_failure
    Purpose: Execute the test rag diagnostic does not classify grounded caveats as generation failure operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    """
    Function: test_rag_diagnostic_reports_grounding_confidence_signals
    Purpose: Execute the test rag diagnostic reports grounding confidence signals operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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


def test_rag_diagnostic_records_route_and_filter():
    """Monitoring must show which deterministic source/filter was used."""
    diagnostic = rag_quality.build_diagnostic(
        "List all Backlog tasks",
        [{"record_type": "structured_project_context", "text": "Backlog task"}],
        answer="There is one Backlog task.",
        route={
            "source": "kanban",
            "filter": "kanban_column=backlog",
            "response_mode": "ai",
        },
    )

    assert diagnostic["route_source"] == "kanban"
    assert diagnostic["route_filter"] == "kanban_column=backlog"
    assert "Route: kanban" in diagnostic["notes"]


def test_sprint4_reporting_and_prompt_writes_require_administrator():
    """
    Function: test_sprint4_reporting_and_prompt_writes_require_administrator
    Purpose: Execute the test sprint4 reporting and prompt writes require administrator operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    """
    Function: test_existing_database_identity_counts_are_unchanged_after_sprint4_migration
    Purpose: Execute the test existing database identity counts are unchanged after sprint4 migration operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    from app_modules import database

    with database.connect() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] >= 1
        assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0


def test_prompt_topics_are_grouped_into_explainable_intents():
    """
    Function: test_prompt_topics_are_grouped_into_explainable_intents
    Purpose: Execute the test prompt topics are grouped into explainable intents operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
