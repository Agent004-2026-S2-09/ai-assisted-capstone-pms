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


def test_api_and_retrieval_metrics_are_admin_only():
    state = {}
    auth.create_user("Vector Admin", "vector-admin", "a-long-vector-password", "Administrator")
    assert auth.login(state, "vector-admin", "a-long-vector-password")
    monitoring.log_api_service_event(state=state, stage="test", latency_ms=10, success=True)
    monitoring.record_retrieval_event(state=state, question="milestone", result_count=1, top_score=0.8)
    assert monitoring.api_service_metrics(state)["successful"] == 1
    assert monitoring.retrieval_quality_metrics(state)["searches"] == 1
