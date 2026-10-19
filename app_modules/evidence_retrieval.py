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
    "deadline": "due", "deadlines": "due", "submission": "submit",
    "submissions": "submit", "assignment": "assessment", "assignments": "assessment",
    "requirements": "requirement", "required": "requirement", "dates": "date",
    "lectures": "lecture", "topics": "topic", "referencing": "reference",
    "acknowledgement": "acknowledge", "acknowledgment": "acknowledge",
    "reference": "acknowledge", "referencing": "acknowledge", "cite": "acknowledge", "citation": "acknowledge",
    "owns": "owner", "owned": "owner", "ownership": "owner",
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


@dataclass(frozen=True)
class QuerySpec:
    text: str
    terms: tuple[str, ...]
    meaningful_terms: tuple[str, ...]
    exhaustive: bool
    table_likely: bool
    requested_week: int | None
    requested_source_tokens: tuple[str, ...]


def _stem(token: str) -> str:
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
    values = []
    for token in re.findall(r"[a-z0-9]+", str(value or "").casefold()):
        values.append(_stem(token))
        if token in {"genai", "chatgpt"}:
            values.extend(("ai", "generative", "artificial", "intelligence"))
    if keep_stop_words:
        return values
    return [value for value in values if value not in STOP_WORDS and len(value) > 1]


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def parse_query(question: str) -> QuerySpec:
    text = str(question or "").strip()
    parsed_terms = tokens(text)
    if _contains_any(text, (r"\bhow\s+many\b", r"\bmaximum\b", r"\bminimum\b", r"\ballowed\b", r"\bpermitted\b", r"\blimit\b")):
        parsed_terms.extend(("size", "limit", "requirement"))
    all_terms = tuple(dict.fromkeys(parsed_terms))
    meaningful = tuple(term for term in all_terms if term not in NOISE_WORDS and not term.isdigit())
    exhaustive = _contains_any(text, (r"\ball\b", r"\bevery\b", r"\beach\b", r"\blist\b", r"\bcount\b", r"\bhow\s+many\b", r"\bbetween\b", r"\bremaining\b", r"\bpending\b"))
    table_likely = _contains_any(text, (
        r"\b(?:row|rows|column|columns|csv|spreadsheet|table|schedule|assessment|assignment|submission|due|deadline|date|mark|points?)\b",
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
    return set(tokens(document.get("source", "")))


def _source_date(source: object) -> date | None:
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


def _header_and_rows(text: str) -> tuple[str, list[str]]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    header = next((line for line in lines if line.casefold().startswith("headers:")), "")
    rows = [line for line in lines if re.match(r"^row\s+\d+:", line, re.IGNORECASE)]
    return header, rows


def _table_fields(header: str, row: str) -> tuple[set[str], set[str]]:
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
) -> list[dict]:
    """Retrieve an explainable, type-aware evidence set.

    Table blocks are never removed merely because the question omitted the
    word ``table``.  When a table is relevant, the complete block is returned
    so rows cannot be lost to chunk ranking.
    """
    spec = parse_query(question)
    candidates = [item for item in documents or [] if isinstance(item, dict) and item.get("text")]
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

