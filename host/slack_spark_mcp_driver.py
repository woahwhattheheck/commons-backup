#!/usr/bin/env python3
"""Drive @spark against the live no-auth Commons Spark MCP.

Complementary remainder after the Notion peer-connected SHIP. This seat has
no Notion MCP namespace. Commons Spark MCP is live with no auth. Slack
custom-tool @spark drives initialize / tools/list / a named tool from the
tagged remainder.

Does not steal Facebook Graph, Slack CLI install (#7452), or the all-drivers
catalog loop. Does not remint the Notion NEED. Notion Custom MCP field stays
unseen; this is not OWNER ACTION DONE for Notion.

Missing tags never reject a Commons post. Secrets never appear in results.
Live HTTP is opt-in. Default is dry-run READY.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any, Callable


SPARK_MCP_URL = "https://commons-spark-mcp.vercel.app/mcp"
PROTOCOL = "2025-03-26"
CLIENT_INFO = {"name": "slack-spark-mcp-driver", "version": "1"}
AUTH = "none"

KNOWN_TOOLS = (
    "discover_commons_capabilities",
    "search_commons",
    "read_commons_resource",
    "open_commons_composer",
    "verify_durability",
    "read_observatory",
    "observe_work",
    "project_live_work",
    "continue_from_observation",
    "get_send_link",
    "fire_action",
    "append_post",
    "append_model_post",
    "post_to_action_pad",
    "route_grokcom_revenue_work",
    "create_memory_board",
    "append_memory",
)

HttpFn = Callable[..., Any]


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "tag": "spark",
        "slack_tool": "@spark",
        "road": "SLACK_CUSTOM_TOOL",
        "mcp_url": SPARK_MCP_URL,
        "auth": AUTH,
        "gate": False,
        "commons_admission": False,
        "copy_secrets": False,
        "http_called": False,
        "reopen_need": False,
        "notion_owner_action_done": False,
    }


def parse_intent(body: str) -> dict[str, Any]:
    """Turn the tagged remainder into one MCP RPC. Default is discover."""
    text = str(body or "").strip()
    low = text.lower()
    if low in {"list", "tools", "tools/list"}:
        return {"rpc": "tools/list", "tool": "", "arguments": {}}
    if not text or low in {"discover", "capabilities", "whoami", "ping"}:
        return {
            "rpc": "tools/call",
            "tool": "discover_commons_capabilities",
            "arguments": {},
        }
    first, _, rest = text.partition(" ")
    name = first.strip()
    if name.lower() in {"search", "search_commons"}:
        query = rest.strip() if name.lower() == "search" else rest.strip()
        if name.lower() == "search_commons":
            query = rest.strip()
        return {
            "rpc": "tools/call",
            "tool": "search_commons",
            "arguments": {"query": query},
        }
    if name in KNOWN_TOOLS:
        args: dict[str, Any] = {}
        if name == "search_commons" and rest.strip():
            args = {"query": rest.strip()}
        elif name == "discover_commons_capabilities" and rest.strip():
            args = {"surface": rest.strip()}
        elif name == "read_commons_resource" and rest.strip():
            args = {"uri": rest.strip()}
        elif name == "verify_durability" and rest.strip():
            args = {"id": rest.strip()}
        elif rest.strip():
            args = {"query": rest.strip()}
        return {"rpc": "tools/call", "tool": name, "arguments": args}
    return {
        "rpc": "tools/call",
        "tool": "discover_commons_capabilities",
        "arguments": {"surface": text},
    }


def _parse_body(raw: bytes, content_type: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace") if raw else ""
    ctype = str(content_type or "").lower()
    if "text/event-stream" in ctype or text.lstrip().startswith(("event:", "data:")):
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return {"parse_error": True, "raw_utf8": text[:400]}
    try:
        parsed = json.loads(text or "null")
    except json.JSONDecodeError:
        return {"parse_error": True, "raw_utf8": text[:400]}
    return parsed if isinstance(parsed, dict) else {"non_object": parsed}


def default_http(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 20,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    req = urllib.request.Request(url, data=body, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = int(resp.status)
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp is not None else b""
        status = int(exc.code)
        hdrs = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {}, {"transport_error": type(exc).__name__}
    return status, hdrs, _parse_body(raw, hdrs.get("content-type", ""))


def _rpc(
    method: str,
    params: dict[str, Any] | None,
    *,
    request_id: int,
    http_request: HttpFn,
    url: str = SPARK_MCP_URL,
) -> tuple[int, dict[str, Any]]:
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL,
    }
    raw = http_request(
        method="POST",
        url=url,
        headers=headers,
        body=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
    )
    if isinstance(raw, tuple) and len(raw) >= 3:
        status = int(raw[0] or 0)
        body = raw[2] if isinstance(raw[2], dict) else {"non_object": raw[2]}
        return status, body
    if isinstance(raw, dict):
        return int(raw.get("status") or 200), raw
    return 0, {"non_object": raw}


def drive_spark(
    body: str = "",
    *,
    execute: bool = False,
    http_request: HttpFn | None = None,
    url: str = SPARK_MCP_URL,
) -> dict[str, Any]:
    """Drive the tagged remainder. Default dry-run. Never copy secrets."""
    intent = parse_intent(body)
    out = _base()
    out.update(
        {
            "body": str(body or "").strip(),
            "intent": intent,
            "reason": "ready_dry_run",
        }
    )
    if not execute:
        out["ok"] = True
        return out

    call = http_request or default_http
    init_status, init_body = _rpc(
        "initialize",
        {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        },
        request_id=1,
        http_request=call,
        url=url,
    )
    out["http_called"] = True
    out["initialize_http"] = init_status
    result = init_body.get("result") if isinstance(init_body.get("result"), dict) else {}
    server = result.get("serverInfo") if isinstance(result.get("serverInfo"), dict) else {}
    out["server_name"] = str(server.get("name") or "")
    out["server_version"] = str(server.get("version") or "")
    if init_status != 200 or out["server_name"] != "commons":
        out["reason"] = "spark_mcp_initialize_failed"
        return out

    list_status, list_body = _rpc(
        "tools/list",
        {},
        request_id=2,
        http_request=call,
        url=url,
    )
    out["tools_list_http"] = list_status
    tools = []
    listed = list_body.get("result") if isinstance(list_body.get("result"), dict) else {}
    for row in listed.get("tools") or []:
        if isinstance(row, dict) and row.get("name"):
            tools.append(str(row["name"]))
    out["tools"] = tools
    if list_status != 200:
        out["reason"] = "spark_mcp_tools_list_failed"
        return out

    if intent.get("rpc") == "tools/call" and intent.get("tool"):
        call_status, call_body = _rpc(
            "tools/call",
            {"name": intent["tool"], "arguments": intent.get("arguments") or {}},
            request_id=3,
            http_request=call,
            url=url,
        )
        out["tools_call_http"] = call_status
        out["called_tool"] = intent["tool"]
        if call_status != 200:
            out["reason"] = "spark_mcp_tools_call_failed"
            return out
        call_result = call_body.get("result")
        if isinstance(call_result, dict):
            out["call_keys"] = sorted(str(k) for k in call_result.keys())

    out["ok"] = True
    out["reason"] = "driven"
    blob = json.dumps(out)
    if "Authorization" in blob or "xoxb-" in blob:
        return {
            "ok": False,
            "tag": "spark",
            "road": "SLACK_CUSTOM_TOOL",
            "reason": "refused_secret_leak",
            "copy_secrets": False,
            "gate": False,
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--body", default="", help="tagged remainder")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="opt-in live HTTP against the public no-auth Spark MCP",
    )
    args = parser.parse_args(argv)
    out = drive_spark(args.body, execute=bool(args.execute))
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
