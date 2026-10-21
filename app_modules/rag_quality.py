## File: app_modules/rag_quality.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Explainable, low-cost diagnostics for grounded retrieval-augmented answers.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Explainable, low-cost diagnostics for grounded retrieval-augmented answers."""

import re


FAILURE_CLASSES = (
    "none",
    "retrieval_failure",
    "context_failure",
    "generation_failure",
    "validation_unavailable",
)

_STOP_WORDS = {
    "a", "about", "an", "and", "are", "can", "do", "for", "from", "how",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "the",
    "this", "to", "what", "when", "where", "which", "who", "with", "would",
    "you", "your", "our", "we", "capstone", "project", "tell", "show",
}


def _terms(value):
    """
    Function: _terms
    Purpose: Execute the  terms operation.
    Inputs:
            value (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return {
        token.casefold()
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{2,}", str(value or ""))
        if token.casefold() not in _STOP_WORDS
    }


def _is_abstention(answer):
    """Detect a response that is primarily an answer refusal.

    "Not specified" and "confirm with the team" are valid caveats in a
    grounded answer. They must not classify an otherwise useful response as a
    generation failure.
    """
    text = re.sub(r"\s+", " ", str(answer or "")).strip()
    if not text:
        return True
    if re.search(
        r"^(?:I\s+)?(?:cannot|can't|can’t|am unable to|do not have enough|"
        r"don't have enough|not enough information|no information|"
        r"I\s+don’t have the information)\b",
        text,
        re.IGNORECASE,
    ):
        return True
    return False


def build_diagnostic(
    question,
    results,
    context_metadata=None,
    answer="",
    validation_status="unknown",
    query_plan=None,
    conflicts=None,
    route=None,
):
    """Return explainable signals without making a second provider request."""

    items = [item for item in (results or []) if isinstance(item, dict)]
    metadata = context_metadata or {}
    structured = [item for item in items if item.get("record_type") == "structured_project_context"]
    complete = [item for item in items if item.get("retrieval_complete")]
    hybrid = [item for item in items if item.get("retrieval_mode") == "hybrid"]
    semantic = [item for item in items if item.get("retrieval_mode") == "semantic"]
    evidence_terms = _terms(" ".join(str(item.get("text", "")) for item in items))
    question_terms = _terms(question)
    overlap = question_terms & evidence_terms
    answer_terms = _terms(answer)
    answer_evidence_overlap = answer_terms & evidence_terms
    question_coverage = (len(overlap) / len(question_terms)) if question_terms else 0.0
    top_score = max((float(item.get("score", 0) or 0) for item in items), default=0.0)
    retrieval_relevant = bool(structured or (items and overlap and top_score >= 0.10))
    truncated = bool(metadata.get("truncated"))
    answer_text = str(answer or "").strip()

    if not items:
        failure_class = "retrieval_failure"
        notes = "No approved evidence was retrieved."
    elif truncated:
        failure_class = "context_failure"
        notes = "Some retrieved evidence was omitted by the context budget."
    elif not retrieval_relevant:
        failure_class = "retrieval_failure"
        notes = "Retrieved evidence had weak question-term or semantic overlap."
    elif validation_status == "unavailable":
        failure_class = "validation_unavailable"
        notes = "The independent groundedness validation pass was unavailable."
    elif not answer_text or _is_abstention(answer_text):
        failure_class = "generation_failure"
        notes = "Relevant evidence was available, but the answer was empty or abstained."
    else:
        failure_class = "none"
        notes = "Relevant evidence was retrieved and a response was produced."

    if not items or not answer_text:
        confidence_band = "low"
    elif validation_status == "validated" and retrieval_relevant and len(answer_evidence_overlap) >= 3:
        confidence_band = "high"
    elif retrieval_relevant and answer_evidence_overlap:
        confidence_band = "medium"
    else:
        confidence_band = "low"

    plan = query_plan or {}
    route = route or {}
    route_source = str(route.get("source", "unclassified"))
    route_filter = str(route.get("filter", "none"))
    response_mode = str(route.get("response_mode", "ai"))
    notes = (
        f"Route: {route_source}; filter: {route_filter}; response: {response_mode}. "
        f"{notes}"
    )
    return {
        "failure_class": failure_class,
        "retrieval_relevant": int(bool(retrieval_relevant)),
        "evidence_sufficient": int(bool(items and not truncated)),
        "validation_status": str(validation_status or "unknown"),
        "result_count": len(items),
        "source_count": len({str(item.get("source", "")) for item in items if item.get("source")}),
        "structured_count": len(structured),
        "complete_evidence_count": len(complete),
        "hybrid_count": len(hybrid),
        "semantic_count": len(semantic),
        "semantic_backend": next((str(item.get("semantic_backend")) for item in items if item.get("semantic_backend") not in {None, "not used"}), "unavailable"),
        "context_truncated": int(truncated),
        "question_term_coverage": round(question_coverage, 3),
        "answer_evidence_overlap": len(answer_evidence_overlap),
        "confidence_band": confidence_band,
        "notes": notes,
        "route_source": route_source,
        "route_filter": route_filter,
        "response_mode": response_mode,
        "query_intent": str(plan.get("intent", "lookup")),
        "query_scope": str(plan.get("scope", "general")),
        "query_entity": str(plan.get("entity", "general")),
        "query_follow_up": int(bool(plan.get("follow_up"))),
        "subquery_count": len(plan.get("subqueries", []) or []),
        "conflict_count": len(conflicts or []),
    }

