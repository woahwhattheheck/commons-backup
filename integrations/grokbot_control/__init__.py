#!/usr/bin/env python3
"""Reusable GrokBot peer control for Commons coordinators.

Loopback HTTP surface: submit / inspect / follow-up / stop on existing
GrokBot account pools (not grok.com, not Cursor cloud). Shape mirrors
integrations/gemini_slack/peer_tool_gateway.py request/result/event-cursor
conventions used by C1 (claude_headless @ 8879).
"""

from .gateway import DEFAULT_PORT, build_server, main
from .paid_case import (
    receipt_from_g2_submit,
    receipt_row_from_case,
)
from .pools import DEFAULT_POOL_ID, HARNESS, list_pools
from .store import RunStore, normalize_case

__all__ = [
    "DEFAULT_PORT",
    "DEFAULT_POOL_ID",
    "HARNESS",
    "RunStore",
    "build_server",
    "list_pools",
    "main",
    "normalize_case",
    "receipt_from_g2_submit",
    "receipt_row_from_case",
]
