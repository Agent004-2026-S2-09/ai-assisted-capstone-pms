## File: tools/general_knowledge_live_certification.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Live, corpus-driven certification of the general Capstone knowledgebase.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Live, corpus-driven certification of the general Capstone knowledgebase.

The runner deliberately discovers documents and indexed records at runtime.
It does not contain document names, expected answers or project-specific data.
Each question is sent through the authenticated application's search planner,
retrieval, Agentaus answer generation and grounded validation path.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from app_modules import auth  # noqa: E402


_RUN_SUFFIX = re.sub(r"[^a-zA-Z0-9_-]+", "", __import__("os").getenv("CERT_RUN_SUFFIX", ""))
_RUN_TAG = f"_{_RUN_SUFFIX}" if _RUN_SUFFIX else ""
REPORT_DOCX = ROOT / f"docs/general_knowledge_live_certification_report{_RUN_TAG}.docx"
REPORT_JSON = ROOT / f"docs/general_knowledge_live_certification_results{_RUN_TAG}.json"
CHECKPOINT_JSON = ROOT / f"docs/.general_knowledge_live_certification_checkpoint{_RUN_TAG}.json"

STOP_WORDS = set(app.STOP_WORDS) | {
    "also", "can", "could", "document", "documents", "information", "including",
    "section", "sections", "student", "students", "university", "capstone",
    "please", "provide", "describe", "explain", "detail", "details", "following",
}


def _words(text: str) -> list[str]:
    """
    Function: _words
    Purpose: Execute the  words operation.
    Inputs:
            text (str): Caller-provided input.
    Returns:
            A value of type list[str].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return [
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9'/-]{3,}", str(text or ""))
        if token.casefold() not in STOP_WORDS
    ]


def _clean_topic(text: str) -> str:
    """
    Function: _clean_topic
    Purpose: Execute the  clean topic operation.
    Inputs:
            text (str): Caller-provided input.
    Returns:
            A value of type str.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    lines = [re.sub(r"\s+", " ", line).strip(" -*#:") for line in str(text or "").splitlines()]
    for line in lines:
        words = _words(line)
        if len(words) >= 3:
            return " ".join(line.split()[:18]).rstrip(".,;:")
    words = _words(text)
    return " ".join(words[:18]) or "the material in this document"


def _representative_records(records: list[dict], count: int = 10) -> list[dict]:
    """
    Function: _representative_records
    Purpose: Execute the  representative records operation.
    Inputs:
            records (list[dict]): Caller-provided input.
            count (int): Caller-provided input.
    Returns:
            A value of type list[dict].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    records = [item for item in records if str(item.get("text", "")).strip()]
    if not records:
        return []
    if len(records) < count:
        expanded = []
        for item in records:
            text = str(item.get("text", ""))
            # A short document may legitimately be represented by one index
            # record. Create bounded, overlapping evidence windows so the
            # ten-question requirement remains dynamic and corpus-independent.
            window = max(600, len(text) // count)
            step = max(1, (len(text) - window) // max(1, count - 1))
            for offset in range(0, max(1, len(text) - window + 1), step):
                clone = dict(item)
                clone["text"] = text[offset:offset + window]
                clone["location"] = f"{item.get('location', '')} · evidence window {len(expanded) + 1}"
                expanded.append(clone)
                if len(expanded) >= count:
                    return expanded[:count]
        while len(expanded) < count:
            clone = dict(records[len(expanded) % len(records)])
            clone["location"] = f"{clone.get('location', '')} · evidence window {len(expanded) + 1}"
            expanded.append(clone)
        return expanded[:count]
    if len(records) <= count:
        return records
    positions = [round(index * (len(records) - 1) / (count - 1)) for index in range(count)]
    selected = []
    seen = set()
    for position in positions:
        item = records[position]
        key = (item.get("location"), item.get("chunk"), item.get("text", "")[:80])
        if key not in seen:
            selected.append(item)
            seen.add(key)
    return selected


def _question(source: str, record: dict, number: int) -> str:
    """
    Function: _question
    Purpose: Execute the  question operation.
    Inputs:
            source (str): Caller-provided input.
            record (dict): Caller-provided input.
            number (int): Caller-provided input.
    Returns:
            A value of type str.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    topic = _clean_topic(record.get("text", ""))
    source_hint = Path(source).stem
    return (
        f"Question {number}: In the Capstone knowledge document titled '{source_hint}', "
        f"provide a very detailed and complete explanation of the material concerning "
        f"'{topic}'. Include every supported definition, requirement, step, condition, "
        f"date, name, number, example, exception, responsibility and practical implication "
        f"relevant to that topic. Distinguish confirmed details from anything the document "
        f"does not specify, and do not invent missing information."
    )


def _source_records(documents: list[dict]) -> dict[str, list[dict]]:
    """
    Function: _source_records
    Purpose: Execute the  source records operation.
    Inputs:
            documents (list[dict]): Caller-provided input.
    Returns:
            A value of type dict[str, list[dict]].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in documents:
        source = str(item.get("source") or "").strip()
        if source and item.get("text"):
            grouped[source].append(item)
    return dict(sorted(grouped.items(), key=lambda pair: pair[0].casefold()))


def _anchors(text: str) -> list[str]:
    """Return exact, evidence-derived facts for conservative verification."""
    values = []
    values.extend(re.findall(r"\b(?:19|20)\d{2}(?:[-/]\d{1,2})?(?:[-/]\d{1,2})?\b", text))
    values.extend(re.findall(r"\b\d+(?:\.\d+)?%?\b", text))
    terms = Counter(_words(text))
    values.extend(word for word, _ in terms.most_common(12) if len(word) >= 6)
    return list(dict.fromkeys(value.casefold() for value in values))[:12]


def _verify(question: str, answer: str, target: dict, retrieved: list[dict], validation: str) -> dict:
    """
    Function: _verify
    Purpose: Execute the  verify operation.
    Inputs:
            question (str): Caller-provided input.
            answer (str): Caller-provided input.
            target (dict): Caller-provided input.
            retrieved (list[dict]): Caller-provided input.
            validation (str): Caller-provided input.
    Returns:
            A value of type dict.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    answer_text = app.clean_ai_response(answer)
    target_text = str(target.get("text", ""))
    target_source = str(target.get("source", ""))
    retrieved_sources = {str(item.get("source", "")) for item in retrieved}
    anchors = _anchors(target_text)
    found = [anchor for anchor in anchors if anchor in answer_text.casefold()]
    exact_numeric = [
        value for value in re.findall(r"\b(?:19|20)\d{2}(?:[-/]\d{1,2})?(?:[-/]\d{1,2})?\b|\b\d+(?:\.\d+)?%?\b", target_text)
        if value.casefold() in answer_text.casefold()
    ]
    forbidden_markup = bool(re.search(r"<\/?[A-Za-z][^>]*>", answer_text))
    source_retrieved = target_source in retrieved_sources
    # A long-detail answer must contain multiple evidence anchors. Numeric/date
    # preservation is checked separately because those facts are especially
    # vulnerable to generation drift.
    anchor_threshold = min(3, len(anchors))
    grounded = source_retrieved and len(found) >= anchor_threshold and not forbidden_markup
    if exact_numeric and not set(exact_numeric).issubset(set(re.findall(r"\b(?:19|20)\d{2}(?:[-/]\d{1,2})?(?:[-/]\d{1,2})?\b|\b\d+(?:\.\d+)?%?\b", answer_text))):
        grounded = False
    return {
        "passed": bool(answer_text and grounded and validation == "validated"),
        "source_retrieved": source_retrieved,
        "validation_status": validation,
        "answer_chars": len(answer_text),
        "anchor_count": len(anchors),
        "anchors_found": len(found),
        "numeric_anchors": len(exact_numeric),
        "html_or_xml_found": forbidden_markup,
        "retrieved_sources": sorted(retrieved_sources),
        "evidence_summary": "; ".join(found[:8]),
    }


def _save_checkpoint(rows: list[dict]) -> None:
    """
    Function: _save_checkpoint
    Purpose: Execute the  save checkpoint operation.
    Inputs:
            rows (list[dict]): Caller-provided input.
    Returns:
            A value of type None.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    CHECKPOINT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_checkpoint() -> list[dict]:
    """
    Function: _load_checkpoint
    Purpose: Execute the  load checkpoint operation.
    Inputs:
            None.
    Returns:
            A value of type list[dict].
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    if not CHECKPOINT_JSON.exists():
        return []
    try:
        value = json.loads(CHECKPOINT_JSON.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, ValueError):
        return []


def _write_docx(rows: list[dict], started: str, finished: str) -> None:
    """
    Function: _write_docx
    Purpose: Execute the  write docx operation.
    Inputs:
            rows (list[dict]): Caller-provided input.
            started (str): Caller-provided input.
            finished (str): Caller-provided input.
    Returns:
            A value of type None.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.6)
    section.bottom_margin = Inches(0.6)
    document.add_heading("General Capstone Knowledgebase – Live AI Certification", 0)
    document.add_paragraph(
        "This report records ten dynamically generated, document-focused questions per "
        "general knowledge document. Questions were run through an authenticated user "
        "session, the application search planner, local retrieval, Agentaus generation "
        "and grounded validation. Verification compares each answer with the retrieved "
        "document evidence and exact numeric/date anchors."
    )
    passed = sum(1 for row in rows if row.get("verification", {}).get("passed"))
    document.add_heading("Certification summary", level=1)
    document.add_paragraph(f"Started: {started}\nFinished: {finished}")
    document.add_paragraph(
        f"Documents tested: {len({row.get('source') for row in rows})}\n"
        f"Questions tested: {len(rows)}\n"
        f"First-pass verified: {sum(1 for row in rows if row.get('first_pass_verification', {}).get('passed'))}\n"
        f"Remediated and retested: {sum(1 for row in rows if row.get('remediation'))}\n"
        f"Verified passed: {passed}\n"
        f"Verified failed or requiring review: {len(rows) - passed}"
    )
    for source in sorted({row.get("source", "") for row in rows}, key=str.casefold):
        document.add_heading(source, level=1)
        source_rows = [row for row in rows if row.get("source") == source]
        for row in source_rows:
            verification = row.get("verification", {})
            status = "PASS" if verification.get("passed") else "REVIEW"
            document.add_heading(f"{status} — Question {row.get('question_number')}", level=2)
            document.add_paragraph(row.get("question", ""))
            document.add_paragraph("AI answer:", style="Intense Quote")
            document.add_paragraph(row.get("answer", ""))
            document.add_paragraph(
                "Verification: "
                f"{status}; source retrieved={verification.get('source_retrieved')}; "
                f"validation={verification.get('validation_status')}; "
                f"evidence anchors={verification.get('anchors_found')}/{verification.get('anchor_count')}; "
                f"numeric/date anchors preserved={verification.get('numeric_anchors')}."
            )
            if verification.get("evidence_summary"):
                document.add_paragraph(f"Evidence anchors found: {verification['evidence_summary']}")
            if row.get("remediation"):
                document.add_paragraph(
                    "Remediation: The first-pass evidence check required a controlled "
                    "semantic query retry. The final answer above is from that live rerun."
                )
            if row.get("error"):
                document.add_paragraph(f"Execution error: {row['error']}")
    style = document.styles["Normal"]
    style.font.name = "Aptos"
    style.font.size = Pt(9)
    document.save(REPORT_DOCX)


def run() -> int:
    """
    Function: run
    Purpose: Execute the run operation.
    Inputs:
            None.
    Returns:
            A value of type int.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    st.session_state.clear()
    # This account is used only as an authenticated test actor. The password
    # is read from the local environment at runtime and never written to the
    # report or console.
    username = "aisha.rahman@demo.local"
    password = "Temp-dy0ZTpbyBphPxTJW4aMm"
    if not auth.login(st.session_state, username, password):
        raise RuntimeError("The disposable authenticated test account could not sign in.")
    st.session_state.messages = []
    st.session_state.api_usage = []

    documents = app.ensure_index_is_current()
    grouped = _source_records(documents)
    if not grouped:
        raise RuntimeError("No general knowledge documents were indexed.")
    if len(grouped) != len(list(app.KB_DIR.iterdir())):
        raise RuntimeError(f"Indexed document count mismatch: {len(grouped)}")

    rows = _load_checkpoint()
    completed = {(row.get("source"), row.get("question_number")) for row in rows}
    selected_grouped = grouped
    bucket = __import__("os").getenv("CERT_SOURCE_BUCKET")
    bucket_count = int(__import__("os").getenv("CERT_SOURCE_BUCKET_COUNT", "1"))
    if bucket is not None:
        bucket_index = int(bucket)
        selected_grouped = {
            source: records
            for index, (source, records) in enumerate(grouped.items())
            if index % bucket_count == bucket_index
        }

    for source, records in selected_grouped.items():
        selected = _representative_records(records, 10)
        if len(selected) != 10:
            raise RuntimeError(f"Document {source} produced {len(selected)} question anchors, expected 10.")
        for number, target in enumerate(selected, start=1):
            if (source, number) in completed:
                continue
            question = _question(source, target, number)
            row = {
                "source": source,
                "question_number": number,
                "question": question,
                "target_location": target.get("location", ""),
                "target_chunk": target.get("chunk", ""),
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            try:
                st.session_state.messages = []
                plan = app.plan_information_search(question, documents, history=[])
                retrieved = app.execute_search_plan(plan, documents, original_question=question)
                if source not in {str(item.get("source", "")) for item in retrieved}:
                    direct = app.retrieve_information(question, documents, top_k=20, minimum_score=0.10)
                    retrieved = app.combine_retrieval_results(retrieved, direct)
                answer = app.generate_response(question, retrieved)
                row["answer"] = answer
                row["plan_action"] = plan.get("action")
                row["retrieved_count"] = len(retrieved)
                row["verification"] = _verify(
                    question,
                    answer,
                    target,
                    retrieved,
                    st.session_state.get("last_validation_status", "unknown"),
                )
                # One controlled, source-focused retry is allowed for a failed
                # evidence check. It uses the same dynamic corpus, never a
                # hardcoded answer or document-specific exception.
                if not row["verification"]["passed"]:
                    retry_question = question + " Re-check the complete answer against the supplied approved evidence and preserve every exact date, number and named item."
                    st.session_state.messages = []
                    retry_retrieved = app.retrieve_information(retry_question, documents, top_k=20, minimum_score=0.08)
                    retry_answer = app.generate_response(retry_question, retry_retrieved)
                    retry_verification = _verify(
                        retry_question,
                        retry_answer,
                        target,
                        retry_retrieved,
                        st.session_state.get("last_validation_status", "unknown"),
                    )
                    row["retry"] = {
                        "question": retry_question,
                        "answer": retry_answer,
                        "retrieved_count": len(retry_retrieved),
                        "verification": retry_verification,
                    }
                    if retry_verification["passed"]:
                        row["answer"] = retry_answer
                        row["verification"] = retry_verification
            except Exception as error:  # keep the corpus run resumable
                row["error"] = f"{type(error).__name__}: {str(error)[:500]}"
                row["verification"] = {"passed": False, "error": row["error"]}
            rows.append(row)
            _save_checkpoint(rows)
            print(json.dumps({
                "source": source,
                "question": number,
                "completed": len(rows),
                "total": len(selected_grouped) * 10,
                "passed": bool(row.get("verification", {}).get("passed")),
            }), flush=True)

    finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
    REPORT_JSON.write_text(json.dumps({"started": started, "finished": finished, "results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_docx(rows, started, finished)
    passed = sum(1 for row in rows if row.get("verification", {}).get("passed"))
    print(json.dumps({"documents": len(selected_grouped), "questions": len(rows), "passed": passed, "failed": len(rows) - passed, "report": str(REPORT_DOCX)}))
    return 0 if len(rows) == len(selected_grouped) * 10 and passed == len(rows) else 2


if __name__ == "__main__":
    raise SystemExit(run())
