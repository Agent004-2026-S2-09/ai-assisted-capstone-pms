## File: app_modules/query_reliability.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Evidence checks shared by retrieval, generation and monitoring.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Evidence checks shared by retrieval, generation and monitoring."""

import re
from collections import defaultdict


_FIELD_PATTERNS = (
    ("project_id", re.compile(r"\bProject\s+ID:\s*(.+)$", re.IGNORECASE)),
    ("project_name", re.compile(r"\bProject\s+name:\s*(.+)$", re.IGNORECASE)),
    ("status", re.compile(r"\bStatus:\s*(.+?)(?:\s*\|\s*|$)", re.IGNORECASE)),
    ("date", re.compile(r"\b(?:Date|Meeting date|Target date):\s*(.+?)(?:\s*\|\s*|$)", re.IGNORECASE)),
)


def _clean(value):
    """
    Function: _clean
    Purpose: Execute the  clean operation.
    Inputs:
            value (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return re.sub(r"\s+", " ", str(value or "")).strip(" .;:").casefold()


def detect_conflicts(results):
    """Find contradictory labelled facts across supplied evidence items."""
    values = defaultdict(list)
    for item in results or []:
        text = str(item.get("text", ""))
        source = item.get("source") or item.get("location") or "structured record"
        for field, pattern in _FIELD_PATTERNS:
            for line in text.splitlines():
                match = pattern.search(line.strip())
                if match:
                    value = _clean(match.group(1))
                    if value:
                        values[field].append((value, str(source)))
    conflicts = []
    for field, entries in values.items():
        by_source = defaultdict(set)
        for value, source in entries:
            by_source[source].add(value)
        distinct_values = set().union(*by_source.values()) if by_source else set()
        # Multiple meetings, tasks or milestones naturally have different
        # dates/statuses within one authoritative collection. A conflict is
        # only meaningful when independent sources disagree.
        if len(by_source) >= 2 and len(distinct_values) > 1:
            conflicts.append({
                "field": field,
                "values": [
                    {"value": value, "sources": sorted(source for source, values_for_source in by_source.items() if value in values_for_source)}
                    for value in sorted(distinct_values)
                ],
            })
    return conflicts


def annotate_results(results):
    """Annotate evidence with conflict metadata without changing its text."""
    conflicts = detect_conflicts(results)
    if not conflicts:
        return list(results or []), []
    fields = {item["field"] for item in conflicts}
    annotated = []
    for item in results or []:
        copy = dict(item)
        copy["retrieval_conflict"] = True
        copy["conflict_fields"] = sorted(fields)
        annotated.append(copy)
    return annotated, conflicts

