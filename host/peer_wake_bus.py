#!/usr/bin/env python3
"""host/peer_wake_bus.py — DIRECTIVE 2 remaining doorbell gap.

Commons can expose work and still cannot doorbell ChatGPT or Claude.
This leftover measures the host-neutral peer wake bus. It does not
remint ping poll adapters, harness_wake, job-watchdog, MCP jobs,
Slack access canary, Gemini Slack, or integrations/grok_slack.
It never fabricates a live wake. titan: NOT_WRITTEN. No auth. No gate.

  python3 host/peer_wake_bus.py
  python3 host/peer_wake_bus.py --root .
  python3 host/peer_wake_bus.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


DEFAULT_CARD = os.path.join("ground", "PEER_WAKE_BUS.md")
DEFAULT_CATALOG = os.path.join("ground", "PEER_WAKE_BUS.json")
BUS_DIR = os.path.join("peer_wake")
SOURCE_ID = "grok-peer-wake-bus-20260828-01"
REQUIRED = (
    os.path.join("peer_wake", "bus.py"),
    os.path.join("peer_wake", "schema.json"),
    os.path.join("peer_wake", "adapters", "poll.py"),
    os.path.join("peer_wake", "adapters", "slack_mention.py"),
    os.path.join("peer_wake", "targets", "chatgpt.json"),
    os.path.join("peer_wake", "targets", "claude.json"),
    os.path.join("peer_wake", "targets", "grok_slack.json"),
    os.path.join("ping", "chatgpt.md"),
    os.path.join("ping", "claude.md"),
    os.path.join("ping", "adapters.md"),
    os.path.join("harness_wake", "watchdog.py"),
    os.path.join("independent_commons_mcp", "jobs.py"),
    os.path.join("integrations", "grok_slack", "bridge.py"),
    os.path.join("integrations", "gemini_slack", "bridge.py"),
    os.path.join("host", "slack_access_canary.py"),
)


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def classify(root="."):
    missing = [rel for rel in REQUIRED if not os.path.isfile(os.path.join(root, rel))]
    card = _read(root, DEFAULT_CARD)
    catalog = _read(root, DEFAULT_CATALOG)
    sys.path.insert(0, str(Path(root).resolve()))
    from peer_wake.bus import doctor

    report = doctor(root=Path(root).resolve(), env={})
    secrets = bool(report.get("secrets_in_config"))
    live = bool(report.get("live_wake"))
    chatgpt = next((row for row in report.get("targets") or [] if row.get("peer") == "CHATGPT"), {})
    claude = next((row for row in report.get("targets") or [] if row.get("peer") == "CLAUDE"), {})
    receipt_rel = os.path.join("p", "%s.md" % SOURCE_ID)
    receipt_present = os.path.isfile(os.path.join(root, receipt_rel))
    ok = (
        not missing
        and SOURCE_ID in card
        and SOURCE_ID in catalog
        and report.get("code") == "CODE_READY"
        and chatgpt.get("doorbell") == "EXTERNAL_PLATFORM_ACTION"
        and claude.get("doorbell") == "EXTERNAL_PLATFORM_ACTION"
        and not secrets
        and not live
        and report.get("no_auth")
        and report.get("no_gate")
    )
    return {
        "ok": bool(ok),
        "state": "INTEGRATED" if ok else "NOT_LANDED",
        "missing": missing,
        "code": report.get("code"),
        "chatgpt_doorbell": chatgpt.get("doorbell"),
        "claude_doorbell": claude.get("doorbell"),
        "live_wake": live,
        "secrets_in_config": secrets,
        "no_auth": report.get("no_auth"),
        "no_gate": report.get("no_gate"),
        "titan": "NOT_WRITTEN",
        "source_id": SOURCE_ID,
        "receipt_path": receipt_rel,
        "receipt_present": receipt_present,
        "doctor": report,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure the peer wake bus leftover.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    row = classify(args.root)
    json.dump(row, sys.stdout, ensure_ascii=True, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if args.self_test and not row.get("ok"):
        return 2
    return 0 if row.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
