"""Response export format and intent regression tests."""

import zipfile
from io import BytesIO

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader
from pptx import Presentation

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


def test_pdf_preserves_unicode_punctuation_and_bullets():
    document = {
        "title": "Unicode export",
        "summary": "TensorRT‑accelerated project using a non‑breaking space and dash.",
        "sections": [{
            "heading": "Next steps",
            "body": "Review the approved plan.",
            "bullets": ["Confirm scope", "Record decisions"],
            "table": [["Item", "Owner"], ["Scope", "Capstone team"]],
        }],
    }
    data, _ = build_export(document, "pdf")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)
    assert "TensorRT‑accelerated" in text
    assert "■" not in text


def test_xlsx_keeps_table_fields_in_separate_columns():
    data, _ = build_export(DOCUMENT, "xlsx")
    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    table_sheet = workbook["Table 1 - Next steps"]
    assert list(table_sheet.values) == [
        ("Item", "Owner"),
        ("Scope", "Team"),
    ]


def test_docx_and_pptx_keep_native_structure():
    docx_data, _ = build_export(DOCUMENT, "docx")
    word = Document(BytesIO(docx_data))
    assert len(word.tables) == 1
    assert [[cell.text for cell in row.cells] for row in word.tables[0].rows] == [
        ["Item", "Owner"],
        ["Scope", "Team"],
    ]

    pptx_data, _ = build_export(DOCUMENT, "pptx")
    presentation = Presentation(BytesIO(pptx_data))
    tables = [shape.table for slide in presentation.slides for shape in slide.shapes if shape.has_table]
    assert len(tables) == 1
    assert tables[0].cell(0, 0).text == "Item"
    assert tables[0].cell(1, 1).text == "Team"


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
