"""Deterministic QA benchmark cases and scoring helpers.

The benchmark evaluates retrieval and routing, not a live LLM answer. That
keeps it repeatable, offline, and useful in CI: an answer cannot be grounded
if the right evidence was never retrieved.
"""

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    category: str
    question: str
    expected_sources: tuple[str, ...] = ()
    expected_record_types: tuple[str, ...] = ()
    forbidden_record_types: tuple[str, ...] = ()
    expected_keywords: tuple[str, ...] = ()
    expected_predicate: Callable[[list[dict]], bool] | None = field(default=None, repr=False)


def _contains_text(fragment: str) -> Callable[[list[dict]], bool]:
    fragment = fragment.casefold()

    def predicate(results: list[dict]) -> bool:
        return any(fragment in str(item.get("text", "")).casefold() for item in results)

    return predicate


BENCHMARK_CASES = (
    BenchmarkCase(
        "support-guidance", "general guidance",
        "What support is available for Capstone students?",
        expected_sources=("Technology Support Guideline", "Tips and Tricks"),
        expected_keywords=("support",),
        expected_predicate=_contains_text("support"),
    ),
    BenchmarkCase(
        "funding-guidance", "general guidance",
        "Are there funding or budget resources for Capstone projects?",
        expected_sources=("Technology Support Guideline",),
        expected_keywords=("fund", "budget"),
        expected_predicate=_contains_text("fund"),
    ),
    BenchmarkCase(
        "assessment-guidance", "general guidance",
        "What does the weekly reflection assessment rubric require?",
        expected_sources=("Reflection Rubric",),
        expected_keywords=("assessment", "rubric"),
        expected_predicate=_contains_text("assess"),
    ),
    BenchmarkCase(
        "project-catalogue", "catalogue", "List available Capstone projects",
        expected_record_types=("project",),
        forbidden_record_types=("document_chunk", "table_block"),
        expected_keywords=("project",),
    ),
    BenchmarkCase(
        "project-count", "catalogue", "How many projects are available?",
        expected_record_types=("project",),
        forbidden_record_types=("document_chunk", "table_block"),
        expected_keywords=("project",),
    ),
    BenchmarkCase(
        "broad-overview", "broad overview",
        "Tell me everything you know about UC Capstone projects",
        forbidden_record_types=("project",),
        expected_keywords=("capstone", "project"),
        expected_predicate=lambda results: len({item.get("source") for item in results}) >= 4,
    ),
    BenchmarkCase(
        "typo-tolerant-support", "robustness",
        "wh at sup p ort is ava ilable for capstone?",
        expected_sources=("Technology Support Guideline",),
        expected_keywords=("support",),
        expected_predicate=_contains_text("support"),
    ),
    BenchmarkCase(
        "unrelated-question-does-not-leak-catalogue", "contamination",
        "What resources and guidance are available to students?",
        forbidden_record_types=("project",),
        expected_keywords=("resource", "guidance"),
        expected_predicate=lambda results: bool(results),
    ),
    BenchmarkCase(
        "ethics-lecture", "document retrieval",
        "What was covered in the ethics lecture?",
        expected_sources=("Professionalism and Ethics",),
        expected_keywords=("ethics", "professional"),
    ),
    BenchmarkCase(
        "week-seven", "document retrieval",
        "What were the Week 7 lectures?",
        expected_sources=("UC_Semester_2_2026_Capstone_Teaching_Weeks",),
        expected_keywords=("week 7",),
    ),
    BenchmarkCase(
        "remaining-assessments", "structured data",
        "What are the assessments between now and the end of the semester?",
        expected_sources=("Assessments_S2_2026.csv",),
        expected_record_types=("table_block",),
        expected_keywords=("poster", "report", "presentation"),
        expected_predicate=lambda results: bool(results and results[0].get("retrieval_complete")),
    ),
    BenchmarkCase(
        "genai-acknowledgement", "document retrieval",
        "How do I reference AI in assessments?",
        expected_sources=("Student_Template_for_GenAI_Acknowledgement",),
        expected_keywords=("acknowledge", "assessment"),
    ),
)


def evaluate_case(case: BenchmarkCase, results: Iterable[dict]) -> dict:
    results = list(results)
    sources = {str(item.get("source", "")) for item in results}
    record_types = {str(item.get("record_type", "")) for item in results}
    expected_sources = {source.casefold() for source in case.expected_sources}
    checks = {
        "has_results": bool(results),
        "expected_sources": not expected_sources or any(
            expected in source.casefold()
            for expected in expected_sources
            for source in sources
        ),
        "expected_record_types": not case.expected_record_types
        or bool(record_types & set(case.expected_record_types)),
        "forbidden_record_types": not (record_types & set(case.forbidden_record_types)),
        "expected_predicate": case.expected_predicate(results) if case.expected_predicate else True,
    }
    keyword_ranks = []
    for keyword in case.expected_keywords:
        keyword_lower = keyword.casefold()
        rank = next(
            (rank for rank, item in enumerate(results, start=1)
             if keyword_lower in str(item.get("text", "")).casefold()),
            None,
        )
        keyword_ranks.append(rank)
    reciprocal_ranks = [1 / rank if rank else 0.0 for rank in keyword_ranks]
    relevances = [
        int(any(keyword.casefold() in str(item.get("text", "")).casefold() for keyword in case.expected_keywords))
        for item in results[:10]
    ]
    dcg = sum(value / math.log2(index + 2) for index, value in enumerate(relevances))
    ideal = sorted(relevances, reverse=True)
    idcg = sum(value / math.log2(index + 2) for index, value in enumerate(ideal))
    return {
        "name": case.name,
        "category": case.category,
        "question": case.question,
        "passed": all(checks.values()),
        "checks": checks,
        "result_count": len(results),
        "sources": sorted(source for source in sources if source),
        "record_types": sorted(record_type for record_type in record_types if record_type),
        "mrr": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4) if reciprocal_ranks else None,
        "ndcg": round(dcg / idcg, 4) if idcg else None,
        "keyword_coverage": round(sum(rank is not None for rank in keyword_ranks) / len(keyword_ranks), 4) if keyword_ranks else None,
    }


def summarise(results: Iterable[dict]) -> dict:
    results = list(results)
    passed = sum(1 for result in results if result["passed"])
    by_category = {}
    for result in results:
        bucket = by_category.setdefault(result["category"], {"passed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed"] += int(result["passed"])
    return {
        "passed": passed,
        "total": len(results),
        "accuracy": round(passed / len(results), 4) if results else 0.0,
        "by_category": by_category,
        "mrr": round(_average(result["mrr"] for result in results if result["mrr"] is not None), 4),
        "ndcg": round(_average(result["ndcg"] for result in results if result["ndcg"] is not None), 4),
        "keyword_coverage": round(_average(result["keyword_coverage"] for result in results if result["keyword_coverage"] is not None), 4),
    }


def _average(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0
