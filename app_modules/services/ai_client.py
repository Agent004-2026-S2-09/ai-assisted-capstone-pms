## File: app_modules/services/ai_client.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: AgentAus AI service client and provider telemetry bridge.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""AgentAus AI service client and provider telemetry bridge.

This module owns provider communication, streaming, safe error messages, and
usage extraction without depending on the Streamlit page layer.
"""

import json
import os
import time
from datetime import datetime

import requests
import streamlit as st

from app_modules import monitoring


def _set_runtime_status(state, *, online, detail):
    """
    Function: _set_runtime_status
    Purpose: Store the result of the latest real AI provider request for the
             authenticated Streamlit session.
    Inputs:
            state (dict-like): Session state or test state container.
            online (bool): Whether the provider request completed successfully.
            detail (str): Safe, user-facing status detail.
    Returns:
            None.
    Raises/side effects:
            Updates only the supplied session state; no credentials or provider
            response content is stored.
    """
    if not isinstance(state, dict):
        return
    state["ai_service_runtime_status"] = {
        "online": bool(online),
        "detail": str(detail or "").strip()[:240],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _retry_settings():
    """
    Function: _retry_settings
    Purpose: Execute the  retry settings operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    try:
        attempts = int(_config("AI_PROVIDER_MAX_ATTEMPTS", "2"))
    except ValueError:
        attempts = 2
    try:
        backoff = float(_config("AI_PROVIDER_RETRY_BACKOFF_SECONDS", "0.5"))
    except ValueError:
        backoff = 0.5
    return max(1, min(attempts, 3)), max(0.0, min(backoff, 5.0))


def _retryable(error):
    """
    Function: _retryable
    Purpose: Execute the  retryable operation.
    Inputs:
            error (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    if isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(error, requests.exceptions.HTTPError):
        status = getattr(error.response, "status_code", None)
        return status == 408 or status == 429 or bool(status and status >= 500)
    return False


def _config(key, default=""):
    """
    Function: _config
    Purpose: Execute the  config operation.
    Inputs:
            key (value): Caller-provided input.
            default (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    try:
        value = st.secrets.get(key)
    except st.errors.StreamlitSecretNotFoundError:
        value = None
    return str(value if value is not None else os.getenv(key, default)).strip()


def _endpoint():
    """
    Function: _endpoint
    Purpose: Execute the  endpoint operation.
    Inputs:
            None.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    host = _config("HOST_NAME")
    return _config("API_ENDPOINT") or (
        f"{host.rstrip('/')}/api/v1/chat/completions" if host else ""
    )


def _credentials(endpoint=None, api_key=None):
    """
    Function: _credentials
    Purpose: Execute the  credentials operation.
    Inputs:
            endpoint (value): Caller-provided input.
            api_key (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    return (
        str(endpoint if endpoint is not None else _endpoint()).strip(),
        str(api_key if api_key is not None else _config("AGENTAUS_API_KEY")).strip(),
    )


def call(messages, *, state=None, endpoint=None, api_key=None):
    """
    Function: call
    Purpose: Execute the call operation.
    Inputs:
            messages (value): Caller-provided input.
            state (value): Caller-provided input.
            endpoint (value): Caller-provided input.
            api_key (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    state = state if state is not None else st.session_state
    endpoint, api_key = _credentials(endpoint, api_key)
    if not api_key:
        _set_runtime_status(state, online=False, detail="AI credentials are not configured.")
        raise RuntimeError("AGENTAUS_API_KEY is not configured in Streamlit secrets or the environment.")
    if not endpoint:
        _set_runtime_status(state, online=False, detail="AI endpoint is not configured.")
        raise RuntimeError("Configure API_ENDPOINT, or set HOST_NAME in Streamlit secrets or the environment.")

    started = time.perf_counter()
    response = None
    try:
        attempts, backoff = _retry_settings()
        for attempt in range(attempts):
            try:
                response = requests.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"messages": messages, "stream": False, "system_prompt_overwrite": True},
                    timeout=90,
                )
                response.raise_for_status()
                try:
                    result = response.json()
                except requests.exceptions.JSONDecodeError as error:
                    raise RuntimeError("Agentaus returned an invalid response.") from error
                if not isinstance(result, dict):
                    raise RuntimeError("Agentaus returned an unexpected response format.")
                break
            except Exception as error:
                if attempt + 1 >= attempts or not _retryable(error):
                    raise
                time.sleep(backoff * (attempt + 1))
        usage = result.get("usage") or {}
        monitoring.log_api_service_event(
            state=state, stage="completion", latency_ms=(time.perf_counter() - started) * 1000,
            success=True, http_status=response.status_code,
            input_tokens=usage.get("input_tokens", usage.get("prompt_tokens")),
            output_tokens=usage.get("output_tokens", usage.get("completion_tokens")),
            total_tokens=usage.get("total_tokens"),
        )
        _set_runtime_status(state, online=True, detail="The AI service completed the latest request.")
        return result
    except Exception as error:
        _set_runtime_status(state, online=False, detail=api_error_message(error))
        monitoring.log_api_service_event(
            state=state, stage="completion", latency_ms=(time.perf_counter() - started) * 1000,
            success=False, http_status=getattr(getattr(error, "response", None), "status_code", None),
            error_type=type(error).__name__,
        )
        raise


def api_error_message(error):
    """
    Function: api_error_message
    Purpose: Execute the api error message operation.
    Inputs:
            error (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    if isinstance(error, requests.exceptions.ConnectionError):
        return (
            "The AI service endpoint could not be reached. In Streamlit Cloud, "
            "confirm that API_ENDPOINT is a public HTTPS URL whose hostname resolves from the internet."
        )
    if isinstance(error, requests.exceptions.Timeout):
        return "The AI service did not respond in time. Please try again shortly."
    if isinstance(error, requests.exceptions.HTTPError):
        response = error.response
        if response is not None:
            return f"The AI service rejected the request (HTTP {response.status_code})."
    return "The AI assistant service is currently unavailable. Please try again shortly."


def check(endpoint=None, api_key=None):
    """
    Function: check
    Purpose: Execute the check operation.
    Inputs:
            endpoint (value): Caller-provided input.
            api_key (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    endpoint, api_key = _credentials(endpoint, api_key)
    if not endpoint:
        return {"online": False, "label": "Agentaus API offline", "detail": "API endpoint is not configured."}
    if not api_key:
        return {"online": False, "label": "Agentaus API offline", "detail": "API credentials are not configured."}
    try:
        response = requests.get(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=(2, 3),
            allow_redirects=False,
        )
    except requests.exceptions.Timeout:
        return {"online": False, "label": "Agentaus API offline", "detail": "The service did not respond within 3 seconds."}
    except requests.exceptions.RequestException:
        return {"online": False, "label": "Agentaus API offline", "detail": "The service could not be reached."}

    status_code = int(response.status_code)
    if 200 <= status_code < 400 or status_code == 405:
        return {"online": True, "label": "Agentaus API online", "detail": "Service is reachable."}
    if status_code in {401, 403}:
        return {"online": False, "label": "Agentaus API offline", "detail": "The service rejected the configured credentials."}
    if status_code >= 500:
        return {"online": False, "label": "Agentaus API offline", "detail": f"The service returned HTTP {status_code}."}
    return {"online": True, "label": "Agentaus API online", "detail": f"Service is reachable (HTTP {status_code} to the GET probe)."}


def record_usage(result, stage, state=None):
    """
    Function: record_usage
    Purpose: Execute the record usage operation.
    Inputs:
            result (value): Caller-provided input.
            stage (value): Caller-provided input.
            state (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    usage = result.get("usage") if isinstance(result, dict) else None
    if not isinstance(usage, dict):
        return
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and isinstance(input_tokens, int) and isinstance(output_tokens, int):
        total_tokens = input_tokens + output_tokens
    entry = {
        "stage": stage,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
    }
    state = state if state is not None else st.session_state
    history = state.setdefault("api_usage", [])
    history.append(entry)
    del history[:-50]


def _stream_event_text(event):
    """
    Function: _stream_event_text
    Purpose: Execute the  stream event text operation.
    Inputs:
            event (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    try:
        choice = event.get("choices", [])[0]
    except (AttributeError, IndexError, TypeError):
        return ""
    content = choice.get("delta", {}).get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("text")
        )
    return ""


def stream(messages, *, stage="answer", state=None, endpoint=None, api_key=None):
    """
    Function: stream
    Purpose: Execute the stream operation.
    Inputs:
            messages (value): Caller-provided input.
            stage (value): Caller-provided input.
            state (value): Caller-provided input.
            endpoint (value): Caller-provided input.
            api_key (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    state = state if state is not None else st.session_state
    endpoint, api_key = _credentials(endpoint, api_key)
    if not api_key:
        _set_runtime_status(state, online=False, detail="AI credentials are not configured.")
        raise RuntimeError("AGENTAUS_API_KEY is not configured in Streamlit secrets or the environment.")
    if not endpoint:
        _set_runtime_status(state, online=False, detail="AI endpoint is not configured.")
        raise RuntimeError("Configure API_ENDPOINT, or set HOST_NAME in Streamlit secrets or the environment.")
    started = time.perf_counter()
    response = None
    try:
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            json={"messages": messages, "stream": True, "system_prompt_overwrite": True},
            stream=True,
            timeout=(10, 90),
        )
        response.raise_for_status()
    except Exception as error:
        if getattr(getattr(error, "response", None), "status_code", None) == 406 and state is not None:
            # Cache the provider capability for this Streamlit session so a
            # known-incompatible stream path is not retried on every question.
            state["agentaus_streaming_supported"] = False
        monitoring.log_api_service_event(
            state=state, stage=stage, latency_ms=(time.perf_counter() - started) * 1000,
            success=False, http_status=getattr(response, "status_code", None),
            error_type=type(error).__name__,
        )
        _set_runtime_status(state, online=False, detail=api_error_message(error))
        if response is not None:
            response.close()
        raise
    yielded_text = False
    stream_error = None
    try:
        if "text/event-stream" not in response.headers.get("Content-Type", "").lower():
            result = response.json()
            record_usage(result, stage, state)
            text = extract_text(result)
            if not text:
                raise RuntimeError("Agentaus returned an empty response.")
            yielded_text = True
            yield text
            return

        for raw_line in response.iter_lines(decode_unicode=True):
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            line = str(line or "").strip()
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            record_usage(event, stage, state)
            text = _stream_event_text(event)
            if text:
                yielded_text = True
                yield text
        if not yielded_text:
            raise RuntimeError("Agentaus returned an empty stream.")
        _set_runtime_status(state, online=True, detail="The AI service completed the latest request.")
    except Exception as error:
        stream_error = error
        _set_runtime_status(state, online=False, detail=api_error_message(error))
        raise
    finally:
        monitoring.log_api_service_event(
            state=state, stage=stage, latency_ms=(time.perf_counter() - started) * 1000,
            success=bool(yielded_text and stream_error is None),
            http_status=getattr(response, "status_code", None),
            error_type=type(stream_error).__name__ if stream_error else None,
        )
        if response is not None:
            response.close()


def streaming_supported(state=None):
    """Return the cached provider streaming capability, if known."""
    if isinstance(state, dict) and state.get("agentaus_streaming_supported") is False:
        return False
    return True


def extract_text(result):
    """
    Function: extract_text
    Purpose: Execute the extract text operation.
    Inputs:
            result (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    try:
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "\n".join(
                str(item.get("text"))
                for item in content
                if isinstance(item, dict) and item.get("text")
            ).strip()
        return str(content).strip()
    except Exception:
        return ""
