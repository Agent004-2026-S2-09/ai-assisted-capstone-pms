## File: app_modules/export_ui.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Answer export controls for the assistant conversation.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Answer export controls for the assistant conversation."""

import re

import streamlit as st


FORMATS = {"PDF": "pdf", "Word": "docx", "PowerPoint": "pptx", "Excel": "xlsx"}
MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

_FORMAT_ALIASES = {"pdf": "pdf", "word": "docx", "docx": "docx", "powerpoint": "pptx", "pptx": "pptx", "excel": "xlsx", "xlsx": "xlsx"}
_EXPORT_ACTIONS = r"export|download|save|prepare|generate|produce|create|make"
_TRAILING_EXPORT_ACTIONS = r"export|download|save|prepare"
_EXPORT_OBJECTS = r"answer|response|result|document|file|report|copy|brief|summary"
_FORMAT_WORDS = r"pdf|word|docx|powerpoint|pptx|excel|xlsx"


def detect_export_intent(text):
    """
    Function: detect_export_intent
    Purpose: Execute the detect export intent operation.
    Inputs:
            text (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    value = str(text or "").casefold()
    format_match = re.search(rf"\b({_FORMAT_WORDS})\b", value)
    has_action = bool(re.search(rf"\b(?:{_EXPORT_ACTIONS})\b", value))
    has_export_word = bool(re.search(r"\bexport(?:ed|ing)?\b", value))
    has_object = bool(re.search(rf"\b(?:{_EXPORT_OBJECTS})s?\b", value))
    requested = has_export_word or (has_action and format_match is not None) or (has_action and has_object and bool(re.search(r"\b(?:as|to|in)\b", value)))
    return {"requested": requested, "format": _FORMAT_ALIASES.get(format_match.group(1)) if format_match else None}


def split_trailing_export_request(text):
    """
    Function: split_trailing_export_request
    Purpose: Execute the split trailing export request operation.
    Inputs:
            text (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    match = re.search(
        rf"\s+(?:and\s+)?(?:{_TRAILING_EXPORT_ACTIONS})\b.*?\b(?:to|as|in)\s+({_FORMAT_WORDS})\b(?:\s+(?:file|document|format))?\s*$",
        str(text or ""), flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    return {"question": text[: match.start()].strip(), "format": _FORMAT_ALIASES[match.group(1).casefold()]}


def is_export_only_request(text):
    """
    Function: is_export_only_request
    Purpose: Execute the is export only request operation.
    Inputs:
            text (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return bool(re.fullmatch(
        rf"\s*(?:please\s+)?(?:{_EXPORT_ACTIONS})\b(?:\s+(?:this|the|latest|previous|current))*"
        rf"(?:\s+(?:answer|response|result|document|file|report|copy))?(?:\s+(?:to|as|in))?"
        rf"(?:\s+(?:a\s+|an\s+)?({_FORMAT_WORDS}))(?:\s+(?:file|document|format))?\s*",
        str(text or ""), flags=re.IGNORECASE,
    ))


def prepare_export(answer, format_name, *, question="", project_name=""):
    """
    Function: prepare_export
    Purpose: Execute the prepare export operation.
    Inputs:
            answer (value): Caller-provided input.
            format_name (value): Caller-provided input.
            question (value): Caller-provided input.
            project_name (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    from app_modules.exporting import build_export, format_with_agentaus

    structured = format_with_agentaus(answer, format_name=format_name, question=question, project_name=project_name)
    data, extension = build_export(structured, format_name)
    return data, extension, structured["title"]


def render_export(message, *, question="", project_name="", identity="0"):
    """
    Function: render_export
    Purpose: Execute the render export operation.
    Inputs:
            message (value): Caller-provided input.
            question (value): Caller-provided input.
            project_name (value): Caller-provided input.
            identity (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    answer = str(message.get("content", "")).strip()
    if not answer:
        return
    with st.expander("Export this answer", expanded=False):
        st.caption("Agentaus will organise the answer for your selected file format before export.")
        key_suffix = str(identity).replace("-", "_")
        label = st.selectbox("File format", list(FORMATS), key=f"export_format_{key_suffix}")
        format_name = FORMATS[label]
        if st.button("Format and prepare download", key=f"prepare_export_{key_suffix}", type="primary"):
            try:
                with st.spinner(f"Agentaus is formatting your answer for {label}..."):
                    data, extension, title = prepare_export(answer, format_name, question=question, project_name=project_name)
                st.session_state[f"export_{key_suffix}"] = {"data": data, "extension": extension, "label": label, "title": title}
                st.success(f"{label} export is ready.")
            except Exception:
                st.error("The answer could not be formatted for export. Please try again shortly.")
        prepared = st.session_state.get(f"export_{key_suffix}")
        if prepared and prepared.get("extension") == format_name:
            st.download_button(
                f"Download {prepared['label']}",
                data=prepared["data"],
                file_name=f"capstone-assistant-answer.{prepared['extension']}",
                mime=MIME_TYPES[prepared["extension"]],
                key=f"download_export_{key_suffix}",
                width="stretch",
            )
