## File: app_modules/qa_benchmark.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Deterministic QA benchmark cases and scoring helpers.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Deterministic QA benchmark cases and scoring helpers.

The benchmark evaluates retrieval and routing, not a live LLM answer. That
keeps it repeatable, offline, and useful in CI: an answer cannot be grounded
if the right evidence was never retrieved.
"""

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable

from app_modules.query_planning import build_plan


@dataclass(frozen=True)
class BenchmarkCase:
    """
    Class: BenchmarkCase
    Purpose: Represent the BenchmarkCase abstraction.
    Responsibilities:
            Preserve the existing class interface and behaviour.
    """
    name: str
    category: str
    question: str
    expected_sources: tuple[str, ...] = ()
    expected_record_types: tuple[str, ...] = ()
    forbidden_record_types: tuple[str, ...] = ()
    expected_keywords: tuple[str, ...] = ()
    expected_predicate: Callable[[list[dict]], bool] | None = field(default=None, repr=False)


@dataclass(frozen=True)
class QueryPlanBenchmarkCase:
    """Offline regression case for routing and interpretation decisions."""

    name: str
    question: str
    intent: str
    entity: str
    sources: tuple[str, ...]
    required_filters: tuple[str, ...] = ()
    follow_up: bool = False
    subquery_count: int | None = None


QUERY_PLAN_BENCHMARK_CASES = (
    QueryPlanBenchmarkCase(
        "paraphrased-overdue-work", "Who owns the overdue work?", "lookup", "task",
        ("database",), ("status",),
    ),
    QueryPlanBenchmarkCase(
        "misspelled-latest-meeting", "What happened at the latest meting?", "summarise", "meeting",
        ("database",), ("relative",),
    ),
    QueryPlanBenchmarkCase(
        "implicit-follow-up", "What about the second one?", "lookup", "meeting",
        ("database",), ("ordinal",), True,
    ),
    QueryPlanBenchmarkCase(
        "multi-part-comparison", "Compare the current records and also the project documents.", "compare", "document",
        ("database", "documents"), (), False, 2,
    ),
    QueryPlanBenchmarkCase(
        "completed-before-break", "Show everything completed before the break.", "list", "general",
        ("documents",), ("status", "date_relation"),
    ),
)


def evaluate_query_plan_case(case: QueryPlanBenchmarkCase, *, history=None, project_id="project-1"):
    """
    Function: evaluate_query_plan_case
    Purpose: Execute the evaluate query plan case operation.
    Inputs:
            case (QueryPlanBenchmarkCase): Caller-provided input.
            history (value): Caller-provided input.
            project_id (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    if history is None and case.follow_up:
        history = [{"role": "user", "content": "What happened in the meetings?"}]
    plan = build_plan(case.question, project_id=project_id, history=history)
    checks = {
        "intent": plan.intent == case.intent,
        "entity": plan.entity == case.entity,
        "sources": tuple(plan.required_sources) == case.sources,
        "filters": all(filter_name in plan.filters for filter_name in case.required_filters),
        "follow_up": plan.follow_up == case.follow_up,
        "subquery_count": case.subquery_count is None or len(plan.subqueries) == case.subquery_count,
    }
    return {
        "name": case.name,
        "question": case.question,
        "passed": all(checks.values()),
        "checks": checks,
        "plan": plan.to_dict(),
    }


def _contains_text(fragment: str) -> Callable[[list[dict]], bool]:
    """
    Function: _contains_text
    Purpose: Execute the  contains text operation.
    Inputs:
            fragment (str): Caller-provided input.
    Returns:
            A value of type Callable[[list[dict]], bool].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    fragment = fragment.casefold()

    def predicate(results: list[dict]) -> bool:
        """
        Function: predicate
        Purpose: Execute the predicate operation.
        Inputs:
                results (list[dict]): Caller-provided input.
        Returns:
                A value of type bool.
        Raises/side effects:
                Existing validation, authorization, persistence, and error handling apply.
        """
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
        expected_sources=(
            "Weekly_Reflection_Journal_Part_2_Assessment_Requirements",
            "Reflection Rubric",
        ),
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
        expected_sources=("Assignments_S2_2026.pdf",),
        expected_record_types=("table_block", "document_chunk"),
        expected_keywords=("poster", "report", "presentation"),
        expected_predicate=lambda results: bool(
            results and (
                results[0].get("retrieval_complete")
                or "due date" in str(results[0].get("text", "")).casefold()
            )
        ),
    ),
    BenchmarkCase(
        "genai-acknowledgement", "document retrieval",
        "How do I reference AI in assessments?",
        expected_sources=("Student_Template_for_GenAI_Acknowledgement",),
        expected_keywords=("acknowledge", "assessment"),
    ),
    BenchmarkCase(
        "proposal-plan-report", "document retrieval",
        "What should be included in the Project Proposal and Plan Report?",
        expected_sources=("Project_Proposal_and_Plan_Group_Assessment_Requirements",),
        expected_keywords=("proposal", "requirements"),
    ),
    BenchmarkCase(
        "presentation-expectations", "document retrieval",
        "What are the main expectations for Capstone project presentations?",
        expected_sources=("Guest Presentation", "Tutorial Workshop 5", "Week 10 Tutorial"),
        expected_keywords=("presentation",),
    ),
)


def evaluate_case(case: BenchmarkCase, results: Iterable[dict]) -> dict:
    """
    Function: evaluate_case
    Purpose: Execute the evaluate case operation.
    Inputs:
            case (BenchmarkCase): Caller-provided input.
            results (Iterable[dict]): Caller-provided input.
    Returns:
            A value of type dict.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    """
    Function: summarise
    Purpose: Execute the summarise operation.
    Inputs:
            results (Iterable[dict]): Caller-provided input.
    Returns:
            A value of type dict.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    """
    Function: _average
    Purpose: Execute the  average operation.
    Inputs:
            values (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    values = list(values)
    return sum(values) / len(values) if values else 0.0
