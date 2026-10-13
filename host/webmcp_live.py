#!/usr/bin/env python3
"""Independent live canary for the one public MCP plus GET /webmcp HTML.

Prints JSON. Exit 0 on LIVE_WEBMCP_HTML. Exit 2 on named Vercel NOT_FOUND.
Exit 1 on any other miss. Does not remint the adapter or pad.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

PUBLIC_MCP = "https://commons-spark-mcp.vercel.app/mcp"
PUBLIC_WEBMCP = "https://commons-spark-mcp.vercel.app/webmcp"


def _rpc_initialize() -> dict:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "webmcp-live-canary", "version": "1"},
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        PUBLIC_MCP,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-03-26",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        info = (body.get("result") or {}).get("serverInfo") or {}
        return {
            "status": resp.status,
            "name": info.get("name"),
            "version": info.get("version"),
        }


def _get_webmcp() -> dict:
    req = urllib.request.Request(PUBLIC_WEBMCP, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            ctype = resp.headers.get("content-type") or ""
            html_ok = (
                resp.status == 200
                and "text/html" in ctype
                and b"document.modelContext" in raw
            )
            return {
                "status": resp.status,
                "ctype": ctype,
                "bytes": len(raw),
                "x_vercel_error": resp.headers.get("x-vercel-error") or "",
                "html_ok": html_ok,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return {
            "status": exc.code,
            "ctype": exc.headers.get("content-type") or "",
            "bytes": len(raw),
            "x_vercel_error": exc.headers.get("x-vercel-error") or "",
            "html_ok": False,
            "head": raw[:160].decode("utf-8", "replace"),
        }


def measure() -> dict:
    mcp = _rpc_initialize()
    door = _get_webmcp()
    live_html = bool(door.get("html_ok"))
    named_404 = (
        door.get("status") == 404
        and "text/plain" in str(door.get("ctype") or "")
        and str(door.get("x_vercel_error") or "") == "NOT_FOUND"
    )
    if live_html:
        verdict = "LIVE_WEBMCP_HTML"
    elif named_404:
        verdict = "NAMED_VERCEL_NOT_FOUND"
    else:
        verdict = "STALE_OR_UNVERIFIED"
    return {
        "mcp": mcp,
        "webmcp": door,
        "one_public_mcp": PUBLIC_MCP,
        "verdict": verdict,
        "LIVE_WEBMCP_HTML": live_html,
    }


def main() -> int:
    row = measure()
    print(json.dumps(row, indent=2, sort_keys=True))
    if row["LIVE_WEBMCP_HTML"]:
        print("LIVE_WEBMCP_HTML")
        return 0
    if row["verdict"] == "NAMED_VERCEL_NOT_FOUND":
        print("NAMED_VERCEL_NOT_FOUND")
        return 2
    print("STALE_OR_UNVERIFIED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
