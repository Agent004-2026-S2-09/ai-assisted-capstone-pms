"""AI-assisted response formatting and native document exporters."""

import json
import re
from io import BytesIO
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pptx import Presentation
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


FORMAT_LABELS = {"pdf": "PDF", "docx": "Word", "pptx": "PowerPoint", "xlsx": "Excel"}


def _fallback(answer):
    return {
        "title": "Capstone Assistant Response",
        "summary": "",
        "sections": [{"heading": "Response", "body": answer, "bullets": [], "table": []}],
    }


def _parse_document(text, answer):
    candidate = str(text or "").strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    try:
        start, end = candidate.find("{"), candidate.rfind("}")
        data = json.loads(candidate[start : end + 1]) if start >= 0 and end > start else None
    except (TypeError, ValueError, json.JSONDecodeError):
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        return _fallback(answer)
    sections = []
    for item in data["sections"]:
        if not isinstance(item, dict):
            continue
        sections.append(
            {
                "heading": str(item.get("heading") or "Section").strip(),
                "body": str(item.get("body") or "").strip(),
                "bullets": [str(value).strip() for value in item.get("bullets", []) if str(value).strip()],
                "table": item.get("table") if isinstance(item.get("table"), list) else [],
            }
        )
    return {
        "title": str(data.get("title") or "Capstone Assistant Response").strip(),
        "summary": str(data.get("summary") or "").strip(),
        "sections": sections or _fallback(answer)["sections"],
    }


def format_with_agentaus(answer, *, format_name, question="", project_name=""):
    """Create a structured export representation without adding facts."""
    if format_name not in FORMAT_LABELS:
        raise ValueError("Unsupported export format.")
    from app import call_agentaus, extract_agentaus_text, record_api_usage

    label = FORMAT_LABELS[format_name]
    messages = [
        {
            "role": "system",
            "content": f"""
You are a document-formatting editor for the UC Canberra Capstone Assistant.
Reformat the supplied answer for a polished {label} export. Preserve every
fact, qualification, date, name and number exactly. Never add information,
citations, filenames or claims. Remove chat filler and organise the answer
into a useful title, short summary and sections. Return JSON only in this
shape:
{{"title":"...","summary":"...","sections":[{{"heading":"...","body":"...","bullets":["..."],"table":[["Column","Column"],["value","value"]]}}]}}
Use an empty array when a section has no bullets or table. Keep table rows
short and consistent. The project name is {project_name or 'General Capstone'}.
""",
        },
        {"role": "user", "content": f"Question: {question}\n\nAnswer to format:\n{answer}"},
    ]
    result = call_agentaus(messages)
    record_api_usage(result, "export_formatting")
    return _parse_document(extract_agentaus_text(result), answer)


def _plain(value):
    return re.sub(r"[*_`#]", "", str(value or "")).strip()


def export_docx(document):
    doc = Document()
    title = doc.add_heading(_plain(document["title"]), level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if document.get("summary"):
        paragraph = doc.add_paragraph(_plain(document["summary"]))
        paragraph.style = doc.styles["Subtitle"]
    for section in document["sections"]:
        doc.add_heading(_plain(section["heading"]), level=1)
        if section.get("body"):
            doc.add_paragraph(_plain(section["body"]))
        for bullet in section.get("bullets", []):
            doc.add_paragraph(_plain(bullet), style="List Bullet")
        rows = section.get("table") or []
        if rows:
            table = doc.add_table(rows=0, cols=max(len(row) for row in rows))
            table.style = "Light Shading Accent 1"
            for row in rows:
                cells = table.add_row().cells
                for index, value in enumerate(row):
                    cells[index].text = _plain(value)
    output = BytesIO()
    doc.save(output)
    return output.getvalue(), "docx"


def export_xlsx(document):
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Summary"
    summary.append([_plain(document["title"])])
    summary.append([_plain(document.get("summary", ""))])
    summary["A1"].font = Font(size=18, bold=True, color="FFFFFF")
    summary["A1"].fill = PatternFill("solid", fgColor="1F4E78")
    summary["A1"].alignment = Alignment(wrap_text=True)
    summary.column_dimensions["A"].width = 110
    summary["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet = workbook.create_sheet("Sections")
    sheet.append(["Section", "Content", "Type"])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
    for section in document["sections"]:
        if section.get("body"):
            sheet.append([_plain(section["heading"]), _plain(section["body"]), "Body"])
        for bullet in section.get("bullets", []):
            sheet.append([_plain(section["heading"]), _plain(bullet), "Bullet"])
        for row in section.get("table") or []:
            sheet.append([_plain(section["heading"]), " | ".join(_plain(value) for value in row), "Table"])
    sheet.column_dimensions["A"].width = 30
    sheet.column_dimensions["B"].width = 100
    sheet.column_dimensions["C"].width = 14
    for row in sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    output = BytesIO()
    workbook.save(output)
    return output.getvalue(), "xlsx"


def export_pptx(document):
    presentation = Presentation()
    presentation.core_properties.title = _plain(document["title"])
    slide = presentation.slides.add_slide(presentation.slide_layouts[0])
    slide.shapes.title.text = _plain(document["title"])
    slide.placeholders[1].text = _plain(document.get("summary", "Capstone Assistant response"))
    for section in document["sections"]:
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = _plain(section["heading"])
        frame = slide.placeholders[1].text_frame
        frame.clear()
        if section.get("body"):
            frame.paragraphs[0].text = _plain(section["body"])
        for bullet in section.get("bullets", []):
            paragraph = frame.add_paragraph()
            paragraph.text = _plain(bullet)
            paragraph.level = 0
        for row in section.get("table") or []:
            paragraph = frame.add_paragraph()
            paragraph.text = " | ".join(_plain(value) for value in row)
    output = BytesIO()
    presentation.save(output)
    return output.getvalue(), "pptx"


def export_pdf(document):
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ExportTitle", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#1F4E78"), spaceAfter=12))
    styles.add(ParagraphStyle(name="ExportHeading", parent=styles["Heading2"], textColor=colors.HexColor("#1F4E78"), spaceBefore=12, spaceAfter=6))
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    story = [Paragraph(escape(_plain(document["title"])), styles["ExportTitle"])]
    if document.get("summary"):
        story += [Paragraph(escape(_plain(document["summary"])), styles["BodyText"]), Spacer(1, 8)]
    for section in document["sections"]:
        story.append(Paragraph(escape(_plain(section["heading"])), styles["ExportHeading"]))
        if section.get("body"):
            story.append(Paragraph(escape(_plain(section["body"])), styles["BodyText"]))
        for bullet in section.get("bullets", []):
            story.append(Paragraph("• " + escape(_plain(bullet)), styles["BodyText"]))
        rows = section.get("table") or []
        if rows:
            table = Table([[escape(_plain(value)) for value in row] for row in rows], repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            story += [Spacer(1, 5), table]
    doc.build(story)
    return output.getvalue(), "pdf"


def build_export(document, format_name):
    exporters = {"pdf": export_pdf, "docx": export_docx, "pptx": export_pptx, "xlsx": export_xlsx}
    if format_name not in exporters:
        raise ValueError("Unsupported export format.")
    return exporters[format_name](document)
