## File: tests/test_query_reliability.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing test query reliability functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

from app_modules import query_reliability


def test_conflict_detection_ignores_multiple_values_inside_one_source():
    """
    Function: test_conflict_detection_ignores_multiple_values_inside_one_source
    Purpose: Execute the test conflict detection ignores multiple values inside one source operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    results = [{
        "source": "project-records",
        "text": "Meeting date: 2026-10-01\nMeeting date: 2026-10-08",
    }]
    assert query_reliability.detect_conflicts(results) == []


def test_conflict_detection_marks_disagreement_between_sources():
    """
    Function: test_conflict_detection_marks_disagreement_between_sources
    Purpose: Execute the test conflict detection marks disagreement between sources operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    results = [
        {"source": "project-records", "text": "Status: Completed"},
        {"source": "proposal.pdf", "text": "Status: Planned"},
    ]
    annotated, conflicts = query_reliability.annotate_results(results)
    assert conflicts[0]["field"] == "status"
    assert all(item["retrieval_conflict"] for item in annotated)

