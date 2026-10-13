"""Format time bounds for the shared and native Slack page readers."""
from __future__ import annotations

import re


_SLACK_READ_NAMES = frozenset({
    "slack_read_channel",
    "slack_read_thread",
    "mcp__codex_apps__slack_slack_read_channel",
    "mcp__codex_apps__slack_slack_read_thread",
})


def normalize_slack_read_arguments(name, arguments):
    """Add Slack's decimal suffix to whole-second bounds without mutating input.

    Fractional strings, cursor values and other arguments pass through exactly.
    This is argument formatting; existing readers retain their validation.
    """
    if (not isinstance(name, str) or name not in _SLACK_READ_NAMES
            or not isinstance(arguments, dict)):
        return arguments
    normalized = arguments.copy()
    for key in ("oldest", "latest"):
        value = normalized.get(key)
        if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
            normalized[key] = value + ".000000"
    return normalized
