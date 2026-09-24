"""SQLite persistence. These low-level helpers are for trusted application/CLI code.

Request handlers must authorize through access_control before using project writes.
Project profiles retain the Sprint 2 JSON shape inside SQLite to avoid a disruptive
rewrite of team, milestone and meeting editors. Assignments are separate identities.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3

ROLES = ("Student", "Mentor", "Convenor", "Administrator")
SCHEMA_VERSION = 2
DEFAULT_PATH = Path(__file__).resolve().parent / "project_data" / "capstone.sqlite3"


def database_path():
    return Path(os.environ.get("CAPSTONE_DB_PATH", str(DEFAULT_PATH))).expanduser()


@contextmanager
def connect(path=None):
    connection = sqlite3.connect(path or database_path(), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path=None, legacy_file=None):
    """Transactional, versioned, one-time import; never modify the legacy file.

    Fail closed on malformed legacy data instead of marking a partial import done.
    """
    path = Path(path or database_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError("Database schema is newer than this application supports.")
        if version == SCHEMA_VERSION:
            return
        if version == 0:
            db.execute("""CREATE TABLE users (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Student','Mentor','Convenor','Administrator')),
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)))""")
            db.execute("""CREATE TABLE projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, profile TEXT NOT NULL)""")
            db.execute("""CREATE TABLE assignments (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                PRIMARY KEY(user_id, project_id))""")
            db.execute("""CREATE TABLE sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL)""")
            legacy = Path(legacy_file) if legacy_file else path.parent / "projects.json"
            if legacy.exists():
                records = json.loads(legacy.read_text(encoding="utf-8"))
                if not isinstance(records, list):
                    raise ValueError("Legacy projects.json must contain a list.")
                for record in records:
                    if (not isinstance(record, dict)
                            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", record.get("id", ""))
                            or not str(record.get("name", "")).strip()):
                        raise ValueError("Invalid legacy project; fix projects.json before migration.")
                    db.execute("INSERT INTO projects VALUES (?, ?, ?)",
                               (record["id"], record["name"], json.dumps(record)))
            db.execute("PRAGMA user_version = 1")

        # Additive v1 -> v2 migration: retain user IDs, hashes and every assignment.
        db.execute("""ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
            CHECK(status IN ('pending', 'active', 'rejected', 'disabled'))""")
        db.execute("ALTER TABLE users ADD COLUMN registered_at TEXT")
        db.execute("UPDATE users SET status = CASE WHEN active = 1 THEN 'active' ELSE 'disabled' END")
        db.execute("""CREATE TABLE password_resets (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            expires_at REAL NOT NULL)""")
        db.execute("PRAGMA user_version = 2")
    # Local database includes private profiles and password hashes.
    if os.name != "nt":
        path.chmod(0o600)


def read_projects():
    with connect() as db:
        return [json.loads(row[0]) for row in db.execute("SELECT profile FROM projects ORDER BY name, id")]


def write_projects(records):
    """Persist a complete snapshot under the application's existing project lock."""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        ids = {record["id"] for record in records}
        for row in db.execute("SELECT id FROM projects").fetchall():
            if row[0] not in ids:
                db.execute("DELETE FROM projects WHERE id = ?", (row[0],))
        for record in records:
            db.execute("""INSERT INTO projects VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, profile=excluded.profile""",
                       (record["id"], record["name"], json.dumps(record)))
