from types import SimpleNamespace

import pytest

import app
from app_modules.services import ai_client


@pytest.mark.parametrize(
    "error, expected",
    [
        (app.requests.exceptions.Timeout(), "did not respond in time"),
        (app.requests.exceptions.ConnectionError(), "could not be reached"),
        (RuntimeError("Agentaus returned an invalid response."), "currently unavailable"),
    ],
)
def test_ai_outage_messages_are_actionable(error, expected):
    message = app.api_service_error_message(error)

    assert message
    assert expected in message
    assert "Traceback" not in message


def test_ai_http_failure_message_does_not_expose_provider_body():
    response = SimpleNamespace(status_code=503, text="private provider diagnostics")
    error = app.requests.exceptions.HTTPError(response=response)

    message = app.api_service_error_message(error)

    assert message == "The AI service rejected the request (HTTP 503)."
    assert "private provider diagnostics" not in message


def test_empty_evidence_fails_closed_before_calling_ai(monkeypatch):
    monkeypatch.setattr(
        app,
        "call_agentaus",
        lambda messages: {"choices": [{"message": {"content": ""}}]},
    )

    answer = app.generate_response("What is documented?", [])

    assert "enough approved evidence" in answer


def test_malformed_stream_events_end_in_a_safe_empty_stream_error(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "text/event-stream"}

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            return ["data: not-json", "data: [DONE]"]

        def close(self):
            return None

    monkeypatch.setattr(ai_client.requests, "post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(RuntimeError, match="empty stream"):
        list(ai_client.stream(
            [{"role": "user", "content": "test"}],
            endpoint="https://example.test/chat",
            api_key="test-key",
            state={},
        ))


def test_completion_retries_transient_provider_failure(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 503

        def __init__(self, ok):
            self.ok = ok

        def raise_for_status(self):
            if not self.ok:
                error = app.requests.exceptions.HTTPError(response=self)
                raise error

        def json(self):
            return {"choices": [{"message": {"content": "grounded"}}]}

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        return FakeResponse(len(calls) > 1)

    monkeypatch.setattr(ai_client.requests, "post", fake_post)
    monkeypatch.setenv("AI_PROVIDER_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("AI_PROVIDER_RETRY_BACKOFF_SECONDS", "0")

    result = ai_client.call(
        [{"role": "user", "content": "test"}],
        endpoint="https://example.test/chat",
        api_key="test-key",
        state={},
    )

    assert result["choices"][0]["message"]["content"] == "grounded"
    assert len(calls) == 2


def test_internal_labels_are_removed_from_provider_output():
    assert app.clean_ai_response("Supported fact (Evidence 9).") == "Supported fact."
