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
    return {
        token.casefold()
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{2,}", str(value or ""))
        if token.casefold() not in _STOP_WORDS
    }


def _is_abstention(answer):
    return bool(re.search(
        r"\b(?:not enough information|cannot answer|can't answer|unable to answer|"
        r"do not have enough|not available|not specified|no information|"
        r"confirm with|contact .* team)\b",
        str(answer or ""),
        re.IGNORECASE,
    ))


def build_diagnostic(question, results, context_metadata=None, answer="", validation_status="unknown"):
    """Return explainable signals without making a second provider request."""

    items = [item for item in (results or []) if isinstance(item, dict)]
    metadata = context_metadata or {}
    structured = [item for item in items if item.get("record_type") == "structured_project_context"]
    evidence_terms = _terms(" ".join(str(item.get("text", "")) for item in items))
    question_terms = _terms(question)
    overlap = question_terms & evidence_terms
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

    return {
        "failure_class": failure_class,
        "retrieval_relevant": int(bool(retrieval_relevant)),
        "evidence_sufficient": int(bool(items and not truncated)),
        "validation_status": str(validation_status or "unknown"),
        "result_count": len(items),
        "source_count": len({str(item.get("source", "")) for item in items if item.get("source")}),
        "structured_count": len(structured),
        "context_truncated": int(truncated),
        "notes": notes,
    }

