"""Human-readable formatting helpers shared by monitoring pages."""

from datetime import datetime, timezone


def percentile(values, fraction):
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
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    except (TypeError, ValueError):
        return str(value or "—")


def latency_ms(value):
    milliseconds = max(0, int(value or 0))
    return f"{milliseconds / 1000:.2f} s" if milliseconds >= 1000 else f"{milliseconds} ms"
