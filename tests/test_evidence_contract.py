"""Regression tests for the canonical evidence boundary."""

from app_modules.evidence_contract import build_bundle


def _item(scope="general", project_id=None, record_type="document_chunk"):
    return {
        "scope": scope,
        "project_id": project_id,
        "record_type": record_type,
        "source": "approved.md",
        "text": "Approved evidence about the requested topic.",
        "score": 0.8,
    }


def test_general_bundle_rejects_project_evidence():
    bundle = build_bundle("question", [_item(scope="project", project_id="p1")])

    assert not bundle.items
    assert "wrong_scope" in bundle.failure_reasons
    assert "no_authorised_evidence" in bundle.failure_reasons


def test_project_bundle_rejects_foreign_and_general_evidence():
    bundle = build_bundle(
        "question",
        [
            _item(scope="project", project_id="p1"),
            _item(scope="project", project_id="p2"),
            _item(scope="general"),
        ],
        project_id="p1",
        query_plan={"scope": "project", "required_sources": ["documents"]},
    )

    assert len(bundle.items) == 1
    assert bundle.items[0]["project_id"] == "p1"
    assert "wrong_scope" in bundle.failure_reasons


def test_structured_project_evidence_is_prioritised():
    bundle = build_bundle(
        "question",
        [
            _item(scope="project", project_id="p1"),
            _item(scope="project", project_id="p1", record_type="structured_project_context"),
        ],
        project_id="p1",
        query_plan={"scope": "project", "required_sources": ["database"]},
    )

    assert bundle.items[0]["record_type"] == "structured_project_context"
    assert "database=1" in bundle.prompt_summary()


def test_evidence_bundle_exposes_internal_answer_status():
    """The answer layer receives one consistent supported/insufficient signal."""
    supported = build_bundle("question", [_item()])
    assert supported.answer_status == "supported"

    empty = build_bundle("question", [])
    assert empty.answer_status == "insufficient_evidence"


def test_general_authoritative_source_is_ranked_for_date_question():
    """A matching official schedule outranks an incidental lecture note."""
    schedule = _item()
    schedule["source"] = "UC Semester 2 Teaching Weeks.pdf"
    schedule["text"] = "Week 7 dates and teaching schedule."
    incidental = _item()
    incidental["source"] = "Tutorial slides.pdf"
    incidental["text"] = "The lecture discussed dates in general."

    bundle = build_bundle("What are the teaching week dates?", [incidental, schedule])

    assert bundle.items[0]["source"] == "UC Semester 2 Teaching Weeks.pdf"
