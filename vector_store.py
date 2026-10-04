"""SQLite-backed document embeddings and vector similarity search.

The default model is a deterministic local hashing embedding.  It needs no
model download, works on Streamlit Cloud, and keeps the actual vectors in
SQLite.  Deployments may select another compatible backend later through
``EMBEDDING_MODEL_NAME`` without changing the retrieval contract.
"""

from __future__ import annotations

import hashlib
import os
import struct
import time
from datetime import datetime, timezone

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize

import database


DEFAULT_MODEL = "hashing-v1"
DEFAULT_DIMENSIONS = 384


def model_name() -> str:
    return os.getenv("EMBEDDING_MODEL_NAME", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def dimensions() -> int:
    try:
        return max(64, min(4096, int(os.getenv("EMBEDDING_DIMENSIONS", DEFAULT_DIMENSIONS))))
    except (TypeError, ValueError):
        return DEFAULT_DIMENSIONS


def document_key(document: dict) -> str:
    identity = "|".join(
        str(document.get(field, ""))
        for field in ("scope", "project_id", "source", "location", "chunk", "record_type")
    )
    return hashlib.sha256(identity.encode("utf-8", errors="ignore")).hexdigest()


def content_hash(document: dict) -> str:
    return hashlib.sha256(str(document.get("text", "")).encode("utf-8", errors="ignore")).hexdigest()


def _vectorizer() -> HashingVectorizer:
    return HashingVectorizer(
        n_features=dimensions(),
        alternate_sign=False,
        norm="l2",
        lowercase=True,
        ngram_range=(1, 2),
        strip_accents="unicode",
    )


def embed_texts(texts) -> np.ndarray:
    matrix = _vectorizer().transform([str(text or "") for text in texts])
    return normalize(matrix, norm="l2", axis=1).toarray().astype(np.float32)


def _pack(vector: np.ndarray) -> bytes:
    values = np.asarray(vector, dtype=np.float32).reshape(-1)
    return struct.pack(f"<{len(values)}f", *values.tolist())


def _unpack(blob: bytes, size: int) -> np.ndarray:
    return np.asarray(struct.unpack(f"<{size}f", blob), dtype=np.float32)


def rebuild_embeddings(documents, *, scope="general", project_id=None) -> int:
    """Replace embeddings for one authorised index scope."""
    started = time.perf_counter()
    selected = [
        item for item in (documents or [])
        if isinstance(item, dict) and item.get("text")
        and item.get("scope", "general") == scope
        and (project_id is None or item.get("project_id") == project_id)
    ]
    vectors = embed_texts([item["text"] for item in selected]) if selected else np.empty((0, dimensions()), dtype=np.float32)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with database.connect() as db:
        if project_id is None:
            db.execute("DELETE FROM document_embeddings WHERE scope = ?", (scope,))
        else:
            db.execute("DELETE FROM document_embeddings WHERE scope = ? AND project_id = ?", (scope, project_id))
        db.executemany(
            """INSERT INTO document_embeddings
               (document_key, scope, project_id, source, location, chunk,
                content_hash, model_name, dimensions, embedding, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    document_key(item), scope, item.get("project_id") if scope == "project" else None, item.get("source", ""),
                    item.get("location", ""), item.get("chunk"), content_hash(item),
                    model_name(), dimensions(), _pack(vector), now,
                )
                for item, vector in zip(selected, vectors)
            ],
        )
        db.execute(
            """INSERT INTO embedding_runs
               (created_at, model_name, scope, document_count, dimensions,
                duration_ms, success, error_message)
               VALUES (?, ?, ?, ?, ?, ?, 1, '')""",
            (now, model_name(), scope, len(selected), dimensions(), int((time.perf_counter() - started) * 1000)),
        )
    return len(selected)


def ensure_embeddings(documents, *, scope="general", project_id=None) -> int:
    """Incrementally rebuild a scope when its SQLite vectors are stale."""
    selected = [
        item for item in (documents or [])
        if isinstance(item, dict) and item.get("text")
        and item.get("scope", "general") == scope
        and (project_id is None or item.get("project_id") == project_id)
    ]
    expected = {document_key(item): content_hash(item) for item in selected}
    with database.connect() as db:
        if project_id is None:
            rows = db.execute(
                "SELECT document_key, content_hash, model_name, dimensions FROM document_embeddings WHERE scope = ?",
                (scope,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT document_key, content_hash, model_name, dimensions FROM document_embeddings WHERE scope = ? AND project_id = ?",
                (scope, project_id),
            ).fetchall()
    current = {row["document_key"]: (row["content_hash"], row["model_name"], row["dimensions"]) for row in rows}
    if expected and expected.keys() == current.keys() and all(
        current[key][0] == value and current[key][1] == model_name() and current[key][2] == dimensions()
        for key, value in expected.items()
    ):
        return len(expected)
    if not expected and not current:
        return 0
    return rebuild_embeddings(selected, scope=scope, project_id=project_id)


def score_documents(question: str, documents) -> list[float]:
    """Return SQLite-vector cosine scores aligned to ``documents``."""
    items = [item for item in (documents or []) if isinstance(item, dict)]
    keys = [document_key(item) for item in items]
    if not keys:
        return []
    with database.connect() as db:
        rows = db.execute(
            f"SELECT document_key, dimensions, embedding FROM document_embeddings WHERE document_key IN ({','.join('?' for _ in keys)})",
            keys,
        ).fetchall()
    stored = {row["document_key"]: _unpack(row["embedding"], int(row["dimensions"])) for row in rows}
    if not stored:
        return [0.0] * len(items)
    query = embed_texts([question])[0]
    return [max(0.0, min(1.0, float(np.dot(query, stored[key])))) if key in stored else 0.0 for key in keys]


def health() -> dict:
    with database.connect() as db:
        row = db.execute(
            """SELECT COUNT(*) document_count,
                      COUNT(DISTINCT model_name) model_count,
                      MAX(created_at) latest_created_at
                 FROM document_embeddings"""
        ).fetchone()
        run = db.execute(
            """SELECT created_at, model_name, scope, document_count, dimensions,
                      duration_ms, success, error_message
                 FROM embedding_runs ORDER BY id DESC LIMIT 1"""
        ).fetchone()
    result = dict(row)
    result.update({"model_name": model_name(), "dimensions": dimensions()})
    result["last_run"] = dict(run) if run else None
    return result
