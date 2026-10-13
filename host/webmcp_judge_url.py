#!/usr/bin/env python3
"""WebMCP judge-URL leftover. Do not remint api/mcp.py or the contest canary."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
ID = "cursor-webmcp-judge-url-20260903-01"
CITE_CLAIM = "1788464053.553519"
CITE_WIRE = "wire-webmcp-challenge-20260903-01"
CITE_CONTEST = "cursor-webmcp-contest-20260903-01"
JUDGE_URL = "https://commons-spark-mcp.vercel.app/webmcp"
MCP_URL = "https://commons-spark-mcp.vercel.app/mcp"
ADAPTER = ROOT / "api" / "mcp.py"
PAD = ROOT / "webmcp.html"
REFUSE = ("--send", "--apply", "--go", "--autopilot", "--live", "--checkout", "--deploy")
DO_NOT_REMINT = (
    "api/mcp.py",
    "webmcp.html",
    "p/wire-webmcp-challenge-20260903-01.md",
    "p/cursor-webmcp-contest-20260903-01.md",
    "test_webmcp_door.py",
    "test_cursor_webmcp_contest.py",
    "vercel.json",
    ".github/workflows/spark-mcp-production.yml",
)


def git_blob(rel: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(ROOT / rel)], text=True
    ).strip()


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "WEBMCP_JUDGE_URL",
        "id": ID,
        "refused": flag,
        "sent": 0,
        "cash": 0,
        "invented_stripe_urls": False,
        "second_mcp": False,
        "verdict": "FINDER-FAILED",
        "note": (
            f"{flag} REFUSED. Did not remint api/mcp.py. Did not remint leftover contest canary. "
            "Judge URL truth is live curl, not git."
        ),
    }


def http_get(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
            return {
                "status": resp.status,
                "content_type": resp.headers.get("Content-Type", ""),
                "bytes": len(body),
                "vercel_error": resp.headers.get("x-vercel-error", ""),
                "html": body.lstrip().lower().startswith(b"<!doctype html")
                or body.lstrip().lower().startswith(b"<html"),
            }
    except urllib.error.HTTPError as visc:
        body = visc.read()
        return {
            "status": visc.code,
            "content_type": visc.headers.get("Content-Type", ""),
            "bytes": len(body),
            "vercel_error": visc.headers.get("x-vercel-error", ""),
            "html": False,
        }
    except Exception as visc:
        return {
            "status": 0,
            "content_type": "",
            "bytes": 0,
            "vercel_error": "",
            "html": False,
            "error": type(visc).__name__,
        }


def mcp_initialize() -> dict[str, Any]:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "webmcp-judge-url", "version": "1"},
            },
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        MCP_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            packet = json.loads(resp.read().decode("utf-8"))
            info = (packet.get("result") or {}).get("serverInfo") or {}
            return {
                "status": resp.status,
                "name": info.get("name"),
                "version": info.get("version"),
            }
    except Exception as visc:
        return {"status": 0, "name": "", "version": "", "error": type(visc).__name__}


def measure() -> dict[str, Any]:
    judge = http_get(JUDGE_URL)
    mcp = mcp_initialize()
    adapter_blob = git_blob("api/mcp.py")
    pad_blob = git_blob("webmcp.html")
    wire_blob = git_blob("p/wire-webmcp-challenge-20260903-01.md")
    contest_blob = git_blob("p/cursor-webmcp-contest-20260903-01.md")
    adapter_bytes = ADAPTER.stat().st_size
    pad_bytes = PAD.stat().st_size
    errors: list[str] = []
    if judge.get("status") != 200:
        errors.append("judge_url_not_200")
    if "text/html" not in str(judge.get("content_type", "")).lower():
        errors.append("judge_url_not_html")
    if not judge.get("html"):
        errors.append("judge_url_not_doctype")
    if mcp.get("status") != 200:
        errors.append("mcp_initialize_not_200")
    if mcp.get("name") != "commons" or mcp.get("version") != "1.4.0":
        errors.append("mcp_identity_drift")
    if adapter_bytes < 20000 or adapter_bytes > 23000:
        errors.append("adapter_size_reminted")
    if not adapter_blob.startswith("393da756"):
        errors.append("adapter_reminted")
    if not pad_blob.startswith("8bb181e0"):
        errors.append("pad_reminted")
    if not wire_blob.startswith("0e815c6d"):
        errors.append("wire_receipt_reminted")
    if not contest_blob.startswith("98fb6b6f"):
        errors.append("contest_leftover_reminted")
    if (ROOT / "marketplace.html").exists():
        errors.append("marketplace_html")
    return {
        "kind": "WEBMCP_JUDGE_URL",
        "id": ID,
        "cite_claim": CITE_CLAIM,
        "cite_wire": CITE_WIRE,
        "cite_contest": CITE_CONTEST,
        "judge_url": JUDGE_URL,
        "mcp_url": MCP_URL,
        "judge": judge,
        "mcp_initialize": mcp,
        "adapter_bytes": adapter_bytes,
        "adapter_blob": adapter_blob[:8],
        "pad_bytes": pad_bytes,
        "pad_blob": pad_blob[:8],
        "wire_receipt": wire_blob[:8],
        "contest_receipt": contest_blob[:8],
        "did_not_remint": list(DO_NOT_REMINT),
        "vercel_team_token": "FINDER-FAILED",
        "spark_mcp_production": "FINDER-FAILED",
        "second_mcp": False,
        "type_devpost": "unread",
        "invented_stripe_urls": False,
        "item_11_next_ui": False,
        "sent": 0,
        "cash": 0,
        "verdict": "RENDER" if not errors else "FINDER-FAILED",
        "errors": errors,
        "note": (
            "Judge URL must be live text/html 200. Git pad and ~21k adapter stay KEEP. "
            "Leftover contest canary 98fb6b6f KEEP. Did not remint api/mcp.py. "
            "This harness has no VERCEL_TEAM_TOKEN."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    for flag in unknown:
        if flag in REFUSE:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "kind": "WEBMCP_JUDGE_URL",
                        "verdict": "FINDER-FAILED",
                        "sent": 0,
                        "unknown": flag,
                        "note": f"{flag} FINDER-FAILED, never silent 0.",
                    },
                    sort_keys=True,
                )
            )
            return 1
    packet = measure()
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0 if packet["verdict"] == "RENDER" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
