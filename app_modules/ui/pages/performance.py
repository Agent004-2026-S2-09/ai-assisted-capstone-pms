## File: app_modules/ui/pages/performance.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Administrator AI and system performance page.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Administrator AI and system performance page."""

from collections import defaultdict
import json

import pandas as pd
import streamlit as st

from app_modules import access_control as access
from app_modules import monitoring
from app_modules import vector_store
from app_modules.ui.formatting import latency_ms, percentile
from app_modules.qa_benchmark import BENCHMARK_CASES, evaluate_case, summarise


def _json_object(value, fallback=None):
    """Safely decode bounded trace JSON for administrator display."""
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, (dict, list)) else (fallback or {})
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback if fallback is not None else {}


def _display_trace_value(value):
    """Return one stable, readable string for mixed trace values.

    Query-plan and evidence telemetry legitimately contains strings, numbers,
    booleans, lists and nested dictionaries.  Streamlit serialises dataframe
    columns through Apache Arrow, which requires one compatible type per
    column.  Converting only the diagnostic detail values keeps the stored
    JSON unchanged while preventing display-time ArrowTypeError warnings.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _render_query_trace_section(state, days):
    """Render the administrator query-trace tables at the bottom of the page."""
    st.divider()
    st.subheader("Query trace diagnostics")
    st.caption(
        "A stage-by-stage view of what happened during each AI query: planning, "
        "routing, retrieval, evidence, validation, security checks and outcome. "
        "This is administrator-only telemetry and does not include hidden model reasoning."
    )
    traces = monitoring.recent_query_traces(state, days, limit=200)
    if not traces:
        st.info("No query traces are available for this period yet.")
        return

    successful = sum(bool(row.get("success")) for row in traces)
    failed = len(traces) - successful
    cards = st.columns(4)
    cards[0].metric("Traced queries", len(traces))
    cards[1].metric("Successful", successful)
    cards[2].metric("Failed", failed)
    cards[3].metric(
        "Average traced latency",
        latency_ms(sum(int(row.get("latency_ms") or 0) for row in traces) / len(traces)),
    )

    overview = []
    for row in traces:
        overview.append({
            "Interaction": row.get("interaction_id"),
            "Time (UTC)": row.get("created_at"),
            "Role": row.get("user_role"),
            "Project": row.get("project_id") or "General Capstone",
            "Question": str(row.get("question_text") or "")[:240],
            "Route": row.get("route_source"),
            "Filter": row.get("route_filter"),
            "Outcome": row.get("final_status"),
            "Failure class": row.get("failure_class"),
            "Validation": row.get("validation_status"),
            "Evidence": row.get("result_count"),
            "Conflicts": row.get("conflict_count"),
            "Latency": latency_ms(row.get("latency_ms") or 0),
        })
    st.dataframe(
        overview,
        hide_index=True,
        width="stretch",
        height=360,
        alt="Recent administrator AI query trace overview",
    )

    choices = [
        f"{row.get('interaction_id')} · {str(row.get('question_text') or '')[:100]}"
        for row in traces
    ]
    selected_label = st.selectbox("Inspect one query trace", choices, key="ai_query_trace_selection")
    selected_index = choices.index(selected_label)
    selected = traces[selected_index]

    st.markdown("#### Selected query trace")
    st.dataframe(
        [{
            "Interaction": selected.get("interaction_id"),
            "Question": selected.get("question_text") or "",
            "Response": selected.get("response_text") or "",
            "Route": selected.get("route_source"),
            "Final status": selected.get("final_status"),
            "Failure class": selected.get("failure_class"),
            "Validation": selected.get("validation_status"),
            "Error": selected.get("error_type") or "",
        }],
        hide_index=True,
        width="stretch",
        alt="Selected AI query question and outcome",
    )

    timeline = _json_object(selected.get("timeline_json"), fallback=[])
    plan = _json_object(selected.get("query_plan_json"))
    evidence = _json_object(selected.get("evidence_json"))
    retrieval = _json_object(selected.get("retrieval_json"))
    security = _json_object(selected.get("security_json"))
    detail_columns = st.columns(2)
    with detail_columns[0]:
        st.markdown("#### Processing timeline")
        timeline_rows = [
            {str(key): _display_trace_value(value) for key, value in row.items()}
            for row in timeline
            if isinstance(row, dict)
        ]
        st.dataframe(
            timeline_rows or [{"stage": "No stage detail recorded"}],
            hide_index=True,
            width="stretch",
            alt="Selected query processing timeline",
        )
        st.markdown("#### Query plan")
        st.dataframe(
            [{"Field": str(key), "Value": _display_trace_value(value)} for key, value in plan.items()]
            or [{"Field": "Status", "Value": "No plan detail recorded"}],
            hide_index=True,
            width="stretch",
            alt="Selected query plan fields",
        )
    with detail_columns[1]:
        st.markdown("#### Evidence and retrieval")
        detail_rows = []
        for label, payload in (("Evidence", evidence), ("Retrieval", retrieval), ("Security", security)):
            for key, value in payload.items():
                detail_rows.append({
                    "Area": label,
                    "Field": str(key),
                    "Value": _display_trace_value(value),
                })
        st.dataframe(
            detail_rows or [{"Area": "Status", "Field": "Detail", "Value": "No detail recorded"}],
            hide_index=True,
            width="stretch",
            alt="Selected query evidence retrieval and security details",
        )
    if selected.get("notes"):
        st.caption(f"Trace notes: {selected['notes']}")

def render(state, render_recent_usage):
    """
    Function: render
    Purpose: Execute the render operation.
    Inputs:
            state (value): Caller-provided input.
            render_recent_usage (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    access.require_admin(state)
    st.title("AI and system performance")
    st.caption("Monitor reliability, response quality and AI service performance.")
    days = st.selectbox("Time range", [7, 30, 90], index=1, format_func=lambda value: f"Last {value} days")
    metrics = monitoring.dashboard_metrics(state, days)
    api_metrics = monitoring.api_service_metrics(state, days)
    retrieval_metrics = monitoring.retrieval_quality_metrics(state, days)
    rag_metrics = monitoring.rag_quality_metrics(state, days)
    embedding_metrics = vector_store.health()
    requests_count = int(metrics["requests"])
    successful = int(metrics["successful"])
    feedback_total = int(metrics["helpful"]) + int(metrics["not_helpful"])
    success_rate = (successful / requests_count * 100) if requests_count else 0
    helpful_rate = (int(metrics["helpful"]) / feedback_total * 100) if feedback_total else 0

    first = st.columns(4)
    first[0].metric("AI requests", requests_count)
    first[1].metric("Successful", successful)
    first[2].metric("Failed", int(metrics["failed"]))
    first[3].metric("Average response time", latency_ms(metrics["avg_latency"]))
    second = st.columns(4)
    second[0].metric("Helpful", int(metrics["helpful"]))
    second[1].metric("Not helpful", int(metrics["not_helpful"]))
    second[2].metric("Grounded accuracy", f"{float(metrics['grounded_accuracy']):.2f}/5")
    second[3].metric("Hallucinations", int(metrics["hallucinations"]))
    st.caption(
        f"Average evaluated usability: {float(metrics['usability']):.2f}/5 "
        f"across {int(metrics['evaluations'])} evaluation(s)."
    )
    st.progress(min(1.0, success_rate / 100), text=f"AI service success rate: {success_rate:.1f}%")
    st.caption(f"Helpful-response rate: {helpful_rate:.1f}% across {feedback_total} submitted ratings.")

    st.subheader("Response latency")
    series = monitoring.latency_series(state, days)
    if series:
        latency_values = [int(row["latency_ms"]) for row in series]
        latency_chart = pd.DataFrame(
            {
                "Time (UTC)": [pd.to_datetime(row["created_at"], utc=True).tz_convert(None) for row in series],
                "Response time (seconds)": [round(int(row["latency_ms"]) / 1000, 3) for row in series],
            }
        )
        st.line_chart(
            latency_chart,
            x="Time (UTC)",
            y="Response time (seconds)",
            x_label="When the response occurred (UTC)",
            y_label="Response time (seconds)",
            alt="AI response latency over time",
        )
        by_mode = defaultdict(list)
        for row in series:
            by_mode[row["assistant_mode"]].append(int(row["latency_ms"]))
        st.dataframe(
            [{"Assistant mode": mode, "Requests": len(values), "Average response time": latency_ms(sum(values) / len(values)),
              "Median response time": latency_ms(percentile(values, 0.5)), "95th percentile": latency_ms(percentile(values, 0.95))}
             for mode, values in sorted(by_mode.items())],
            hide_index=True,
            alt="Response time summary by assistant mode",
        )
        st.caption(f"Overall median: {latency_ms(percentile(latency_values, 0.5))} · 95th percentile: {latency_ms(percentile(latency_values, 0.95))}")
    else:
        st.info("No successful AI interactions are available for this period.")

    st.subheader("Recent failed AI interactions")
    errors = monitoring.recent_errors(state)
    if errors:
        st.dataframe(errors, hide_index=True)
    else:
        st.info("No failed AI interactions recorded.")

    st.subheader("Recent response feedback")
    feedback = monitoring.recent_feedback(state, days)
    if feedback:
        st.dataframe(
            [{**row, "rating": "Helpful" if row["rating"] == 1 else "Not helpful"} for row in feedback],
            hide_index=True,
        )
    else:
        st.info("No feedback has been submitted for this period.")
    st.divider()
    st.subheader("API service monitoring")
    api_cards = st.columns(5)
    api_cards[0].metric("Provider calls", int(api_metrics["requests"]))
    api_cards[1].metric("Provider success", f"{(int(api_metrics['successful']) / int(api_metrics['requests']) * 100) if api_metrics['requests'] else 0:.1f}%")
    api_cards[2].metric("Average API latency", f"{int(api_metrics['avg_latency']):,} ms")
    api_cards[3].metric("Total tokens", f"{int(api_metrics['total_tokens']):,}")
    api_cards[4].metric("API failures", int(api_metrics["failed"]))
    if api_metrics["stages"]:
        st.dataframe(api_metrics["stages"], hide_index=True, width="stretch")
    else:
        st.info("No provider API telemetry is available for this period.")

    st.divider()
    render_recent_usage()

    st.subheader("Retrieval quality")
    retrieval_cards = st.columns(5)
    retrieval_cards[0].metric("Searches", int(retrieval_metrics["searches"]))
    retrieval_cards[1].metric("No-match rate", f"{float(retrieval_metrics['no_match_rate']):.1f}%")
    retrieval_cards[2].metric("Average results", f"{float(retrieval_metrics['avg_results']):.1f}")
    retrieval_cards[3].metric("Average top score", f"{float(retrieval_metrics['avg_top_score']):.3f}")
    retrieval_cards[4].metric("Average search time", f"{int(retrieval_metrics['avg_latency']):,} ms")
    if retrieval_metrics["daily"]:
        st.line_chart(
            pd.DataFrame(
                {
                    "Date": [row["day"] for row in retrieval_metrics["daily"]],
                    "No-match searches": [int(row["no_match"]) for row in retrieval_metrics["daily"]],
                }
            ),
            x="Date",
            y="No-match searches",
            x_label="Date",
            y_label="Number of searches",
            alt="Daily retrieval searches with no matching results",
        )
    else:
        st.info("No retrieval-quality telemetry is available for this period.")

    st.subheader("RAG diagnostic quality")
    rag_cards = st.columns(4)
    rag_cards[0].metric("Diagnostic answers", int(rag_metrics["diagnostics"]))
    rag_cards[1].metric("Relevant evidence", f"{float(rag_metrics['relevance_rate']):.1f}%")
    rag_cards[2].metric("Sufficient context", f"{float(rag_metrics['evidence_sufficiency_rate']):.1f}%")
    rag_cards[3].metric("Clean RAG answers", f"{float(rag_metrics['clean_rate']):.1f}%")
    if rag_metrics["classes"]:
        st.dataframe(
            [{"Diagnostic": item["failure_class"], "Count": int(item["count"])} for item in rag_metrics["classes"]],
            hide_index=True,
            width="stretch",
        )
        diagnostic_rows = monitoring.recent_rag_diagnostics(state, days)
        if diagnostic_rows:
            with st.expander("Recent RAG diagnostic details"):
                st.dataframe(diagnostic_rows, hide_index=True, width="stretch")
    else:
        st.info("No RAG diagnostics have been recorded for this period yet.")

    st.subheader("SQLite vector embedding index")
    embedding_cards = st.columns(4)
    embedding_cards[0].metric("Embedded documents", int(embedding_metrics["document_count"]))
    embedding_cards[1].metric("Embedding model", embedding_metrics["model_name"])
    embedding_cards[2].metric("Vector dimensions", int(embedding_metrics["dimensions"]))
    embedding_cards[3].metric("Embedding models", int(embedding_metrics["model_count"]))
    last_run = embedding_metrics.get("last_run")
    if last_run:
        st.caption(
            f"Last {last_run['scope']} embedding run: {last_run['document_count']:,} documents · "
            f"{last_run['duration_ms']:,} ms · {last_run['created_at']}"
        )

    st.divider()
    st.subheader("Offline retrieval benchmark")
    st.caption(
        "Run the deterministic benchmark against the current approved knowledge index. "
        "This measures retrieval quality only; it does not call the AI provider."
    )
    if st.button("Run retrieval benchmark", type="secondary"):
        import app

        documents = app.ensure_index_is_current()
        benchmark_results = []
        for case in BENCHMARK_CASES:
            retrieved = (
                app.retrieve_broad_overview(case.question, documents)
                if app.is_broad_overview_question(case.question)
                else app.retrieve_information(case.question, documents, top_k=10)
            )
            benchmark_results.append(evaluate_case(case, retrieved))
        st.session_state.retrieval_benchmark_report = {
            "summary": summarise(benchmark_results),
            "cases": benchmark_results,
        }
    report = st.session_state.get("retrieval_benchmark_report")
    if report:
        summary = report["summary"]
        cards = st.columns(4)
        cards[0].metric("Cases passed", f"{summary['passed']}/{summary['total']}")
        cards[1].metric("MRR", f"{summary['mrr']:.3f}")
        cards[2].metric("nDCG", f"{summary['ndcg']:.3f}")
        cards[3].metric("Keyword coverage", f"{summary['keyword_coverage']:.1%}")
        st.dataframe(
            [
                {
                    "Case": item["name"],
                    "Category": item["category"],
                    "Passed": item["passed"],
                    "MRR": item["mrr"],
                    "nDCG": item["ndcg"],
                    "Keyword coverage": item["keyword_coverage"],
                    "Results": item["result_count"],
                }
                for item in report["cases"]
            ],
            hide_index=True,
            width="stretch",
        )

    # Keep the detailed trace section at the very bottom so existing
    # performance, RAG and benchmark panels retain their current layout.
    _render_query_trace_section(state, days)
