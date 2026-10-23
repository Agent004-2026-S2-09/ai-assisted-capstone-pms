## File: app_modules/vector_store.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: SQLite-backed semantic embeddings and vector similarity search.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""SQLite-backed deterministic hashing embeddings and vector similarity search."""

from __future__ import annotations

import hashlib
import struct
import time
from datetime import datetime, timezone

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize

from app_modules import database


DEFAULT_HASHING_MODEL = "hashing-v1"
DEFAULT_DIMENSIONS = 384


def backend_name() -> str:
    """
    Function: backend_name
    Purpose: Execute the backend name operation.
    Inputs:
            None.
    Returns:
            A value of type str.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return "hashing"


def model_name() -> str:
    """
    Function: model_name
    Purpose: Execute the model name operation.
    Inputs:
            None.
    Returns:
            A value of type str.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return DEFAULT_HASHING_MODEL


def dimensions() -> int:
    """
    Function: dimensions
    Purpose: Execute the dimensions operation.
    Inputs:
            None.
    Returns:
            A value of type int.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return DEFAULT_DIMENSIONS


def document_key(document: dict) -> str:
    # Page/chunk metadata is not guaranteed to be unique. PDF extraction can
    # legitimately emit multiple records on the same page with the same
    # chunk number, especially for structured project tables. Include the
    # content digest so those records remain distinct in SQLite.
    """
    Function: document_key
    Purpose: Execute the document key operation.
    Inputs:
            document (dict): Caller-provided input.
    Returns:
            A value of type str.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    text_digest = hashlib.sha256(
        str(document.get("text", "")).encode("utf-8", errors="ignore")
    ).hexdigest()
    identity = "|".join(
        str(document.get(field, ""))
        for field in ("scope", "project_id", "source", "location", "chunk", "record_type")
    ) + f"|{text_digest}"
    return hashlib.sha256(identity.encode("utf-8", errors="ignore")).hexdigest()


def content_hash(document: dict) -> str:
    """
    Function: content_hash
    Purpose: Execute the content hash operation.
    Inputs:
            document (dict): Caller-provided input.
    Returns:
            A value of type str.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return hashlib.sha256(str(document.get("text", "")).encode("utf-8", errors="ignore")).hexdigest()


def _vectorizer() -> HashingVectorizer:
    """
    Function: _vectorizer
    Purpose: Execute the  vectorizer operation.
    Inputs:
            None.
    Returns:
            A value of type HashingVectorizer.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return HashingVectorizer(
        n_features=dimensions(),
        alternate_sign=False,
        norm="l2",
        lowercase=True,
        ngram_range=(1, 2),
        strip_accents="unicode",
    )


def embed_texts(texts, *, is_query=False) -> np.ndarray:
    """
    Function: embed_texts
    Purpose: Execute the embed texts operation.
    Inputs:
            texts (value): Caller-provided input.
            is_query (value): Caller-provided input.
    Returns:
            A value of type np.ndarray.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    del is_query  # Hashing uses the same deterministic representation for documents and queries.
    matrix = _vectorizer().transform([str(text or "") for text in texts])
    return normalize(matrix, norm="l2", axis=1).toarray().astype(np.float32)


def _pack(vector: np.ndarray) -> bytes:
    """
    Function: _pack
    Purpose: Execute the  pack operation.
    Inputs:
            vector (np.ndarray): Caller-provided input.
    Returns:
            A value of type bytes.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    values = np.asarray(vector, dtype=np.float32).reshape(-1)
    return struct.pack(f"<{len(values)}f", *values.tolist())


def _unpack(blob: bytes, size: int) -> np.ndarray:
    """
    Function: _unpack
    Purpose: Execute the  unpack operation.
    Inputs:
            blob (bytes): Caller-provided input.
            size (int): Caller-provided input.
    Returns:
            A value of type np.ndarray.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return np.asarray(struct.unpack(f"<{size}f", blob), dtype=np.float32)


def _selected_documents(documents, *, scope, project_id=None):
    """Filter and de-duplicate source records before vector persistence."""
    selected = []
    seen = set()
    for item in documents or []:
        if not (
            isinstance(item, dict)
            and item.get("text")
            and item.get("scope", "general") == scope
            and (project_id is None or item.get("project_id") == project_id)
        ):
            continue
        key = document_key(item)
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
    return selected


def rebuild_embeddings(documents, *, scope="general", project_id=None) -> int:
    """Replace embeddings for one authorised index scope."""
    started = time.perf_counter()
    selected = _selected_documents(documents, scope=scope, project_id=project_id)
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
    selected = _selected_documents(documents, scope=scope, project_id=project_id)
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
    query = embed_texts([question], is_query=True)[0]
    return [max(0.0, min(1.0, float(np.dot(query, stored[key])))) if key in stored else 0.0 for key in keys]


def health() -> dict:
    """
    Function: health
    Purpose: Execute the health operation.
    Inputs:
            None.
    Returns:
            A value of type dict.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
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
