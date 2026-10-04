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
from datetime import datetime, timezone

ROLES = ("Student", "Mentor", "Convenor", "Administrator")
SCHEMA_VERSION = 8
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
        if version < 2:
            db.execute("""ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
                CHECK(status IN ('pending', 'active', 'rejected', 'disabled'))""")
            db.execute("ALTER TABLE users ADD COLUMN registered_at TEXT")
            db.execute("UPDATE users SET status = CASE WHEN active = 1 THEN 'active' ELSE 'disabled' END")
            db.execute("""CREATE TABLE password_resets (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                expires_at REAL NOT NULL)""")
            version = 2

        # Additive v2 -> v3 migration for AI monitoring. It creates no users,
        # projects, assignments or sessions and is safe to repeat.
        if version < 3:
            db.execute("""CREATE TABLE IF NOT EXISTS prompt_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL CHECK(name IN ('general', 'project')),
                version INTEGER NOT NULL,
                prompt_text TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0, 1)),
                created_at TEXT NOT NULL,
                UNIQUE(name, version))""")
            db.execute("""CREATE TABLE IF NOT EXISTS ai_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                created_epoch REAL NOT NULL,
                user_id INTEGER,
                user_role TEXT,
                project_id TEXT,
                assistant_mode TEXT NOT NULL,
                prompt_name TEXT NOT NULL,
                prompt_version INTEGER,
                request_hash TEXT,
                request_chars INTEGER NOT NULL DEFAULT 0,
                response_chars INTEGER NOT NULL DEFAULT 0,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 0 CHECK(success IN (0, 1)),
                error_type TEXT,
                http_status INTEGER,
                input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS response_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interaction_id INTEGER NOT NULL UNIQUE,
                rating INTEGER NOT NULL CHECK(rating IN (-1, 1)),
                comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                created_epoch REAL NOT NULL,
                FOREIGN KEY(interaction_id) REFERENCES ai_interactions(id) ON DELETE CASCADE)""")
            db.execute("""CREATE TABLE IF NOT EXISTS ai_prompt_archive (
                interaction_id INTEGER PRIMARY KEY,
                question_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(interaction_id) REFERENCES ai_interactions(id) ON DELETE CASCADE)""")
            db.execute("""CREATE TABLE IF NOT EXISTS ai_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interaction_id INTEGER NOT NULL,
                test_name TEXT NOT NULL,
                relevance INTEGER NOT NULL CHECK(relevance BETWEEN 1 AND 5),
                grounded_accuracy INTEGER NOT NULL CHECK(grounded_accuracy BETWEEN 1 AND 5),
                hallucination_detected INTEGER NOT NULL CHECK(hallucination_detected IN (0, 1)),
                evaluator_notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                created_epoch REAL NOT NULL,
                FOREIGN KEY(interaction_id) REFERENCES ai_interactions(id) ON DELETE CASCADE)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_ai_interactions_epoch ON ai_interactions(created_epoch)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_ai_interactions_project ON ai_interactions(project_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_ai_interactions_role_epoch ON ai_interactions(user_role, created_epoch)")
            db.execute("PRAGMA user_version = 3")
            version = 3

        # Additive v3 -> v4 migration for SQLite-backed vector retrieval and
        # operational quality monitoring.  No identity, project or assignment
        # data is changed by this migration.
        if version < 4:
            db.execute("""CREATE TABLE IF NOT EXISTS document_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_key TEXT NOT NULL UNIQUE,
                scope TEXT NOT NULL DEFAULT 'general',
                project_id TEXT,
                source TEXT NOT NULL,
                location TEXT NOT NULL DEFAULT '',
                chunk INTEGER,
                content_hash TEXT NOT NULL,
                model_name TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)""")
            db.execute("""CREATE TABLE IF NOT EXISTS embedding_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                model_name TEXT NOT NULL,
                scope TEXT NOT NULL,
                document_count INTEGER NOT NULL DEFAULT 0,
                dimensions INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 0 CHECK(success IN (0, 1)),
                error_message TEXT NOT NULL DEFAULT '')""")
            db.execute("""CREATE TABLE IF NOT EXISTS api_service_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                created_epoch REAL NOT NULL,
                user_id INTEGER,
                stage TEXT NOT NULL,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 0 CHECK(success IN (0, 1)),
                http_status INTEGER,
                error_type TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS retrieval_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                created_epoch REAL NOT NULL,
                user_id INTEGER,
                project_id TEXT,
                query_hash TEXT NOT NULL,
                query_chars INTEGER NOT NULL DEFAULT 0,
                result_count INTEGER NOT NULL DEFAULT 0,
                vector_result_count INTEGER NOT NULL DEFAULT 0,
                top_score REAL NOT NULL DEFAULT 0,
                retrieval_latency_ms INTEGER NOT NULL DEFAULT 0,
                planner_success INTEGER NOT NULL DEFAULT 0,
                no_match INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_document_embeddings_scope ON document_embeddings(scope, project_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_api_service_events_epoch ON api_service_events(created_epoch)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_retrieval_events_epoch ON retrieval_events(created_epoch)")
            db.execute("PRAGMA user_version = 4")

        # Additive v4 -> v5 migration for project scheduling, Kanban boards,
        # feature flags and account lifecycle improvements.
        if version < 5:
            existing_columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
            if "first_name" not in existing_columns:
                db.execute("ALTER TABLE users ADD COLUMN first_name TEXT NOT NULL DEFAULT ''")
            if "last_name" not in existing_columns:
                db.execute("ALTER TABLE users ADD COLUMN last_name TEXT NOT NULL DEFAULT ''")
            if "email" not in existing_columns:
                db.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
            if "must_change_password" not in existing_columns:
                db.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0 CHECK(must_change_password IN (0,1))")
            if "updated_at" not in existing_columns:
                db.execute("ALTER TABLE users ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email <> ''")
            db.execute("""CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS gantt_plans (
                project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                plan_json TEXT NOT NULL,
                updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS kanban_boards (
                project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                board_json TEXT NOT NULL,
                updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS project_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                user_id INTEGER,
                project_id TEXT,
                action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS password_change_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                attempted_at REAL NOT NULL,
                successful INTEGER NOT NULL DEFAULT 0 CHECK(successful IN (0,1)))""")
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            db.execute("UPDATE users SET updated_at = ? WHERE updated_at = ''", (now,))
            defaults = {
                "feature_gantt": "1", "feature_kanban": "1",
                "feature_kanban_ai": "1", "feature_gantt_import": "1",
                "feature_backlog_sync": "1", "feature_user_creation": "1",
            }
            for key, value in defaults.items():
                db.execute(
                    "INSERT OR IGNORE INTO app_settings(key, value, updated_at) VALUES (?, ?, ?)",
                    (key, value, now),
                )
            db.execute("PRAGMA user_version = 5")

        # Additive v5 -> v6 migration for explicit AI response usability
        # evaluation. Existing evaluations remain valid with a neutral score.
        if version < 6:
            evaluation_columns = {row[1] for row in db.execute("PRAGMA table_info(ai_evaluations)").fetchall()}
            if "usability" not in evaluation_columns:
                db.execute("ALTER TABLE ai_evaluations ADD COLUMN usability INTEGER NOT NULL DEFAULT 3 CHECK(usability BETWEEN 1 AND 5)")
            db.execute("PRAGMA user_version = 6")
            version = 6

        # Additive v6 -> v7 operational indexes. This does not alter users,
        # projects, assignments or stored content.
        if version < 7:
            db.execute("CREATE INDEX IF NOT EXISTS idx_project_audit_project_time ON project_audit_log(project_id, created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_project_audit_action_time ON project_audit_log(action, created_at)")
            db.execute("PRAGMA user_version = 7")
            version = 7

        # Additive v7 -> v8 migration for Administrator response evaluation.
        # Existing interactions remain valid; older records have no retained
        # answer text and are labelled accordingly in the evaluation UI.
        if version < 8:
            interaction_columns = {row[1] for row in db.execute("PRAGMA table_info(ai_interactions)").fetchall()}
            if "response_text" not in interaction_columns:
                db.execute("ALTER TABLE ai_interactions ADD COLUMN response_text TEXT NOT NULL DEFAULT ''")
            db.execute("PRAGMA user_version = 8")
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
