## File: scripts/manage.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Trusted local operator CLI for database setup and account administration.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Trusted local operator CLI for database setup and account administration.

Run from the repository. This tool never prints or stores plaintext passwords
and is intended for local/deployment environments with trusted shell access.
"""
import argparse
from getpass import getpass
import secrets

from dotenv import load_dotenv

from app_modules import auth
from app_modules import database


def _assign(db, username, project_id, remove=False):
    """
    Function: _assign
    Purpose: Execute the  assign operation.
    Inputs:
            db (value): Caller-provided input.
            username (value): Caller-provided input.
            project_id (value): Caller-provided input.
            remove (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    user = db.execute(
        "SELECT id, role FROM users WHERE username = ?",
        (username.strip().casefold(),),
    ).fetchone()
    project = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not user or not project:
        raise ValueError("Unknown user or project; use the list command.")
    if remove:
        db.execute(
            "DELETE FROM assignments WHERE user_id = ? AND project_id = ?",
            (user["id"], project_id),
        )
        return
    if user["role"] == "Student" and db.execute(
        "SELECT 1 FROM assignments WHERE user_id = ? AND project_id <> ?",
        (user["id"], project_id),
    ).fetchone():
        raise ValueError("A Student can be assigned to only one project.")
    db.execute(
        "INSERT OR IGNORE INTO assignments VALUES (?, ?)",
        (user["id"], project_id),
    )


def main():
    """
    Function: main
    Purpose: Execute the main operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Initialize SQLite and import existing JSON projects once")
    create = commands.add_parser("create-user")
    create.add_argument("--name", required=True)
    create.add_argument("--username", required=True)
    create.add_argument("--role", choices=database.ROLES, required=True)
    assign = commands.add_parser("assign")
    assign.add_argument("--username", required=True)
    assign.add_argument("--project", required=True)
    assign.add_argument("--remove", action="store_true")
    reset = commands.add_parser("reset-password")
    reset.add_argument("--username", required=True)
    commands.add_parser("list", help="List project IDs and usernames, never hashes")
    commands.add_parser("seed-demo", help="Create development accounts with random passwords")
    args = parser.parse_args()

    database.initialize(legacy_file=database.DEFAULT_PATH.parent / "projects.json")
    if args.command == "init":
        print(f"Initialized {database.database_path()}")
    elif args.command == "create-user":
        password = getpass("Password (12+ characters): ")
        if password != getpass("Confirm password: "):
            parser.error("Passwords do not match.")
        auth.create_user(args.name, args.username, password, args.role)
        print("User created.")
    elif args.command == "assign":
        try:
            with database.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                _assign(db, args.username, args.project, remove=args.remove)
        except ValueError as error:
            parser.error(str(error))
        print("Assignment updated.")
    elif args.command == "reset-password":
        password = getpass("New password (12+ characters): ")
        if password != getpass("Confirm password: "):
            parser.error("Passwords do not match.")
        try:
            auth.reset_password_for_operator(args.username, password)
        except ValueError as error:
            parser.error(str(error))
        print("Password reset; existing sessions revoked.")
    elif args.command == "list":
        with database.connect() as db:
            for row in db.execute("SELECT username, role, status FROM users ORDER BY username"):
                print("User:", *row)
            for row in db.execute("SELECT id, name FROM projects ORDER BY id"):
                print("Project:", *row)
    elif args.command == "seed-demo":
        print("DEVELOPMENT / DEMO ONLY. Random passwords are shown once; existing accounts are unchanged.")
        with database.connect() as db:
            for project_id, name in (("demo-alpha", "Demo Alpha"), ("demo-beta", "Demo Beta")):
                profile = database.json.dumps({
                    "id": project_id,
                    "name": name,
                    "description": f"Development workspace: {name}",
                })
                db.execute(
                    "INSERT OR IGNORE INTO projects VALUES (?, ?, ?)",
                    (project_id, name, profile),
                )
        for role in database.ROLES:
            username = f"{role.lower()}@demo.local"
            with database.connect() as db:
                existing = db.execute(
                    "SELECT id FROM users WHERE username = ?",
                    (username,),
                ).fetchone()
            if existing:
                print(f"Skipped existing {username}")
                continue
            password = secrets.token_urlsafe(18)
            user_id = auth.create_user(f"Demo {role}", username, password, role)
            if role != "Administrator":
                with database.connect() as db:
                    db.execute(
                        "INSERT OR IGNORE INTO assignments VALUES (?, ?)",
                        (user_id, "demo-alpha"),
                    )
            print(f"{username}  {password}")


if __name__ == "__main__":
    main()
