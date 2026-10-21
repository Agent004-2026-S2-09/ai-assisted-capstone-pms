## File: tests/test_vector_store.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing test vector store functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

from app_modules import auth
from app_modules import database
from app_modules import monitoring
from app_modules import vector_store


def test_sqlite_vector_embeddings_are_rebuilt_and_scored():
    """
    Function: test_sqlite_vector_embeddings_are_rebuilt_and_scored
    Purpose: Execute the test sqlite vector embeddings are rebuilt and scored operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {"text": "milestone risk management guidance", "source": "a.txt", "location": "p1", "chunk": 1},
        {"text": "sponsor meeting agenda and actions", "source": "b.txt", "location": "p1", "chunk": 1},
    ]
    assert vector_store.rebuild_embeddings(documents) == 2
    scores = vector_store.score_documents("milestone risk", documents)
    assert scores[0] > scores[1]
    assert vector_store.health()["document_count"] == 2


def test_embedding_keys_distinguish_records_sharing_page_metadata():
    """
    Function: test_embedding_keys_distinguish_records_sharing_page_metadata
    Purpose: Execute the test embedding keys distinguish records sharing page metadata operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    documents = [
        {
            "text": "first project record",
            "source": "projects.pdf",
            "location": "Page 2",
            "chunk": 1,
            "record_type": "project",
            "project_id": "2026-S2-05",
        },
        {
            "text": "second project record",
            "source": "projects.pdf",
            "location": "Page 2",
            "chunk": 1,
            "record_type": "project",
            "project_id": "2026-S2-05",
        },
    ]
    assert vector_store.rebuild_embeddings(documents) == 2
    with database.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM document_embeddings").fetchone()[0] == 2


def test_embedding_rebuild_deduplicates_identical_records():
    """
    Function: test_embedding_rebuild_deduplicates_identical_records
    Purpose: Execute the test embedding rebuild deduplicates identical records operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    document = {"text": "same record", "source": "a.pdf", "location": "Page 1", "chunk": 1}
    assert vector_store.rebuild_embeddings([document, dict(document)]) == 1


def test_hashing_backend_remains_explicit_and_deterministic(monkeypatch):
    """
    Function: test_hashing_backend_remains_explicit_and_deterministic
    Purpose: Execute the test hashing backend remains explicit and deterministic operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    monkeypatch.setenv("EMBEDDING_BACKEND", "hashing")
    first = vector_store.embed_texts(["milestone risk management"])
    second = vector_store.embed_texts(["milestone risk management"])

    assert vector_store.backend_name() == "hashing"
    assert vector_store.model_name() == "hashing-v1"
    assert first.shape == (1, vector_store.dimensions())
    assert (first == second).all()


def test_neural_backend_uses_query_encoding_when_available(monkeypatch):
    """
    Function: test_neural_backend_uses_query_encoding_when_available
    Purpose: Execute the test neural backend uses query encoding when available operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    class FakeModel:
        """
        Class: FakeModel
        Purpose: Represent the FakeModel abstraction.
        Responsibilities:
                Preserve the existing class interface and behaviour.
        """
        def get_sentence_embedding_dimension(self):
            """
            Function: get_sentence_embedding_dimension
            Purpose: Execute the get sentence embedding dimension operation.
            Inputs:
                    None.
            Returns:
                    The function result, or None where no value is returned.
            Raises/side effects:
                    Existing validation, authorization, persistence, and error handling apply.
            """
            return 3

        def encode(self, values, **kwargs):
            """
            Function: encode
            Purpose: Execute the encode operation.
            Inputs:
                    values (value): Caller-provided input.
            Returns:
                    The function result, or None where no value is returned.
            Raises/side effects:
                    Existing validation, authorization, persistence, and error handling apply.
            """
            return [[1.0, 0.0, 0.0] for _ in values]

        def encode_query(self, values, **kwargs):
            """
            Function: encode_query
            Purpose: Execute the encode query operation.
            Inputs:
                    values (value): Caller-provided input.
            Returns:
                    The function result, or None where no value is returned.
            Raises/side effects:
                    Existing validation, authorization, persistence, and error handling apply.
            """
            return [[0.0, 1.0, 0.0] for _ in values]

    monkeypatch.setenv("EMBEDDING_BACKEND", "sentence-transformers")
    monkeypatch.setattr(vector_store, "_sentence_transformers_available", lambda: True)
    monkeypatch.setattr(vector_store, "_sentence_model", lambda: FakeModel())

    document = vector_store.embed_texts(["document"])
    query = vector_store.embed_texts(["question"], is_query=True)

    assert document.tolist() == [[1.0, 0.0, 0.0]]
    assert query.tolist() == [[0.0, 1.0, 0.0]]


def test_api_and_retrieval_metrics_are_admin_only():
    """
    Function: test_api_and_retrieval_metrics_are_admin_only
    Purpose: Execute the test api and retrieval metrics are admin only operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    state = {}
    auth.create_user("Vector Admin", "vector-admin", "a-long-vector-password", "Administrator")
    assert auth.login(state, "vector-admin", "a-long-vector-password")
    monitoring.log_api_service_event(state=state, stage="test", latency_ms=10, success=True)
    monitoring.record_retrieval_event(state=state, question="milestone", result_count=1, top_score=0.8)
    assert monitoring.api_service_metrics(state)["successful"] == 1
    assert monitoring.retrieval_quality_metrics(state)["searches"] == 1
