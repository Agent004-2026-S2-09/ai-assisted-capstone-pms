"""SQLite-backed semantic embeddings and vector similarity search.

When ``sentence-transformers`` is installed, the default backend uses a
compact neural retrieval model (BGE small).  A deterministic hashing backend
remains available as a dependency-light fallback and can be selected with
``EMBEDDING_BACKEND=hashing``.  The retrieval contract and SQLite storage are
unchanged between backends; model and dimension metadata invalidate stale
vectors automatically.
"""

from __future__ import annotations

import hashlib
import os
import struct
import time
from functools import lru_cache
from datetime import datetime, timezone

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize

from app_modules import database


DEFAULT_NEURAL_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_HASHING_MODEL = "hashing-v1"
DEFAULT_DIMENSIONS = 384


def _sentence_transformers_available() -> bool:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        return False
    return True


def backend_name() -> str:
    configured = os.getenv("EMBEDDING_BACKEND", "auto").strip().casefold()
    if configured in {"hashing", "hashing-v1", "lexical"}:
        return "hashing"
    if configured in {"sentence-transformers", "sentence_transformers", "neural", "bge"}:
        if not _sentence_transformers_available():
            raise RuntimeError(
                "EMBEDDING_BACKEND requests sentence-transformers, but the package is not installed."
            )
        return "sentence-transformers"
    return "sentence-transformers" if _sentence_transformers_available() else "hashing"


def model_name() -> str:
    if backend_name() == "hashing":
        return DEFAULT_HASHING_MODEL
    return os.getenv("EMBEDDING_MODEL_NAME", DEFAULT_NEURAL_MODEL).strip() or DEFAULT_NEURAL_MODEL


@lru_cache(maxsize=1)
def _sentence_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name())


def dimensions() -> int:
    if backend_name() == "sentence-transformers":
        return int(_sentence_model().get_sentence_embedding_dimension())
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


def embed_texts(texts, *, is_query=False) -> np.ndarray:
    values = [str(text or "") for text in texts]
    if backend_name() == "sentence-transformers":
        model = _sentence_model()
        if is_query and hasattr(model, "encode_query"):
            vectors = model.encode_query(values, normalize_embeddings=True, show_progress_bar=False)
        else:
            if is_query:
                values = [
                    "Represent this sentence for searching relevant passages: " + value
                    for value in values
                ]
            vectors = model.encode(values, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)
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
    query = embed_texts([question], is_query=True)[0]
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
