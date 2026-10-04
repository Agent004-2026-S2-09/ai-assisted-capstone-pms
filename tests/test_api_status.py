from types import SimpleNamespace

import app


def _clear_status_cache():
    app.check_agentaus_api.clear()


def test_api_status_is_online_for_reachable_post_only_endpoint(monkeypatch):
    monkeypatch.setattr(app, "API_ENDPOINT", "https://api.example.test/chat/completions")
    monkeypatch.setattr(app, "AGENTAUS_API_KEY", "test-key")
    monkeypatch.setattr(app.requests, "get", lambda *args, **kwargs: SimpleNamespace(status_code=405))
    _clear_status_cache()
    status = app.check_agentaus_api()
    assert status["online"] is True
    assert status["label"] == "Agentaus API online"


def test_api_status_is_online_when_get_probe_returns_not_found(monkeypatch):
    monkeypatch.setattr(app, "API_ENDPOINT", "https://api.example.test/chat/completions")
    monkeypatch.setattr(app, "AGENTAUS_API_KEY", "test-key")
    monkeypatch.setattr(app.requests, "get", lambda *args, **kwargs: SimpleNamespace(status_code=404))
    _clear_status_cache()
    status = app.check_agentaus_api()
    assert status["online"] is True
    assert "GET probe" in status["detail"]


def test_api_status_is_offline_for_timeout(monkeypatch):
    monkeypatch.setattr(app, "API_ENDPOINT", "https://api.example.test/chat/completions")
    monkeypatch.setattr(app, "AGENTAUS_API_KEY", "test-key")

    def timeout(*args, **kwargs):
        raise app.requests.exceptions.Timeout()

    monkeypatch.setattr(app.requests, "get", timeout)
    _clear_status_cache()
    status = app.check_agentaus_api()
    assert status["online"] is False
    assert "did not respond" in status["detail"]


def test_api_status_is_offline_when_not_configured(monkeypatch):
    monkeypatch.setattr(app, "API_ENDPOINT", "")
    monkeypatch.setattr(app, "AGENTAUS_API_KEY", "")
    _clear_status_cache()
    status = app.check_agentaus_api()
    assert status["online"] is False
    assert "not configured" in status["detail"]
