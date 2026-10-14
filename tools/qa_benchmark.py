#!/usr/bin/env python3
"""Run the offline retrieval benchmark against the current general index."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from app_modules.qa_benchmark import BENCHMARK_CASES, evaluate_case, summarise  # noqa: E402


def run() -> dict:
    documents = app.load_index()
    results = []
    for case in BENCHMARK_CASES:
        retrieved = (
            app.retrieve_broad_overview(case.question, documents)
            if app.is_broad_overview_question(case.question)
            else app.retrieve_information(case.question, documents, top_k=10)
        )
        results.append(evaluate_case(case, retrieved))
    return {"summary": summarise(results), "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args()
    report = run()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        summary = report["summary"]
        print(f"QA retrieval benchmark: {summary['passed']}/{summary['total']} passed ({summary['accuracy']:.0%})")
        for category, values in summary["by_category"].items():
            print(f"  {category}: {values['passed']}/{values['total']}")
        for case in report["cases"]:
            marker = "PASS" if case["passed"] else "FAIL"
            print(f"{marker:4} {case['name']}: {case['result_count']} results")
            if not case["passed"]:
                print(f"      sources={case['sources']} types={case['record_types']}")
                print(f"      checks={case['checks']}")
        print(
            f"Retrieval metrics: MRR={summary['mrr']:.3f} · "
            f"nDCG={summary['ndcg']:.3f} · "
            f"keyword coverage={summary['keyword_coverage']:.1%}"
        )
    return 0 if report["summary"]["accuracy"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
