## File: app_modules/exporting.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: AI-assisted response formatting and native document exporters.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""AI-assisted response formatting and native document exporters."""

import json
import re
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table as ExcelTable, TableStyleInfo
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches as PptxInches, Pt as PptxPt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


FORMAT_LABELS = {"pdf": "PDF", "docx": "Word", "pptx": "PowerPoint", "xlsx": "Excel"}


def _register_pdf_fonts():
    """Register a Unicode font so exported PDFs preserve AI-generated punctuation."""
    candidates = (
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    )
    for regular_path, bold_path in candidates:
        if Path(regular_path).exists() and Path(bold_path).exists():
            if "ExportUnicode" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("ExportUnicode", regular_path))
                pdfmetrics.registerFont(TTFont("ExportUnicode-Bold", bold_path))
            return "ExportUnicode", "ExportUnicode-Bold"
    return "Helvetica", "Helvetica-Bold"


def _fallback(answer):
    """
    Function: _fallback
    Purpose: Execute the  fallback operation.
    Inputs:
            answer (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return {
        "title": "Capstone Assistant Response",
        "summary": "",
        "sections": [{"heading": "Response", "body": answer, "bullets": [], "table": []}],
    }


def _parse_document(text, answer):
    """
    Function: _parse_document
    Purpose: Execute the  parse document operation.
    Inputs:
            text (value): Caller-provided input.
            answer (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
    """
    Function: _plain
    Purpose: Execute the  plain operation.
    Inputs:
            value (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return re.sub(r"[*_`#]", "", str(value or "")).strip()


def _normalised_rows(rows):
    """Return rectangular, cleaned table rows for all exporters."""
    rows = [list(row) for row in rows if isinstance(row, (list, tuple))]
    if not rows:
        return []
    width = max(len(row) for row in rows)
    return [[_plain(value) for value in row] + [""] * (width - len(row)) for row in rows]


def export_docx(document):
    """
    Function: export_docx
    Purpose: Execute the export docx operation.
    Inputs:
            document (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)
    normal = doc.styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10.5)
    title = doc.add_heading(_plain(document["title"]), level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.runs[0].font.name = "Aptos Display"
    title.runs[0].font.size = Pt(24)
    if document.get("summary"):
        paragraph = doc.add_paragraph(_plain(document["summary"]))
        paragraph.style = doc.styles["Subtitle"]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for section in document["sections"]:
        doc.add_heading(_plain(section["heading"]), level=1)
        if section.get("body"):
            paragraph = doc.add_paragraph(_plain(section["body"]))
            paragraph.paragraph_format.space_after = Pt(6)
        for bullet in section.get("bullets", []):
            doc.add_paragraph(_plain(bullet), style="List Bullet")
        rows = _normalised_rows(section.get("table") or [])
        if rows:
            table = doc.add_table(rows=1, cols=len(rows[0]))
            table.style = "Light Shading Accent 1"
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.autofit = True
            header_cells = table.rows[0].cells
            for index, value in enumerate(rows[0]):
                header_cells[index].text = value
            for row in rows[1:]:
                cells = table.add_row().cells
                for index, value in enumerate(row):
                    cells[index].text = value
            for row in table.rows:
                for cell in row.cells:
                    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
                    for paragraph in cell.paragraphs:
                        paragraph.paragraph_format.space_after = Pt(0)
            # Repeat the header when a table spans multiple Word pages.
            header_properties = table.rows[0]._tr.get_or_add_trPr()
            from docx.oxml import OxmlElement
            header_properties.append(OxmlElement("w:tblHeader"))
    output = BytesIO()
    doc.save(output)
    return output.getvalue(), "docx"


def export_xlsx(document):
    """
    Function: export_xlsx
    Purpose: Execute the export xlsx operation.
    Inputs:
            document (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    workbook = Workbook()
    workbook.properties.title = _plain(document["title"])
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
    sheet.column_dimensions["A"].width = 30
    sheet.column_dimensions["B"].width = 100
    sheet.column_dimensions["C"].width = 14
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for row in sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # Keep structured answer tables useful for filtering, sorting, and importing:
    # each table gets its own worksheet and each source field remains a column.
    used_titles = set(workbook.sheetnames)
    for table_number, section in enumerate(document["sections"], start=1):
        rows = _normalised_rows(section.get("table") or [])
        if not rows:
            continue
        base_title = re.sub(r"[^A-Za-z0-9 _-]", "", _plain(section["heading"]))[:24].strip() or "Table"
        title = f"Table {table_number} - {base_title}"[:31]
        suffix = 2
        while title in used_titles:
            suffix_text = f" ({suffix})"
            title = f"{base_title[:31 - len(suffix_text)]}{suffix_text}"
            suffix += 1
        used_titles.add(title)
        table_sheet = workbook.create_sheet(title)
        for row_number, row in enumerate(rows, start=1):
            for column_number, value in enumerate(row, start=1):
                cell = table_sheet.cell(row=row_number, column=column_number, value=_plain(value))
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                if row_number == 1:
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = PatternFill("solid", fgColor="1F4E78")
        column_count = len(rows[0])
        for column_number in range(1, column_count + 1):
            values = [str(table_sheet.cell(row=row_number, column=column_number).value or "") for row_number in range(1, table_sheet.max_row + 1)]
            table_sheet.column_dimensions[table_sheet.cell(row=1, column=column_number).column_letter].width = min(max(max(map(len, values), default=12) + 2, 12), 50)
        table_sheet.freeze_panes = "A2"
        excel_table = ExcelTable(displayName=f"ExportTable{table_number}", ref=table_sheet.dimensions)
        excel_table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=False)
        table_sheet.add_table(excel_table)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue(), "xlsx"


def _pptx_title(slide, text, *, size=26):
    """
    Function: _pptx_title
    Purpose: Execute the  pptx title operation.
    Inputs:
            slide (value): Caller-provided input.
            text (value): Caller-provided input.
            size (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    shape = slide.shapes.add_textbox(PptxInches(0.55), PptxInches(0.25), PptxInches(12.2), PptxInches(0.55))
    frame = shape.text_frame
    frame.clear()
    paragraph = frame.paragraphs[0]
    paragraph.text = _plain(text)
    paragraph.font.size = PptxPt(size)
    paragraph.font.bold = True
    paragraph.font.color.rgb = RGBColor(31, 78, 121)
    return shape


def _pptx_content_slide(presentation, section):
    """
    Function: _pptx_content_slide
    Purpose: Execute the  pptx content slide operation.
    Inputs:
            presentation (value): Caller-provided input.
            section (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    _pptx_title(slide, section["heading"])
    shape = slide.shapes.add_textbox(PptxInches(0.7), PptxInches(1.05), PptxInches(11.9), PptxInches(5.9))
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = PptxInches(0.08)
    frame.margin_right = PptxInches(0.08)
    items = []
    if section.get("body"):
        items.append((_plain(section["body"]), False))
    items.extend((_plain(bullet), True) for bullet in section.get("bullets", []))
    if not items:
        return slide
    base_size = 19 if sum(len(text) for text, _ in items) < 650 else 15
    for index, (text, is_bullet) in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = text
        paragraph.level = 0
        paragraph.font.size = PptxPt(base_size)
        paragraph.font.color.rgb = RGBColor(35, 35, 35)
        paragraph.space_after = PptxPt(8)
        if is_bullet:
            paragraph.text = f"• {text}"
    return slide


def _pptx_table_slides(presentation, heading, rows):
    """
    Function: _pptx_table_slides
    Purpose: Execute the  pptx table slides operation.
    Inputs:
            presentation (value): Caller-provided input.
            heading (value): Caller-provided input.
            rows (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    rows = _normalised_rows(rows)
    if not rows:
        return
    # Keep tables readable and repeat the header across continuation slides.
    for chunk_number, start in enumerate(range(1, len(rows), 9), start=1):
        chunk = [rows[0]] + rows[start : start + 9]
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        suffix = f" (table {chunk_number})" if len(rows) > 10 else ""
        _pptx_title(slide, f"{heading}{suffix}", size=22)
        left, top, width, height = PptxInches(0.45), PptxInches(1.15), PptxInches(12.45), PptxInches(5.9)
        shape = slide.shapes.add_table(len(chunk), len(chunk[0]), left, top, width, height)
        table = shape.table
        for column in table.columns:
            column.width = int(width / len(chunk[0]))
        row_height = int(height / len(chunk))
        for row_index, row in enumerate(chunk):
            table.rows[row_index].height = row_height
            for column_index, value in enumerate(row):
                cell = table.cell(row_index, column_index)
                cell.text = value
                cell.vertical_anchor = MSO_ANCHOR.TOP
                cell.margin_left = PptxInches(0.06)
                cell.margin_right = PptxInches(0.06)
                cell.margin_top = PptxInches(0.04)
                cell.margin_bottom = PptxInches(0.04)
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(217, 234, 247) if row_index == 0 else RGBColor(250, 252, 254)
                paragraph = cell.text_frame.paragraphs[0]
                paragraph.font.size = PptxPt(11 if row_index == 0 else 10)
                paragraph.font.bold = row_index == 0
                paragraph.font.color.rgb = RGBColor(31, 31, 31)
                paragraph.alignment = PP_ALIGN.LEFT


def export_pptx(document):
    """
    Function: export_pptx
    Purpose: Execute the export pptx operation.
    Inputs:
            document (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    presentation = Presentation()
    presentation.slide_width = PptxInches(13.333)
    presentation.slide_height = PptxInches(7.5)
    presentation.core_properties.title = _plain(document["title"])
    title_slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    _pptx_title(title_slide, document["title"], size=30)
    summary_box = title_slide.shapes.add_textbox(PptxInches(0.8), PptxInches(2.1), PptxInches(11.7), PptxInches(2.5))
    summary_frame = summary_box.text_frame
    summary_frame.word_wrap = True
    summary_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    summary_frame.text = _plain(document.get("summary", "Capstone Assistant response"))
    summary_frame.paragraphs[0].font.size = PptxPt(24)
    summary_frame.paragraphs[0].font.color.rgb = RGBColor(55, 55, 55)
    summary_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    for section in document["sections"]:
        if section.get("body") or section.get("bullets") or not section.get("table"):
            _pptx_content_slide(presentation, section)
        if section.get("table"):
            _pptx_table_slides(presentation, section["heading"], section["table"])
    output = BytesIO()
    presentation.save(output)
    return output.getvalue(), "pptx"


def export_pdf(document):
    """
    Function: export_pdf
    Purpose: Execute the export pdf operation.
    Inputs:
            document (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    output = BytesIO()
    regular_font, bold_font = _register_pdf_fonts()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ExportTitle", parent=styles["Title"], fontName=bold_font, alignment=TA_CENTER, textColor=colors.HexColor("#1F4E78"), spaceAfter=12))
    styles.add(ParagraphStyle(name="ExportHeading", parent=styles["Heading2"], fontName=bold_font, textColor=colors.HexColor("#1F4E78"), spaceBefore=12, spaceAfter=6))
    styles.add(ParagraphStyle(name="ExportBody", parent=styles["BodyText"], fontName=regular_font, leading=14))
    styles.add(ParagraphStyle(name="ExportTableHeader", parent=styles["BodyText"], fontName=bold_font, fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="ExportTableCell", parent=styles["BodyText"], fontName=regular_font, fontSize=8, leading=10))
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm)
    story = [Paragraph(escape(_plain(document["title"])), styles["ExportTitle"])]
    if document.get("summary"):
        story += [Paragraph(escape(_plain(document["summary"])), styles["ExportBody"]), Spacer(1, 8)]
    for section in document["sections"]:
        story.append(Paragraph(escape(_plain(section["heading"])), styles["ExportHeading"]))
        if section.get("body"):
            story.append(Paragraph(escape(_plain(section["body"])), styles["ExportBody"]))
        for bullet in section.get("bullets", []):
            story.append(Paragraph("• " + escape(_plain(bullet)), styles["ExportBody"]))
        rows = section.get("table") or []
        if rows:
            column_count = max(len(row) for row in rows)
            table_data = []
            for row_number, row in enumerate(rows):
                cells = []
                for value in list(row) + [""] * (column_count - len(row)):
                    style = styles["ExportTableHeader"] if row_number == 0 else styles["ExportTableCell"]
                    cells.append(Paragraph(escape(_plain(value)), style))
                table_data.append(cells)
            available_width = A4[0] - (36 * mm)
            weights = [
                max(1, min(45, max((len(str(row[index])) for row in rows), default=12)))
                for index in range(column_count)
            ]
            table_widths = [available_width * weight / sum(weights) for weight in weights]
            table = Table(table_data, colWidths=table_widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story += [Spacer(1, 5), table]
    doc.build(story)
    return output.getvalue(), "pdf"


def build_export(document, format_name):
    """
    Function: build_export
    Purpose: Execute the build export operation.
    Inputs:
            document (value): Caller-provided input.
            format_name (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    exporters = {"pdf": export_pdf, "docx": export_docx, "pptx": export_pptx, "xlsx": export_xlsx}
    if format_name not in exporters:
        raise ValueError("Unsupported export format.")
    return exporters[format_name](document)
