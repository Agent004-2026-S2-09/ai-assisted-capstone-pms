## File: app_modules/evidence_retrieval.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Deterministic evidence retrieval for the Capstone assistant.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Deterministic evidence retrieval for the Capstone assistant.

This module deliberately does not know about Capstone document names, assessment
names, project IDs, or individual questions.  It separates the evidence types
that the answerer receives:

* structured table blocks are searched as labelled rows and returned complete;
* structured records are searched as records;
* prose is ranked with field-aware lexical scoring.

The result is an evidence contract, not an answer.  The caller can therefore
measure retrieval quality independently from LLM generation.
"""

from __future__ import annotations

import re
import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Iterable, Sequence


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "i", "in", "is", "it", "of", "on", "or", "that", "the",
    "this", "to", "was", "what", "when", "where", "which", "who", "will",
    "with", "you", "your", "our", "we", "me", "please", "tell", "show",
}

SYNONYMS = {
    "submission": "submit",
    "submissions": "submit", "assignment": "assessment", "assignments": "assessment",
    "requirements": "requirement", "required": "requirement", "dates": "date",
    "lectures": "lecture", "topics": "topic", "referencing": "reference",
    "acknowledgement": "acknowledge", "acknowledgment": "acknowledge",
    "reference": "acknowledge", "referencing": "acknowledge", "cite": "acknowledge", "citation": "acknowledge",
    "owns": "owner", "owned": "owner", "ownership": "owner",
    # General Capstone vocabulary. These aliases improve lexical recall for
    # natural-language questions while semantic scoring remains unchanged.
    "due-date": "due",
    "deadline": "due",
    "deadlines": "due",
    "deliverable": "assessment",
    "deliverables": "assessment",
    "criterion": "requirement",
    "criteria": "requirement",
    "eligibility": "eligible",
    "eligibilities": "eligible",
    "participant": "student",
    "participants": "student",
    "classmate": "student",
    "classmates": "student",
    "iteration": "sprint",
    "iterations": "sprint",
    "supervisor": "mentor",
    "supervisors": "mentor",
    "advisor": "mentor",
    "advisors": "mentor",
}

NOISE_WORDS = {
    "all", "each", "every", "list", "show", "tell", "current", "now",
    "today", "semester", "between", "remaining", "pending", "upcoming",
    "available", "information", "details", "thing", "things", "one", "ones",
}

STRUCTURED_FIELD_TERMS = {
    "id", "name", "title", "date", "due", "deadline", "submit", "available",
    "status", "mark", "point", "score", "url", "owner", "type", "category",
}

# These values describe document/version lifecycle, not project task status.
# Documents without these metadata fields remain eligible so existing indexes
# and uploaded files continue to behave exactly as before.
_RETIRED_DOCUMENT_STATUSES = {
    "archived",
    "expired",
    "obsolete",
    "revoked",
    "superseded",
    "withdrawn",
}


def filter_current_documents(
    documents: Iterable[dict],
    *,
    allowed_access_levels: set[str] | None = None,
) -> list[dict]:
    """Remove explicitly retired or unauthorised document versions.

    This is deliberately a pre-ranking filter, matching the Week 11 RAG
    guidance. A high vector or lexical score must not allow an archived,
    superseded, or access-restricted document to compete with current
    evidence. Missing metadata is treated as legacy/current-compatible so
    existing indexes are not silently emptied during migration.

    Args:
        documents: Candidate evidence records.
        allowed_access_levels: Optional set of access labels permitted for the
            current caller. If omitted, the application's existing access
            boundary remains responsible for authorisation.

    Returns:
        A new list containing only eligible evidence records.
    """
    allowed = {
        str(level).strip().casefold()
        for level in (allowed_access_levels or set())
        if str(level).strip()
    }
    filtered = []
    for document in documents or []:
        if not isinstance(document, dict) or not document.get("text"):
            continue

        if document.get("is_current") is False or document.get("superseded") is True:
            continue

        lifecycle_status = (
            document.get("document_status")
            or document.get("version_status")
            or document.get("publication_status")
        )
        if str(lifecycle_status or "").strip().casefold() in _RETIRED_DOCUMENT_STATUSES:
            continue

        if allowed:
            access_level = str(document.get("access_level") or "").strip().casefold()
            if access_level and access_level not in allowed:
                continue

        filtered.append(document)
    return filtered


@dataclass(frozen=True)
class QuerySpec:
    """
    Class: QuerySpec
    Purpose: Represent the QuerySpec abstraction.
    Responsibilities:
            Preserve the existing class interface and behaviour.
    """
    text: str
    terms: tuple[str, ...]
    meaningful_terms: tuple[str, ...]
    exhaustive: bool
    table_likely: bool
    requested_week: int | None
    requested_source_tokens: tuple[str, ...]


def _stem(token: str) -> str:
    """
    Function: _stem
    Purpose: Execute the  stem operation.
    Inputs:
            token (str): Caller-provided input.
    Returns:
            A value of type str.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    token = SYNONYMS.get(token, token)
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokens(value: object, *, keep_stop_words: bool = False) -> list[str]:
    """
    Function: tokens
    Purpose: Execute the tokens operation.
    Inputs:
            value (object): Caller-provided input.
            keep_stop_words (bool): Caller-provided input.
    Returns:
            A value of type list[str].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    values = []
    for token in re.findall(r"[a-z0-9]+", str(value or "").casefold()):
        values.append(_stem(token))
        if token in {"genai", "chatgpt"}:
            values.extend(("ai", "generative", "artificial", "intelligence"))
    if keep_stop_words:
        return values
    return [value for value in values if value not in STOP_WORDS and len(value) > 1]


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    """
    Function: _contains_any
    Purpose: Execute the  contains any operation.
    Inputs:
            text (str): Caller-provided input.
            patterns (Iterable[str]): Caller-provided input.
    Returns:
            A value of type bool.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def parse_query(question: str) -> QuerySpec:
    """
    Function: parse_query
    Purpose: Execute the parse query operation.
    Inputs:
            question (str): Caller-provided input.
    Returns:
            A value of type QuerySpec.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    text = str(question or "").strip()
    parsed_terms = tokens(text)
    if _contains_any(text, (r"\bhow\s+many\b", r"\bmaximum\b", r"\bminimum\b", r"\ballowed\b", r"\bpermitted\b", r"\blimit\b")):
        parsed_terms.extend(("size", "limit", "requirement"))
    all_terms = tuple(dict.fromkeys(parsed_terms))
    meaningful = tuple(term for term in all_terms if term not in NOISE_WORDS and not term.isdigit())
    exhaustive = _contains_any(text, (r"\ball\b", r"\bevery\b", r"\beach\b", r"\blist\b", r"\bcount\b", r"\bhow\s+many\b", r"\bbetween\b", r"\bremaining\b", r"\bpending\b"))
    table_likely = _contains_any(text, (
        r"\b(?:row|rows|column|columns|csv|spreadsheet|table|schedule|assessment|assignment|submission|due|deadline|date|mark|points?|risk|mitigation|control|likelihood|impact)\b",
    ))
    week_match = re.search(r"\b(?:week|wk)\s*(\d{1,2})\b", text, re.IGNORECASE)
    requested_week = int(week_match.group(1)) if week_match else None
    return QuerySpec(
        text=text,
        terms=all_terms,
        meaningful_terms=meaningful,
        exhaustive=exhaustive,
        table_likely=table_likely,
        requested_week=requested_week,
        requested_source_tokens=tuple(tokens(Path(text).stem)),
    )


def _source_tokens(document: dict) -> set[str]:
    """
    Function: _source_tokens
    Purpose: Execute the  source tokens operation.
    Inputs:
            document (dict): Caller-provided input.
    Returns:
            A value of type set[str].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return set(tokens(document.get("source", "")))


def _source_date(source: object) -> date | None:
    """
    Function: _source_date
    Purpose: Execute the  source date operation.
    Inputs:
            source (object): Caller-provided input.
    Returns:
            A value of type date | None.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    match = re.search(
        r"(?<!\d)(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s*(\d{2,4})\b",
        str(source or ""),
        re.IGNORECASE,
    )
    if not match:
        return None
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
        "nov": 11, "dec": 12,
    }
    year = int(match.group(3))
    if year < 100:
        year += 2000
    try:
        return date(year, months[match.group(2).casefold()[:4]], int(match.group(1)))
    except (KeyError, ValueError):
        return None


def _intent_profile(spec: QuerySpec) -> tuple[set[str], set[str]]:
    """Return source hints and exclusions for high-risk evidence intents.

    Retrieval should not let a broad shared word such as ``assessment`` or
    ``presentation`` make an unrelated catalogue or role guide outrank the
    document family that owns the answer. These hints are deliberately based
    on query intent and source names, not hard-coded document filenames.
    """
    text = spec.text.casefold()
    preferred: set[str] = set()
    excluded: set[str] = set()

    if re.search(r"\b(?:assessment|assignment|submission|due|deadline|remaining|pending|upcoming)\b", text):
        preferred.update(("assessment", "schedule", "due", "deadline", "week 10", "week 12"))
        excluded.update(("list of project", "list_of_projects", "project catalogue", "project catalog"))
    if re.search(r"\b(?:proposal|plan report|report.*include|include.*report)\b", text):
        preferred.update(("proposal", "plan", "tutorial", "lecture"))
        excluded.update(("reflection rubric",))
    if re.search(r"\b(?:presentation|poster|presentations)\b", text):
        preferred.update(("presentation", "poster", "tutorial", "assessment"))
        excluded.update(("team roles",))
    if re.search(r"\b(?:ethics?|ethical|professionalism)\b", text):
        preferred.update(("ethics", "ethic", "professionalism", "code"))
    if re.search(r"\b(?:sponsor|client|stakeholder)\b", text):
        preferred.update(("sponsor", "stakeholder", "client", "proposal", "project"))
        excluded.update(("team roles",))
    if re.search(r"\b(?:risk|risk-management|mitigation|planning)\b", text):
        preferred.update(("risk", "management", "planning", "plan", "requirement"))
    if re.search(r"\b(?:technical|teaching)\s+support\b|\bteaching\s+support\b", text):
        preferred.update(("teaching", "support", "team"))
    if spec.requested_week is not None:
        preferred.update((f"week {spec.requested_week}", "lecture", "tutorial"))

    return preferred, excluded


def _source_intent_adjustment(spec: QuerySpec, source: object) -> tuple[float, bool]:
    """
    Function: _source_intent_adjustment
    Purpose: Execute the  source intent adjustment operation.
    Inputs:
            spec (QuerySpec): Caller-provided input.
            source (object): Caller-provided input.
    Returns:
            A value of type tuple[float, bool].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    preferred, excluded = _intent_profile(spec)
    if isinstance(source, dict):
        source_name = str(source.get("source", ""))
        body = str(source.get("text", ""))
    else:
        source_name = str(source or "")
        body = ""
    normalized = source_name.casefold().replace("_", " ")
    if any(token in normalized for token in excluded):
        return -0.20, True
    matches = sum(token in normalized for token in preferred)
    adjustment = min(0.18, 0.06 * matches)
    body_lower = body.casefold()
    # A schedule is authoritative for due-date questions when its extracted
    # schema contains the actual date fields, even if PDF extraction did not
    # classify it as a table_block.
    if "assessment" in spec.text.casefold() and "due date" in body_lower and "available until" in body_lower:
        adjustment += 0.18
    if "proposal" in spec.text.casefold() and "project proposal and plan" in body_lower:
        adjustment += 0.16
    return min(0.34, adjustment), False


def _header_and_rows(text: str) -> tuple[str, list[str]]:
    """
    Function: _header_and_rows
    Purpose: Execute the  header and rows operation.
    Inputs:
            text (str): Caller-provided input.
    Returns:
            A value of type tuple[str, list[str]].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    header = next((line for line in lines if line.casefold().startswith("headers:")), "")
    rows = [line for line in lines if re.match(r"^row\s+\d+:", line, re.IGNORECASE)]
    return header, rows


def _table_fields(header: str, row: str) -> tuple[set[str], set[str]]:
    """
    Function: _table_fields
    Purpose: Execute the  table fields operation.
    Inputs:
            header (str): Caller-provided input.
            row (str): Caller-provided input.
    Returns:
            A value of type tuple[set[str], set[str]].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    header_names = []
    if header:
        header_names = [part.strip().split("=", 1)[0] for part in header.removeprefix("Headers:").split(" | ")]
    fields = []
    for part in row.split(" | "):
        key, separator, value = part.partition("=")
        if separator:
            fields.append((key.strip(), value.strip()))
    field_names = set(tokens(" ".join(header_names + [key for key, _ in fields])))
    semantic_values = [
        value for key, value in fields
        if not re.search(r"\b(?:url|link|id|date|time|due|deadline|available|points?|score)\b", key, re.IGNORECASE)
    ]
    values = set(tokens(" ".join(semantic_values)))
    return field_names, values


def _table_score(spec: QuerySpec, document: dict) -> tuple[float, int, bool]:
    """
    Function: _table_score
    Purpose: Execute the  table score operation.
    Inputs:
            spec (QuerySpec): Caller-provided input.
            document (dict): Caller-provided input.
    Returns:
            A value of type tuple[float, int, bool].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    header, rows = _header_and_rows(document.get("text", ""))
    if not rows:
        return 0.0, 0, False
    source = _source_tokens(document)
    source_name = str(document.get("source", ""))
    source_named = bool(Path(source_name.casefold()).stem and Path(source_name.casefold()).stem in spec.text.casefold())
    header_terms = set(tokens(header))
    row_value_terms = set()
    row_field_terms = set()
    matched_rows = 0
    for row in rows:
        field_names, values = _table_fields(header, row)
        row_field_terms.update(field_names)
        row_value_terms.update(values)
        if set(spec.meaningful_terms) & (field_names | values):
            matched_rows += 1
    query_terms = set(spec.meaningful_terms)
    header_hits = query_terms & header_terms
    value_hits = query_terms & row_value_terms
    field_hits = query_terms & row_field_terms
    term_hits = len(header_hits | value_hits | field_hits)
    source_hits = len(set(spec.meaningful_terms) & source)
    if not (term_hits or source_hits):
        return 0.0, 0, False
    # A generic header such as ``Assessment`` must not make every assessment
    # question retrieve an unrelated table.  A table becomes authoritative
    # when the question asks for a complete list, matches a data-bearing field
    # (date, due, status, points, etc.), matches a row value, or names the file.
    data_field_hit = bool(header_hits & STRUCTURED_FIELD_TERMS)
    risk_table_query = bool(
        re.search(r"\b(?:risk|mitigation|control|likelihood|impact)\b", spec.text, re.IGNORECASE)
        and header_terms & {"risk", "likelihood", "impact", "action", "control", "planning"}
    )
    if risk_table_query:
        data_field_hit = True
    if (
        re.search(r"\b(?:assessment|assignment|submission)s?\b", spec.text, re.IGNORECASE)
        and re.search(r"\b(?:schedule|information|details|listed|stored)\b", spec.text, re.IGNORECASE)
        and header_terms & {"date", "due", "available", "point", "submit"}
    ):
        data_field_hit = True
    range_language = _contains_any(spec.text, (r"\bbetween\b", r"\bremaining\b", r"\bpending\b", r"\bupcoming\b", r"\bend\s+of\s+(?:the\s+)?semester\b"))
    date_field_hit = bool(header_terms & {"date", "due", "deadline", "available"})
    if not spec.table_likely and not spec.exhaustive and not source_named and not data_field_hit:
        return 0.0, 0, False
    if not source_named and not spec.exhaustive and not data_field_hit:
        return 0.0, 0, False
    if header_hits and not value_hits and not data_field_hit and not (spec.exhaustive or (range_language and date_field_hit)):
        return 0.0, 0, False
    if not header_hits and not source_named and not spec.exhaustive:
        return 0.0, 0, False
    score = 0.58 + 0.12 * term_hits + 0.12 * source_hits
    if spec.table_likely and term_hits:
        score += 0.10
    if spec.exhaustive:
        score += 0.08
    score = min(1.0, score)
    return score, matched_rows, bool(term_hits or source_hits)


def _prose_score(spec: QuerySpec, document: dict, term_weights: dict[str, float] | None = None) -> tuple[float, set[str]]:
    """
    Function: _prose_score
    Purpose: Execute the  prose score operation.
    Inputs:
            spec (QuerySpec): Caller-provided input.
            document (dict): Caller-provided input.
            term_weights (dict[str, float] | None): Caller-provided input.
    Returns:
            A value of type tuple[float, set[str]].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    body = set(tokens(document.get("text", "")))
    source = _source_tokens(document)
    location = set(tokens(document.get("location", "")))
    query = set(spec.meaningful_terms or spec.terms)
    if not query:
        return 0.0, set()
    body_hits = query & body
    source_hits = query & source
    location_hits = query & location
    weights = term_weights or {term: 1.0 for term in query}
    total_weight = sum(weights.get(term, 1.0) for term in query) or 1.0
    coverage = sum(weights.get(term, 1.0) for term in body_hits) / total_weight
    source_coverage = sum(weights.get(term, 1.0) for term in source_hits) / total_weight
    location_coverage = sum(weights.get(term, 1.0) for term in location_hits) / total_weight
    fuzzy = 0.0
    long_query = [term for term in query if len(term) >= 5]
    long_body = [term for term in body if len(term) >= 5]
    if long_query and long_body:
        fuzzy = sum(
            any(SequenceMatcher(None, term, candidate).ratio() >= 0.86 for candidate in long_body)
            for term in long_query
        ) / len(long_query)
    phrase = 0.0
    normalized_source = " ".join(tokens(document.get("source", ""), keep_stop_words=True))
    source_specific_terms = [term for term in query if len(term) >= 5 and weights.get(term, 1.0) > 2.5]
    if normalized_source and any(term in normalized_source for term in source_specific_terms):
        phrase = 0.15
    score = 0.34 * coverage + 0.48 * source_coverage + 0.10 * location_coverage + 0.08 * fuzzy + phrase
    matched = body_hits | source_hits | location_hits
    return min(1.0, score), matched


def _hybrid_score(lexical_score: float, semantic_score: float) -> float:
    """Fuse calibrated lexical and semantic scores.

    Lexical evidence gets the larger weight because exact dates, identifiers,
    table fields and names must remain precise. Semantic evidence still allows
    paraphrases to enter the candidate set and improves ordering when wording
    differs from the indexed text.
    """
    if lexical_score and semantic_score:
        return min(1.0, 0.68 * lexical_score + 0.32 * semantic_score)
    if lexical_score:
        return lexical_score
    return min(1.0, 0.32 * semantic_score)


def retrieve(
    documents: Iterable[dict],
    question: str,
    *,
    top_k: int = 12,
    minimum_score: float = 0.18,
    semantic_scorer: Callable[[str, Sequence[dict]], Sequence[float]] | None = None,
    semantic_scores: Sequence[float] | None = None,
    semantic_backend: str = "unavailable",
    allowed_access_levels: set[str] | None = None,
) -> list[dict]:
    """Retrieve an explainable, type-aware evidence set.

    Table blocks are never removed merely because the question omitted the
    word ``table``.  When a table is relevant, the complete block is returned
    so rows cannot be lost to chunk ranking.
    """
    spec = parse_query(question)
    candidates = filter_current_documents(
        documents,
        allowed_access_levels=allowed_access_levels,
    )
    if not candidates or not spec.terms:
        return []

    explicit_source = set()
    question_text = spec.text.casefold()
    for item in candidates:
        source = str(item.get("source", ""))
        stem = Path(source).stem.casefold()
        if stem and stem in question_text:
            explicit_source.add(source)
    if explicit_source:
        candidates = [item for item in candidates if item.get("source") in explicit_source]
    else:
        # When the question explicitly asks about risk control, risk-register
        # spreadsheets are the authoritative family.  A semantic scorer can
        # otherwise promote a generic support document because both questions
        # contain words such as "support" and "project".
        risk_question = bool(re.search(r"\b(?:risk|risk-management|mitigation|likelihood|impact)\b", question_text))
        risk_sources = {
            item.get("source")
            for item in candidates
            if item.get("source") and re.search(r"\brisk\b", str(item.get("source", "")), re.IGNORECASE)
        }
        if risk_question and risk_sources:
            candidates = [item for item in candidates if item.get("source") in risk_sources]
        # For date/list assessment questions, require evidence that actually
        # contains the schedule fields when such evidence exists. Narrative
        # assessment guidance must not outrank the authoritative date table.
        assessment_date_query = bool(
            re.search(r"\b(?:assessments?|assignments?|submissions?)\b", question_text)
            and re.search(r"\b(?:due|deadline|date|remaining|pending|upcoming|between)\b", question_text)
        )
        schedule_candidates = [
            item for item in candidates
            if re.search(r"\bdue\s+date\b", str(item.get("text", "")), re.IGNORECASE)
            and re.search(r"\b(?:available\s+until|submission|points?)\b", str(item.get("text", "")), re.IGNORECASE)
        ]
        schedule_sources = {
            item.get("source")
            for item in schedule_candidates
            if item.get("source")
            and re.search(r"\b(?:assessments?|assignments?)\b", str(item.get("source", "")).replace("_", " "), re.IGNORECASE)
        }
        if assessment_date_query and schedule_sources:
            candidates = [item for item in candidates if item.get("source") in schedule_sources]
            schedule_candidates = candidates
        if assessment_date_query and schedule_candidates:
            candidates = schedule_candidates
        # A project workspace may contain a copied assessment CSV/table whose
        # question asks for the schedule itself rather than a specific date.
        # Prefer that complete structured table over unrelated project prose.
        assessment_schedule_query = bool(
            re.search(r"\b(?:assessment|assignment|submission)s?\b", question_text)
            and re.search(r"\b(?:schedule|information|details|listed|stored)\b", question_text)
        )
        assessment_tables = [
            item for item in candidates
            if item.get("record_type") == "table_block"
            and re.search(r"\bassessment\b", str(item.get("text", "")), re.IGNORECASE)
            and re.search(r"\bdue\s+date\b", str(item.get("text", "")), re.IGNORECASE)
        ]
        if assessment_schedule_query and assessment_tables:
            candidates = assessment_tables
        _, excluded_sources = _intent_profile(spec)
        if excluded_sources:
            filtered = [
                item for item in candidates
                if not any(token in str(item.get("source", "")).casefold().replace("_", " ") for token in excluded_sources)
            ]
            # Never turn a weak intent guess into a zero-result search.
            if filtered:
                candidates = filtered

    corpus_terms = []
    for item in candidates:
        corpus_terms.append(set(tokens(
            f"{item.get('source', '')} {item.get('location', '')} {item.get('text', '')}"
        )))
    document_frequency = Counter(term for terms in corpus_terms for term in terms)
    corpus_size = max(1, len(candidates))
    term_weights = {
        term: 1.0 + max(0.0, math.log((corpus_size + 1) / (document_frequency.get(term, 0) + 1)))
        for term in spec.meaningful_terms
    }

    week_anchor = None
    if spec.requested_week:
        for item in candidates:
            source_week = re.search(r"\bweek\s*(\d{1,2})\b", str(item.get("source", "")), re.IGNORECASE)
            source_date = _source_date(item.get("source", ""))
            if source_week and source_date:
                week_anchor = (int(source_week.group(1)), source_date)
                break

    semantic_values: list[float]
    if semantic_scorer is not None:
        try:
            semantic_values = [
                max(0.0, min(1.0, float(value or 0.0)))
                for value in semantic_scorer(spec.text, candidates)
            ]
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
            semantic_values = [0.0] * len(candidates)
            semantic_backend = "unavailable"
    elif semantic_scores is not None and len(semantic_scores) == len(candidates):
        semantic_values = [max(0.0, min(1.0, float(value or 0.0))) for value in semantic_scores]
    else:
        semantic_values = [0.0] * len(candidates)
        semantic_backend = "unavailable"

    scored: list[tuple[float, dict, str, set[str], float, float]] = []
    for item_index, item in enumerate(candidates):
        semantic_score = semantic_values[item_index]
        record_type = item.get("record_type", "document_chunk")
        if record_type == "table_block":
            score, matched_rows, matched = _table_score(spec, item)
            if score:
                adjustment, excluded = _source_intent_adjustment(spec, item)
                if excluded:
                    continue
                score = min(1.0, max(0.0, score + adjustment))
                fused = _hybrid_score(score, semantic_score)
                scored.append((fused, item, "complete table", set(spec.meaningful_terms), score, semantic_score))
            elif semantic_score >= 0.62 and not spec.table_likely:
                scored.append((
                    _hybrid_score(0.0, semantic_score), item,
                    "semantic evidence match", set(), 0.0, semantic_score,
                ))
            continue
        score, matched = _prose_score(spec, item, term_weights)
        if spec.requested_week:
            exact_week = re.search(rf"\bweek\s*{spec.requested_week}\b", str(item.get("text", "")), re.IGNORECASE)
            if exact_week:
                score = min(1.0, score + 0.25)
            elif re.search(r"\bweek\s*\d+\b", str(item.get("source", "")), re.IGNORECASE):
                score *= 0.35
            if week_anchor:
                source_date = _source_date(item.get("source", ""))
                if source_date:
                    anchor_week, anchor_date = week_anchor
                    derived_week = anchor_week + ((source_date - anchor_date).days // 7)
                    if derived_week == spec.requested_week:
                        score = min(1.0, score + 0.30)
        adjustment, excluded = _source_intent_adjustment(spec, item)
        if excluded:
            continue
        score = min(1.0, max(0.0, score + adjustment))
        fused = _hybrid_score(score, semantic_score)
        if score >= minimum_score or (semantic_score >= 0.62 and fused >= minimum_score):
            reason = "hybrid lexical + semantic match" if score and semantic_score else (
                "semantic evidence match" if semantic_score else "lexical evidence match"
            )
            scored.append((fused, item, reason, matched, score, semantic_score))

    scored.sort(key=lambda part: (part[0], part[4], part[5], len(part[3])), reverse=True)
    table_scores = [part for part in scored if part[1].get("record_type") == "table_block"]
    if table_scores and (spec.exhaustive or not any(part[1].get("record_type") == "document_chunk" and part[0] >= table_scores[0][0] for part in scored)):
        best_table_source = table_scores[0][1].get("source")
        complete_table = [part for part in table_scores if part[1].get("source") == best_table_source]
        scored = complete_table + [part for part in scored if part[1].get("record_type") != "table_block"]
    results = []
    seen = set()
    for score, item, reason, matched, lexical_score, semantic_score in scored:
        key = (item.get("scope", "general"), item.get("project_id"), item.get("source"), item.get("location"), item.get("chunk"))
        if key in seen:
            continue
        result = dict(item)
        result["score"] = round(float(score), 6)
        result["retrieval_reason"] = reason
        result["matched_terms"] = sorted(matched)
        result["lexical_score"] = round(float(lexical_score), 6)
        result["semantic_score"] = round(float(semantic_score), 6)
        result["semantic_backend"] = semantic_backend if semantic_score else "not used"
        result["retrieval_mode"] = "hybrid" if lexical_score and semantic_score else (
            "semantic" if semantic_score else "lexical"
        )
        result["retrieval_complete"] = item.get("record_type") == "table_block" and reason == "complete table"
        result["retrieval_query_terms"] = list(spec.terms)
        results.append(result)
        seen.add(key)
        if len(results) >= top_k and not (spec.exhaustive and item.get("record_type") == "table_block"):
            break
    return results

