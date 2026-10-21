## File: tests/test_query_planning.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing test query planning functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

from app_modules import query_planning


def test_query_plan_routes_exact_project_task_question_to_database():
    """
    Function: test_query_plan_routes_exact_project_task_question_to_database
    Purpose: Execute the test query plan routes exact project task question to database operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    plan = query_planning.build_plan(
        "Show every task that is in progress",
        project_id="alpha",
    )
    assert plan.entity == "task"
    assert plan.intent == "list"
    assert plan.required_sources == ["database"]
    assert plan.filters["status"] == "in progress"


def test_query_plan_handles_typo_and_implicit_latest_meeting_follow_up():
    """
    Function: test_query_plan_handles_typo_and_implicit_latest_meeting_follow_up
    Purpose: Execute the test query plan handles typo and implicit latest meeting follow up operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    plan = query_planning.build_plan(
        "What did we agree last time?",
        project_id="alpha",
        history=[{"role": "user", "content": "Tell me about the sprinnt meetings"}],
    )
    assert plan.entity == "meeting"
    assert plan.follow_up is True
    assert plan.filters["relative"] == "latest"
    assert "sprinnt" in plan.resolved_question
    assert plan.required_sources == ["database"]


def test_query_plan_decomposes_comparison_into_two_bounded_subqueries():
    """
    Function: test_query_plan_decomposes_comparison_into_two_bounded_subqueries
    Purpose: Execute the test query plan decomposes comparison into two bounded subqueries operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    plan = query_planning.build_plan(
        "Compare the current workspace and project documents",
        project_id="alpha",
    )
    assert plan.intent == "compare"
    assert plan.required_sources == ["database", "documents"]
    assert len(plan.subqueries) == 2


def test_question_normalisation_handles_mobile_and_document_punctuation():
    """
    Function: test_question_normalisation_handles_mobile_and_document_punctuation
    Purpose: Verify copied project identifiers remain routable across user devices.
    Inputs:
            None.
    Returns:
            None.
    Raises/side effects:
            None; this is a deterministic planner regression test.
    """
    question = "Give me details of Project ID:\u202f2026\u2011S2\u201121"
    assert query_planning.normalise_question(question) == "Give me details of Project ID: 2026-S2-21"


def test_general_query_variants_preserve_scope_and_expand_common_terms():
    """General rewrites remain bounded and add no external source terms."""
    variants = query_planning.general_query_variants(
        "What is the deadline for the deliverable from my supervisor?"
    )

    assert variants[0].startswith("What is the deadline")
    assert any("due date" in item.casefold() for item in variants)
    assert len(variants) <= 3

