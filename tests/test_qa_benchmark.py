import app
from app_modules.qa_benchmark import BENCHMARK_CASES, evaluate_case, summarise


def _documents():
    return [
        {"text": "Technology support is available through the student help desk.", "source": "Technology Support Guideline.pdf", "location": "Page 1", "record_type": "document_chunk"},
        {"text": "The reflection rubric explains assessment criteria.", "source": "Reflection Rubric.pdf", "location": "Page 1", "record_type": "document_chunk"},
        {"text": "Tips include project funding and budget planning.", "source": "Tips and Tricks for Capstone Projects.pdf", "location": "Page 1", "record_type": "document_chunk"},
        {"text": "Project ID: 2026-S2-01\nProject title: Digital archive", "source": "List of project S2 2026 V.1.pdf", "location": "Page 1", "record_type": "project", "project_id": "2026-S2-01", "title": "Digital archive"},
    ]


def test_benchmark_defines_multiple_system_wide_question_classes():
    assert {case.category for case in BENCHMARK_CASES} >= {"general guidance", "catalogue", "broad overview", "robustness", "contamination"}


def test_benchmark_scoring_reports_failed_grounding_checks():
    case = BENCHMARK_CASES[0]
    result = evaluate_case(case, [{"text": "unrelated", "source": "other.pdf", "record_type": "project"}])
    assert not result["passed"]
    assert not result["checks"]["expected_sources"]


def test_benchmark_runs_against_a_small_representative_collection():
    results = []
    documents = _documents()
    for case in BENCHMARK_CASES:
        retrieved = (
            app.retrieve_broad_overview(case.question, documents)
            if app.is_broad_overview_question(case.question)
            else app.retrieve_information(case.question, documents, top_k=10)
        )
        results.append(evaluate_case(case, retrieved))
    summary = summarise(results)
    assert summary["total"] == len(BENCHMARK_CASES)
    # This compact fixture intentionally does not contain every source and
    # catalogue row needed by the full benchmark; the real-index runner is the
    # authoritative system-wide measurement.
    assert summary["accuracy"] >= 0.25
    assert summary["by_category"]["contamination"]["total"] == 1
