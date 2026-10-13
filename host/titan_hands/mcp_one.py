#!/usr/bin/env python3
"""One-tool MCP stdio facade for TITAN Hands.

The five-tool host.titan_hands.mcp_server and four-tool Windows facade stay.
This entry point advertises a single model-facing tool named `hands`.
`titan_hands` remains a call alias for that same handle.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from host.titan_hands.mcp_server import ACTION_PROPERTY, MCP_PROTOCOL, _tool_result
from host.titan_hands.one_tool import TitanHandsOne


SERVER_INSTRUCTIONS = (
    "One TITAN Hands call named hands. titan_hands is a call alias for the same handle. "
    "Set op to observe, act, capture, capabilities, targets, or reset. "
    "Set target to windows, android, android-lan, linux, files, git, slack, board, shell, or browser. "
    "Windows and Android use the existing DeltaUI adapters. android-lan is the physical Commons APK host "
    "(user-started; set TITAN_HANDS_ANDROID_LAN). Linux uses AT-SPI; "
    "a missing bus returns TRANSPORT_UNCONFIGURED. "
    "Normal observations contain no screenshots. Pixels are returned only when op is capture. "
    "The server performs requested operations directly and has no internal approval dialogue."
)

TOOL_NAMES = frozenset({"hands", "titan_hands"})

TOOL = {
    "name": "hands",
    "description": (
        "One model-facing TITAN Hands call. Routes computer-use, files/git, Slack #commons, "
        "board posts, shell, and browser through the existing DeltaUI contract. "
        "Linux is AT-SPI; a missing bus returns TRANSPORT_UNCONFIGURED. "
        "Pixels are returned only when op is capture. titan_hands is a call alias."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "description": "observe, act, capture, capabilities, targets, or reset. Free-form; typed failure if unimplemented.",
            },
            "target": {
                "type": "string",
                "description": (
                    "windows, android, android-lan, linux, files, git, slack, board, shell, or browser. "
                    "Defaults to windows. android-lan is the physical Commons APK "
                    "(TITAN_HANDS_ANDROID_LAN after Start host). "
                    "Linux is AT-SPI (TRANSPORT_UNCONFIGURED if the bus is absent)."
                ),
            },
            "route": {
                "type": "string",
                "description": (
                    "Optional leftover alias for target. computer (default), linux, file, git, "
                    "slack, board, shell, web, or catalog."
                ),
            },
            "action": ACTION_PROPERTY,
            "expect": {"description": "Optional post-action expectation; never required."},
            "observe_after": {"type": "boolean"},
            "max_nodes": {"type": "integer", "minimum": 1},
            "max_depth": {"type": "integer", "minimum": 0},
            "include_offscreen": {"type": "boolean"},
            "id": {"type": "string"},
            "path": {"type": "string"},
            "text": {"type": "string"},
            "body": {"type": "string"},
            "command": {"type": "string"},
        },
    },
    "annotations": {
        "readOnlyHint": False,
        "destructiveHint": True,
        "openWorldHint": True,
    },
}


def dispatch(router: TitanHandsOne, message: Mapping[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        result: dict[str, Any] = {
            "protocolVersion": MCP_PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "titan-hands-one", "version": "0.3.0"},
            "instructions": SERVER_INSTRUCTIONS,
        }
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in TOOL_NAMES:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": f"unknown tool: {name}"},
            }
        result = _tool_result(router.handle(dict(arguments)))
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> int:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    router = TitanHandsOne()
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
                response = dispatch(router, message)
            except Exception as exc:
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(exc)},
                }
            if response is not None:
                print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
        return 0
    finally:
        router.close()


if __name__ == "__main__":
    raise SystemExit(main())
