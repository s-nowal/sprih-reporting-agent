"""SSE (Server-Sent Events) response parser for e2e tests.

Parses raw ``text/event-stream`` response bodies into structured dicts
so tests can assert on event types and payloads.
"""

from __future__ import annotations

import json
from typing import Any


def parse_sse_events(text: str) -> list[dict[str, Any]]:
    """Parse a raw SSE response body into a list of event dicts.

    Each SSE event in the stream is separated by a blank line. Within an
    event block, lines starting with ``event:`` set the event type and
    lines starting with ``data:`` provide the payload. Multiple ``data:``
    lines within one block are joined with newlines.

    Args:
        text: The full response body from a ``text/event-stream`` endpoint.

    Returns:
        List of dicts, each with:
        - ``event`` (str): The event type (defaults to ``"message"``).
        - ``data`` (Any): JSON-parsed payload, or raw string if not valid JSON.
    """
    events: list[dict[str, Any]] = []
    current_event: str | None = None
    current_data_lines: list[str] = []

    for line in text.splitlines():
        # Blank line = end of event block
        if not line.strip():
            if current_data_lines:
                raw_data = "\n".join(current_data_lines)
                try:
                    parsed = json.loads(raw_data)
                except (json.JSONDecodeError, ValueError):
                    parsed = raw_data

                events.append({
                    "event": current_event or "message",
                    "data": parsed,
                })
            current_event = None
            current_data_lines = []
            continue

        # Skip SSE comments
        if line.startswith(":"):
            continue

        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current_data_lines.append(line[len("data:"):].strip())

    # Handle trailing event without final blank line
    if current_data_lines:
        raw_data = "\n".join(current_data_lines)
        try:
            parsed = json.loads(raw_data)
        except (json.JSONDecodeError, ValueError):
            parsed = raw_data

        events.append({
            "event": current_event or "message",
            "data": parsed,
        })

    return events
