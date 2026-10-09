"""Canonical filesystem locations used by the application."""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
ASSET_DIR = BASE_DIR / "assets"
UC_LOGO_PATH = ASSET_DIR / "uc_logo_inline_padded.png"
UC_LOGO_WHITE_PATH = ASSET_DIR / "uc-logo-white-padded.png"

KB_DIR = BASE_DIR / "knowledge_base"
INDEX_DIR = BASE_DIR / "knowledge_index"
PROJECT_DATA_DIR = BASE_DIR / "project_data"
PROJECT_KNOWLEDGE_DIR = BASE_DIR / "project_knowledge"
INDEX_FILE = INDEX_DIR / "index.json"
PROJECTS_FILE = PROJECT_DATA_DIR / "projects.json"


def ensure_runtime_directories():
    for directory in (KB_DIR, INDEX_DIR, PROJECT_DATA_DIR, PROJECT_KNOWLEDGE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


ensure_runtime_directories()
