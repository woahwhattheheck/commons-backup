#!/usr/bin/env python3
"""Dependency-free MCP stdio facade for TITAN Hands on Windows."""

from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from .server import TitanHandsServer


MCP_PROTOCOL = "2025-03-26"


TOOLS = [
    {
        "name": "hands_observe",
        "description": "Return a semantic Windows UI delta; pixels are not captured.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_nodes": {"type": "integer", "minimum": 1},
                "max_depth": {"type": "integer", "minimum": 0},
                "include_offscreen": {"type": "boolean"},
            },
        },
    },
    {
        "name": "hands_act",
        "description": "Perform one semantic or input action, retarget stale ids using the live tree, and return the UI delta plus honest post-action verification.",
        "inputSchema": {
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "label": {"type": "string"},
                        "text": {"type": "string"},
                        "value": {"type": "string"},
                        "state": {"type": "string"},
                        "that": {"type": "string"},
                        "expect": {},
                    },
                },
                "expect": {},
                "observe_after": {"type": "boolean"},
                "max_nodes": {"type": "integer", "minimum": 1},
                "max_depth": {"type": "integer", "minimum": 0},
            },
        },
    },
    {
        "name": "hands_capture",
        "description": "Capture pixels on demand for a target element or foreground window.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "path": {"type": "string"},
            },
        },
    },
    {
        "name": "hands_capabilities",
        "description": "Describe the Windows adapter and supported action surface.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _tool_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(dict(result), ensure_ascii=False, separators=(",", ":")),
            }
        ],
        "isError": not bool(result.get("ok")),
    }


def dispatch(server: TitanHandsServer, message: Mapping[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        result = {
            "protocolVersion": MCP_PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "titan-hands-windows", "version": "0.1.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name == "hands_observe":
            result = _tool_result(server.handle({"op": "observe", **arguments}))
        elif name == "hands_act":
            result = _tool_result(server.handle({"op": "act", **arguments}))
        elif name == "hands_capture":
            result = _tool_result(server.handle({"op": "capture", **arguments}))
        elif name == "hands_capabilities":
            result = _tool_result(server.handle({"op": "capabilities"}))
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": f"unknown tool: {name}"},
            }
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
    server = TitanHandsServer()
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
                response = dispatch(server, message)
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
        server.close()


if __name__ == "__main__":
    raise SystemExit(main())
