## File: scripts/convert_knowledge_csvs_to_pdf.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing convert knowledge csvs to pdf functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

import csv
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE = ROOT / "knowledge_base"


def make_pdf(csv_path: Path, pdf_path: Path) -> None:
    """
    Function: make_pdf
    Purpose: Execute the make pdf operation.
    Inputs:
            csv_path (Path): Caller-provided input.
            pdf_path (Path): Caller-provided input.
    Returns:
            A value of type None.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    headers, records = rows[0], rows[1:]
    page = landscape(A3 if len(headers) >= 5 else A4)
    document = SimpleDocTemplate(
        str(pdf_path),
        pagesize=page,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title=csv_path.stem.replace("_", " "),
        author="Capstone Project Management System",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocumentTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=16,
        leading=20,
        spaceAfter=8,
    )
    header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontSize=6.5,
        leading=8,
        wordWrap="CJK",
    )

    # Wide columns keep the long project fields readable while preserving all data.
    available_width = page[0] - document.leftMargin - document.rightMargin
    if len(headers) == 6:
        ratios = [0.22, 0.12, 0.24, 0.16, 0.16, 0.10]
    else:
        ratios = [0.10, 0.19, 0.25, 0.28, 0.18]
    widths = [available_width * ratio for ratio in ratios]

    table_data = [[Paragraph(header, header_style) for header in headers]]
    for record in records:
        padded = record + [""] * (len(headers) - len(record))
        table_data.append([Paragraph(value.replace("\n", "<br/>"), cell_style) for value in padded])

    table = Table(table_data, colWidths=widths, repeatRows=1, splitByRow=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9aa7b2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef4f8")]),
            ]
        )
    )

    story = [Paragraph(csv_path.stem.replace("_", " "), title_style), Spacer(1, 3 * mm), table]
    document.build(story)


if __name__ == "__main__":
    for name in ("Assignments_S2_2026", "List_of_Projects_S2_2026"):
        make_pdf(KNOWLEDGE_BASE / f"{name}.csv", KNOWLEDGE_BASE / f"{name}.pdf")
        print(f"Created {KNOWLEDGE_BASE / f'{name}.pdf'}")
