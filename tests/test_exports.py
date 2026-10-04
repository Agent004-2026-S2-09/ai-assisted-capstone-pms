"""Response export format and intent regression tests."""

import zipfile
from io import BytesIO

from exporting import build_export
from export_ui import detect_export_intent, is_export_only_request, split_trailing_export_request


DOCUMENT = {
    "title": "Project response",
    "summary": "A short summary.",
    "sections": [
        {
            "heading": "Next steps",
            "body": "Review the approved plan.",
            "bullets": ["Confirm scope", "Record decisions"],
            "table": [["Item", "Owner"], ["Scope", "Team"]],
        }
    ],
}


def test_all_export_formats_produce_downloadable_bytes():
    outputs = {format_name: build_export(DOCUMENT, format_name)[0] for format_name in ("docx", "xlsx", "pptx", "pdf")}
    assert all(outputs.values())
    assert outputs["pdf"].startswith(b"%PDF")
    for format_name in ("docx", "xlsx", "pptx"):
        with zipfile.ZipFile(BytesIO(outputs[format_name])) as archive:
            assert archive.namelist()


def test_export_intent_supports_natural_language_phrasings():
    assert detect_export_intent("Download this as a Word document")["format"] == "docx"
    assert detect_export_intent("Save the answer to PDF")["format"] == "pdf"
    assert detect_export_intent("Prepare a PowerPoint version")["format"] == "pptx"
    assert detect_export_intent("Create an Excel copy")["format"] == "xlsx"
    assert is_export_only_request("download the previous answer as a Word document")
    assert split_trailing_export_request("Summarise the milestones and download it as PDF") == {
        "question": "Summarise the milestones",
        "format": "pdf",
    }
