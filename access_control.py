"""Authorization uses a live database session, never caller-supplied roles/names."""
import json
import secrets
import time
import auth
import database


class AccessDenied(PermissionError):
    pass


def require_user(state):
    user = auth.current_user(state)
    if user is None:
        raise AccessDenied("Please sign in with an active account.")
    return user


def require_admin(state):
    user = require_user(state)
    if user["role"] != "Administrator":
        raise AccessDenied("Administrator access is required.")
    return user


def can_access_project(state, project_id):
    user = require_user(state)
    with database.connect() as db:
        row = db.execute("""SELECT id FROM projects WHERE id = ? AND
            (? IN ('Administrator', 'Convenor') OR EXISTS (
                SELECT 1 FROM assignments WHERE project_id = projects.id AND user_id = ?))""",
                         (project_id, user["role"], user["id"])).fetchone()
    return row is not None


def require_project(state, project_id, write=False):
    user = require_user(state)
    if not can_access_project(state, project_id):
        raise AccessDenied("You are not authorised to access this project.")
    if write and user["role"] == "Student":
        raise AccessDenied("Students have read-only project access.")
    return user


def accessible_projects(state):
    user = require_user(state)
    with database.connect() as db:
        return [json.loads(row[0]) for row in db.execute("""SELECT profile FROM projects WHERE
            ? IN ('Administrator', 'Convenor') OR EXISTS (SELECT 1 FROM assignments
                WHERE project_id = projects.id AND user_id = ?) ORDER BY name, id""",
            (user["role"], user["id"]))]


def assign_project(state, user_id, project_id, assigned=True):
    require_admin(state)
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        require_admin(state)
        target = db.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise ValueError("Account does not exist.")
        if not db.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone():
            raise ValueError("Project does not exist.")
        if assigned and target["role"] == "Student":
            existing = db.execute(
                "SELECT 1 FROM assignments WHERE user_id = ? AND project_id <> ?",
                (user_id, project_id),
            ).fetchone()
            if existing:
                raise ValueError("A Student can be assigned to only one project.")
        if assigned:
            db.execute("INSERT OR IGNORE INTO assignments VALUES (?, ?)", (user_id, project_id))
        else:
            db.execute("DELETE FROM assignments WHERE user_id = ? AND project_id = ?", (user_id, project_id))


def managed_users(state):
    require_admin(state)
    with database.connect() as db:
        return [dict(row) for row in db.execute(f"SELECT {auth.PUBLIC_USER_COLUMNS} FROM users ORDER BY username")]


def project_assignment_summary(state):
    """Return an administrator-only summary of stored project assignments."""
    require_admin(state)
    with database.connect() as db:
        rows = db.execute("""
            SELECT u.id, u.name, u.username, u.role,
                   p.id AS project_id, p.name AS project_name
            FROM users u
            LEFT JOIN assignments a ON a.user_id = u.id
            LEFT JOIN projects p ON p.id = a.project_id
            ORDER BY u.username, p.name, p.id
        """).fetchall()

    grouped = {}
    for row in rows:
        item = grouped.setdefault(row["id"], {
            "User": row["name"],
            "Username": row["username"],
            "Role": row["role"],
            "Assigned projects": [],
            "Assignment count": 0,
        })
        if row["project_id"]:
            item["Assigned projects"].append(f"{row['project_name']} ({row['project_id']})")
            item["Assignment count"] += 1

    summary = []
    for item in grouped.values():
        item["Assigned projects"] = ", ".join(item["Assigned projects"]) or "None"
        if item["Role"] == "Convenor":
            item["Effective access"] = "All Capstone projects"
        elif item["Role"] == "Administrator":
            item["Effective access"] = "All Capstone projects"
        else:
            item["Effective access"] = item["Assigned projects"]
        summary.append(item)
    return summary


def user_project_assignments(state, user_id):
    """Return stored project assignments for one user after admin authorization."""
    require_admin(state)
    with database.connect() as db:
        return [dict(row) for row in db.execute("""
            SELECT p.id, p.name
            FROM assignments a
            JOIN projects p ON p.id = a.project_id
            WHERE a.user_id = ?
            ORDER BY p.name, p.id
        """, (user_id,))]


def update_user(state, user_id, role, active):
    actor = require_admin(state)
    if role not in database.ROLES:
        raise ValueError("Unsupported role.")
    if actor["id"] == user_id and (role != "Administrator" or not active):
        raise ValueError("Use another administrator to change your own access.")
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        require_admin(state)
        db.execute("UPDATE users SET role = ?, active = ?, status = ? WHERE id = ?",
                   (role, int(active), "active" if active else "disabled", user_id))
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM password_resets WHERE user_id = ?", (user_id,))


def create_user(state, *args, **kwargs):
    require_admin(state)
    return auth.create_user(*args, **kwargs)


def issue_password_reset(state, user_id):
    """Generate a reset code once; only its hash is stored, never the code itself."""
    require_admin(state)
    token = secrets.token_urlsafe(32)
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        require_admin(state)
        if not db.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone():
            raise ValueError("Account does not exist.")
        db.execute("DELETE FROM password_resets WHERE user_id = ? OR expires_at <= ?", (user_id, time.time()))
        db.execute("INSERT INTO password_resets VALUES (?, ?, ?)",
                   (auth._token_hash(token), user_id, time.time() + auth.RESET_SECONDS))
    return token
