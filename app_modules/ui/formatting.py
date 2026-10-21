## File: app_modules/ui/formatting.py
## Date Created: Existing repository file
## Date Last Modified: 20-10-2026
## Description: Human-readable formatting helpers shared by monitoring pages.
## Inputs: Function arguments, application state, files, or service data as applicable
## Outputs: Return values, persisted state, or user-facing output as applicable
## Notes: Existing security, validation, and error-handling behaviour is preserved.

"""Human-readable formatting helpers shared by monitoring pages."""

from datetime import datetime, timezone


def percentile(values, fraction):
    """
    Function: percentile
    Purpose: Execute the percentile operation.
    Inputs:
            values (value): Caller-provided input.
            fraction (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    values = sorted(float(value) for value in values)
    if not values:
        return 0
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(len(values) - 1, lower + 1)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def timestamp(value):
    """
    Function: timestamp
    Purpose: Execute the timestamp operation.
    Inputs:
            value (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    except (TypeError, ValueError):
        return str(value or "—")


def latency_ms(value):
    """
    Function: latency_ms
    Purpose: Execute the latency ms operation.
    Inputs:
            value (value): Caller-provided input.
    Returns:
            The function result, or None where no value is returned.
    Raises/side effects:
            Existing validation, authorization, persistence, and error handling apply.
    """
    milliseconds = max(0, int(value or 0))
    return f"{milliseconds / 1000:.2f} s" if milliseconds >= 1000 else f"{milliseconds} ms"
