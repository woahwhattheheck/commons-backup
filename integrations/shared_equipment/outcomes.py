"""Project native outcome metadata without replacing the original result.

Status reads can successfully describe failed jobs. Only tool-result envelopes
declare tool failure. Unknown effects keep their native handles and stable IDs.
These helpers do not admit peers, select tools, or repeat an operation.
"""
from __future__ import annotations


def tool_failed(value):
    if not isinstance(value, dict):
        return False
    if value.get("ok") is False or value.get("isError") is True:
        return True
    return any(tool_failed(value.get(key)) for key in ("result", "structuredContent"))


def effect_uncertain(value):
    if not isinstance(value, dict):
        return False
    if value.get("uncertain") is True:
        return True
    code = str(value.get("code", "")).lower()
    error = value.get("error")
    if (code.endswith("_outcome_unknown") or error == "tool_effect_unknown_after_interruption"
            or isinstance(error, str) and error.lower().endswith("_outcome_unknown")):
        return True
    return any(effect_uncertain(value.get(key)) for key in ("error", "result", "structuredContent"))
