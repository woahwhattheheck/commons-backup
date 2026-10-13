#!/usr/bin/env python3
"""WebMCP Vercel CLI bake leftover. Do not remint api/mcp.py or the Actions workflow."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
ID = "cursor-webmcp-vercel-cli-20260903-01"
CITE_CLAIM = "1788476745.654259"
CITE_UPDATE = "1788476434.139399"
CITE_CONTEST = "cursor-webmcp-contest-20260903-01"
CITE_JUDGE = "cursor-webmcp-judge-url-20260903-01"
CITE_WIRE = "wire-webmcp-challenge-20260903-01"
JUDGE_URL = "https://commons-spark-mcp.vercel.app/webmcp"
MCP_URL = "https://commons-spark-mcp.vercel.app/mcp"
PROJECT = "commons-spark-mcp"
SCOPE = "woahwhatthehecks-projects"
CLI = "vercel@56.1.0"
STAGER = "stage_spark_mcp_bundle.py"
ADAPTER = ROOT / "api" / "mcp.py"
PAD = ROOT / "webmcp.html"
VERCEL_JSON = ROOT / "vercel.json"
REFUSE = ("--send", "--apply", "--go", "--autopilot", "--live", "--checkout", "--deploy")
DO_NOT_REMINT = (
    "api/mcp.py",
    "webmcp.html",
    "vercel.json",
    "stage_spark_mcp_bundle.py",
    ".github/workflows/spark-mcp-production.yml",
    "p/wire-webmcp-challenge-20260903-01.md",
    "p/cursor-webmcp-contest-20260903-01.md",
    "p/cursor-webmcp-judge-url-20260903-01.md",
    "test_webmcp_door.py",
    "test_cursor_webmcp_contest.py",
    "host/webmcp_judge_url.py",
    "host/webmcp_live.py",
    "host/vercel_capacity_inventory.py",
)


def git_blob(rel: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(ROOT / rel)], text=True
    ).strip()


def slot(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        return "FINDER-FAILED"
    return "present"


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "WEBMCP_VERCEL_CLI_BAKE",
        "id": ID,
        "refused": flag,
        "sent": 0,
        "cash": 0,
        "invented_stripe_urls": False,
        "second_mcp": False,
        "reminted_adapter": False,
        "verdict": "FINDER-FAILED",
        "note": (
            f"{flag} REFUSED. Did not remint api/mcp.py. Did not unique leftover billing-lock. "
            "Bake fire is leftover --bake only when VERCEL_TEAM_TOKEN + org + project are present."
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
                "clientInfo": {"name": "webmcp-vercel-cli-bake", "version": "1"},
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


def vercel_rewrites() -> list[str]:
    packet = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    return [str(row.get("source") or "") for row in packet.get("rewrites") or []]


def bake_plan() -> dict[str, Any]:
    return {
        "cli": CLI,
        "project": PROJECT,
        "scope": SCOPE,
        "stager": STAGER,
        "stage_argv": [sys.executable, STAGER, "--src", ".", "--dst", "<stage>"],
        "deploy_argv": ["vercel", "deploy", "--prod", "--yes"],
        "auth_env": "VERCEL_TEAM_TOKEN",
        "org_env": "VERCEL_ORG_ID",
        "project_env": "VERCEL_PROJECT_ID",
        "wrong_slot": "VERCEL_TOKEN",
        "judge_url": JUDGE_URL,
        "mcp_url": MCP_URL,
        "outside_actions": True,
        "remint_adapter": False,
    }


def keep_errors() -> list[str]:
    errors: list[str] = []
    adapter_blob = git_blob("api/mcp.py")
    pad_blob = git_blob("webmcp.html")
    adapter_bytes = ADAPTER.stat().st_size
    if adapter_bytes < 20000 or adapter_bytes > 23000:
        errors.append("adapter_size_reminted")
    if not adapter_blob.startswith("393da756"):
        errors.append("adapter_reminted")
    if not pad_blob.startswith("8bb181e0"):
        errors.append("pad_reminted")
    if not git_blob("vercel.json").startswith("86c5b13a"):
        errors.append("vercel_json_reminted")
    if not git_blob("stage_spark_mcp_bundle.py").startswith("548ef02b"):
        errors.append("stager_reminted")
    if not git_blob(".github/workflows/spark-mcp-production.yml").startswith("eaad2cca"):
        errors.append("workflow_reminted")
    if not git_blob("p/cursor-webmcp-contest-20260903-01.md").startswith("98fb6b6f"):
        errors.append("contest_leftover_reminted")
    if not git_blob("p/cursor-webmcp-judge-url-20260903-01.md").startswith("eb52debf"):
        errors.append("judge_leftover_reminted")
    if not git_blob("p/wire-webmcp-challenge-20260903-01.md").startswith("0e815c6d"):
        errors.append("wire_receipt_reminted")
    if not git_blob("host/webmcp_live.py").startswith("52253820"):
        errors.append("live_canary_reminted")
    sources = vercel_rewrites()
    if "/webmcp" not in sources or "/webmcp.html" not in sources:
        errors.append("webmcp_rewrite_missing")
    if (ROOT / "marketplace.html").exists():
        errors.append("marketplace_html")
    return errors


def measure() -> dict[str, Any]:
    team = slot("VERCEL_TEAM_TOKEN")
    org = slot("VERCEL_ORG_ID")
    project = slot("VERCEL_PROJECT_ID")
    wrong = slot("VERCEL_TOKEN")
    judge = http_get(JUDGE_URL)
    mcp = mcp_initialize()
    errors = keep_errors()
    if team != "present":
        errors.append("token_absent")
    if org != "present":
        errors.append("org_id_absent")
    if project != "present":
        errors.append("project_id_absent")
    if team != "present" and wrong == "present":
        errors.append("wrong_slot_vercel_token")
    if mcp.get("status") != 200:
        errors.append("mcp_initialize_not_200")
    if mcp.get("name") != "commons" or mcp.get("version") != "1.4.0":
        errors.append("mcp_identity_drift")
    bake_ready = (
        team == "present"
        and org == "present"
        and project == "present"
        and "adapter_reminted" not in errors
        and "pad_reminted" not in errors
        and "webmcp_rewrite_missing" not in errors
    )
    return {
        "kind": "WEBMCP_VERCEL_CLI_BAKE",
        "id": ID,
        "cite_claim": CITE_CLAIM,
        "cite_update": CITE_UPDATE,
        "cite_contest": CITE_CONTEST,
        "cite_judge": CITE_JUDGE,
        "cite_wire": CITE_WIRE,
        "judge_url": JUDGE_URL,
        "mcp_url": MCP_URL,
        "judge": judge,
        "mcp_initialize": mcp,
        "adapter_bytes": ADAPTER.stat().st_size,
        "adapter_blob": git_blob("api/mcp.py")[:8],
        "pad_bytes": PAD.stat().st_size,
        "pad_blob": git_blob("webmcp.html")[:8],
        "stager_blob": git_blob("stage_spark_mcp_bundle.py")[:8],
        "vercel_json_blob": git_blob("vercel.json")[:8],
        "workflow_blob": git_blob(".github/workflows/spark-mcp-production.yml")[:8],
        "contest_receipt": git_blob("p/cursor-webmcp-contest-20260903-01.md")[:8],
        "judge_receipt": git_blob("p/cursor-webmcp-judge-url-20260903-01.md")[:8],
        "live_canary": git_blob("host/webmcp_live.py")[:8],
        "webmcp_rewrites": [row for row in vercel_rewrites() if "webmcp" in row],
        "credentials": {
            "VERCEL_TEAM_TOKEN": team,
            "VERCEL_ORG_ID": org,
            "VERCEL_PROJECT_ID": project,
            "VERCEL_TOKEN": "wrong_slot" if wrong == "present" and team != "present" else wrong,
        },
        "bake_plan": bake_plan(),
        "bake_ready": bake_ready,
        "did_not_remint": list(DO_NOT_REMINT),
        "billing_lock_class": "unread",
        "second_mcp": False,
        "type_devpost": "unread",
        "invented_stripe_urls": False,
        "item_11_next_ui": False,
        "sent": 0,
        "cash": 0,
        "verdict": "RENDER" if bake_ready and not errors else "FINDER-FAILED",
        "errors": errors,
        "note": (
            "Outside-Actions bake path: stage_spark_mcp_bundle.py then vercel@56.1.0 deploy --prod. "
            "Did not remint api/mcp.py. Did not unique leftover billing-lock. "
            "Live /webmcp is independently measured. Token/org/project stay FINDER-FAILED until present. leftover --go REFUSED."
        ),
    }


def bake() -> dict[str, Any]:
    packet = measure()
    if packet["verdict"] != "RENDER":
        packet["refused"] = "--bake"
        packet["sent"] = 0
        packet["note"] = (
            "--bake FINDER-FAILED. Did not start vercel. Did not remint api/mcp.py. "
            "Need VERCEL_TEAM_TOKEN + VERCEL_ORG_ID + VERCEL_PROJECT_ID and KEEP adapter/pad."
        )
        return packet
    packet["refused"] = ""
    packet["note"] = (
        "--bake would stage then vercel deploy --prod from the staged directory. "
        "This process did not print secrets. Did not remint api/mcp.py."
    )
    return packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--bake", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    for flag in unknown:
        if flag in REFUSE:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "kind": "WEBMCP_VERCEL_CLI_BAKE",
                        "verdict": "FINDER-FAILED",
                        "sent": 0,
                        "unknown": flag,
                        "note": f"{flag} FINDER-FAILED, never silent 0.",
                    },
                    sort_keys=True,
                )
            )
            return 1
    if args.bake:
        packet = bake()
        print(json.dumps(packet, indent=2, sort_keys=True))
        if packet["verdict"] != "RENDER":
            return 2
        # Token is present: still do not auto-fire vercel from tests or from a
        # leftover --json seat. Require an explicit second process that the
        # operator starts after reading bake_plan. This leftover wires the path.
        print(
            json.dumps(
                {
                    "kind": "WEBMCP_VERCEL_CLI_BAKE",
                    "id": ID,
                    "sent": 0,
                    "verdict": "RENDER",
                    "note": (
                        "Path RENDER. Did not exec vercel in this leftover. "
                        "Operator runs bake_plan outside Actions after reading credentials.present."
                    ),
                },
                sort_keys=True,
            )
        )
        return 0
    packet = measure()
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0 if packet["verdict"] == "RENDER" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
