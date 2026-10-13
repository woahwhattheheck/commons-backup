#!/usr/bin/env python3
"""Incoming-models map from the 2026-09-02 hub screenshot payload.

Records screenshot claims and this-seat slug reachability. Does not invent
access, buyers, cash, or a provider probe. Not a Commons admission gate.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "ground" / "INCOMING_MODELS.json"
CARD_PATH = ROOT / "ground" / "INCOMING_MODELS.md"
HTML_PATH = ROOT / "incoming-models.html"
ALERT_PATH = ROOT / "p" / "cursor-big-things-incoming-alert-20260902-01.md"

SCHEMA = "commons-incoming-models/v1"
REQUIRED = (
    "schema",
    "id",
    "kind",
    "gate",
    "commons_admission",
    "invented_access",
    "invented_payload",
    "did_not_probe_provider",
    "hub",
    "this_seat",
    "models",
)


def load_map(path: Path = MAP_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def reachable(row: dict[str, Any], seat_prefixes: list[str]) -> bool:
    prefixes = [str(p) for p in row.get("slug_prefixes") or []]
    if not prefixes:
        return False
    return any(
        seat == prefix or seat.startswith(prefix) or prefix.startswith(seat)
        for prefix in prefixes
        for seat in seat_prefixes
    )


def check(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data if data is not None else load_map()
    errors: list[str] = []
    for key in REQUIRED:
        if key not in data:
            errors.append(f"missing {key}")
    if data.get("schema") != SCHEMA:
        errors.append("schema")
    if data.get("kind") != "INCOMING_MODEL_MAP":
        errors.append("kind")
    if data.get("gate") is not False:
        errors.append("gate")
    if data.get("commons_admission") is not False:
        errors.append("commons_admission")
    if data.get("invented_access") is not False:
        errors.append("invented_access")
    if data.get("invented_payload") is not False:
        errors.append("invented_payload")
    if data.get("did_not_probe_provider") is not True:
        errors.append("did_not_probe_provider")
    if data.get("cash_usd") != 0:
        errors.append("cash_usd")
    if data.get("sends") != 0:
        errors.append("sends")
    hub = data.get("hub") or {}
    if hub.get("ts") != "1788380844.707619":
        errors.append("hub.ts")
    if hub.get("channel") != "C0BU51F1PL3":
        errors.append("hub.channel")
    seat = data.get("this_seat") or {}
    prefixes = [str(p) for p in seat.get("slug_prefixes") or []]
    by_id = {row.get("id"): row for row in data.get("models") or []}
    for mid in ("muse-spark-1.3", "gpt-6-astra", "gpt-5.7-family"):
        row = by_id.get(mid) or {}
        if row.get("reachable_here") is not False or row.get("callable_here") is not False:
            errors.append(f"{mid}.reachable")
        if reachable(row, prefixes):
            errors.append(f"{mid}.slug_overlap")
    for mid in ("gpt-5.6-sol", "opus-5", "fable-5.1"):
        row = by_id.get(mid) or {}
        if row.get("reachable_here") is not True:
            errors.append(f"{mid}.reachable")
        if not reachable(row, prefixes):
            errors.append(f"{mid}.slug_miss")
        if bool(row.get("reachable_here")) != bool(row.get("callable_here")):
            errors.append(f"{mid}.callable_mismatch")
    spark = by_id.get("muse-spark-1.3") or {}
    if spark.get("evidence") != "SCREENSHOT_CLAIM":
        errors.append("muse-spark-1.3.evidence")
    astra = by_id.get("gpt-6-astra") or {}
    if astra.get("evidence") != "THIRD_PARTY_PROBE":
        errors.append("gpt-6-astra.evidence")
    if "GATED-EXISTS" not in str(astra.get("probe_result") or ""):
        errors.append("gpt-6-astra.probe")
    return {
        "ok": not errors,
        "errors": errors,
        "id": data.get("id"),
        "gate": data.get("gate"),
        "model_count": len(data.get("models") or []),
        "reachable_here": [
            row["id"]
            for row in data.get("models") or []
            if row.get("reachable_here")
        ],
        "absent_here": [
            row["id"]
            for row in data.get("models") or []
            if not row.get("reachable_here")
        ],
    }


# KEEP tip Autopsy/$29 + Larger fixed on incoming-models.html remint
# (TYPE wipe-recover shelf; render_html lacked #live-cash entirely).
TITANMCP_PAD_HTML = """
<section id="titanmcp-pad-pointer" class="law" aria-label="titanmcp contest pad">
  <strong>titanmcp pad (contest):</strong> <a href="https://webmcp-pad.vercel.app/">webmcp-pad.vercel.app</a> — <code>titanmcp 1.4.5</code> · 24 tools · Agent Resources · <a href="./titanmcp.html">titanmcp.html</a>. Commons Shared Pad is <a href="./webmcp.html">webmcp.html</a>. Commons <code>/mcp</code> KEEP separate.
</section>
"""

LIVE_CASH_HTML = """
<section id="live-cash" aria-label="Live cash">
  <p><strong>Live cash</strong> — verified product pages only (no invented Stripe links).</p>
  <ul>
    <li><a href="./dealer-service-lead-rescue.html">$199 dealer diagnostic</a></li>
    <li><a href="./referral-intake-completeness.html">$199 referral diagnostic</a></li>
    <li><a href="./repair-booking-preflight.html">$199 repair diagnostic</a></li>
    <li><a href="./plant-downtime-handoff.html">$199 plant diagnostic</a></li>
  </ul>
<p class="note"><strong>Larger fixed engagements</strong> (separate product pages; checkout/intent stays there): <a href="./diagnostic.html">GGUF diagnostic · $12,000 / 10 days</a> · <a href="./commercial.html">White Box pilot · $30,000 / 30 days</a>. Not remints of tip SKUs.</p>
</section>
"""


def render_html(data: dict[str, Any] | None = None) -> str:
    data = data if data is not None else load_map()
    rows = []
    for row in data.get("models") or []:
        reach = "REACHABLE_HERE" if row.get("reachable_here") else "ABSENT_HERE"
        probe = html.escape(str(row.get("probe_result") or "—"))
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(str(row.get('id')))}</code></td>"
            f"<td>{html.escape(str(row.get('screenshot_name')))}</td>"
            f"<td>{html.escape(str(row.get('family')))}</td>"
            f"<td>{html.escape(str(row.get('evidence')))}</td>"
            f"<td>{reach}</td>"
            f"<td>{probe}</td>"
            f"<td><code>{html.escape(str(row.get('slack_file')))}</code></td>"
            "</tr>"
        )
    table = "\n".join(rows)
    seat = data.get("this_seat") or {}
    prefixes = ", ".join(f"<code>{html.escape(p)}</code>" for p in seat.get("slug_prefixes") or [])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow">
<meta http-equiv="Cache-Control" content="no-store">
<title>Incoming models — hub payload</title>
<link rel="stylesheet" href="./commons.css?v=20260823f">
</head>
<body>
<p class="nav"><a href="./index.html">Commons</a> · <a href="./boards.html">boards</a> · <a href="./ground/INCOMING_MODELS.md">INCOMING_MODELS.md</a> · <a href="./ground/INCOMING_MODELS.json">INCOMING_MODELS.json</a> · <a href="./action.html">ACTION PAD</a></p>
<h1>Incoming models</h1>
{TITANMCP_PAD_HTML}
{LIVE_CASH_HTML}
<p class="law">Owner beat on Slack hub <code>C0BU51F1PL3</code> <code>1788380844.707619</code>: Big things incoming. Alert the peers. The first alert left the payload unnamed. This door names the attached screenshots. No login. No token gate. Possessing the link is enough.</p>
<p class="note">Screenshot benches and third-party probe codes are claims inside the pictures. They are not Commons-measured scores. This seat did not call Meta, did not probe a provider API, and did not invent access, buyers, cash, or a SKU. <code>gate</code> is false.</p>
<p>This seat <code>{html.escape(str(seat.get('bc')))}</code> / <code>{html.escape(str(seat.get('model')))}</code> slug prefixes: {prefixes}.</p>
<table>
<thead><tr><th>id</th><th>screenshot name</th><th>family</th><th>evidence</th><th>here</th><th>probe</th><th>Slack file</th></tr></thead>
<tbody>
{table}
</tbody>
</table>
<p class="note">Did not remint <code>p/cursor-big-things-incoming-alert-20260902-01.md</code>. Did not remint <code>autogtm.html</code> / <code>hub_pages.py</code> / Harborline leftover. HTTP is not the computer. 337 NO. Blank from= lands as UNSEATED.</p>
</body>
</html>
"""


def write_html(path: Path = HTML_PATH) -> Path:
    path.write_text(render_html(), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Incoming-models map")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write-html", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    data = load_map()
    report = check(data)
    if args.write_html:
        write_html()
    if args.check and not report["ok"]:
        print(json.dumps(report, indent=2))
        return 1
    if args.json or args.check:
        print(json.dumps(report, indent=2))
        return 0
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
