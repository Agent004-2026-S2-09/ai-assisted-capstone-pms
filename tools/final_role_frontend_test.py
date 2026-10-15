"""Run the final role-based AI benchmark through Streamlit's frontend widgets.

The runner intentionally uses AppTest for the same widget/form path a browser
uses, while checking the persisted SQLite interaction after every response.
It is invoked once per role so each role has an independent frontend session.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app
from app_modules import database


ROLE_USERS = {
    "student": "final.test.student@qa.local",
    "mentor": "final.test.mentor@qa.local",
    "convenor": "final.test.convenor@qa.local",
    "administrator": "final.test.admin@qa.local",
}
PROJECT_ID = "ai-assisted-capstone-project-assistant"


def load_runner():
    path = ROOT / "tools" / "final_system_test.py"
    spec = importlib.util.spec_from_file_location("final_system_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def db_user(username: str) -> dict:
    with database.connect() as db:
        row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        raise RuntimeError(f"Final test account is missing: {username}")
    return dict(row)


def latest_interaction(user_id: int, project_id: str | None) -> dict | None:
    with database.connect() as db:
        row = db.execute(
            """SELECT ai.*, ap.question_text, rd.validation_status, rd.failure_class,
                      rd.source_count, rd.evidence_sufficient
               FROM ai_interactions ai
               LEFT JOIN ai_prompt_archive ap ON ap.interaction_id = ai.id
               LEFT JOIN rag_diagnostics rd ON rd.interaction_id = ai.id
               WHERE ai.user_id = ? AND (ai.project_id IS ? OR ai.project_id = ?)
               ORDER BY ai.id DESC LIMIT 1""",
            (user_id, project_id, project_id),
        ).fetchone()
    return dict(row) if row else None


def answer_text(at: AppTest) -> str:
    messages = list(at.chat_message)
    for message in reversed(messages):
        name = str(getattr(message, "name", "") or "").casefold()
        if name in {"assistant", "ai", "agentaus ai"}:
            return "\n".join(str(item.value) for item in message.markdown)
    return "\n".join(str(item.value) for item in at.markdown[-8:])


def login(role: str, password: str) -> AppTest:
    at = AppTest.from_string("import app\napp.main()", default_timeout=180).run()
    if at.exception:
        raise RuntimeError(f"Initial frontend render failed: {at.exception}")
    at.text_input[0].input(ROLE_USERS[role])
    at.text_input[1].input(password)
    at.button[0].click().run(timeout=180)
    if at.exception:
        raise RuntimeError(f"Frontend login failed for {role}: {at.exception}")
    return at


def select_scope(at: AppTest, scope: str) -> None:
    selector = next(widget for widget in at.selectbox if widget.label == "Current project")
    value = "General Capstone"
    if scope == "project":
        selector_options = list(selector.options)
        value = next(
            (option for option in selector_options if str(option).startswith("AI-assisted Capstone Project Assistant (")),
            "",
        )
        if not value:
            raise RuntimeError(f"Authorised project is not available in the frontend: {selector_options}")
    if selector.value != value:
        selector.select(value).run(timeout=180)
    if at.exception:
        raise RuntimeError(f"Project selection failed: {at.exception}")
    # ChatInput does not expose its label as a public AppTest attribute.  The
    # sidebar selection leaves the assistant page active for these sessions;
    # use the first rendered chat input directly below.


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=sorted(ROLE_USERS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    password = os.environ.get("FINAL_TEST_PASSWORD")
    if not password:
        raise RuntimeError("FINAL_TEST_PASSWORD must be supplied through the environment")

    runner = load_runner()
    documents = runner.general_documents()
    _, records, _ = runner.project_data()
    project_records = [item for item in records if item.get("project_id") == PROJECT_ID]
    questions = [
        *runner.make_general_questions(documents, 50),
        *runner.make_project_questions(project_records, 50),
    ]
    if len(questions) != 100:
        raise RuntimeError(f"Expected 100 questions, generated {len(questions)}")
    if args.offset < 0 or args.limit < 1 or args.offset + args.limit > len(questions):
        raise RuntimeError("Question slice is outside the role's 100-question batch")
    questions = questions[args.offset:args.offset + args.limit]

    user = db_user(ROLE_USERS[args.role])
    at = login(args.role, password)
    # Each independent slice contains one scope (general or project) except
    # the unsliced default run. Select it once; repeating a selectbox event
    # after every chat rerun creates a stale widget state in AppTest.
    if args.offset >= 50:
        select_scope(at, "project")
    elif args.offset + args.limit <= 50:
        select_scope(at, "general")
    results = []
    for local_number, item in enumerate(questions, 1):
        number = args.offset + local_number
        scope = "general" if number <= 50 else "project"
        question = item["question"]
        started = time.perf_counter()
        record = {
            "role": args.role,
            "number": number,
            "scope": scope,
            "category": item.get("category"),
            "question": question,
        }
        try:
            chat = at.chat_input[0]
            chat.set_value(question).run(timeout=240)
            if at.exception:
                raise RuntimeError(str(at.exception))
            saved = latest_interaction(user["id"], None if scope == "general" else PROJECT_ID)
            response = answer_text(at)
            record.update({
                "response": response,
                "elapsed_seconds": round(time.perf_counter() - started, 2),
                "saved_interaction_id": saved.get("id") if saved else None,
                "saved_question_matches": bool(saved and saved.get("question_text") == question),
                "saved_response_chars": int(saved.get("response_chars", 0)) if saved else 0,
                "saved_success": bool(saved and saved.get("success")),
                "saved_project_id": saved.get("project_id") if saved else None,
                "validation_status": saved.get("validation_status") if saved else None,
                "failure_class": saved.get("failure_class") if saved else None,
                "source_count": saved.get("source_count") if saved else None,
                "evidence_sufficient": saved.get("evidence_sufficient") if saved else None,
                "frontend_error": None,
            })
        except Exception as error:
            record.update({
                "response": "",
                "elapsed_seconds": round(time.perf_counter() - started, 2),
                "saved_interaction_id": None,
                "saved_question_matches": False,
                "saved_response_chars": 0,
                "saved_success": False,
                "saved_project_id": None,
                "validation_status": None,
                "failure_class": None,
                "source_count": None,
                "evidence_sufficient": None,
                "frontend_error": repr(error),
            })
        results.append(record)
        if local_number % 10 == 0:
            print(json.dumps({"role": args.role, "completed": local_number, "offset": args.offset}), flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"role": args.role, "offset": args.offset, "questions": len(results), "results": results}, indent=2), encoding="utf-8")
    print(json.dumps({
        "role": args.role,
        "questions": len(results),
        "frontend_errors": sum(bool(item["frontend_error"]) for item in results),
        "saved": sum(bool(item["saved_interaction_id"]) for item in results),
        "successful": sum(bool(item["saved_success"]) for item in results),
        "output": str(args.output),
    }), flush=True)


if __name__ == "__main__":
    main()
