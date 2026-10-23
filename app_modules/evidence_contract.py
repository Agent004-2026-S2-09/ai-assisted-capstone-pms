"""Canonical evidence contract for grounded assistant responses.

This module does not retrieve or generate content.  It is the boundary between
the existing retrieval/structured-record paths and Agentaus.  Its purpose is
to make scope, authority, conflicts and completeness explicit and consistent
for both the General Capstone and selected-project experiences.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from app_modules import query_reliability


@dataclass(frozen=True)
class EvidenceBundle:
    """Verified, ordered evidence presented to the answer-generation layer."""

    question: str
    scope: str
    project_id: str | None
    items: tuple[dict, ...] = field(default_factory=tuple)
    conflicts: tuple[dict, ...] = field(default_factory=tuple)
    failure_reasons: tuple[str, ...] = field(default_factory=tuple)
    source_counts: dict = field(default_factory=dict)
    complete: bool = False

    @property
    def has_evidence(self) -> bool:
        return bool(self.items)

    @property
    def answer_status(self) -> str:
        """Return the internal evidence status used by answer generation.

        The value is intentionally not shown to students. It gives the
        generation and monitoring layers one consistent signal for deciding
        whether an answer is supported, incomplete, or unavailable.
        """
        if not self.items:
            return "insufficient_evidence"
        if self.conflicts:
            return "conflict_requires_review"
        if not self.complete:
            return "insufficient_evidence"
        return "supported"

    def prompt_summary(self) -> str:
        """Return a compact, non-sensitive control summary for the model."""
        source_summary = ", ".join(
            f"{name}={count}" for name, count in sorted(self.source_counts.items())
        ) or "none"
        conflict_summary = (
            "; ".join(str(item.get("field", "unknown")) for item in self.conflicts)
            or "none"
        )
        failures = ", ".join(self.failure_reasons) or "none"
        return (
            "EVIDENCE CONTRACT\n"
            f"Authorised scope: {self.scope}"
            + (f" ({self.project_id})" if self.project_id else "")
            + "\n"
            f"Evidence items: {len(self.items)}\n"
            f"Evidence by source type: {source_summary}\n"
            f"Conflicts detected: {conflict_summary}\n"
            f"Evidence complete for the selected retrieval operation: {'yes' if self.complete else 'no'}\n"
            f"Answer evidence status: {self.answer_status}\n"
            f"Reliability flags: {failures}\n"
            "Use this contract as an execution boundary. Do not widen the "
            "scope or claim completeness when it is marked incomplete."
        )


def _scope_for(project_id, query_plan):
    plan = query_plan or {}
    if project_id:
        return "selected_project"
    return "general" if plan.get("scope", "general") != "project" else "project"


def _authority_rank(item, question=""):
    record_type = str(item.get("record_type", "document_chunk"))
    if record_type == "structured_project_context":
        return 50
    if record_type in {"table_block", "project"}:
        return 40
    rank = 35 if item.get("retrieval_complete") else 10
    source = " ".join(
        str(item.get(key) or "")
        for key in ("source", "title", "location")
    ).casefold().replace("_", " ")
    lowered_question = str(question or "").casefold()

    # General evidence often contains overlapping lecture notes, guides and
    # schedules. Prefer an official source family only when it matches the
    # requested topic; this is additive ranking and does not remove evidence.
    authority_families = (
        (r"\b(?:due|deadline|assessment|assignment|submission|deliverable)s?\b",
         ("assessment", "assignment", "unit outline", "syllabus"), 16),
        (r"\b(?:week|teaching|semester|calendar|date)s?\b",
         ("teaching week", "teaching weeks", "unit outline", "syllabus"), 16),
        (r"\b(?:requirement|eligible|eligibility|policy|rule|mark|grade)s?\b",
         ("unit outline", "syllabus", "assessment", "rubric", "policy"), 14),
        (r"\b(?:reference|referencing|acknowledge|citation)s?\b",
         ("acknowledgement", "referencing", "assessment", "template"), 12),
    )
    for query_pattern, source_terms, bonus in authority_families:
        if re.search(query_pattern, lowered_question) and any(term in source for term in source_terms):
            rank += bonus
            break
    return rank


def _is_calendar_question(question):
    return bool(re.search(
        r"\b(?:today|current date|what date|date is it|teaching week|academic week|"
        r"which week|what week|week are we|semester week)\b",
        str(question or ""),
        re.IGNORECASE,
    ))


def _is_calendar_document(item):
    source = re.sub(r"[^a-z0-9]+", " ", str(item.get("source") or "").casefold()).strip()
    return bool(re.search(r"teaching\s+weeks?|semester\s+calendar|academic\s+calendar", source))


def build_bundle(question, results, *, query_plan=None, project_id=None):
    """Validate and order evidence without changing the existing retrievers.

    Scope failures are removed before prompt construction.  A caller that
    supplied evidence from another project therefore cannot accidentally pass
    it to the model while still receiving an explicit diagnostic flag.
    """
    expected_scope = _scope_for(project_id, query_plan)
    valid = []
    failures = set()

    for item in results or []:
        if not isinstance(item, dict) or not item.get("text"):
            continue
        item_scope = str(item.get("scope", "general"))
        item_project = item.get("project_id")
        if project_id:
            is_authorised_calendar = _is_calendar_question(question) and _is_calendar_document(item)
            if (
                (item_scope != "project" or str(item_project) != str(project_id))
                and not is_authorised_calendar
            ):
                failures.add("wrong_scope")
                continue
        elif item_scope == "project":
            failures.add("wrong_scope")
            continue
        valid.append(dict(item))

    annotated, conflicts = query_reliability.annotate_results(valid)
    annotated.sort(
        key=lambda item: (
            _authority_rank(item, question),
            float(item.get("score", 0) or 0),
            float(item.get("lexical_score", 0) or 0),
        ),
        reverse=True,
    )

    source_counts = {}
    for item in annotated:
        if item.get("record_type") == "structured_project_context":
            source_name = "database"
        else:
            source_name = "documents"
        source_counts[source_name] = source_counts.get(source_name, 0) + 1

    if not annotated:
        failures.add("no_authorised_evidence")

    plan = query_plan or {}
    required_sources = set(plan.get("required_sources") or [])
    if required_sources and not required_sources.issubset(source_counts):
        # A comparison context is intentionally represented as one structured
        # item containing both sides, so do not mark it incomplete solely from
        # its source labels.
        if not any(item.get("record_type") == "structured_project_context" for item in annotated):
            failures.add("required_source_missing")

    complete = bool(annotated) and not failures and not any(
        item.get("retrieval_conflict") for item in annotated
    )
    return EvidenceBundle(
        question=str(question or ""),
        scope=expected_scope,
        project_id=str(project_id) if project_id else None,
        items=tuple(annotated),
        conflicts=tuple(conflicts),
        failure_reasons=tuple(sorted(failures)),
        source_counts=source_counts,
        complete=complete,
    )
