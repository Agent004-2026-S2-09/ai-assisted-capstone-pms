## File: app_modules/monitoring.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Privacy-conscious AI interaction monitoring and administrator reporting.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Privacy-conscious AI interaction monitoring and administrator reporting."""

import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone

from app_modules import access_control as access
from app_modules import auth
from app_modules import database

MAX_FEEDBACK_COMMENT_LENGTH = 2000
MAX_EVALUATION_RESPONSE_LENGTH = 50000

PROMPT_TOPIC_RULES = (
    ("Project planning and scheduling", (
        "plan", "planning", "schedule", "scheduling", "gantt", "deadline", "timeline", "wbs",
    )),
    ("Tasks, Kanban and milestones", (
        "task", "kanban", "backlog", "milestone", "sprint", "board", "progress", "assign",
    )),
    ("Documents and knowledge base", (
        "document", "upload", "file", "pdf", "knowledge", "search", "source", "template",
    )),
    ("Assessment and capstone guidance", (
        "assessment", "rubric", "capstone", "proposal", "report", "presentation", "requirement",
    )),
    ("Team, roles and access", (
        "team", "role", "member", "student", "mentor", "sponsor", "login", "password", "access",
    )),
    ("Meetings, decisions and actions", (
        "meeting", "minutes", "agenda", "decision", "action", "attendee", "discussion",
    )),
    ("Risks, issues and quality", (
        "risk", "issue", "blocker", "quality", "testing", "test", "problem", "concern",
    )),
    ("AI assistant and prompts", (
        "ai", "assistant", "prompt", "answer", "question", "chat", "response", "explain",
    )),
    ("Administration and system settings", (
        "admin", "setting", "feature", "performance", "latency", "feedback", "account",
    )),
)


def hash_request(text):
    """
    Function: hash_request
    Purpose: Execute the hash request operation.
    Inputs:
            text (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def log_interaction(
    *,
    user,
    project_id,
    assistant_mode,
    prompt_name,
    prompt_version,
    question,
    response_text="",
    latency_ms=0,
    success=True,
    error_type=None,
    http_status=None,
    input_tokens=None,
    output_tokens=None,
    total_tokens=None,
):
    """
    Function: log_interaction
    Purpose: Execute the log interaction operation.
    Inputs:
            user (value): Caller-provided input.
            project_id (value): Caller-provided input.
            assistant_mode (value): Caller-provided input.
            prompt_name (value): Caller-provided input.
            prompt_version (value): Caller-provided input.
            question (value): Caller-provided input.
            response_text (value): Caller-provided input.
            latency_ms (value): Caller-provided input.
            success (value): Caller-provided input.
            error_type (value): Caller-provided input.
            http_status (value): Caller-provided input.
            input_tokens (value): Caller-provided input.
            output_tokens (value): Caller-provided input.
            total_tokens (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    current = auth.current_user(user)
    if not current:
        raise PermissionError("An active signed-in user is required.")
    if project_id:
        access.require_project(user, project_id)
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    created_epoch = time.time()
    with database.connect() as db:
        cursor = db.execute(
            """INSERT INTO ai_interactions
            (created_at, user_id, user_role, project_id, assistant_mode,
             prompt_name, prompt_version, request_hash, request_chars,
             response_chars, response_text, latency_ms, success, error_type, http_status,
             input_tokens, output_tokens, total_tokens, created_epoch)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                created_at,
                current["id"],
                current["role"],
                project_id or None,
                assistant_mode,
                prompt_name,
                prompt_version,
                hash_request(question),
                len(str(question or "")),
                len(str(response_text or "")),
                str(response_text or "")[:MAX_EVALUATION_RESPONSE_LENGTH],
                max(0, int(latency_ms)),
                int(bool(success)),
                error_type,
                http_status,
                input_tokens,
                output_tokens,
                total_tokens,
                created_epoch,
            ),
        )
        interaction_id = cursor.lastrowid
        db.execute(
            """INSERT INTO ai_prompt_archive(interaction_id, question_text, created_at)
               VALUES (?, ?, ?)""",
            (interaction_id, str(question or ""), created_at),
        )
    return interaction_id


def log_rag_diagnostic(interaction_id, diagnostic):
    """Persist explainable retrieval/grounding signals for one answer."""

    if not interaction_id or not isinstance(diagnostic, dict):
        return
    with database.connect() as db:
        db.execute(
            """INSERT INTO rag_diagnostics
               (interaction_id, created_at, failure_class, retrieval_relevant,
                evidence_sufficient, validation_status, result_count, source_count,
                structured_count, context_truncated, notes, query_intent,
                query_scope, query_entity, query_follow_up, subquery_count,
                conflict_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(interaction_id) DO UPDATE SET
                 failure_class = excluded.failure_class,
                 retrieval_relevant = excluded.retrieval_relevant,
                 evidence_sufficient = excluded.evidence_sufficient,
                 validation_status = excluded.validation_status,
                 result_count = excluded.result_count,
                 source_count = excluded.source_count,
                 structured_count = excluded.structured_count,
                 context_truncated = excluded.context_truncated,
                 notes = excluded.notes,
                 query_intent = excluded.query_intent,
                 query_scope = excluded.query_scope,
                 query_entity = excluded.query_entity,
                 query_follow_up = excluded.query_follow_up,
                 subquery_count = excluded.subquery_count,
                 conflict_count = excluded.conflict_count""",
            (
                interaction_id,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                str(diagnostic.get("failure_class", "unknown")),
                int(bool(diagnostic.get("retrieval_relevant"))),
                int(bool(diagnostic.get("evidence_sufficient"))),
                str(diagnostic.get("validation_status", "unknown")),
                max(0, int(diagnostic.get("result_count", 0))),
                max(0, int(diagnostic.get("source_count", 0))),
                max(0, int(diagnostic.get("structured_count", 0))),
                int(bool(diagnostic.get("context_truncated"))),
                str(diagnostic.get("notes", ""))[:1000],
                str(diagnostic.get("query_intent", "lookup"))[:40],
                str(diagnostic.get("query_scope", "general"))[:40],
                str(diagnostic.get("query_entity", "general"))[:40],
                int(bool(diagnostic.get("query_follow_up"))),
                max(0, int(diagnostic.get("subquery_count", 0))),
                max(0, int(diagnostic.get("conflict_count", 0))),
            ),
        )


def log_query_trace(interaction_id, trace):
    """Persist bounded administrator diagnostics for one completed query."""

    if not interaction_id or not isinstance(trace, dict):
        return
    route = trace.get("route") or {}
    payload = {
        "query_plan": trace.get("query_plan") or {},
        "evidence": trace.get("evidence") or {},
        "retrieval": trace.get("retrieval") or {},
        "timeline": trace.get("timeline") or [],
        "security": trace.get("security") or {},
    }
    with database.connect() as db:
        db.execute(
            """INSERT INTO ai_query_traces(
                   interaction_id, created_at, route_source, route_filter,
                   response_mode, final_status, query_plan_json, evidence_json,
                   retrieval_json, timeline_json, security_json, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(interaction_id) DO UPDATE SET
                   created_at = excluded.created_at,
                   route_source = excluded.route_source,
                   route_filter = excluded.route_filter,
                   response_mode = excluded.response_mode,
                   final_status = excluded.final_status,
                   query_plan_json = excluded.query_plan_json,
                   evidence_json = excluded.evidence_json,
                   retrieval_json = excluded.retrieval_json,
                   timeline_json = excluded.timeline_json,
                   security_json = excluded.security_json,
                   notes = excluded.notes""",
            (
                interaction_id,
                str(trace.get("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")),
                str(route.get("source", "unclassified"))[:80],
                str(route.get("filter", "none"))[:120],
                str(route.get("response_mode", "ai"))[:40],
                str(trace.get("final_status", "unknown"))[:60],
                json.dumps(payload["query_plan"], ensure_ascii=False, default=str)[:4000],
                json.dumps(payload["evidence"], ensure_ascii=False, default=str)[:4000],
                json.dumps(payload["retrieval"], ensure_ascii=False, default=str)[:4000],
                json.dumps(payload["timeline"], ensure_ascii=False, default=str)[:6000],
                json.dumps(payload["security"], ensure_ascii=False, default=str)[:2000],
                str(trace.get("notes", ""))[:1000],
            ),
        )


def recent_query_traces(state, days=30, limit=200):
    """Return administrator-only query traces with linked answer metadata."""

    _admin(state)
    since = time.time() - max(1, int(days)) * 86400
    with database.connect() as db:
        rows = db.execute(
            """SELECT qt.interaction_id, qt.created_at, ai.user_role,
                      ai.project_id, ai.assistant_mode, ai.request_chars,
                      ai.response_chars, ai.latency_ms, ai.success,
                      ai.error_type, ai.total_tokens, pa.question_text,
                      ai.response_text, qt.route_source, qt.route_filter,
                      qt.response_mode, qt.final_status, qt.query_plan_json,
                      qt.evidence_json, qt.retrieval_json, qt.timeline_json,
                      qt.security_json, qt.notes,
                      COALESCE(rd.failure_class, 'not_recorded') AS failure_class,
                      COALESCE(rd.validation_status, 'not_recorded') AS validation_status,
                      COALESCE(rd.result_count, 0) AS result_count,
                      COALESCE(rd.conflict_count, 0) AS conflict_count
               FROM ai_query_traces qt
               JOIN ai_interactions ai ON ai.id = qt.interaction_id
               LEFT JOIN ai_prompt_archive pa ON pa.interaction_id = qt.interaction_id
               LEFT JOIN rag_diagnostics rd ON rd.interaction_id = qt.interaction_id
               WHERE ai.created_epoch >= ?
               ORDER BY qt.id DESC LIMIT ?""",
            (since, max(1, min(int(limit), 500))),
        ).fetchall()
    return [dict(row) for row in rows]


def rag_quality_metrics(state, days=30):
    """Return administrator-only RAG failure and evidence metrics."""

    _admin(state)
    since = time.time() - max(1, int(days)) * 86400
    with database.connect() as db:
        row = db.execute(
            """SELECT COUNT(*) diagnostics,
                      COALESCE(SUM(retrieval_relevant), 0) relevant,
                      COALESCE(SUM(evidence_sufficient), 0) sufficient,
                      COALESCE(SUM(context_truncated), 0) truncated,
                      COALESCE(SUM(CASE WHEN failure_class = 'none' THEN 1 ELSE 0 END), 0) clean
                 FROM rag_diagnostics rd JOIN ai_interactions ai
                   ON ai.id = rd.interaction_id WHERE ai.created_epoch >= ?""",
            (since,),
        ).fetchone()
        classes = db.execute(
            """SELECT failure_class, COUNT(*) count
               FROM rag_diagnostics rd JOIN ai_interactions ai
                 ON ai.id = rd.interaction_id WHERE ai.created_epoch >= ?
               GROUP BY failure_class ORDER BY count DESC""",
            (since,),
        ).fetchall()
    result = dict(row)
    result["relevance_rate"] = (result["relevant"] / result["diagnostics"] * 100) if result["diagnostics"] else 0
    result["evidence_sufficiency_rate"] = (result["sufficient"] / result["diagnostics"] * 100) if result["diagnostics"] else 0
    result["clean_rate"] = (result["clean"] / result["diagnostics"] * 100) if result["diagnostics"] else 0
    result["classes"] = [dict(item) for item in classes]
    return result


def recent_rag_diagnostics(state, days=30, limit=100):
    """
    Function: recent_rag_diagnostics
    Purpose: Execute the recent rag diagnostics operation.
    Inputs:
            state (value): Caller-provided input.
            days (value): Caller-provided input.
            limit (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _admin(state)
    since = time.time() - max(1, int(days)) * 86400
    with database.connect() as db:
        rows = db.execute(
            """SELECT rd.interaction_id, rd.created_at, ai.assistant_mode,
                      ai.project_id, rd.failure_class, rd.retrieval_relevant,
                      rd.evidence_sufficient, rd.validation_status, rd.result_count,
                      rd.source_count, rd.structured_count, rd.context_truncated, rd.notes,
                      rd.query_intent, rd.query_scope, rd.query_entity,
                      rd.query_follow_up, rd.subquery_count, rd.conflict_count
               FROM rag_diagnostics rd JOIN ai_interactions ai
                 ON ai.id = rd.interaction_id
               WHERE rd.created_at >= datetime(?, 'unixepoch')
               ORDER BY rd.id DESC LIMIT ?""",
            (since, max(1, min(int(limit), 500))),
        ).fetchall()
    return [dict(row) for row in rows]


def _owned_successful_interaction(interaction_id, user):
    """
    Function: _owned_successful_interaction
    Purpose: Execute the  owned successful interaction operation.
    Inputs:
            interaction_id (value): Caller-provided input.
            user (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    current = auth.current_user(user)
    if not current:
        raise PermissionError("Please sign in to leave feedback.")
    with database.connect() as db:
        row = db.execute(
            """SELECT user_id, project_id, success FROM ai_interactions WHERE id = ?""",
            (interaction_id,),
        ).fetchone()
    if not row or row["user_id"] != current["id"] or not row["success"]:
        raise PermissionError("Feedback is available only for your completed answers.")
    if row["project_id"] and not access.can_access_project(user, row["project_id"]):
        raise PermissionError("You no longer have access to this project.")


def get_feedback(interaction_id, *, user):
    """
    Function: get_feedback
    Purpose: Execute the get feedback operation.
    Inputs:
            interaction_id (value): Caller-provided input.
            user (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _owned_successful_interaction(interaction_id, user)
    with database.connect() as db:
        row = db.execute(
            "SELECT rating, comment FROM response_feedback WHERE interaction_id = ?",
            (interaction_id,),
        ).fetchone()
    return dict(row) if row else None


def add_feedback(interaction_id, rating, comment=None, *, user):
    """
    Function: add_feedback
    Purpose: Execute the add feedback operation.
    Inputs:
            interaction_id (value): Caller-provided input.
            rating (value): Caller-provided input.
            comment (value): Caller-provided input.
            user (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _owned_successful_interaction(interaction_id, user)
    if type(rating) is not int or rating not in {-1, 1}:
        raise ValueError("Choose Helpful or Not Helpful.")
    if comment is not None:
        if not isinstance(comment, str) or len(comment) > MAX_FEEDBACK_COMMENT_LENGTH:
            raise ValueError(f"Feedback must be at most {MAX_FEEDBACK_COMMENT_LENGTH} characters.")
        comment = comment.strip()
    with database.connect() as db:
        db.execute(
            """INSERT INTO response_feedback(interaction_id, rating, comment, created_at, created_epoch)
               VALUES (?, ?, COALESCE(?, ''), ?, ?)
               ON CONFLICT(interaction_id) DO UPDATE SET
                 rating = excluded.rating,
                 comment = excluded.comment,
                 created_at = excluded.created_at""",
            (interaction_id, rating, comment, datetime.now(timezone.utc).isoformat(timespec="seconds"), time.time()),
        )
    access.record_audit(user, "ai_response_feedback_recorded",
                        details={"interaction_id": interaction_id, "rating": rating})


def _admin(state):
    """
    Function: _admin
    Purpose: Execute the  admin operation.
    Inputs:
            state (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return access.require_admin(state)


def dashboard_metrics(state, days=30):
    """
    Function: dashboard_metrics
    Purpose: Execute the dashboard metrics operation.
    Inputs:
            state (value): Caller-provided input.
            days (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _admin(state)
    since = time.time() - max(1, int(days)) * 86400
    with database.connect() as db:
        row = db.execute(
            """SELECT COUNT(*) requests,
                      COALESCE(SUM(success), 0) successful,
                      COUNT(*) - COALESCE(SUM(success), 0) failed,
                      COALESCE(AVG(CASE WHEN success = 1 THEN latency_ms END), 0) avg_latency,
                      COALESCE(AVG(CASE WHEN success = 1 THEN input_tokens END), 0) avg_input_tokens,
                      COALESCE(AVG(CASE WHEN success = 1 THEN output_tokens END), 0) avg_output_tokens
               FROM ai_interactions WHERE created_epoch >= ?""",
            (since,),
        ).fetchone()
        feedback = db.execute(
            """SELECT COALESCE(SUM(CASE WHEN rf.rating = 1 THEN 1 ELSE 0 END), 0) helpful,
                      COALESCE(SUM(CASE WHEN rf.rating = -1 THEN 1 ELSE 0 END), 0) not_helpful
               FROM response_feedback rf JOIN ai_interactions ai ON ai.id = rf.interaction_id
               WHERE ai.created_epoch >= ?""",
            (since,),
        ).fetchone()
        evaluation = db.execute(
            """SELECT COALESCE(AVG(e.grounded_accuracy), 0) grounded_accuracy,
                      COALESCE(AVG(e.relevance), 0) relevance,
                      COALESCE(AVG(e.usability), 0) usability,
                      COALESCE(SUM(e.hallucination_detected), 0) hallucinations,
                      COUNT(e.id) evaluations
               FROM ai_evaluations e JOIN ai_interactions ai ON ai.id = e.interaction_id
               WHERE ai.created_epoch >= ?""",
            (since,),
        ).fetchone()
    return {**dict(row), **dict(feedback), **dict(evaluation)}


def latency_series(state, days=30):
    """
    Function: latency_series
    Purpose: Execute the latency series operation.
    Inputs:
            state (value): Caller-provided input.
            days (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _admin(state)
    since = time.time() - max(1, int(days)) * 86400
    with database.connect() as db:
        rows = db.execute(
            """SELECT created_at, latency_ms, assistant_mode
               FROM ai_interactions WHERE created_epoch >= ? AND success = 1
               ORDER BY created_epoch""",
            (since,),
        ).fetchall()
    return [dict(row) for row in rows]


def recent_errors(state, limit=25):
    """
    Function: recent_errors
    Purpose: Execute the recent errors operation.
    Inputs:
            state (value): Caller-provided input.
            limit (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _admin(state)
    with database.connect() as db:
        rows = db.execute(
            """SELECT created_at, assistant_mode, error_type, http_status, latency_ms
               FROM ai_interactions WHERE success = 0
               ORDER BY id DESC LIMIT ?""",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
    return [dict(row) for row in rows]


def recent_feedback(state, days=30, limit=50):
    """
    Function: recent_feedback
    Purpose: Execute the recent feedback operation.
    Inputs:
            state (value): Caller-provided input.
            days (value): Caller-provided input.
            limit (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _admin(state)
    since = time.time() - max(1, int(days)) * 86400
    with database.connect() as db:
        rows = db.execute(
            """SELECT rf.interaction_id, rf.created_at, ai.user_role,
                      ai.assistant_mode, ai.project_id, rf.rating, rf.comment
               FROM response_feedback rf JOIN ai_interactions ai ON ai.id = rf.interaction_id
               WHERE ai.created_epoch >= ? ORDER BY rf.created_epoch DESC LIMIT ?""",
            (since, max(1, min(int(limit), 100)),),
        ).fetchall()
    return [dict(row) for row in rows]


def recent_successful_interactions(state, limit=50):
    """
    Function: recent_successful_interactions
    Purpose: Execute the recent successful interactions operation.
    Inputs:
            state (value): Caller-provided input.
            limit (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _admin(state)
    with database.connect() as db:
        rows = db.execute(
            """SELECT ai.id, ai.created_at, ai.user_role, ai.project_id,
                      ai.assistant_mode, ai.prompt_name, ai.prompt_version,
                      ai.latency_ms, COALESCE(ap.question_text, '') question_text,
                      COALESCE(ai.response_text, '') response_text
               FROM ai_interactions ai LEFT JOIN ai_prompt_archive ap
                 ON ap.interaction_id = ai.id
               WHERE ai.success = 1 ORDER BY ai.id DESC LIMIT ?""",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
    return [dict(row) for row in rows]


def add_evaluation(state, interaction_id, test_name, relevance, grounded_accuracy, hallucination_detected, notes="", usability=3):
    """
    Function: add_evaluation
    Purpose: Execute the add evaluation operation.
    Inputs:
            state (value): Caller-provided input.
            interaction_id (value): Caller-provided input.
            test_name (value): Caller-provided input.
            relevance (value): Caller-provided input.
            grounded_accuracy (value): Caller-provided input.
            hallucination_detected (value): Caller-provided input.
            notes (value): Caller-provided input.
            usability (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _admin(state)
    if not str(test_name or "").strip():
        raise ValueError("Test case name is required.")
    if (
        not 1 <= int(relevance) <= 5
        or not 1 <= int(grounded_accuracy) <= 5
        or not 1 <= int(usability) <= 5
    ):
        raise ValueError("Evaluation scores must be between 1 and 5.")
    with database.connect() as db:
        if not db.execute("SELECT 1 FROM ai_interactions WHERE id = ? AND success = 1", (interaction_id,)).fetchone():
            raise ValueError("The selected interaction is not a completed answer.")
        db.execute(
            """INSERT INTO ai_evaluations
               (interaction_id, test_name, relevance, grounded_accuracy, usability,
                hallucination_detected, evaluator_notes, created_at, created_epoch)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (interaction_id, str(test_name).strip(), int(relevance), int(grounded_accuracy),
             int(usability), int(bool(hallucination_detected)), str(notes or "").strip(),
             datetime.now(timezone.utc).isoformat(timespec="seconds"), time.time()),
        )
    access.record_audit(state, "ai_response_evaluated",
                        details={"interaction_id": interaction_id,
                                 "test_name": str(test_name).strip()[:120],
                                 "hallucination_detected": bool(hallucination_detected)})


def prompt_analytics(state, days=30, limit=500):
    """
    Function: prompt_analytics
    Purpose: Execute the prompt analytics operation.
    Inputs:
            state (value): Caller-provided input.
            days (value): Caller-provided input.
            limit (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _admin(state)
    since = time.time() - max(1, int(days)) * 86400
    with database.connect() as db:
        rows = db.execute(
            """SELECT ai.id, ai.created_at, ai.user_role, ai.project_id,
                      ai.assistant_mode, ap.question_text, ai.request_chars,
                      ai.latency_ms, ai.success
               FROM ai_interactions ai JOIN ai_prompt_archive ap
                 ON ap.interaction_id = ai.id
               WHERE ai.created_epoch >= ? AND ap.question_text <> ''
               ORDER BY ai.created_epoch DESC LIMIT ?""",
            (since, max(1, min(int(limit), 2000)),),
        ).fetchall()
    return [dict(row) for row in rows]


def summarise_prompt_terms(rows, maximum=15):
    """
    Function: summarise_prompt_terms
    Purpose: Execute the summarise prompt terms operation.
    Inputs:
            rows (value): Caller-provided input.
            maximum (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    stop_words = {
        "a", "about", "an", "and", "are", "can", "do", "for", "from", "how",
        "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "the",
        "this", "to", "what", "when", "where", "which", "who", "with", "would",
        "you", "your", "our", "we", "capstone", "project",
    }
    terms = Counter()
    for row in rows:
        for word in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", row.get("question_text", "").lower()):
            if word not in stop_words:
                terms[word] += 1
    return terms.most_common(maximum)


def classify_prompt_topic(question):
    """Return an explainable administrator-facing intent category."""
    text = str(question or "").casefold()
    for topic, keywords in PROMPT_TOPIC_RULES:
        if any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords):
            return topic
    return "Other project information"


def summarise_prompt_topics(rows, maximum=10):
    """Group captured questions into clear topics with counts and examples."""
    grouped = {}
    for row in rows:
        topic = classify_prompt_topic(row.get("question_text", ""))
        entry = grouped.setdefault(topic, {"Topic": topic, "Questions": 0, "Example question": ""})
        entry["Questions"] += 1
        question = " ".join(str(row.get("question_text", "")).split())
        if question and (not entry["Example question"] or len(question) < len(entry["Example question"])):
            entry["Example question"] = question[:140]
    total = sum(item["Questions"] for item in grouped.values())
    topics = sorted(grouped.values(), key=lambda item: (-item["Questions"], item["Topic"]))
    result = []
    for item in topics[:max(1, int(maximum))]:
        result.append({
            **item,
            "Share": f"{(item['Questions'] / total * 100):.1f}%" if total else "0.0%",
        })
    return result


def _optional_user_id(state):
    """
    Function: _optional_user_id
    Purpose: Execute the  optional user id operation.
    Inputs:
            state (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    if not state:
        return None
    try:
        user = auth.current_user(state)
    except Exception:
        return None
    return user.get("id") if user else None


def log_api_service_event(*, state=None, stage, latency_ms, success, http_status=None,
                          error_type=None, input_tokens=None, output_tokens=None,
                          total_tokens=None):
    """Persist provider/API health telemetry without storing prompts or answers."""
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with database.connect() as db:
        cursor = db.execute(
            """INSERT INTO api_service_events
               (created_at, created_epoch, user_id, stage, latency_ms, success,
                http_status, error_type, input_tokens, output_tokens, total_tokens)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (created_at, time.time(), _optional_user_id(state), str(stage),
             max(0, int(latency_ms)), int(bool(success)), http_status, error_type,
             input_tokens, output_tokens, total_tokens),
        )
        return cursor.lastrowid


def record_retrieval_event(*, state=None, project_id=None, question="", result_count=0,
                           vector_result_count=0, top_score=0, retrieval_latency_ms=0,
                           planner_success=False):
    """Record retrieval quality signals without retaining the query text."""
    with database.connect() as db:
        db.execute(
            """INSERT INTO retrieval_events
               (created_at, created_epoch, user_id, project_id, query_hash,
                query_chars, result_count, vector_result_count, top_score,
                retrieval_latency_ms, planner_success, no_match)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), time.time(),
             _optional_user_id(state), project_id, hash_request(question), len(str(question or "")),
             int(result_count), int(vector_result_count), float(top_score or 0),
             max(0, int(retrieval_latency_ms)), int(bool(planner_success)), int(not result_count)),
        )


def api_service_metrics(state, days=30):
    """
    Function: api_service_metrics
    Purpose: Execute the api service metrics operation.
    Inputs:
            state (value): Caller-provided input.
            days (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _admin(state)
    since = time.time() - max(1, int(days)) * 86400
    with database.connect() as db:
        row = db.execute(
            """SELECT COUNT(*) requests, COALESCE(SUM(success), 0) successful,
                      COUNT(*) - COALESCE(SUM(success), 0) failed,
                      COALESCE(AVG(latency_ms), 0) avg_latency,
                      COALESCE(AVG(input_tokens), 0) avg_input_tokens,
                      COALESCE(AVG(output_tokens), 0) avg_output_tokens,
                      COALESCE(SUM(total_tokens), 0) total_tokens
                 FROM api_service_events WHERE created_epoch >= ?""", (since,)
        ).fetchone()
        stages = db.execute(
            """SELECT stage, COUNT(*) requests, COALESCE(SUM(success), 0) successful,
                      COALESCE(AVG(latency_ms), 0) avg_latency
                 FROM api_service_events WHERE created_epoch >= ?
                 GROUP BY stage ORDER BY requests DESC""", (since,)
        ).fetchall()
    return {**dict(row), "stages": [dict(item) for item in stages]}


def retrieval_quality_metrics(state, days=30):
    """
    Function: retrieval_quality_metrics
    Purpose: Execute the retrieval quality metrics operation.
    Inputs:
            state (value): Caller-provided input.
            days (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    _admin(state)
    since = time.time() - max(1, int(days)) * 86400
    with database.connect() as db:
        row = db.execute(
            """SELECT COUNT(*) searches, COALESCE(SUM(no_match), 0) no_match,
                      COALESCE(AVG(result_count), 0) avg_results,
                      COALESCE(AVG(vector_result_count), 0) avg_vector_results,
                      COALESCE(AVG(top_score), 0) avg_top_score,
                      COALESCE(AVG(retrieval_latency_ms), 0) avg_latency,
                      COALESCE(SUM(planner_success), 0) planner_success
                 FROM retrieval_events WHERE created_epoch >= ?""", (since,)
        ).fetchone()
        daily = db.execute(
            """SELECT substr(created_at, 1, 10) day, COUNT(*) searches,
                      COALESCE(SUM(no_match), 0) no_match,
                      COALESCE(AVG(top_score), 0) avg_top_score
                 FROM retrieval_events WHERE created_epoch >= ?
                 GROUP BY day ORDER BY day""", (since,)
        ).fetchall()
    result = dict(row)
    result["no_match_rate"] = (result["no_match"] / result["searches"] * 100) if result["searches"] else 0
    result["daily"] = [dict(item) for item in daily]
    return result
