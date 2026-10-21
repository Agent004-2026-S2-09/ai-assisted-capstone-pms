## File: app_modules/query_planning.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Shared, deterministic query plans for project and Capstone questions.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Shared, deterministic query plans for project and Capstone questions.

The plan is deliberately small and serialisable. It is used as a routing
contract before either structured records or document retrieval are queried;
the language model may enrich it, but cannot widen its authorised scope.
"""

from dataclasses import asdict, dataclass, field
from difflib import get_close_matches
import re
import unicodedata


INTENTS = ("lookup", "list", "summarise", "compare", "count", "explain")
ENTITIES = ("meeting", "milestone", "task", "document", "team", "project", "assessment", "general")
SCOPES = ("general", "project")
SOURCE_TYPES = ("database", "documents")

_STOP = {
    "a", "about", "after", "all", "an", "and", "are", "as", "at", "be", "before",
    "can", "do", "for", "from", "how", "i", "in", "is", "it", "my", "of", "on",
    "or", "please", "show", "tell", "the", "this", "to", "what", "when", "where",
    "which", "who", "with", "would", "you", "your", "our", "we", "us",
}


@dataclass
class QueryPlan:
    """
    Class: QueryPlan
    Purpose: Represent the QueryPlan abstraction.
    Responsibilities:
            Preserve the existing class interface and behaviour.
    """
    question: str
    resolved_question: str
    intent: str = "lookup"
    scope: str = "general"
    entity: str = "general"
    filters: dict = field(default_factory=dict)
    required_sources: list[str] = field(default_factory=lambda: ["documents"])
    subqueries: list[str] = field(default_factory=list)
    follow_up: bool = False
    confidence: float = 0.0
    action: str = "search"
    queries: list[str] = field(default_factory=list)

    def to_dict(self):
        """
        Function: to_dict
        Purpose: Execute the to dict operation.
        Inputs:
                None.
        Returns:
                The function result, or None where no value is returned.
        Raises/side effects:
                Existing validation, authorization, persistence, and error handling apply.
        """
        return asdict(self)


def normalise_question(value):
    """Return a stable text form for routing natural-language questions.

    Unicode punctuation and spacing commonly introduced by mobile keyboards,
    copied PDFs, Word documents, and messaging applications are normalised
    before intent/entity detection. The original user text remains available
    for display and audit purposes.

    Args:
        value: User-provided question or a planner-generated query.

    Returns:
        A whitespace- and punctuation-normalised string.
    """
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"[\u2010-\u2015\u2212\ufe58\ufe63\uff0d]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalise(value):
    """Backward-compatible private alias for the shared question normalizer."""
    return normalise_question(value)


def _tokens(value):
    """
    Function: _tokens
    Purpose: Execute the  tokens operation.
    Inputs:
            value (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return re.findall(r"[a-z0-9]+", str(value or "").casefold())


def _closest_entity(text):
    """
    Function: _closest_entity
    Purpose: Execute the  closest entity operation.
    Inputs:
            text (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    tokens = _tokens(text)
    aliases = {
        "meeting": ("meeting", "meetings", "session", "sessions", "minutes", "catchup", "catchup"),
        "milestone": ("milestone", "milestones", "stage", "stages", "phase", "phases", "sprint", "sprints"),
        "task": ("task", "tasks", "work", "item", "items", "card", "cards", "gantt", "kanban", "schedule"),
        "document": ("document", "documents", "file", "files", "pdf", "charter", "proposal", "report"),
        "team": ("team", "member", "members", "teammate", "teammates", "mentor", "sponsor", "owner", "responsible"),
        "assessment": ("assessment", "assessments", "assignment", "assignments", "rubric", "rubrics", "submission", "submissions", "deliverable", "deliverables", "deadline", "deadlines", "due"),
        "project": ("project", "projects"),
    }
    scores = {}
    for entity, aliases_for_entity in aliases.items():
        score = 0
        for token in tokens:
            if token in aliases_for_entity:
                score += 2
            elif get_close_matches(token, aliases_for_entity, n=1, cutoff=0.84):
                score += 1
        if score:
            scores[entity] = score
    return max(scores, key=scores.get) if scores else "general"


def _intent(text):
    """
    Function: _intent
    Purpose: Execute the  intent operation.
    Inputs:
            text (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    lowered = str(text or "").casefold()
    if re.search(r"\b(?:compare|comparison|versus|vs\.?|difference|against)\b", lowered):
        return "compare"
    if re.search(r"\b(?:summari[sz]e|summary|overview|report|detail(?:ed)?|what happened)\b", lowered):
        return "summarise"
    if re.search(r"\b(?:how many|count|number of|total|amount)\b", lowered):
        return "count"
    if re.search(r"\b(?:list|show(?:\s+all|\s+everything)?|which|every|all)\b", lowered):
        return "list"
    if re.search(r"\b(?:why|how does|how do|explain|meaning|what does)\b", lowered):
        return "explain"
    return "lookup"


def _filters(text):
    """
    Function: _filters
    Purpose: Execute the  filters operation.
    Inputs:
            text (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    lowered = str(text or "").casefold()
    result = {}
    ordinal_words = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
                     "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
    ordinal = re.search(r"\b(\d+)(?:st|nd|rd|th)\b", lowered)
    if ordinal:
        result["ordinal"] = int(ordinal.group(1))
    else:
        for word, value in ordinal_words.items():
            if re.search(rf"\b{word}\b", lowered):
                result["ordinal"] = value
                break
    if re.search(r"\b(?:last|latest|most recent|newest|previous|prior|current)\b", lowered):
        result["relative"] = "latest"
    elif re.search(r"\b(?:earliest|oldest|initial|opening|first)\b", lowered):
        result["relative"] = "earliest"
    status = re.search(r"\b(?:planned|in progress|completed|complete|done|finished|overdue|at risk|blocked|backlog|to do|todo|review)\b", lowered)
    if status:
        result["status"] = status.group(0)
    percentage = re.search(r"\b(\d{1,3})\s*%", lowered)
    if percentage:
        result["progress"] = int(percentage.group(1))
    if re.search(r"\b(?:before|prior to|earlier than)\b", lowered):
        result["date_relation"] = "before"
    elif re.search(r"\b(?:after|later than|following)\b", lowered):
        result["date_relation"] = "after"
    week = re.search(r"\bweek\s*(\d{1,2})\b", lowered)
    if week:
        result["week"] = int(week.group(1))
    return result


def _split_subqueries(text):
    """
    Function: _split_subqueries
    Purpose: Execute the  split subqueries operation.
    Inputs:
            text (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    parts = re.split(r"\s+(?:and also|also|plus|as well as)\s+|\s*;\s*", _normalise(text), flags=re.IGNORECASE)
    parts = [part.strip(" ,") for part in parts if len(part.strip()) >= 8]
    return list(dict.fromkeys(parts)) if len(parts) > 1 else []


def build_plan(question, *, project_id=None, history=None):
    """
    Function: build_plan
    Purpose: Execute the build plan operation.
    Inputs:
            question (value): Caller-provided input.
            project_id (value): Caller-provided input.
            history (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    question = _normalise(question)
    previous = [
        _normalise(item.get("content"))
        for item in (history or [])
        if item.get("role") == "user" and _normalise(item.get("content"))
    ]
    tokens = set(_tokens(question))
    follow_up = bool(
        tokens & {"it", "this", "that", "these", "those", "them", "one", "ones", "another", "same", "second", "next"}
        or re.search(r"\b(?:last\s+time|previously|as\s+before|again|more)\b", question, re.IGNORECASE)
    )
    resolved = question
    if follow_up and previous:
        resolved = f"{previous[-1]} {question}"[:1000]
    entity = _closest_entity(resolved)
    intent = _intent(question)
    filters = _filters(question)
    scope = "project" if project_id else "general"
    lowered = resolved.casefold()
    document_language = bool(re.search(r"\b(?:document|file|pdf|charter|proposal|report|rubric|assessment|assignment|teaching|policy|guidance)\b", lowered))
    comparison = intent == "compare" or bool(re.search(r"\b(?:database|workspace|records?)\b.*\b(?:document|file)s?\b|\b(?:document|file)s?\b.*\b(?:database|workspace|records?)\b", lowered))
    structured_entity = entity in {"meeting", "milestone", "task", "team", "project"}
    if project_id and structured_entity and not document_language and not comparison:
        sources = ["database"]
    elif comparison and project_id:
        sources = ["database", "documents"]
    else:
        sources = ["documents"]
    subqueries = _split_subqueries(question)
    if comparison and project_id and not subqueries:
        subqueries = [f"current authorised project records {question}", f"authorised project documents {question}"]
    confidence = min(1.0, 0.35 + (0.2 if entity != "general" else 0) + (0.15 if filters else 0) + (0.15 if intent != "lookup" else 0))
    return QueryPlan(
        question=question,
        resolved_question=resolved,
        intent=intent,
        scope=scope,
        entity=entity,
        filters=filters,
        required_sources=sources,
        subqueries=subqueries,
        follow_up=follow_up,
        confidence=confidence,
        action="search",
        queries=[resolved],
    )


def general_query_variants(question):
    """
    Function: general_query_variants
    Purpose: Produce a small set of safe equivalent searches for general
             Capstone questions when terminology differs between a student
             and the approved documents.
    Inputs:
            question: The student's natural-language question.
    Returns:
            The original question followed by at most two bounded variants.
    Raises/side effects:
            None; this function only rewrites search text and does not add
            facts, sources, or external instructions.
    """
    original = normalise_question(question)
    if not original:
        return []
    variants = [original]
    replacements = (
        (r"\bdeadline(s)?\b", "due date"),
        (r"\bdue date(s)?\b", "deadline"),
        (r"\bdeliverable(s)?\b", "assessment submission"),
        (r"\bparticipants?\b", "students"),
        (r"\biterations?\b", "sprints"),
        (r"\bsupervisor(s)?\b", "mentor"),
    )
    lowered = original.casefold()
    for pattern, replacement in replacements:
        if re.search(pattern, lowered):
            variant = re.sub(pattern, replacement, original, flags=re.IGNORECASE)
            variant = normalise_question(variant)
            if variant and variant.casefold() not in {item.casefold() for item in variants}:
                variants.append(variant)
        if len(variants) >= 3:
            break
    return variants


def merge_provider_plan(local_plan, provider_plan):
    """Accept provider enrichment only within the local scope contract."""
    result = local_plan.to_dict() if isinstance(local_plan, QueryPlan) else dict(local_plan or {})
    provider_plan = provider_plan or {}
    for key in ("intent", "entity", "filters", "subqueries"):
        if key in provider_plan and provider_plan[key] not in (None, "", []):
            result[key] = provider_plan[key]
    if isinstance(provider_plan.get("queries"), list):
        result["queries"] = list(dict.fromkeys(str(item).strip() for item in provider_plan["queries"] if str(item).strip()))[:4]
    result["action"] = provider_plan.get("action", result.get("action", "search"))
    result["scope"] = local_plan.scope if isinstance(local_plan, QueryPlan) else result.get("scope", "general")
    result["required_sources"] = local_plan.required_sources if isinstance(local_plan, QueryPlan) else result.get("required_sources", ["documents"])
    return result
