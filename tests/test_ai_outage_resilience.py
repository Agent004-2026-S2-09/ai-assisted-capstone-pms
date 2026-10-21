## File: tests/test_ai_outage_resilience.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Python module providing test ai outage resilience functionality.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

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
    """
    Function: test_ai_outage_messages_are_actionable
    Purpose: Execute the test ai outage messages are actionable operation.
    Inputs:
            error (value): Caller-provided input.
            expected (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    message = app.api_service_error_message(error)

    assert message
    assert expected in message
    assert "Traceback" not in message


def test_ai_http_failure_message_does_not_expose_provider_body():
    """
    Function: test_ai_http_failure_message_does_not_expose_provider_body
    Purpose: Execute the test ai http failure message does not expose provider body operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    response = SimpleNamespace(status_code=503, text="private provider diagnostics")
    error = app.requests.exceptions.HTTPError(response=response)

    message = app.api_service_error_message(error)

    assert message == "The AI service rejected the request (HTTP 503)."
    assert "private provider diagnostics" not in message


def test_unknown_provider_error_message_does_not_expose_traceback_or_code():
    """
    Function: test_unknown_provider_error_message_does_not_expose_traceback_or_code
    Purpose: Ensure unexpected provider failures are reduced to a safe UI message.
    Inputs:
            None.
    Returns:
            None.
    Raises/side effects:
            None.
    """
    error = RuntimeError("Traceback (most recent call last): secret/path/app.py line 99")

    message = app.api_service_error_message(error)

    assert message == "The AI assistant service is currently unavailable. Please try again shortly."
    assert "Traceback" not in message
    assert "secret/path" not in message


def test_real_provider_failure_marks_runtime_status_offline(monkeypatch):
    """
    Function: test_real_provider_failure_marks_runtime_status_offline
    Purpose: Ensure a failed provider request drives the UI service indicator red.
    Inputs:
            monkeypatch (pytest fixture): Replaces the network request.
    Returns:
            None.
    Raises/side effects:
            None.
    """
    state = {}

    def fail_post(*args, **kwargs):
        raise app.requests.exceptions.ConnectionError("private connection details")

    monkeypatch.setattr(ai_client.requests, "post", fail_post)

    with pytest.raises(app.requests.exceptions.ConnectionError):
        ai_client.call(
            [{"role": "user", "content": "test"}],
            endpoint="https://example.test/chat",
            api_key="test-key",
            state=state,
        )

    assert state["ai_service_runtime_status"]["online"] is False
    assert "private connection details" not in state["ai_service_runtime_status"]["detail"]


def test_empty_evidence_fails_closed_before_calling_ai(monkeypatch):
    """
    Function: test_empty_evidence_fails_closed_before_calling_ai
    Purpose: Execute the test empty evidence fails closed before calling ai operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    monkeypatch.setattr(
        app,
        "call_agentaus",
        lambda messages: {"choices": [{"message": {"content": ""}}]},
    )

    answer = app.generate_response("What is documented?", [])

    assert "enough approved evidence" in answer


def test_malformed_stream_events_end_in_a_safe_empty_stream_error(monkeypatch):
    """
    Function: test_malformed_stream_events_end_in_a_safe_empty_stream_error
    Purpose: Execute the test malformed stream events end in a safe empty stream error operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    class FakeResponse:
        """
        Class: FakeResponse
        Purpose: Represent the FakeResponse abstraction.
        Responsibilities:
                Preserve the existing class interface and behaviour.
        """
        status_code = 200
        headers = {"Content-Type": "text/event-stream"}

        def raise_for_status(self):
            """
            Function: raise_for_status
            Purpose: Execute the raise for status operation.
            Inputs:
                    None.
            Returns:
                    The function result, or None where no value is returned.
            Raises/side effects:
                    Existing validation, authorization, persistence, and error handling apply.
            """
            return None

        def iter_lines(self, decode_unicode=True):
            """
            Function: iter_lines
            Purpose: Execute the iter lines operation.
            Inputs:
                    decode_unicode (value): Caller-provided input.
            Returns:
                    The function result, or None where no value is returned.
            Raises/side effects:
                    Existing validation, authorization, persistence, and error handling apply.
            """
            return ["data: not-json", "data: [DONE]"]

        def close(self):
            """
            Function: close
            Purpose: Execute the close operation.
            Inputs:
                    None.
            Returns:
                    The function result, or None where no value is returned.
            Raises/side effects:
                    Existing validation, authorization, persistence, and error handling apply.
            """
            return None

    monkeypatch.setattr(ai_client.requests, "post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(RuntimeError, match="empty stream"):
        list(ai_client.stream(
            [{"role": "user", "content": "test"}],
            endpoint="https://example.test/chat",
            api_key="test-key",
            state={},
        ))


def test_stream_406_is_cached_as_provider_capability_failure(monkeypatch):
    """
    Function: test_stream_406_is_cached_as_provider_capability_failure
    Purpose: Execute the test stream 406 is cached as provider capability failure operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    class FakeResponse:
        """
        Class: FakeResponse
        Purpose: Represent the FakeResponse abstraction.
        Responsibilities:
                Preserve the existing class interface and behaviour.
        """
        status_code = 406
        headers = {}

        def raise_for_status(self):
            """
            Function: raise_for_status
            Purpose: Execute the raise for status operation.
            Inputs:
                    None.
            Returns:
                    The function result, or None where no value is returned.
            Raises/side effects:
                    Existing validation, authorization, persistence, and error handling apply.
            """
            raise app.requests.exceptions.HTTPError(response=self)

        def close(self):
            """
            Function: close
            Purpose: Execute the close operation.
            Inputs:
                    None.
            Returns:
                    The function result, or None where no value is returned.
            Raises/side effects:
                    Existing validation, authorization, persistence, and error handling apply.
            """
            return None

    monkeypatch.setattr(ai_client.requests, "post", lambda *args, **kwargs: FakeResponse())
    state = {}

    with pytest.raises(app.requests.exceptions.HTTPError):
        list(ai_client.stream([], endpoint="https://example.test/chat", api_key="test-key", state=state))

    assert state["agentaus_streaming_supported"] is False
    assert ai_client.streaming_supported(state) is False


def test_completion_retries_transient_provider_failure(monkeypatch):
    """
    Function: test_completion_retries_transient_provider_failure
    Purpose: Execute the test completion retries transient provider failure operation.
    Inputs:
            monkeypatch (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    calls = []

    class FakeResponse:
        """
        Class: FakeResponse
        Purpose: Represent the FakeResponse abstraction.
        Responsibilities:
                Preserve the existing class interface and behaviour.
        """
        status_code = 503

        def __init__(self, ok):
            """
            Function: __init__
            Purpose: Execute the   init   operation.
            Inputs:
                    ok (value): Caller-provided input.
            Returns:
                    The function result, or None where no value is returned.
            Raises/side effects:
                    Existing validation, authorization, persistence, and error handling apply.
            """
            self.ok = ok

        def raise_for_status(self):
            """
            Function: raise_for_status
            Purpose: Execute the raise for status operation.
            Inputs:
                    None.
            Returns:
                    The function result, or None where no value is returned.
            Raises/side effects:
                    Existing validation, authorization, persistence, and error handling apply.
            """
            if not self.ok:
                error = app.requests.exceptions.HTTPError(response=self)
                raise error

        def json(self):
            """
            Function: json
            Purpose: Execute the json operation.
            Inputs:
                    None.
            Returns:
                    The function result, or None where no value is returned.
            Raises/side effects:
                    Existing validation, authorization, persistence, and error handling apply.
            """
            return {"choices": [{"message": {"content": "grounded"}}]}

    def fake_post(*args, **kwargs):
        """
        Function: fake_post
        Purpose: Execute the fake post operation.
        Inputs:
                None.
        Returns:
                The function result, or None where no value is returned.
        Raises/side effects:
                Existing validation, authorization, persistence, and error handling apply.
        """
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
    """
    Function: test_internal_labels_are_removed_from_provider_output
    Purpose: Execute the test internal labels are removed from provider output operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    assert app.clean_ai_response("Supported fact (Evidence 9).") == "Supported fact."
