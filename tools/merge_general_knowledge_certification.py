## File: tools/merge_general_knowledge_certification.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Merge the four live certification checkpoints and remediation results.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Merge the four live certification checkpoints and remediation results."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from general_knowledge_live_certification import REPORT_DOCX, REPORT_JSON, _write_docx  # noqa: E402


def run():
    """
    Function: run
    Purpose: Execute the run operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    rows = []
    for path in sorted((ROOT / "docs").glob(".general_knowledge_live_certification_checkpoint_worker*.json")):
        rows.extend(json.loads(path.read_text(encoding="utf-8")))
    remediation = {}
    for path in sorted((ROOT / "docs").glob(".general_knowledge_remediation_rem*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            remediation[(item.get("source"), item.get("question_number"))] = item
    if len(rows) != 340:
        raise RuntimeError(f"Expected 340 questions, found {len(rows)}")
    for row in rows:
        row["first_pass_verification"] = dict(row.get("verification", {}))
        key = (row.get("source"), row.get("question_number"))
        if not row["first_pass_verification"].get("passed"):
            retry = remediation.get(key)
            if not retry or not retry.get("verification", {}).get("passed"):
                raise RuntimeError(f"Unresolved review case: {key}")
            row["remediation"] = {
                "question": retry.get("remediation_question", ""),
                "retrieved_count": retry.get("retrieved_count", 0),
                "verification": retry.get("verification", {}),
            }
            row["answer"] = retry.get("answer", "")
            row["verification"] = retry.get("verification", {})
    rows.sort(key=lambda item: (str(item.get("source", "")).casefold(), int(item.get("question_number", 0))))
    started = min((row.get("started_at", "") for row in rows), default=datetime.now(timezone.utc).isoformat())
    finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
    REPORT_JSON.write_text(json.dumps({"started": started, "finished": finished, "documents": 34, "questions": 340, "first_pass_verified": sum(bool(row["first_pass_verification"].get("passed")) for row in rows), "final_verified": sum(bool(row["verification"].get("passed")) for row in rows), "results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_docx(rows, started, finished)
    print(json.dumps({"documents": 34, "questions": len(rows), "first_pass_verified": sum(bool(row["first_pass_verification"].get("passed")) for row in rows), "final_verified": sum(bool(row["verification"].get("passed")) for row in rows), "report": str(REPORT_DOCX)}))


if __name__ == "__main__":
    run()
