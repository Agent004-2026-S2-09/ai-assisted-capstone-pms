## File: tools/project_specific_100.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Run 100 live, project-scoped questions for one project.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Run 100 live, project-scoped questions for one project."""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app  # noqa: E402
from app_modules import auth, database  # noqa: E402
from qa_100_questions import Case, _configure_evaluation_access, _load_corpus, _retrieve, _restore_evaluation_access, _check_answer, write_report  # noqa: E402
import qa_100_questions as qa  # noqa: E402

PROJECT_ID = os.environ.get("PROJECT_ID", "ai-assisted-capstone-project-assistant")
TEST_USERNAME = os.environ.get("TEST_USERNAME", "")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "")
IMPERSONATE_USER_ID = os.environ.get("IMPERSONATE_USER_ID", "")
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "project_specific_100")
REPORT_PATH = ROOT / f"docs/{OUTPUT_PREFIX}_report.docx"
JSON_PATH = ROOT / f"docs/{OUTPUT_PREFIX}_results.json"


def load_project():
    """
    Function: load_project
    Purpose: Execute the load project operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    with sqlite3.connect(ROOT / "project_data/capstone.sqlite3") as db:
        return app.Project.from_dict(json.loads(db.execute("SELECT profile FROM projects WHERE id = ?", (PROJECT_ID,)).fetchone()[0]))


def load_schedule():
    """
    Function: load_schedule
    Purpose: Execute the load schedule operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    with sqlite3.connect(ROOT / "project_data/capstone.sqlite3") as db:
        gantt = json.loads(db.execute("SELECT plan_json FROM gantt_plans WHERE project_id = ?", (PROJECT_ID,)).fetchone()[0])
        kanban = json.loads(db.execute("SELECT board_json FROM kanban_boards WHERE project_id = ?", (PROJECT_ID,)).fetchone()[0])
    return gantt["tasks"], kanban["cards"]


def build_cases(project, gantt_tasks, cards):
    """
    Function: build_cases
    Purpose: Execute the build cases operation.
    Inputs:
            project (value): Caller-provided input.
            gantt_tasks (value): Caller-provided input.
            cards (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    cases = []
    number = 0
    def add(question, expected, category, structured=True):
        """
        Function: add
        Purpose: Execute the add operation.
        Inputs:
                question (value): Caller-provided input.
                expected (value): Caller-provided input.
                category (value): Caller-provided input.
                structured (value): Caller-provided input.
        Returns:
                The function result, or None where no value is returned.
        Raises/side effects:
                Existing validation, authorization, persistence, and error handling apply.
        """
        nonlocal number
        number += 1
        cases.append(Case(number, "Project-specific", question, tuple((x,) for x in expected), category, structured=structured))

    add("What is the selected project's name and project code?", [project.name, project.code], "project identity")
    add("Who sponsors the selected project?", [project.sponsor], "project identity")
    add("Who is recorded as the mentor for the selected project?", [project.mentor], "project identity")
    add("What is the current status of the selected project?", [project.status], "project identity")
    manager = next((m for m in project.team if "manager" in str(m.get("role", "")).casefold()), project.team[0])
    quality = next((m for m in project.team if "quality" in str(m.get("role", "")).casefold()), project.team[min(1, len(project.team)-1)])
    developers = [m for m in project.team if "developer" in str(m.get("role", "")).casefold() or "tech lead" in str(m.get("role", "")).casefold()]
    add("Who is the project manager and what role is recorded for that person?", [manager.get("name", ""), manager.get("role", "")], "team")
    add("Who is the Quality and AI Lead or equivalent quality lead?", [quality.get("name", ""), quality.get("role", "")], "team")
    add("Which people are recorded as Developer, Tech Lead, Firmware, App, Calibration, Testing, or equivalent technical team members?", [m.get("name", "") for m in (developers or project.team[2:])], "team")
    add("How many meetings and milestones are currently recorded for this project?", [str(len(project.meetings)), str(len(project.milestones))], "project records")
    add("What is the project sponsor and what is the project's current status?", [project.sponsor, project.status], "project summary")
    add("List the named team members and their recorded responsibilities.", [m.get("name", "") for m in project.team], "team list")

    for meeting in project.meetings:
        title, date = meeting.get("title", ""), meeting.get("date", "")
        add(f"For the project meeting titled '{title}', when was it held and what were the main decisions?", [date, meeting.get("decisions", "")[:80]], "meetings")
        add(f"What attendees and actions were recorded for the meeting '{title}'?", [meeting.get("attendees", "").splitlines()[0], meeting.get("actions", "")[:80]], "meetings")
        add(f"Summarise the discussion and decisions recorded in the project meeting '{title}'.", [title, meeting.get("discussion", "")[:80]], "meetings")
        add(f"What follow-up work was recorded for '{title}', and when did the meeting occur?", [date, meeting.get("actions", "")[:80]], "meetings")

    for milestone in project.milestones:
        name, status = milestone.get("name", ""), milestone.get("status", "")
        progress = str(milestone.get("progress", ""))
        add(f"What is the status, date and percentage progress of the milestone '{name}'?", [name, status, progress], "milestones")
        add(f"How many tasks are linked to '{name}', and how many are completed?", [name, str(milestone.get("linked_task_count", "")), str(milestone.get("completed_task_count", ""))], "milestones")
        add(f"Explain what the project record says about the milestone '{name}', including its status and progress.", [name, status, progress], "milestones")

    task_items = [item for item in gantt_tasks if str(item.get("type", "")).casefold() == "task"][:25]
    for task in task_items:
        name, status, progress = task.get("name", ""), task.get("status", ""), str(task.get("progress", ""))
        add(f"What is the status and progress of the Gantt task '{name}'?", [name, status, progress], "Gantt tasks")

    project_index = json.loads((ROOT / "project_data" / PROJECT_ID / "index.json").read_text(encoding="utf-8"))
    sources = sorted({item.get("source") for item in project_index.get("documents", []) if item.get("source")})
    if not sources:
        for _ in range(6):
            add(f"Are any project-specific knowledgebase documents currently indexed for this project, and what evidence is available? (Check {number + 1})", ["no", "none", "not available", "no project knowledge"], "project knowledge", structured=False)
    else:
        for source in sources:
            add(f"What is the purpose of the project knowledge document '{Path(source).stem}', and what project-specific requirements or decisions does it record?", [Path(source).stem], "project knowledge", structured=False)
            if number >= 100:
                break
    while number < 100:
        if sources:
            source = sources[(number - 1) % len(sources)]
            add(f"Summarise the key project-specific guidance and deliverables in '{Path(source).stem}', including names, dates or requirements supported by the document.", [Path(source).stem], "project knowledge", structured=False)
        else:
            add(f"What should the assistant do when a user asks about project knowledge but no project documents are indexed? (Check {number + 1})", ["no", "not available", "cannot", "insufficient"], "project knowledge", structured=False)
    assert number == 100 and len({c.question for c in cases}) == 100
    return cases


def main():
    """
    Function: main
    Purpose: Execute the main operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    project = load_project()
    gantt_tasks, cards = load_schedule()
    cases = build_cases(project, gantt_tasks, cards)
    original_access = None
    qa.REPORT_PATH, qa.JSON_PATH = REPORT_PATH, JSON_PATH
    st.session_state.clear()
    if TEST_USERNAME:
        if not auth.login(st.session_state, TEST_USERNAME, TEST_PASSWORD):
            raise RuntimeError("Authenticated project test login failed")
    elif IMPERSONATE_USER_ID:
        token = secrets.token_urlsafe(32)
        with database.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (auth._token_hash(token), int(IMPERSONATE_USER_ID), __import__('time').time() + auth.SESSION_SECONDS))
        st.session_state["auth_token"] = token
    else:
        raise RuntimeError("Set TEST_USERNAME/TEST_PASSWORD or IMPERSONATE_USER_ID")
    try:
        # This is a project-only certification. Do not re-extract the entire
        # general Capstone corpus; that would add latency and is outside the
        # authorised question scope.
        general = []
        project_index = json.loads((ROOT / "project_data" / PROJECT_ID / "index.json").read_text(encoding="utf-8"))
        project_documents = project_index.get("documents", [])
        if not project_documents:
            project_documents = [{
                "scope": "project",
                "project_id": project.id,
                "record_type": "project_knowledge_index",
                "source": "Project knowledge index",
                "location": "Project database",
                "text": "Authoritative project knowledge index: zero project-specific documents are currently indexed.",
            }]
        extracted = [
            {"source": source, "readable": True, "records": sum(1 for item in project_documents if item.get("source") == source)}
            for source in sorted({item.get("source") for item in project_documents if item.get("source")})
        ]
        results = []
        for index, case in enumerate(cases, 1):
            result = qa.run_case(case, general, project_documents, project, use_planner=False)
            result.answer = app.clean_ai_response(result.answer)
            result.correct, result.missing_groups = _check_answer(result.answer, case.expected_groups)
            if not result.answer:
                result.correct = False
            if result.answer and __import__("re").search(r"</?[A-Za-z][^>]*>", result.answer):
                result.correct = False
                result.notes += " HTML/XML tag detected."
            results.append(result)
            print(json.dumps({"question": index, "passed": result.correct, "category": case.category}), flush=True)
        from datetime import datetime, timezone
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        write_report(cases, results, extracted, started, finished)
        passed = sum(r.correct for r in results)
        print(json.dumps({"questions": len(results), "passed": passed, "failed": len(results) - passed, "report": str(REPORT_PATH), "json": str(JSON_PATH)}))
        return 0 if passed == 100 else 1
    finally:
        if st.session_state.get("auth_token"):
            auth.logout(st.session_state)


if __name__ == "__main__":
    raise SystemExit(main())
