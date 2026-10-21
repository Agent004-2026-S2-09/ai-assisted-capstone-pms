## File: app_modules/ui/pages/prompt_intelligence.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Administrator prompt intelligence page.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Administrator prompt intelligence page."""

from collections import Counter

import pandas as pd
import streamlit as st

from app_modules import access_control as access
from app_modules import monitoring
from app_modules.ui.formatting import latency_ms, timestamp


def render(state):
    """
    Function: render
    Purpose: Execute the render operation.
    Inputs:
            state (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    access.require_admin(state)
    st.title("Prompt and topic intelligence")
    st.caption("Use submitted questions to identify documentation and assistant improvements.")
    days = st.select_slider(
        "Analysis window",
        options=[7, 30, 90, 180],
        value=30,
        format_func=lambda value: f"Last {value} days",
    )
    rows = monitoring.prompt_analytics(state, days)
    if not rows:
        st.info("No captured prompts are available for this period yet.")
        return

    topics = monitoring.summarise_prompt_topics(rows, 10)
    all_topics = monitoring.summarise_prompt_topics(rows, 1000)
    metrics = st.columns(4)
    metrics[0].metric("Questions captured", f"{len(rows):,}")
    metrics[1].metric("Average prompt length", f"{round(sum(len(row['question_text']) for row in rows) / len(rows))} chars")
    metrics[2].metric("Active roles", len({row["user_role"] for row in rows}))
    metrics[3].metric("Intent categories", len(all_topics))

    themes, trends, explorer = st.tabs(["Question themes", "Trends", "Prompt explorer"])
    with themes:
        if topics:
            st.subheader("Frequently requested topics and intents")
            st.bar_chart(
                pd.DataFrame(topics),
                x="Topic",
                y="Questions",
                x_label="Topic",
                y_label="Number of questions",
                alt="Frequently requested assistant topics by question count",
            )
        st.subheader("Frequently requested topics table")
        st.dataframe(
            topics,
            hide_index=True,
            alt="Frequently requested assistant topics, question counts and representative questions",
        )
        st.caption(
            "Each question is assigned to the first matching administrator-facing intent category. "
            "The example helps validate the grouping."
        )
        st.write("Documentation opportunities: " + ", ".join(row["Topic"] for row in topics[:8]) + ".")

    with trends:
        daily = Counter(row["created_at"][:10] for row in rows)
        by_role = Counter(row["user_role"] for row in rows)
        by_mode = Counter(row["assistant_mode"] for row in rows)
        st.subheader("Questions over time")
        questions_over_time = pd.DataFrame(
            {
                "Date": [pd.to_datetime(key).date() for key in sorted(daily)],
                "Questions": [daily[key] for key in sorted(daily)],
            }
        )
        st.line_chart(
            questions_over_time,
            x="Date",
            y="Questions",
            x_label="Date",
            y_label="Number of questions",
            alt="Questions captured per day",
        )
        st.subheader("Questions by role")
        st.dataframe(
            [{"Role": key, "Questions": value} for key, value in sorted(by_role.items())],
            hide_index=True,
            alt="Questions grouped by user role",
        )
        st.subheader("General versus project-specific")
        st.dataframe(
            [{"Mode": key, "Questions": value} for key, value in sorted(by_mode.items())],
            hide_index=True,
            alt="Questions grouped by assistant mode",
        )

    with explorer:
        st.subheader("Captured prompts")
        roles = sorted({row["user_role"] for row in rows})
        selected_roles = st.multiselect("Filter by role", roles)
        filtered = rows if not selected_roles else [row for row in rows if row["user_role"] in selected_roles]
        st.dataframe(
            [
                {
                    "Time (UTC)": timestamp(row["created_at"]),
                    "Role": row["user_role"],
                    "Mode": row["assistant_mode"],
                    "Question": row["question_text"],
                    "Response time": latency_ms(row["latency_ms"]),
                }
                for row in filtered
            ],
            hide_index=True,
            alt="Captured prompts with time, role, mode and response time",
        )
