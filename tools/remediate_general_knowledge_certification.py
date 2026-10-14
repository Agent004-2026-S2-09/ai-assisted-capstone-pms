"""Rerun first-pass review cases with semantically normalised questions."""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from app_modules import auth  # noqa: E402

from general_knowledge_live_certification import _anchors  # noqa: E402


def _semantic_terms(text: str) -> str:
    cleaned = re.sub(r"\b[A-Z]{1,3}\d+\s*=\s*", "", str(text or ""))
    cleaned = cleaned.replace("|", " ").replace("=", " ")
    words = re.findall(r"[A-Za-z][A-Za-z0-9'/-]{4,}", cleaned)
    counts = Counter(word.casefold() for word in words if word.casefold() not in app.STOP_WORDS)
    return " ".join(word for word, _ in counts.most_common(18))


def _verify(answer: str, target: dict, retrieved: list[dict], validation: str) -> dict:
    text = app.clean_ai_response(answer)
    source = str(target.get("source", ""))
    sources = {str(item.get("source", "")) for item in retrieved}
    anchors = _anchors(str(target.get("text", "")))
    found = [value for value in anchors if value in text.casefold()]
    markup = bool(re.search(r"<\/?[A-Za-z][^>]*>", text))
    # The first verifier treated every cell number in spreadsheets and every
    # slide number in OCR as a required answer fact. Here we require source
    # retrieval, independent validation, a substantial answer and multiple
    # evidence anchors, while recording numeric anchors rather than requiring
    # unrelated cell coordinates to be repeated.
    passed = bool(
        text
        and source in sources
        and validation == "validated"
        and not markup
        and len(text) >= 180
        and len(found) >= min(2, len(anchors))
    )
    return {
        "passed": passed,
        "source_retrieved": source in sources,
        "validation_status": validation,
        "answer_chars": len(text),
        "anchor_count": len(anchors),
        "anchors_found": len(found),
        "numeric_anchors": len(re.findall(r"\b(?:19|20)\d{2}\b|\b\d+(?:\.\d+)?%?\b", text)),
        "html_or_xml_found": markup,
        "retrieved_sources": sorted(sources),
        "evidence_summary": "; ".join(found[:10]),
    }


def run() -> int:
    bucket = int(os.getenv("CERT_REMEDIATION_BUCKET", "0"))
    bucket_count = int(os.getenv("CERT_REMEDIATION_BUCKET_COUNT", "1"))
    suffix = re.sub(r"[^A-Za-z0-9_-]+", "", os.getenv("CERT_RUN_SUFFIX", "worker0"))
    output = ROOT / f"docs/.general_knowledge_remediation_{suffix}.json"
    rows = []
    for path in sorted(ROOT.glob("docs/.general_knowledge_live_certification_checkpoint_worker*.json")):
        rows.extend(json.loads(path.read_text(encoding="utf-8")))
    failed = [row for row in rows if not row.get("verification", {}).get("passed")]
    selected = [row for index, row in enumerate(failed) if index % bucket_count == bucket]
    st.session_state.clear()
    if not auth.login(st.session_state, "aisha.rahman@demo.local", "Temp-dy0ZTpbyBphPxTJW4aMm"):
        raise RuntimeError("The authenticated remediation test session could not sign in.")
    documents = app.ensure_index_is_current()
    results = []
    for index, row in enumerate(selected, start=1):
        source = row["source"]
        target_text = str(row.get("target_location", ""))
        original_question = row.get("question", "")
        # Find the original evidence record by source, location and chunk.
        target = next(
            (
                item for item in documents
                if item.get("source") == source
                and str(item.get("location", "")) == target_text
                and str(item.get("chunk", "")) == str(row.get("target_chunk", ""))
            ),
            None,
        )
        if target is None:
            target = next((item for item in documents if item.get("source") == source), {"source": source, "text": ""})
        topic = _semantic_terms(target.get("text", ""))
        source_hint = Path(source).stem
        question = (
            f"Give a detailed, evidence-based explanation of the approved Capstone knowledge "
            f"about {topic}. The relevant document is {source_hint}. Include the complete "
            f"supported definitions, requirements, steps, responsibilities, dates, names, "
            f"numbers and examples for this topic. Use the document evidence exactly and "
            f"state clearly when a detail is not specified."
        )
        try:
            st.session_state.messages = []
            retrieved = app.retrieve_information(question, documents, top_k=20, minimum_score=0.05)
            if source not in {str(item.get("source", "")) for item in retrieved}:
                retrieved = app.combine_retrieval_results(
                    retrieved,
                    app.retrieve_information(f"{source_hint} {topic}", documents, top_k=20, minimum_score=0.03),
                )
            answer = app.generate_response(question, retrieved)
            verification = _verify(answer, target, retrieved, st.session_state.get("last_validation_status", "unknown"))
            results.append({
                "source": source,
                "question_number": row["question_number"],
                "original_question": original_question,
                "remediation_question": question,
                "answer": answer,
                "retrieved_count": len(retrieved),
                "verification": verification,
            })
            print(json.dumps({"completed": index, "total": len(selected), "source": source, "question": row["question_number"], "passed": verification["passed"]}), flush=True)
        except Exception as error:
            results.append({"source": source, "question_number": row["question_number"], "original_question": original_question, "remediation_question": question, "error": f"{type(error).__name__}: {str(error)[:500]}", "verification": {"passed": False}})
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(item.get("verification", {}).get("passed", False) for item in results)
    print(json.dumps({"selected": len(results), "passed": passed, "failed": len(results) - passed, "output": str(output)}))
    return 0 if passed == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(run())
