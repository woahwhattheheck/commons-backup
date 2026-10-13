#!/usr/bin/env python3
"""Dependency-free MCP facade for unified local TITAN Hands."""

from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from .broker import TitanHandsBroker


MCP_PROTOCOL = "2025-03-26"
SERVER_INSTRUCTIONS = (
    "Direct local semantic computer use for Windows and Android. Observe before acting. "
    "Use target=windows or target=android; Windows is the default. Normal observations are "
    "UIA/UIAutomator deltas and contain no screenshots. Call hands_capture only when pixels "
    "are actually needed. The server performs requested actions directly and has no internal "
    "approval dialogue."
)

TARGET_PROPERTY = {
    "type": "string",
    "enum": ["windows", "android"],
    "description": "Execution surface. Defaults to windows.",
}

ACTION_PROPERTY = {
    "type": "object",
    "required": ["type"],
    "description": (
        "One semantic or input action. For launch, Windows requires file and accepts an "
        "optional args array. Android prefers the LDA Kotlin operator: common TITAN verbs are "
        "translated, and LDA-native verbs remain free-form. Android launch accepts name/app/package."
    ),
    "properties": {
        "type": {
            "type": "string",
            "description": (
                "Free-form adapter action verb. Built-ins include invoke, set_value, toggle, "
                "expand, collapse, select, focus, click, type_text, key, scroll, launch, wait, "
                "done, assert, verify, check, set_text, type, tap, and clear. Other types stay "
                "free-form and are forwarded to the adapter."
            ),
        },
        "id": {"type": "string", "description": "Stable node ID from hands_observe."},
        "text": {"type": "string"},
        "value": {"type": "string"},
        "key": {"type": "string"},
        "delta": {"type": "integer"},
        "file": {"type": "string", "description": "Windows executable for launch."},
        "args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional Windows launch arguments; omit when none are needed.",
        },
        "package": {"type": "string", "description": "Android package for launch."},
        "name": {"type": "string", "description": "App or semantic target name."},
        "app": {"type": "string", "description": "Android app name for LDA open_app."},
        "activity": {"type": "string", "description": "Optional Android activity."},
        "milliseconds": {"type": "integer", "minimum": 0},
        "state": {"type": "string", "description": "Optional assert/verify element state."},
        "that": {"type": "string", "description": "Optional assert/verify expectation text."},
        "expect": {"description": "Optional post-action expectation; never required."},
        "label": {"type": "string", "description": "Optional retarget label if id is stale."},
        "query": {"type": "string"},
    },
}

TOOLS = [
    {
        "name": "hands_targets",
        "description": "List the local Windows and Android hands and their live availability.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "hands_observe",
        "description": "Return a semantic UI delta for Windows or Android; no pixels are captured.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": TARGET_PROPERTY,
                "max_nodes": {"type": "integer", "minimum": 1},
                "max_depth": {"type": "integer", "minimum": 0},
                "include_offscreen": {"type": "boolean"},
            },
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "hands_act",
        "description": "Perform one direct local semantic/input action and return the resulting UI delta.",
        "inputSchema": {
            "type": "object",
            "required": ["action"],
            "properties": {
                "target": TARGET_PROPERTY,
                "action": ACTION_PROPERTY,
                "expect": {"description": "Optional post-action expectation; never required."},
                "observe_after": {"type": "boolean"},
                "max_nodes": {"type": "integer", "minimum": 1},
                "max_depth": {"type": "integer", "minimum": 0},
            },
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True},
    },
    {
        "name": "hands_capture",
        "description": (
            "Explicitly capture pixels from the selected Windows or Android surface. "
            "On Android with LDA, this returns the Kotlin Set-of-Marks screenshot "
            "rather than a raw ADB framebuffer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": TARGET_PROPERTY,
                "id": {"type": "string"},
                "path": {"type": "string"},
            },
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "hands_capabilities",
        "description": "Describe one adapter, or list both targets when target is omitted.",
        "inputSchema": {"type": "object", "properties": {"target": TARGET_PROPERTY}},
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
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


def dispatch(broker: TitanHandsBroker, message: Mapping[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        result = {
            "protocolVersion": MCP_PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "titan-hands", "version": "0.2.0"},
            "instructions": SERVER_INSTRUCTIONS,
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        operations = {
            "hands_targets": "targets",
            "hands_observe": "observe",
            "hands_act": "act",
            "hands_capture": "capture",
            "hands_capabilities": "capabilities",
        }
        if name not in operations:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": f"unknown tool: {name}"},
            }
        result = _tool_result(broker.handle({"op": operations[name], **arguments}))
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
    broker = TitanHandsBroker()
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
                response = dispatch(broker, message)
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
        broker.close()


if __name__ == "__main__":
    raise SystemExit(main())
