#!/usr/bin/env python3
"""Stealable lane + role files from the 2026-09-02 meeting approvals.

Meeting shape: lane/role, holder username, pool, claimed_at, last receipt SHA,
state. Claim is a Slack post. Silence opens the slot. Any harness may pick up.
Does not remint salon lanes.json / roles.json or HEAVY_LANES.
"""
from __future__ import annotations

import argparse
import html
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
LANES_PATH = ROOT / "ground" / "STEALABLE_LANES.json"
ROLES_PATH = ROOT / "ground" / "STEALABLE_ROLES.json"
LANES_CARD = ROOT / "ground" / "STEALABLE_LANES.md"
ROLES_CARD = ROOT / "ground" / "STEALABLE_ROLES.md"
HTML_PATH = ROOT / "stealable-lanes.html"
SALON_LANES = ROOT / "lanes.json"
SALON_ROLES = ROOT / "roles.json"
HEAVY = ROOT / "ground" / "HEAVY_LANES.json"

# KEEP tip $199 live-cash doors + Larger fixed on stealable-lanes.html remint
# (newbot-02 additive shelf; render_html lacked #live-cash entirely).
LIVE_CASH_HTML = """
<section id="live-cash">
  <h2>Live cash</h2>
  <p>Verified product pages only — no invented Stripe links.</p>
  <ul>
    <li><a href="dealer-service-lead-rescue.html">$199 dealer diagnostic</a></li>
    <li><a href="referral-intake-completeness.html">$199 referral diagnostic</a></li>
    <li><a href="repair-booking-preflight.html">$199 repair diagnostic</a></li>
    <li><a href="plant-downtime-handoff.html">$199 plant diagnostic</a></li>
  </ul>
  <p class="note"><strong>Larger fixed engagements</strong> (separate product pages; checkout/intent stays there): <a href="./diagnostic.html">GGUF diagnostic · $12,000 / 10 days</a> · <a href="./commercial.html">White Box pilot · $30,000 / 30 days</a>. Not remints of tip SKUs.</p>
  <p>Shelf: <a href="tools-cash.html">tools-cash.html</a>. Catalog: <a href="commerce.html">commerce.html</a>. Cite spy-html-money-doors-live-cash-20260905-05 — do not remint.</p>
</section>
"""

LANE_SCHEMA = "commons-stealable-lanes/v1"
ROLE_SCHEMA = "commons-stealable-roles/v1"
ALLOWED_STATES = {"OPEN", "HELD", "LANDED", "DONE"}
ROW_KEYS = (
    "holder_username",
    "pool",
    "claimed_at",
    "last_receipt_sha",
    "state",
)


def git_blob(rel: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(ROOT / rel)], text=True
    ).strip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(lanes: dict[str, Any] | None = None, roles: dict[str, Any] | None = None) -> dict[str, Any]:
    lanes = lanes if lanes is not None else load_json(LANES_PATH)
    roles = roles if roles is not None else load_json(ROLES_PATH)
    errors: list[str] = []
    if lanes.get("schema") != LANE_SCHEMA:
        errors.append("lanes.schema")
    if lanes.get("kind") != "STEALABLE_LANE_FILE":
        errors.append("lanes.kind")
    if roles.get("schema") != ROLE_SCHEMA:
        errors.append("roles.schema")
    if roles.get("kind") != "STEALABLE_ROLE_FILE":
        errors.append("roles.kind")
    for label, blob in (
        ("lanes", lanes),
        ("roles", roles),
    ):
        rule = blob.get("rule") or {}
        if rule.get("claim_is_a_post") is not True:
            errors.append(f"{label}.claim_is_a_post")
        if rule.get("open_on_silence") is not True:
            errors.append(f"{label}.open_on_silence")
        if rule.get("gate") is not False:
            errors.append(f"{label}.gate")
        if rule.get("login") is not False:
            errors.append(f"{label}.login")
        if blob.get("cash_usd") != 0:
            errors.append(f"{label}.cash_usd")
        if blob.get("sends") != 0:
            errors.append(f"{label}.sends")
        hub = blob.get("hub") or {}
        if hub.get("channel") != "C0BU51F1PL3":
            errors.append(f"{label}.hub.channel")
        if hub.get("approvals_ts") != "1788381748.979959":
            errors.append(f"{label}.hub.approvals_ts")
        if hub.get("claim_ts") != "1788381921.814949":
            errors.append(f"{label}.hub.claim_ts")
    keep = lanes.get("keep_unread") or {}
    for rel, prefix in keep.items():
        blob = git_blob(rel)
        if not blob.startswith(prefix):
            errors.append(f"keep:{rel}")
    for row in lanes.get("lanes") or []:
        for key in ("lane",) + ROW_KEYS:
            if key not in row:
                errors.append(f"lane.missing.{key}")
        if row.get("state") not in ALLOWED_STATES:
            errors.append(f"lane.state:{row.get('lane')}")
        if row.get("state") == "OPEN" and row.get("holder_username"):
            errors.append(f"lane.open-held:{row.get('lane')}")
        if row.get("state") == "HELD" and not (row.get("claim_post") or row.get("last_receipt_sha")):
            errors.append(f"lane.held-no-post:{row.get('lane')}")
    for row in roles.get("roles") or []:
        for key in ("role",) + ROW_KEYS:
            if key not in row:
                errors.append(f"role.missing.{key}")
        if row.get("state") not in ALLOWED_STATES:
            errors.append(f"role.state:{row.get('role')}")
        if row.get("state") == "HELD" and not row.get("claim_post"):
            errors.append(f"role.held-no-post:{row.get('role')}")
    item5 = next(
        (row for row in lanes.get("lanes") or [] if row.get("lane") == "stealable-lanes-roles"),
        None,
    )
    if not item5 or item5.get("holder_username") != "bc-23891c63":
        errors.append("item5.holder")
    if item5 and item5.get("claim_post") != "1788381921.814949":
        errors.append("item5.claim_post")
    peer = next(
        (row for row in lanes.get("lanes") or [] if row.get("lane") == "public-mcp-get-capability-map"),
        None,
    )
    if not peer or peer.get("holder_username") != "bc-847e1c9a":
        errors.append("item8.not-stolen")
    harbor = next(
        (row for row in lanes.get("lanes") or [] if row.get("lane") == "harborline-qualify-live-probe"),
        None,
    )
    if not harbor or harbor.get("holder_username") != "bc-31c8ef9a":
        errors.append("harborline.stolen")
    market = next(
        (row for row in lanes.get("lanes") or [] if row.get("lane") == "business-pack-marketplace"),
        None,
    )
    if not market or market.get("holder_username") != "bc-31c8ef9a":
        errors.append("harborline.market.stolen")
    if market and market.get("state") == "HELD" and not market.get("claim_post") and not market.get("last_receipt_sha"):
        errors.append("harborline.market.evidence")
    if SALON_LANES.read_bytes()[:1] != b"{":
        errors.append("salon.lanes")
    return {"ok": not errors, "errors": errors, "cash_usd": 0, "sends": 0}


def _rows_md(kind: str, rows: list[dict[str, Any]]) -> str:
    key = "lane" if kind == "lane" else "role"
    lines = [
        f"| {key} | holder_username | pool | claimed_at | last_receipt_sha | state | claim_post |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| `{name}` | `{holder}` | `{pool}` | `{when}` | `{sha}` | `{state}` | `{post}` |".format(
                name=row.get(key) or "",
                holder=row.get("holder_username") or "—",
                pool=row.get("pool") or "—",
                when=row.get("claimed_at") or "—",
                sha=(row.get("last_receipt_sha") or "—")[:12],
                state=row.get("state") or "",
                post=row.get("claim_post") or "—",
            )
        )
    return "\n".join(lines)


def write_cards(lanes: dict[str, Any] | None = None, roles: dict[str, Any] | None = None) -> None:
    lanes = lanes if lanes is not None else load_json(LANES_PATH)
    roles = roles if roles is not None else load_json(ROLES_PATH)
    LANES_CARD.write_text(
        "# STEALABLE LANES\n\n"
        "Meeting item 5. Claim is a Slack post. Silence opens the slot. "
        "Latest claim holds. This file is not salon `lanes.json` and not HEAVY_LANES.\n\n"
        "Cite hub `C0BU51F1PL3` `1788381748.979959`. CLAIM `1788381921.814949`.\n\n"
        + _rows_md("lane", list(lanes.get("lanes") or []))
        + "\n",
        encoding="utf-8",
    )
    ROLES_CARD.write_text(
        "# STEALABLE ROLES\n\n"
        "Same shape as the lane file. Role cards stay stealable. "
        "No single-clan choke. Usernames are per session.\n\n"
        "Cite hub `C0BU51F1PL3` `1788381748.979959`.\n\n"
        + _rows_md("role", list(roles.get("roles") or []))
        + "\n",
        encoding="utf-8",
    )


def render_html(lanes: dict[str, Any] | None = None, roles: dict[str, Any] | None = None) -> str:
    lanes = lanes if lanes is not None else load_json(LANES_PATH)
    roles = roles if roles is not None else load_json(ROLES_PATH)
    lane_rows = list(lanes.get("lanes") or [])
    role_rows = list(roles.get("roles") or [])

    def table(kind: str, rows: list[dict[str, Any]]) -> str:
        key = "lane" if kind == "lane" else "role"
        if not rows:
            return '<p class="note">Empty — every slot is open. Claim with a Slack post in the approvals thread.</p>'
        body = []
        for row in rows:
            body.append(
                "<tr><td><code>{name}</code></td><td><code>{holder}</code></td>"
                "<td><code>{pool}</code></td><td>{when}</td><td><code>{sha}</code></td>"
                "<td>{state}</td><td><code>{post}</code></td></tr>".format(
                    name=html.escape(str(row.get(key) or "")),
                    holder=html.escape(str(row.get("holder_username") or "—")),
                    pool=html.escape(str(row.get("pool") or "—")),
                    when=html.escape(str(row.get("claimed_at") or "—")),
                    sha=html.escape(str(row.get("last_receipt_sha") or "—")[:12]),
                    state=html.escape(str(row.get("state") or "")),
                    post=html.escape(str(row.get("claim_post") or "—")),
                )
            )
        head = (
            f"<thead><tr><th>{key}</th><th>holder_username</th><th>pool</th>"
            "<th>claimed_at</th><th>last receipt SHA</th><th>state</th>"
            "<th>claim post</th></tr></thead>"
        )
        return f'<div class="table-wrap"><table>{head}<tbody>{ "".join(body)}</tbody></table></div>'

    open_n = sum(1 for row in lane_rows if row.get("state") == "OPEN")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index,follow">
<meta http-equiv="Cache-Control" content="no-store">
<title>Stealable lanes and roles</title>
<link rel="stylesheet" href="./commons.css?v=20260823f">
<style>
.table-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:.4rem .5rem;border-bottom:1px solid #333;vertical-align:top}}
@media (max-width:640px){{body{{padding:1rem}} h1{{font-size:1.4rem}}}}
</style>
</head>
<body>
<p class="nav"><a href="./index.html">Commons</a> · <a href="./boards.html">boards</a> · <a href="./ground/STEALABLE_LANES.md">STEALABLE_LANES.md</a> · <a href="./ground/STEALABLE_ROLES.md">STEALABLE_ROLES.md</a> · <a href="./ground/OWNER_NOW.md">OWNER_NOW</a> · <a href="./action.html">ACTION PAD</a></p>
<h1>Stealable lanes and roles</h1>
<p class="law">Owner approval item 5 on hub <code>C0BU51F1PL3</code> <code>1788381748.979959</code>: lane file + role file, same shape. Claim is a Slack post. Silence opens the slot. Latest claim holds. Any harness picks up. Usernames are per session so fifty Codex windows stay distinguishable. No login. Possessing the link is enough.</p>
<p class="note">{open_n} approval lanes are OPEN. Claude keeps the scrub, Sidewalk gates, headless enforcer, and OWNER_NOW seed. Peer <code>bc-847e1c9a</code> holds items 8 and 3. Harborline <code>/qualify</code> stays <code>bc-31c8ef9a</code>. This door does not remint salon <code>lanes.json</code> / <code>roles.json</code> or HEAVY_LANES. Helper <code>python3 host/stealable_lanes.py --check</code>.</p>
<h2>Lanes</h2>
{table("lane", lane_rows)}
<h2>Roles</h2>
{table("role", role_rows)}
<p class="note">Role cards stay stealable. No single-clan choke. Did not invent Stripe URLs. Did not spawn Muse Spark / gpt-6 / gpt-5.7. Empty checkout is a measurement, not a freeze. Sends 0.</p>
{LIVE_CASH_HTML}
</body>
</html>
"""


def write_html() -> None:
    HTML_PATH.write_text(render_html(), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = check()
    if args.write:
        write_cards()
        write_html()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    if args.check or not (args.write or args.json):
        if not result["ok"]:
            print("FINDER-FAILED", ",".join(result["errors"]))
            return 1
        print("ok")
        return 0
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
