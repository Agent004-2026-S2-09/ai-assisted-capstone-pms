## File: tools/rigorous_student_frontend_test.py
## Date Created: 20-10-2026
## Description: Resumable student-facing Streamlit RAG coverage benchmark.

"""Run broad RAG coverage through the authenticated Streamlit widget path.

The benchmark is deliberately corpus-driven. It does not add question-specific
answer rules to the application: questions are generated from the current
indexed sources and project sections, submitted through AppTest's rendered
login/project/chat widgets, and linked to the application's persisted audit
records. A checkpoint makes the long run resumable.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app
from app_modules import database

USER = "rag.e2e.student@local"
PASSWORD = "Rag-E2E-Student-2026!"
PROJECT_ID = "ai-assisted-capstone-project-assistant"
PROJECT_LABEL = "AI-assisted Capstone Project Assistant (2026-S2-09)"
RUN_NAME = "rigorous_student_frontend_rag_2026-10-20"
OUT = ROOT / "docs" / "test" / "rigorous_student_frontend_test.json"
CHECKPOINT = ROOT / "docs" / "test" / ".rigorous_student_frontend_test.checkpoint.json"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def words(text):
    stop = set(getattr(app, "STOP_WORDS", set())) | {
        "document", "documents", "information", "knowledge", "capstone",
        "student", "students", "university", "provide", "detailed", "explain",
        "following", "material", "section", "project", "current", "record",
        "records", "please", "answer", "question", "what", "which", "should",
    }
    return [w.casefold() for w in re.findall(r"[A-Za-z][A-Za-z0-9/-]{3,}", str(text or "")) if w.casefold() not in stop]


def topic(text, limit=8):
    counts = Counter(words(text))
    return " ".join(w for w, _ in counts.most_common(limit)) or "the documented requirements"


def load_runner():
    import importlib.util
    path = ROOT / "tools" / "final_system_test.py"
    spec = importlib.util.spec_from_file_location("final_system_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def questions():
    runner = load_runner()
    general = runner.general_documents()
    grouped = {}
    for item in general:
        if item.get("source") and item.get("text"):
            grouped.setdefault(str(item["source"]), []).append(item)
    styles = [
        "What is the purpose and main message of",
        "What exact dates, numbers, roles or definitions are stated in",
        "What requirements or steps does",
        "What practical actions should a Capstone student take from",
        "What risks, cautions or exceptions are identified by",
        "What responsibilities or stakeholders are described in",
        "What evidence, deliverables or outcomes does",
        "What does this source explicitly leave unspecified, and what should be verified",
        "How should the guidance in this source be applied during a Capstone project",
        "Give a grounded student briefing on the most important information in",
    ]
    result = []
    n = 0
    for source in sorted(grouped, key=str.casefold):
        item = grouped[source][0]
        title = Path(source).stem
        subject = topic(item.get("text", ""))
        for style in styles:
            n += 1
            result.append({
                "number": n, "scope": "general", "category": "per-document",
                "source_group": [source],
                "question": f"{style} '{title}' concerning {subject}? Use only authorised evidence, preserve exact facts, and state when the source does not specify something.",
            })

    projects, records, _ = runner.project_data()
    project_records = [r for r in records if r.get("project_id") == PROJECT_ID]
    sections = ["teams", "meetings", "milestones", "Gantt chart", "task board", "knowledge base"]
    section_items = {s: [r for r in project_records if r.get("section") == s] for s in sections}
    section_styles = [
        "Summarise every current entry in the",
        "Which exact names, dates, statuses and responsibilities appear in the",
        "What delivery implications follow from the",
        "What is complete, active, blocked or unspecified in the",
        "What should a student verify next using the",
        "Identify dependencies, risks and actions supported by the",
        "Compare the entries in the",
        "What facts in the",
        "How does the",
        "Give a complete evidence-grounded briefing on the",
    ]
    for section in sections:
        item = section_items[section][0] if section_items[section] else {"text": "No records are currently available."}
        subject = topic(item.get("text", ""))
        for style in section_styles:
            n += 1
            result.append({
                "number": n, "scope": "project", "category": f"project-section:{section}",
                "source_group": [str(x.get("source", "")) for x in section_items[section]],
                "question": f"{style} {section} section in the selected project, especially {subject}. Preserve exact values, distinguish database facts from document facts, and do not infer missing records.",
            })

    # 50 general cross-document questions.
    sources = sorted(grouped, key=str.casefold)
    for i in range(50):
        left = sources[i % len(sources)]
        right = sources[(i * 7 + 11) % len(sources)]
        if left == right:
            right = sources[(i + 1) % len(sources)]
        n += 1
        result.append({
            "number": n, "scope": "general", "category": "cross-document-general",
            "source_group": [left, right],
            "question": f"Compare '{Path(left).stem}' and '{Path(right).stem}' for a student planning Capstone work. What do they jointly say about requirements, roles, dates, risks or actions; where do they differ; and what remains unspecified? Cite the evidence conceptually without inventing facts.",
        })

    # 50 project cross-section/document questions.
    project_sources = [str(x.get("source", "")) for x in project_records if x.get("source")]
    for i in range(50):
        left = project_sources[i % len(project_sources)]
        right = project_sources[(i * 5 + 3) % len(project_sources)]
        if left == right:
            right = project_sources[(i + 1) % len(project_sources)]
        n += 1
        result.append({
            "number": n, "scope": "project", "category": "cross-document-project",
            "source_group": [left, right],
            "question": f"In the selected project, reconcile the authorised records represented by '{Path(left).stem}' and '{Path(right).stem}'. Explain the current status, responsibilities, dates, dependencies and next actions supported by both sources, and explicitly flag conflicts or missing information.",
        })
    return result, len(grouped), len(sections)


def choose_scope(at, scope):
    selector = next(x for x in at.selectbox if x.label == "Current project")
    target = "General Capstone" if scope == "general" else PROJECT_LABEL
    if selector.value != target:
        selector.select(target).run(timeout=180)
    if at.exception:
        raise RuntimeError(str(at.exception))


def answer_text(at):
    for message in reversed(list(at.chat_message)):
        if str(getattr(message, "name", "") or "").casefold() in {"assistant", "ai", "agentaus ai"}:
            return "\n".join(str(item.value) for item in message.markdown)
    return "\n".join(str(item.value) for item in at.markdown[-8:])


def latest(question):
    with database.connect() as db:
        row = db.execute(
            """SELECT ai.id, ai.success, ai.response_chars, ai.response_text,
                      ai.project_id, ap.question_text, rd.validation_status,
                      rd.failure_class, rd.source_count, rd.evidence_sufficient,
                      rd.retrieval_relevant
               FROM ai_interactions ai
               LEFT JOIN ai_prompt_archive ap ON ap.interaction_id = ai.id
               LEFT JOIN rag_diagnostics rd ON rd.interaction_id = ai.id
               WHERE ai.user_id = (SELECT id FROM users WHERE username = ?)
                 AND ap.question_text = ?
               ORDER BY ai.id DESC LIMIT 1""", (USER, question)
        ).fetchone()
    return dict(row) if row else None


def score(row, response, item):
    clean = app.clean_ai_response(response or "")
    expected = set(item.get("source_group", []))
    source_count = int(row.get("source_count") or 0) if row else 0
    success = bool(row and row.get("success"))
    validation = str(row.get("validation_status") or "") if row else ""
    failure = str(row.get("failure_class") or "") if row else "missing"
    # This is an automated triage score, not a claim of semantic proof. It is
    # intentionally conservative: semantic review is required for flagged rows.
    grounded = success and len(clean) >= 80 and validation in {"validated", "not_required", ""} and failure in {"none", ""}
    if item["scope"] == "general" and expected and source_count < min(1, len(expected)):
        grounded = False
    if item["scope"] == "project" and not row:
        grounded = False
    return {
        "automated_pass": bool(grounded),
        "relevance": 5 if success and clean else 1,
        "grounded_accuracy": 5 if grounded else (3 if success else 1),
        "hallucination_detected": 0 if grounded else 1,
        "usability": 5 if len(clean) >= 80 else (2 if clean else 1),
        "notes": f"Automated triage: success={success}; validation={validation or 'missing'}; failure={failure}; source_count={source_count}. Semantic review required for any flagged result.",
    }


def persist_evaluation(interaction_id, scored):
    if not interaction_id:
        return
    with database.connect() as db:
        db.execute(
            """INSERT INTO ai_evaluations
               (interaction_id, test_name, relevance, grounded_accuracy,
                hallucination_detected, evaluator_notes, created_at,
                created_epoch, usability)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (interaction_id, RUN_NAME, scored["relevance"], scored["grounded_accuracy"],
             scored["hallucination_detected"], scored["notes"], now(), time.time(), scored["usability"]),
        )


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Optional smoke limit; default runs all generated questions")
    args = parser.parse_args()
    all_questions, document_count, section_count = questions()
    if args.limit:
        all_questions = all_questions[:args.limit]
    rows = json.loads(CHECKPOINT.read_text()) if CHECKPOINT.exists() else []
    done = {int(x["number"]) for x in rows if x.get("interaction_id")}
    at = AppTest.from_string("import app\napp.main()", default_timeout=180).run()
    if at.exception:
        raise RuntimeError(str(at.exception))
    at.text_input[0].input(USER)
    at.text_input[1].input(PASSWORD)
    at.button[0].click().run(timeout=180)
    if at.exception or not at.chat_input:
        raise RuntimeError(f"Student frontend login failed: {at.exception}")
    current_scope = None
    started = now()
    for item in all_questions:
        if item["number"] in done:
            continue
        try:
            if current_scope != item["scope"]:
                choose_scope(at, item["scope"])
                current_scope = item["scope"]
            started_at = time.perf_counter()
            at.chat_input[0].set_value(item["question"]).run(timeout=240)
            if at.exception:
                raise RuntimeError(str(at.exception))
            response = answer_text(at)
            saved = latest(item["question"])
            scored = score(saved, response, item)
            persist_evaluation(saved.get("id") if saved else None, scored)
            rows.append({**item, "interaction_id": saved.get("id") if saved else None,
                         "response_chars": len(response), "success": bool(saved and saved.get("success")),
                         "validation_status": saved.get("validation_status") if saved else None,
                         "failure_class": saved.get("failure_class") if saved else "missing",
                         "source_count": saved.get("source_count") if saved else 0,
                         "evidence_sufficient": saved.get("evidence_sufficient") if saved else 0,
                         "elapsed_seconds": round(time.perf_counter() - started_at, 2),
                         "score": scored, "completed_at": now()})
        except Exception as error:
            rows.append({**item, "interaction_id": None, "success": False, "response_chars": 0,
                         "failure_class": type(error).__name__, "error": str(error)[:500],
                         "score": {"automated_pass": False, "relevance": 1, "grounded_accuracy": 1,
                                   "hallucination_detected": 1, "usability": 1, "notes": str(error)[:500]},
                         "completed_at": now()})
        CHECKPOINT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"completed": len(rows), "total": len(all_questions), "number": item["number"],
                          "passed": bool(rows[-1].get("score", {}).get("automated_pass"))}), flush=True)
    passed = sum(bool(x.get("score", {}).get("automated_pass")) for x in rows)
    payload = {"run": RUN_NAME, "started": started, "finished": now(),
               "student_account": USER, "project_id": PROJECT_ID,
               "general_document_count": document_count, "project_section_count": section_count,
               "target_questions": len(all_questions), "questions_recorded": len(rows),
               "automated_pass": passed, "automated_review": len(rows) - passed, "results": rows}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("target_questions", "questions_recorded", "automated_pass", "automated_review", "general_document_count", "project_section_count")}))


if __name__ == "__main__":
    run()
