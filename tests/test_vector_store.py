from app_modules import auth
from app_modules import database
from app_modules import monitoring
from app_modules import vector_store


def test_sqlite_vector_embeddings_are_rebuilt_and_scored():
    documents = [
        {"text": "milestone risk management guidance", "source": "a.txt", "location": "p1", "chunk": 1},
        {"text": "sponsor meeting agenda and actions", "source": "b.txt", "location": "p1", "chunk": 1},
    ]
    assert vector_store.rebuild_embeddings(documents) == 2
    scores = vector_store.score_documents("milestone risk", documents)
    assert scores[0] > scores[1]
    assert vector_store.health()["document_count"] == 2


def test_hashing_backend_remains_explicit_and_deterministic(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "hashing")
    first = vector_store.embed_texts(["milestone risk management"])
    second = vector_store.embed_texts(["milestone risk management"])

    assert vector_store.backend_name() == "hashing"
    assert vector_store.model_name() == "hashing-v1"
    assert first.shape == (1, vector_store.dimensions())
    assert (first == second).all()


def test_neural_backend_uses_query_encoding_when_available(monkeypatch):
    class FakeModel:
        def get_sentence_embedding_dimension(self):
            return 3

        def encode(self, values, **kwargs):
            return [[1.0, 0.0, 0.0] for _ in values]

        def encode_query(self, values, **kwargs):
            return [[0.0, 1.0, 0.0] for _ in values]

    monkeypatch.setenv("EMBEDDING_BACKEND", "sentence-transformers")
    monkeypatch.setattr(vector_store, "_sentence_transformers_available", lambda: True)
    monkeypatch.setattr(vector_store, "_sentence_model", lambda: FakeModel())

    document = vector_store.embed_texts(["document"])
    query = vector_store.embed_texts(["question"], is_query=True)

    assert document.tolist() == [[1.0, 0.0, 0.0]]
    assert query.tolist() == [[0.0, 1.0, 0.0]]


def test_api_and_retrieval_metrics_are_admin_only():
    state = {}
    auth.create_user("Vector Admin", "vector-admin", "a-long-vector-password", "Administrator")
    assert auth.login(state, "vector-admin", "a-long-vector-password")
    monitoring.log_api_service_event(state=state, stage="test", latency_ms=10, success=True)
    monitoring.record_retrieval_event(state=state, question="milestone", result_count=1, top_score=0.8)
    assert monitoring.api_service_metrics(state)["successful"] == 1
    assert monitoring.retrieval_quality_metrics(state)["searches"] == 1
