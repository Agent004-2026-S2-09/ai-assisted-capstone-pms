## File: tests/test_api_status.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing test api status functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

from types import SimpleNamespace

import app


def _clear_status_cache():
    """
    Function: _clear_status_cache
    Purpose: Execute the  clear status cache operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    app.check_agentaus_api.clear()


def test_api_status_is_online_for_reachable_post_only_endpoint(monkeypatch):
    """
    Function: test_api_status_is_online_for_reachable_post_only_endpoint
    Purpose: Execute the test api status is online for reachable post only endpoint operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    monkeypatch.setattr(app, "API_ENDPOINT", "https://api.example.test/chat/completions")
    monkeypatch.setattr(app, "AGENTAUS_API_KEY", "test-key")
    monkeypatch.setattr(app.requests, "get", lambda *args, **kwargs: SimpleNamespace(status_code=405))
    _clear_status_cache()
    status = app.check_agentaus_api()
    assert status["online"] is True
    assert status["label"] == "Agentaus API online"


def test_api_status_is_online_when_get_probe_returns_not_found(monkeypatch):
    """
    Function: test_api_status_is_online_when_get_probe_returns_not_found
    Purpose: Execute the test api status is online when get probe returns not found operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    monkeypatch.setattr(app, "API_ENDPOINT", "https://api.example.test/chat/completions")
    monkeypatch.setattr(app, "AGENTAUS_API_KEY", "test-key")
    monkeypatch.setattr(app.requests, "get", lambda *args, **kwargs: SimpleNamespace(status_code=404))
    _clear_status_cache()
    status = app.check_agentaus_api()
    assert status["online"] is True
    assert "GET probe" in status["detail"]


def test_api_status_is_offline_for_timeout(monkeypatch):
    """
    Function: test_api_status_is_offline_for_timeout
    Purpose: Execute the test api status is offline for timeout operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    monkeypatch.setattr(app, "API_ENDPOINT", "https://api.example.test/chat/completions")
    monkeypatch.setattr(app, "AGENTAUS_API_KEY", "test-key")

    def timeout(*args, **kwargs):
        """
        Function: timeout
        Purpose: Execute the timeout operation.
        Inputs:
                None.
        Returns:
                The function result, or None where no value is returned.
        Raises/side effects:
                Existing validation, authorization, persistence, and error handling apply.
        """
        raise app.requests.exceptions.Timeout()

    monkeypatch.setattr(app.requests, "get", timeout)
    _clear_status_cache()
    status = app.check_agentaus_api()
    assert status["online"] is False
    assert "did not respond" in status["detail"]


def test_api_status_is_offline_when_not_configured(monkeypatch):
    """
    Function: test_api_status_is_offline_when_not_configured
    Purpose: Execute the test api status is offline when not configured operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    monkeypatch.setattr(app, "API_ENDPOINT", "")
    monkeypatch.setattr(app, "AGENTAUS_API_KEY", "")
    _clear_status_cache()
    status = app.check_agentaus_api()
    assert status["online"] is False
    assert "not configured" in status["detail"]
