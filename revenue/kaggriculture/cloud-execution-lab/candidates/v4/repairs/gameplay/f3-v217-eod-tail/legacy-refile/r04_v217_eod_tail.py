# SPDX-License-Identifier: Apache-2.0
"""Pure selector for the V4 V217 end-of-day reset tail.

The incumbent planner owns route construction.  This helper may only replace an
otherwise-too-long round trip with its already-constructed outbound+FEED prefix
when the official nightly reset immediately follows FEED.  Every failed proof
returns the exact incumbent ``roundtrip`` object unchanged.
"""
from __future__ import annotations


_MISSING = object()
_STANDARD_CONFIG = {
    "episodeSteps": 720,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "maxMarketOrdersPerTurn": 10,
}


def _cfg(configuration, name):
    if isinstance(configuration, dict):
        return configuration.get(name, _MISSING)
    return getattr(configuration, name, _MISSING) if configuration is not None else _MISSING


def _standard_configuration(configuration):
    for name, expected in _STANDARD_CONFIG.items():
        value = _cfg(configuration, name)
        if type(value) is not int or value != expected:
            return False
    return True


def apply_v217_eod_tail(forward, roundtrip, *, targets, step, end,
                         farmer_rows, configuration, enabled=False):
    """Return ``(commands, eod_tail)`` without mutating either input route."""
    if not enabled:
        return roundtrip, False
    if not isinstance(forward, list) or not isinstance(roundtrip, list):
        return roundtrip, False
    if type(step) is not int or type(end) is not int or end <= step:
        return roundtrip, False
    if not _standard_configuration(configuration):
        return roundtrip, False
    try:
        if len(targets) != 1:
            return roundtrip, False
    except TypeError:
        return roundtrip, False
    if end >= 719:
        return roundtrip, False
    remaining = end - step
    if not (len(forward) == remaining < len(roundtrip)):
        return roundtrip, False
    if not isinstance(farmer_rows, list) or len(farmer_rows) != remaining:
        return roundtrip, False
    if any(row != ["PASS"] for row in farmer_rows):
        return roundtrip, False
    return forward, True
