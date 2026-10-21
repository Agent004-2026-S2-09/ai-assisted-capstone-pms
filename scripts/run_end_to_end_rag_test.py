## File: scripts/run_end_to_end_rag_test.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Run the local authenticated RAG acceptance test and export an Excel report.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Run the local authenticated RAG acceptance test and export an Excel report.

This deliberately drives the Streamlit UI with Playwright. Completed answers
are read back from SQLite so the report matches what the application recorded
and the AI Evaluation page can display the same interactions.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
from app_modules import auth, database, evidence_retrieval, monitoring, vector_store


REPORT_DIR = ROOT / "docs" / "test"
REPORT_PATH = REPORT_DIR / "rag_end_to_end_test.xlsx"
APP_URL = os.getenv("RAG_TEST_APP_URL", "http://127.0.0.1:8501")
STUDENT_USERNAME = os.getenv("BROWSER_TEST_USERNAME", "rag.e2e.student@local")
STUDENT_PASSWORD = os.getenv("BROWSER_TEST_PASSWORD", "Rag-E2E-Student-2026!")
ADMIN_USERNAME = os.getenv("RAG_TEST_ADMIN_USERNAME", "rag.e2e.admin@local")
ADMIN_PASSWORD = os.getenv("RAG_TEST_ADMIN_PASSWORD", "Rag-E2E-Admin-2026!")
PROJECT_ID = "ai-assisted-capstone-project-assistant"
MAX_WAIT_SECONDS = int(os.getenv("RAG_TEST_MAX_WAIT_SECONDS", "180"))
START_INDEX = max(1, int(os.getenv("RAG_TEST_START_INDEX", "1")))


def case(name, section, question, *, keywords=(), sources=(), project=False):
    """
    Function: case
    Purpose: Execute the case operation.
    Inputs:
            name (value): Caller-provided input.
            section (value): Caller-provided input.
            question (value): Caller-provided input.
            keywords (value): Caller-provided input.
            sources (value): Caller-provided input.
            project (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return {
        "name": name,
        "section": section,
        "question": question,
        "keywords": tuple(keywords),
        "sources": tuple(sources),
        "project": project,
    }


CASES = [
    case("assessment schedule", "single-document", "What are the assessments, submission types, due dates, available-until dates and points in the official assessment schedule?", keywords=("Poster", "Deliverable and Report", "Project Presentation", "30/10/2026", "100"), sources=("Assignments_S2_2026",)),
    case("generative AI acknowledgement", "single-document", "How should a student acknowledge generative AI used in an assessment?", keywords=("acknowledge", "generative", "assessment"), sources=("Student_Template_for_GenAI_Acknowledgement",)),
    case("reflection rubric", "single-document", "What does the weekly reflection journal rubric require?", keywords=("reflection", "journal", "rubric"), sources=("Reflection Rubric",)),
    case("ethics lecture", "single-document", "What topics are covered in the Professionalism and Ethics guest lecture?", keywords=("ethics", "professional", "ACS Code"), sources=("Professionalism and Ethics",)),
    case("technology support", "single-document", "What technology support is available to Capstone students?", keywords=("support", "student", "Capstone"), sources=("Technology Support Guideline",)),
    case("teaching weeks", "single-document", "What does the teaching-weeks document say about Week 7?", keywords=("Week 7",), sources=("UC_Semester_2_2026_Capstone_Teaching_Weeks",)),
    case("proposal report guidance", "single-document", "What should be included in the Project Proposal and Plan Report?", keywords=("problem", "background", "requirements"), sources=("Tutorial  Slides week 2", "Week 1 Lecture")),
    case("team charter", "single-document", "What commitments and responsibilities are recorded in the project Team Charter?", keywords=("team", "responsibil", "meeting"), sources=("Team Charter",), project=True),
    case("sponsor agenda", "single-document", "What was recorded in the initial sponsor and mentor meeting agenda?", keywords=("sponsor", "mentor", "agenda"), sources=("Initial_Sponsor_Mentor_Meeting_Agenda",), project=True),
    case("project teaching weeks", "single-document", "What teaching-week information is stored in the project knowledge area?", keywords=("week", "teaching"), sources=("UC_Semester_2_2026_Capstone_Teaching_Weeks",), project=True),
    case("assessment and poster rules", "multi-document", "What assessments remain, and what do the poster guidance and official schedule say about the poster deadline and submission format?", keywords=("Poster", "30/10/2026", "PDF", "Canvas"), sources=("Assignments_S2_2026", "Week 10 Tutorial")),
    case("reflection due and rubric", "multi-document", "When is the weekly reflection due and what does the reflection rubric say should be included?", keywords=("reflection", "18/10/2026", "journal"), sources=("Assignments_S2_2026", "Reflection Rubric")),
    case("proposal assignment and report", "multi-document", "What is the due date for the Project Proposal and Plan Report and what sections does the teaching material require?", keywords=("Project Proposal", "04/09/2026", "requirements"), sources=("Assignments_S2_2026", "Tutorial  Slides week 2")),
    case("AI acknowledgement and poster restriction", "multi-document", "How should AI use be acknowledged, and what restriction applies to using generative AI for the poster?", keywords=("acknowledge", "poster", "generative AI"), sources=("Student_Template_for_GenAI_Acknowledgement", "Week 10 Tutorial")),
    case("ethics and project", "multi-document", "What ethical and professional considerations should be applied when working on a Capstone project?", keywords=("ethics", "professional", "public"), sources=("Professionalism and Ethics", "ACS Code-of-Ethics")),
    case("support and project work", "multi-document", "What technical support is available for Capstone project work?", keywords=("support", "project"), sources=("Technology Support Guideline",)),
    case("proposal and team roles", "multi-document", "How do the Project Proposal and Plan Report and Team Charter divide project scope, responsibilities and deliverables?", keywords=("scope", "responsibil", "deliverable"), sources=("Project Proposal and Plan Report", "Team Charter"), project=True),
    case("sponsor decisions and plan", "multi-document", "Which decisions from the initial sponsor meeting should be reflected in the project proposal and plan?", keywords=("scope", "sponsor", "decision"), sources=("Initial_Sponsor_Mentor_Meeting_Agenda", "Project Proposal and Plan Report"), project=True),
    case("assessment timeline", "multi-document", "Using the teaching weeks and assessment schedule, what are the important assessment dates around Weeks 10 to 12?", keywords=("Week", "30/10/2026", "01/11/2026", "06/11/2026"), sources=("Assignments_S2_2026", "UC_Semester_2_2026_Capstone_Teaching_Weeks")),
    case("team formation and EOI", "multi-document", "What does the official assessment schedule require for team formation, and what team commitments are recorded in the Team Charter?", keywords=("Team formation", "12/08/2026", "team"), sources=("Assignments_S2_2026", "Team Charter"), project=True),
    case("presentations and project evidence", "multi-document", "What are the presentation expectations, and what evidence should a Capstone team use to prepare?", keywords=("presentation", "project", "result"), sources=("Guest Presentation", "Week 10 Tutorial")),
    case("academic integrity and AI", "multi-document", "How do the AI acknowledgement template, ethics guidance and assessment material fit together for responsible assessment work?", keywords=("acknowledge", "ethics", "assessment"), sources=("Student_Template_for_GenAI_Acknowledgement", "Professionalism and Ethics", "Assignments_S2_2026")),
    case("sponsor stakeholder guidance", "multi-document", "What guidance is available for working with a sponsor or stakeholder, and what should a project team discuss in meetings?", keywords=("sponsor", "stakeholder", "meeting"), sources=("Decoding your Stakeholder", "Tips on Professional Meetings")),
    case("risk and planning", "multi-document", "How do the risk-management documents and project planning guidance support risk control?", keywords=("risk", "plan", "requirement"), sources=("Risk log v2", "Team Roles Starter Guide")),
    case("support and teaching team", "multi-document", "Where can a Capstone student get technical or teaching support, and who is responsible for providing it?", keywords=("support", "teaching", "student"), sources=("Technology Support Guideline", "Teaching Team")),
    case("project proposal and assessment", "multi-document", "How do the proposal report requirements relate to its official assessment weight and deadline?", keywords=("Project Proposal", "15%", "04/09/2026"), sources=("Assignments_S2_2026", "Tutorial  Slides week 2")),
    case("meeting and weekly reflection", "multi-document", "How should weekly reflection evidence connect lectures, workshops, meetings and project work?", keywords=("reflection", "lecture", "meeting", "project"), sources=("Reflection Rubric", "UC_Semester_2_2026_Capstone_Teaching_Weeks")),
    case("poster versus presentation", "multi-document", "What is the difference between the poster submission and the project presentation in the assessment and tutorial material?", keywords=("Poster", "Project Presentation", "submit"), sources=("Assignments_S2_2026", "Week 10 Tutorial")),
    case("ethics and stakeholder", "multi-document", "How should professional ethics guide stakeholder and sponsor decisions in a Capstone project?", keywords=("ethics", "stakeholder", "sponsor"), sources=("Professionalism and Ethics", "Decoding your Stakeholder")),
    case("all assessment completion", "multi-document", "Which assessment items are listed in the official schedule, and which ones are still upcoming based on the current date?", keywords=("Assessment", "Poster", "Deliverable and Report", "upcoming"), sources=("Assignments_S2_2026",)),
    case("project title and scope", "project-document", "What project title, problem and scope are recorded in the authorised project proposal?", keywords=("Capstone Assistant", "scope", "problem"), sources=("Project Proposal and Plan Report",), project=True),
    case("team charter commitments", "project-document", "List the key team roles, commitments and meeting expectations in the Team Charter.", keywords=("team", "role", "meeting"), sources=("Team Charter",), project=True),
    case("sponsor meeting outcomes", "project-document", "What scope, architecture or next-step decisions are recorded in the initial sponsor and mentor meeting agenda?", keywords=("scope", "architecture", "sponsor"), sources=("Initial_Sponsor_Mentor_Meeting_Agenda",), project=True),
    case("project teaching schedule", "project-document", "What dates or week information are recorded in the project's teaching-weeks document?", keywords=("week", "2026"), sources=("UC_Semester_2_2026_Capstone_Teaching_Weeks",), project=True),
    case("project assessment copy", "project-document", "What assessment schedule information is stored inside the authorised project knowledge area?", keywords=("Assessment", "Due"), sources=("Assessments_S2_2026",), project=True),
    case("project report sections", "project-document", "What report sections are required by the project proposal document?", keywords=("problem", "background", "requirements"), sources=("Project Proposal and Plan Report",), project=True),
    case("project team working agreement", "project-document", "What does the Team Charter say about communication, attendance and resolving team issues?", keywords=("communication", "attendance", "issue"), sources=("Team Charter",), project=True),
    case("project sponsor relationship", "project-document", "What does the initial agenda record about communicating with the sponsor and mentor?", keywords=("sponsor", "mentor", "communication"), sources=("Initial_Sponsor_Mentor_Meeting_Agenda",), project=True),
    case("project document completeness", "project-document", "Which authorised project documents are available and what is the purpose of each?", keywords=("Team Charter", "Proposal", "Agenda"), sources=("Team Charter", "Project Proposal and Plan Report", "Initial_Sponsor_Mentor_Meeting_Agenda"), project=True),
    case("project evidence boundaries", "project-document", "Which facts can be confirmed from the authorised project documents, and which details are not specified?", keywords=("specified", "project"), sources=("Team Charter", "Project Proposal and Plan Report"), project=True),
    case("selected project identity", "project-database", "What is the name and ID of the selected project in the project workspace?", keywords=("AI-assisted Capstone Project Assistant", PROJECT_ID), project=True),
    case("project team members", "project-database", "Who are the recorded team members for the selected project?", keywords=("team",), project=True),
    case("project milestones", "project-database", "How many milestones are recorded for the selected project and what are their current states?", keywords=("milestone",), project=True),
    case("project tasks", "project-database", "What tasks or work items are recorded for the selected project?", keywords=("task",), project=True),
    case("project meetings", "project-database", "What meetings and decisions are recorded for the selected project?", keywords=("meeting",), project=True),
    case("project progress", "project-database", "What current progress, status or completion information is recorded for the selected project?", keywords=("progress", "status"), project=True),
    case("project sponsor", "project-database", "Who is the recorded sponsor or stakeholder for the selected project?", keywords=("sponsor",), project=True),
    case("project risks", "project-database", "What risks or issues are recorded for the selected project?", keywords=("risk", "issue"), project=True),
    case("project actions", "project-database", "What actions or next steps are recorded from the selected project's meetings?", keywords=("action", "next"), project=True),
    case("project database versus documents", "project-database", "What current project facts come from the database, and how do they compare with the authorised project documents?", keywords=("database", "document", "project"), project=True),
]


def ensure_admin():
    """
    Function: ensure_admin
    Purpose: Execute the ensure admin operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    user = auth.authenticate(ADMIN_USERNAME, ADMIN_PASSWORD)
    if user is None:
        try:
            auth.create_user("RAG E2E Administrator", ADMIN_USERNAME, ADMIN_PASSWORD, "Administrator", email=ADMIN_USERNAME, first_name="RAG E2E", last_name="Administrator")
        except sqlite3.IntegrityError:
            pass
    state = {}
    if not auth.login(state, ADMIN_USERNAME, ADMIN_PASSWORD):
        raise RuntimeError("Could not authenticate the local evaluation administrator")
    return state


def normalize(value):
    """
    Function: normalize
    Purpose: Execute the normalize operation.
    Inputs:
            value (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


KEYWORD_ALIASES = {
    "public interest": ("public interest", "public welfare", "human dignity", "public trust"),
    "background": ("background", "literature", "existing work", "context"),
    "student": ("student", "students", "capstone"),
    "04/09/2026": ("04/09/2026", "4/09/2026", "4 september 2026", "4 september"),
    "01/11/2026": ("01/11/2026", "1/11/2026", "1 november 2026", "1 november"),
    "06/11/2026": ("06/11/2026", "6/11/2026", "6 november 2026", "6 november"),
    "18/10/2026": ("18/10/2026", "18 october 2026", "18 october", "18 oct 2026", "18 oct"),
    "30/10/2026": ("30/10/2026", "30 october 2026", "30 october", "30 oct 2026", "30 oct"),
    "100": ("100", "one hundred"),
    "requirement": ("requirement", "responsibility", "criteria", "process"),
    "result": ("result", "outcome", "deliverable", "evidence"),
    "UC Canberra": ("UC Canberra", "University of Canberra"),
    "journal": ("journal", "reflection"),
    "generative AI": ("generative ai", "gener ative ai"),
    "Capstone Assistant": ("capstone assistant", "capstone project assistant", "ai assisted capstone project assistant"),
}


def keyword_match(keyword, answer_norm):
    """
    Function: keyword_match
    Purpose: Execute the keyword match operation.
    Inputs:
            keyword (value): Caller-provided input.
            answer_norm (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    variants = next(
        (values for raw, values in KEYWORD_ALIASES.items() if normalize(raw) == str(keyword).casefold()),
        (str(keyword),),
    )
    return any(normalize(variant) in answer_norm for variant in variants)


def evaluate(case_item, answer, retrieved, interaction):
    """
    Function: evaluate
    Purpose: Execute the evaluate operation.
    Inputs:
            case_item (value): Caller-provided input.
            answer (value): Caller-provided input.
            retrieved (value): Caller-provided input.
            interaction (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    answer_norm = normalize(answer)
    keywords = [normalize(x) for x in case_item["keywords"]]
    keyword_hits = [bool(key and keyword_match(key, answer_norm)) for key in keywords]
    sources = " ".join(str(item.get("source", "")) for item in retrieved)
    source_norm = normalize(sources)
    source_hits = [normalize(x) in source_norm for x in case_item["sources"]]
    abstained = bool(re.match(
        r"^\s*(?:sorry|i\s+(?:do\s+not|don't|cannot|can't|am\s+unable)|"
        r"the\s+(?:approved|provided|supplied)\s+evidence\s+(?:does\s+not|contains\s+only)|"
        r"hi\b.*(?:clarif|rephrase)|i\s+(?:need|want)\s+to\s+make\s+sure)",
        answer_norm,
    ))
    passed = bool(interaction and interaction.get("success") and answer.strip() and all(keyword_hits) and all(source_hits) and not abstained)
    notes = []
    if not answer.strip(): notes.append("empty answer")
    if not all(keyword_hits): notes.append("missing expected answer terms")
    if not all(source_hits): notes.append("retrieval did not include every expected source")
    if abstained: notes.append("answer abstained despite expected evidence")
    return {
        "passed": passed,
        "keyword_hits": sum(keyword_hits),
        "keyword_total": len(keywords),
        "source_hits": sum(source_hits),
        "source_total": len(source_hits),
        "abstained": abstained,
        "notes": "; ".join(notes) or "passed deterministic evidence checks",
    }


def read_interaction(question, user_id, started):
    """
    Function: read_interaction
    Purpose: Execute the read interaction operation.
    Inputs:
            question (value): Caller-provided input.
            user_id (value): Caller-provided input.
            started (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    with database.connect() as db:
        row = db.execute(
            """SELECT ai.*, ap.question_text FROM ai_interactions ai
               JOIN ai_prompt_archive ap ON ap.interaction_id = ai.id
               WHERE ai.user_id = ? AND ap.question_text = ? AND ai.created_epoch >= ?
               ORDER BY ai.id DESC LIMIT 1""",
            (user_id, question, started),
        ).fetchone()
    return dict(row) if row else None


def wait_for_interaction(question, user_id, started):
    """
    Function: wait_for_interaction
    Purpose: Execute the wait for interaction operation.
    Inputs:
            question (value): Caller-provided input.
            user_id (value): Caller-provided input.
            started (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    deadline = time.time() + MAX_WAIT_SECONDS
    while time.time() < deadline:
        row = read_interaction(question, user_id, started)
        if row:
            return row
        time.sleep(1)
    return None


def choose_project(page, label):
    """
    Function: choose_project
    Purpose: Execute the choose project operation.
    Inputs:
            page (value): Caller-provided input.
            label (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    page.get_by_label("Current project").click()
    option = page.get_by_role("option").filter(has_text=label).first
    if option.count() == 0:
        option = page.get_by_text(label, exact=True)
    option.click()
    page.wait_for_timeout(2200)
    if label == "General Capstone":
        page.get_by_text("General Capstone assistant mode", exact=False).wait_for(timeout=15000)
    else:
        page.get_by_text("Project-specific assistant mode", exact=False).wait_for(timeout=15000)


def submit_question(page, question):
    """
    Function: submit_question
    Purpose: Execute the submit question operation.
    Inputs:
            page (value): Caller-provided input.
            question (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    if page.get_by_role("button", name="New Conversation").count():
        try:
            page.get_by_role("button", name="New Conversation").click()
            page.wait_for_timeout(300)
        except Exception:
            pass
    # The evaluation panel also contains a hidden/secondary textarea for an
    # optional comment.  Always target the visible chat composer so a rerun
    # cannot stall after the first evaluation widget is rendered.
    textarea = page.locator("[data-testid='stChatInput'] textarea:visible").first
    if textarea.count() == 0:
        textarea = page.locator("textarea:visible").first
    textarea.fill(question)
    textarea.press("Enter")


def inventory_rows(general_documents, project_documents):
    """
    Function: inventory_rows
    Purpose: Execute the inventory rows operation.
    Inputs:
            general_documents (value): Caller-provided input.
            project_documents (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    rows = []
    for item in [*general_documents, *project_documents]:
        rows.append({
            "scope": item.get("scope", "general"),
            "source": item.get("source", ""),
            "location": item.get("location", ""),
            "record_type": item.get("record_type", ""),
            "project_id": item.get("project_id", ""),
            "text_length": len(str(item.get("text", ""))),
        })
    return rows


def write_report(results, document_rows, database_rows):
    """
    Function: write_report
    Purpose: Execute the write report operation.
    Inputs:
            results (value): Caller-provided input.
            document_rows (value): Caller-provided input.
            database_rows (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    passed = sum(bool(row["passed"]) for row in results)
    summary_rows = [
        ("Run timestamp", datetime.now(timezone.utc).isoformat()),
        ("Application URL", APP_URL),
        ("Student account", STUDENT_USERNAME),
        ("Total prompts", len(results)),
        ("Passed deterministic checks", passed),
        ("Failed deterministic checks", len(results) - passed),
        ("Pass rate", passed / len(results) if results else 0),
    ]
    for row in summary_rows: summary.append(row)
    summary["A8"] = "Note"
    summary["B8"] = "Correctness checks are evidence-based and include the recorded answer, expected terms and expected source retrieval. Failed rows require manual/root-cause review."
    for cell in summary[1]: cell.font = Font(bold=True)

    sheet = workbook.create_sheet("Results")
    columns = ["name", "section", "question", "interaction_id", "success", "latency_ms", "answer", "retrieved_sources", "keyword_hits", "keyword_total", "source_hits", "source_total", "passed", "notes"]
    sheet.append(columns)
    for row in results:
        sheet.append([row.get(column, "") for column in columns])
    for cell in sheet[1]: cell.font = Font(bold=True); cell.fill = PatternFill("solid", fgColor="D9EAF7")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    widths = {"A": 28, "B": 18, "C": 70, "G": 100, "H": 65, "N": 50}
    for col, width in widths.items(): sheet.column_dimensions[col].width = width

    inv = workbook.create_sheet("Document Inventory")
    inv.append(list(document_rows[0]) if document_rows else ["scope"])
    for row in document_rows: inv.append(list(row.values()))
    dbs = workbook.create_sheet("Database Inventory")
    dbs.append(list(database_rows[0]) if database_rows else ["table"])
    for row in database_rows: dbs.append(list(row.values()))
    failures = workbook.create_sheet("Failures")
    failures.append(columns)
    for row in results:
        if not row.get("passed"): failures.append([row.get(column, "") for column in columns])
    for target in (inv, dbs, failures):
        for cell in target[1]: cell.font = Font(bold=True); cell.fill = PatternFill("solid", fgColor="D9EAF7")
        target.freeze_panes = "A2"
        target.auto_filter.ref = target.dimensions
    workbook.save(REPORT_PATH)


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
    with open(ROOT / "knowledge_index" / "index.json", encoding="utf-8") as handle:
        general_documents = json.load(handle).get("documents", [])
    project_index = ROOT / "project_data" / PROJECT_ID / "index.json"
    project_documents = json.loads(project_index.read_text(encoding="utf-8")).get("documents", []) if project_index.exists() else []
    user = auth.authenticate(STUDENT_USERNAME, STUDENT_PASSWORD)
    if not user:
        raise RuntimeError("The dedicated student account does not exist or cannot authenticate")
    admin_state = ensure_admin()
    with database.connect() as db:
        database_rows = []
        for table in ("users", "projects", "assignments", "ai_interactions", "ai_evaluations", "rag_diagnostics"):
            try:
                database_rows.append({"table": table, "row_count": db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]})
            except sqlite3.Error:
                database_rows.append({"table": table, "row_count": "missing"})

    results = []
    if START_INDEX > 1 and REPORT_PATH.exists():
        workbook = __import__("openpyxl").load_workbook(REPORT_PATH, read_only=True, data_only=True)
        sheet = workbook["Results"]
        headers = [cell.value for cell in next(sheet.iter_rows())]
        results = [dict(zip(headers, row)) for row in sheet.iter_rows(min_row=2, values_only=True)]
        workbook.close()
        # A resumed run replaces prior rows for the cases it re-executes. Do
        # not append duplicate case rows to the audit workbook.
        results = results[: START_INDEX - 1]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
        page.get_by_label("Email / username").fill(STUDENT_USERNAME)
        page.get_by_role("textbox", name="Password").fill(STUDENT_PASSWORD)
        page.get_by_role("button", name="Sign in to workspace").click()
        page.wait_for_timeout(4000)
        if page.get_by_text("RAG E2E Student", exact=False).count() == 0:
            raise RuntimeError("Student login did not reach the authenticated workspace")
        # Streamlit can leave the previous login DOM mounted for one rerun
        # while the authenticated page is restoring its browser session.
        # A reload gives the app one clean authenticated render before the
        # first project switch.
        if page.locator("[data-testid='stChatInput'] textarea").count() == 0:
            page.reload(wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
        choose_project(page, "General Capstone")

        for index, item in enumerate(CASES, start=1):
            if index < START_INDEX:
                continue
            if item["project"]:
                choose_project(page, "AI-assisted Capstone Project Assistant")
            else:
                choose_project(page, "General Capstone")
            started = time.time()
            submit_question(page, item["question"])
            interaction = wait_for_interaction(item["question"], user["id"], started)
            answer = str(interaction.get("response_text", "") if interaction else "")
            if item["project"]:
                if app.requests_project_document_inventory(item["question"]):
                    retrieved = app.retrieve_project_document_inventory(
                        project_documents, PROJECT_ID
                    )
                else:
                    retrieved = evidence_retrieval.retrieve(
                        project_documents,
                        item["question"],
                        top_k=10,
                        minimum_score=0.10,
                        semantic_scorer=lambda query, items: vector_store.score_documents(query, items),
                        semantic_backend=f"{vector_store.backend_name()}:{vector_store.model_name()}",
                    )
                    retrieved = app._ensure_multi_source_context(
                        item["question"],
                        retrieved,
                        project_documents,
                        project_id=PROJECT_ID,
                    )
            else:
                retrieved = app.retrieve_information(item["question"], general_documents, top_k=10, minimum_score=0.10)
                retrieved = app._ensure_multi_source_context(
                    item["question"], retrieved, general_documents
                )
            check = evaluate(item, answer, retrieved, interaction)
            sources = "; ".join(sorted({str(result.get("source", "")) for result in retrieved if result.get("source")}))
            result = {
                **item,
                "interaction_id": interaction.get("id", "") if interaction else "",
                "success": interaction.get("success", 0) if interaction else 0,
                "latency_ms": interaction.get("latency_ms", "") if interaction else "",
                "answer": answer,
                "retrieved_sources": sources,
                **check,
            }
            results.append(result)
            if interaction and interaction.get("success"):
                monitoring.add_evaluation(
                    admin_state,
                    interaction["id"],
                    f"RAG E2E {index:02d} - {item['name']}",
                    5 if check["passed"] else 2,
                    5 if check["passed"] else 1,
                    not check["passed"],
                    check["notes"],
                    usability=5 if check["passed"] else 2,
                )
            write_report(results, inventory_rows(general_documents, project_documents), database_rows)
            print(json.dumps({"index": index, "total": len(CASES), "name": item["name"], "passed": check["passed"], "interaction_id": result["interaction_id"], "latency_ms": result["latency_ms"]}), flush=True)
        browser.close()
    print(f"REPORT={REPORT_PATH}")
    print(json.dumps({"total": len(results), "passed": sum(bool(row["passed"]) for row in results), "failed": sum(not row["passed"] for row in results)}))


if __name__ == "__main__":
    main()
