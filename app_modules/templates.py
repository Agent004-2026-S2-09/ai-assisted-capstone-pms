"""Downloadable Excel templates for administrators and project schedules."""

import io

import openpyxl


REQUIRED_USER_HEADERS = ["Username", "First name", "Last name", "Email", "Role", "Temporary password", "Status"]
USER_HEADERS = REQUIRED_USER_HEADERS + ["Permissions"]


def user_template_bytes():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "User accounts"
    sheet.append(USER_HEADERS)
    sheet.append(["student@example.edu", "Alex", "Student", "student@example.edu", "Student", "ReplaceWithSecurePassword", "active", "Student"])
    for cell in sheet[1]:
        cell.font = openpyxl.styles.Font(bold=True, color="FFFFFF")
        cell.fill = openpyxl.styles.PatternFill("solid", fgColor="001B2F")
    sheet.freeze_panes = "A2"
    instructions = workbook.create_sheet("Instructions")
    instructions.append(["User account template instructions"])
    instructions.append(["Roles and permissions: Student, Mentor, Convenor, Administrator"])
    instructions.append(["Students must have only Student. Other accounts may use comma-separated permissions, e.g. Mentor, Administrator."])
    instructions.append(["Statuses: pending, active, rejected, disabled"])
    instructions.append(["Temporary passwords must meet the application password requirements."])
    instructions.append(["Use secure transfer methods for temporary passwords; do not email this workbook unprotected."])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def parse_user_workbook(content, *, maximum_rows=500):
    """Read and validate the administrator user-import workbook."""
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
    except Exception as error:
        raise ValueError(f"The user workbook could not be read: {error}") from error
    if not rows:
        raise ValueError("The user workbook is empty.")
    headers = [str(value or "").strip().casefold() for value in rows[0]]
    required = [header.casefold() for header in REQUIRED_USER_HEADERS]
    if headers[: len(required)] != required:
        raise ValueError("Use the official user-account template with the required columns in order.")
    permissions_column = headers.index("permissions") if "permissions" in headers else None
    imported = []
    for row_number, values in enumerate(rows[1:], 2):
        cells = list(values) + [None] * len(USER_HEADERS)
        if not any(str(value or "").strip() for value in cells[: len(REQUIRED_USER_HEADERS)]):
            continue
        if len(imported) >= maximum_rows:
            raise ValueError(f"The import cannot contain more than {maximum_rows} users.")
        item = {
            "username": str(cells[0] or "").strip().casefold(),
            "first_name": str(cells[1] or "").strip(),
            "last_name": str(cells[2] or "").strip(),
            "email": str(cells[3] or "").strip().casefold(),
            "role": str(cells[4] or "").strip(),
            "password": str(cells[5] or ""),
            "status": str(cells[6] or "").strip().casefold(),
            "permissions": str(values[permissions_column] or "").strip() if permissions_column is not None and permissions_column < len(values) else "",
            "source_row": row_number,
        }
        if not item["username"] or not item["first_name"] or not item["last_name"]:
            raise ValueError(f"Row {row_number}: username, first name and last name are required.")
        if not item["email"] or "@" not in item["email"]:
            raise ValueError(f"Row {row_number}: enter a valid email address.")
        if item["role"] not in {"Student", "Mentor", "Convenor", "Administrator"}:
            raise ValueError(f"Row {row_number}: unsupported role.")
        if item["status"] not in {"pending", "active", "disabled", "rejected"}:
            raise ValueError(f"Row {row_number}: unsupported account status.")
        if not 12 <= len(item["password"]) <= 1024:
            raise ValueError(f"Row {row_number}: temporary password must contain 12 to 1024 characters.")
        imported.append(item)
    if not imported:
        raise ValueError("The user workbook contains no user rows.")
    return imported
