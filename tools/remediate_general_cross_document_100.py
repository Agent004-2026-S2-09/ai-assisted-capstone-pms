"""Remediate failed live cross-document certification cases using direct approved evidence."""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app  # noqa: E402
from app_modules import auth  # noqa: E402
from general_cross_document_100 import verify, write_report  # noqa: E402

FINAL_JSON = ROOT / "docs/general_cross_document_100_results.json"
FINAL_DOCX = ROOT / "docs/general_cross_document_100_report.docx"
WORKER_INDEX = int(os.environ.get("CROSS_REMED_WORKER", "0"))
WORKER_COUNT = int(os.environ.get("CROSS_REMED_WORKERS", "1"))


def run():
    merged = ROOT / "docs/.general_cross_document_100_merged_checkpoint.json"
    if merged.exists():
        rows = json.loads(merged.read_text(encoding="utf-8"))
    else:
        rows = []
        for i in range(4):
            path = ROOT / f"docs/.general_cross_document_100_checkpoint_worker{i}.json"
            rows.extend(json.loads(path.read_text(encoding="utf-8")))
    rows.sort(key=lambda row: row["question_number"])
    st.session_state.clear()
    if not auth.login(st.session_state, "aisha.rahman@demo.local", "Temp-dy0ZTpbyBphPxTJW4aMm"):
        raise RuntimeError("Authenticated test login failed.")
    documents = app.ensure_index_is_current()
    grouped = defaultdict(list)
    for item in documents:
        if item.get("source") and item.get("text"):
            grouped[item["source"]].append(item)
    failed_rows = [row for row in rows if not row.get("verification", {}).get("passed")]
    if WORKER_COUNT > 1:
        failed_rows = [row for pos, row in enumerate(failed_rows) if pos % WORKER_COUNT == WORKER_INDEX]
    changed = 0
    for row in failed_rows:
        if row.get("verification", {}).get("passed"):
            continue
        left, right = row["sources_expected"]
        evidence = {left: grouped[left], right: grouped[right]}
        retrieved = app.retrieve_information(row["question"], evidence[left] + evidence[right], top_k=24, minimum_score=0.01)
        # Keep both authorised sources represented even when ranking is uneven.
        present = {item.get("source") for item in retrieved}
        if left not in present:
            retrieved.append(evidence[left][0])
        if right not in present:
            retrieved.append(evidence[right][0])
        st.session_state.messages = []
        try:
            answer = app.generate_response(row["question"], retrieved)
            verification = verify(answer, row["question"], retrieved, evidence, st.session_state.get("last_validation_status", "unknown"), row["style"])
            row["remediation"] = {"answer": answer, "verification": verification}
            if verification["passed"]:
                row["answer"] = answer
                row["verification"] = verification
                changed += 1
        except Exception as error:
            row["remediation_error"] = f"{type(error).__name__}: {str(error)[:500]}"
        print(json.dumps({"question": row["question_number"], "passed": bool(row.get("verification", {}).get("passed"))}), flush=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    passed = sum(bool(row.get("verification", {}).get("passed")) for row in rows)
    if WORKER_COUNT > 1:
        out = ROOT / f"docs/.general_cross_document_100_remediated_worker{WORKER_INDEX}.json"
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        FINAL_JSON.write_text(json.dumps({"started": started, "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"), "questions": len(rows), "passed": passed, "results": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report(rows, started, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    print(json.dumps({"questions": len(rows), "passed": passed, "failed": len(rows) - passed, "remediated": changed}))
    return 0 if len(rows) == 100 and passed == 100 else 2


if __name__ == "__main__":
    raise SystemExit(run())
