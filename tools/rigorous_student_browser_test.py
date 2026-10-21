## File: tools/rigorous_student_browser_test.py
## Date Created: 20-10-2026
## Description: Real Chromium/Playwright wrapper for the rigorous student benchmark.

"""Submit the corpus-driven benchmark through a real browser-rendered UI."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_modules import auth

APP_URL = "http://127.0.0.1:8501"
USER = "rag.e2e.student@local"
PASSWORD = "Rag-E2E-Student-2026!"
MAX_WAIT = 300


def load_module():
    path = ROOT / "tools" / "rigorous_student_frontend_test.py"
    spec = importlib.util.spec_from_file_location("rigorous_student_frontend_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def wait_interaction(module, question, started):
    deadline = time.time() + MAX_WAIT
    user = auth.authenticate(USER, PASSWORD)
    while time.time() < deadline:
        row = module.latest(question)
        if row and float(row.get("id", 0)) and row.get("question_text") == question:
            # A row is written before the UI rerun finishes; success/response
            # are the completion boundary for this benchmark.
            if row.get("success") is not None or row.get("response_chars"):
                return row
        time.sleep(1)
    return module.latest(question)


def choose_scope(page, scope):
    target = "General Capstone" if scope == "general" else "AI-assisted Capstone Project Assistant (2026-S2-09)"
    selector = page.get_by_label("Current project")
    selector.click()
    selector.fill("General" if scope == "general" else "AI-assisted")
    page.get_by_text(target, exact=True).first.click()
    page.wait_for_timeout(1800)
    marker = "General Capstone assistant mode" if scope == "general" else "Project-specific assistant mode"
    page.get_by_text(marker, exact=False).wait_for(timeout=30000)


def submit(page, question):
    if page.get_by_role("button", name="New Conversation").count():
        try:
            page.get_by_role("button", name="New Conversation").click()
            page.wait_for_timeout(300)
        except Exception:
            pass
    composer = page.locator("[data-testid='stChatInput'] textarea:visible").first
    if composer.count() == 0:
        composer = page.locator("textarea:visible").first
    composer.fill(question)
    composer.press("Enter")


def run(limit=0):
    print(json.dumps({"phase": "build_questions"}), flush=True)
    module = load_module()
    all_questions, docs, sections = module.questions()
    if limit:
        all_questions = all_questions[:limit]
    rows = json.loads(module.CHECKPOINT.read_text()) if module.CHECKPOINT.exists() else []
    done = {int(x["number"]) for x in rows if x.get("interaction_id")}
    user = auth.authenticate(USER, PASSWORD)
    if not user:
        raise RuntimeError("Student account could not authenticate")
    current = None
    print(json.dumps({"phase": "launch_browser", "questions": len(all_questions)}), flush=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60000)
        print(json.dumps({"phase": "login_page_loaded"}), flush=True)
        page.get_by_label("Email / username").fill(USER)
        page.get_by_role("textbox", name="Password").fill(PASSWORD)
        page.get_by_role("button", name="Sign in to workspace").click()
        page.get_by_label("Current project").wait_for(timeout=60000)
        print(json.dumps({"phase": "student_authenticated"}), flush=True)
        for item in all_questions:
            if item["number"] in done:
                continue
            started = time.time()
            try:
                if current != item["scope"]:
                    choose_scope(page, item["scope"])
                    current = item["scope"]
                submit(page, item["question"])
                saved = wait_interaction(module, item["question"], started)
                # Require a rendered assistant message before accepting the
                # persisted answer as a browser-level completion.
                page.locator("[data-testid='stChatMessageContent']").last.wait_for(timeout=MAX_WAIT * 1000)
                rendered = page.locator("[data-testid='stChatMessageContent']").last.inner_text()
                scored = module.score(saved, rendered, item)
                module.persist_evaluation(saved.get("id") if saved else None, scored)
                row = {**item, "interaction_id": saved.get("id") if saved else None,
                       "response_chars": len(rendered), "rendered": True,
                       "success": bool(saved and saved.get("success")),
                       "validation_status": saved.get("validation_status") if saved else None,
                       "failure_class": saved.get("failure_class") if saved else "missing",
                       "source_count": saved.get("source_count") if saved else 0,
                       "evidence_sufficient": saved.get("evidence_sufficient") if saved else 0,
                       "elapsed_seconds": round(time.time() - started, 2), "score": scored,
                       "completed_at": module.now()}
            except Exception as error:
                row = {**item, "interaction_id": None, "rendered": False, "success": False,
                       "failure_class": type(error).__name__, "error": str(error)[:500],
                       "score": {"automated_pass": False, "relevance": 1, "grounded_accuracy": 1,
                                 "hallucination_detected": 1, "usability": 1, "notes": str(error)[:500]},
                       "completed_at": module.now()}
            rows.append(row)
            module.CHECKPOINT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({"completed": len(rows), "total": len(all_questions), "number": item["number"],
                              "passed": bool(row.get("score", {}).get("automated_pass")),
                              "interaction_id": row.get("interaction_id")}), flush=True)
        browser.close()
    passed = sum(bool(x.get("score", {}).get("automated_pass")) for x in rows)
    payload = {"run": module.RUN_NAME + "_browser", "finished": module.now(),
               "student_account": USER, "project_id": module.PROJECT_ID,
               "general_document_count": docs, "project_section_count": sections,
               "target_questions": len(all_questions), "questions_recorded": len(rows),
               "automated_pass": passed, "automated_review": len(rows) - passed, "results": rows}
    module.OUT.with_name("rigorous_student_browser_test.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("target_questions", "questions_recorded", "automated_pass", "automated_review")}))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    run(parser.parse_args().limit)
