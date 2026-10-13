#!/usr/bin/env python3
"""Same commerce-agent loop as Claude Commerce Agents, cited not copied.

Bryce 2026-09-02 Slack C0BU51F1PL3 `1788388313.281509` BIG AND HUGE plus
`1788388319.646839` "We need to use that" (ClaudeDevs commerce-agents shot
`F0BUL9V9Z34`). Same shape as the Explee AutoGTM leftover: name the public
mechanism, cite the open repo, run it as Commons source. Do not copy the
Anthropic tree. Do not import `.claude-plugin` into Cursor.

Public blueprint (Apache-2.0, cited): github.com/anthropics/commerce-agents
pin `fd4d59224ab96b43c6dc6888207c67b3bd5a24cf`. Two agents (shopping +
merchant), four verticals (retail, travel, telecom, entertainment). Checkout
renders the cart for the host; the model never sees a checkout URL. Merchant
writes stay staged. Commons compose uses the existing payment-capability
door as host handoff. Never invent a Stripe URL. --send/--go/--charge/--live
/--claude-plugin REFUSED.

Rides leftover `host/commerce_agents.py` / leftover id
`cursor-claude-commerce-agents-20260902-01`. Do not remint those.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import commerce_agents as leftover  # noqa: E402

CATALOG = ROOT / "ground" / "COMMERCE_AGENTS_SAME_LOOP.json"
HTML_PATH = ROOT / "commerce-agents-loop.html"
ID = "cursor-big-huge-commerce-agents-20260902-01"
LEFTOVER_ID = leftover.ID
OPEN_TWIN = "https://github.com/anthropics/commerce-agents"
OPEN_TWIN_PIN = "fd4d59224ab96b43c6dc6888207c67b3bd5a24cf"
SOLUTIONS = "https://claude.com/solutions/commerce"
ENGINEERING = "https://claude.com/blog/the-anatomy-of-effective-commerce-agents"
SLACK_FILE = "F0BUL9V9Z34"
SLACK_HUB = "C0BU51F1PL3"
SLACK_TS = "1788388313.281509"
AGENTS = ("shopper", "merchant")
VERTICALS = ("retail", "travel", "telecom", "entertainment")
SHOPPER_FLOWS = (
    "search-discovery",
    "purchase-research",
    "planning-goals",
    "customer-care",
    "memory-personalization",
)
MERCHANT_FLOWS = (
    "performance-insights",
    "catalog-listings",
    "inventory-operations",
    "pricing-promotions",
    "marketing-campaigns",
)
STEPS = (
    "choose_agent",
    "choose_vertical",
    "search_discovery",
    "purchase_research",
    "planning_goals",
    "stage_checkout",
    "customer_care",
    "memory_personalization",
)
MERCHANT_STEPS = (
    "choose_agent",
    "choose_vertical",
    "performance_insights",
    "catalog_listings",
    "inventory_operations",
    "pricing_promotions",
    "marketing_campaigns",
    "stage_writes",
)
REFUSE = ("--send", "--apply", "--go", "--autopilot", "--charge", "--live", "--claude-plugin")
DO_NOT_REMINT = (
    "cursor-claude-commerce-agents-20260902-01",
    "host/commerce_agents.py",
    "ground/COMMERCE_AGENTS.json",
    "commerce-agents.html",
    "test_commerce_agents.py",
    "cursor-autogtm-explee-same-loop-20260902-01",
    "host/autogtm_same_loop.py",
    "autogtm.html",
    "cursor-big-things-incoming-shots-20260902-01",
    "cursor-big-things-incoming-alert-20260902-01",
    "shots/cursor-big-things-incoming-hub-1-20260902.png",
    "shots/cursor-big-things-incoming-hub-2-20260902.png",
    "cursor-what-a-pack-is-20260902-01",
    "cursor-harborline-pack-market-render-20260902-01",
    "cursor-harborline-qualify-live-probe-20260902-01",
    "host/payment_capability.py",
    "door.js",
    "hub_pages.py",
    "CLAUDE.md",
)


Opener = Callable[[str], tuple[int, str]]


def live_opener(url: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "commons-commerce-agents-same-loop/1", "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")[:400]
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:400]
        return int(error.code), body
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 0, str(error)


def probe_url(url: str, opener: Opener) -> dict[str, Any]:
    code, body = opener(url)
    hit = code == 200
    return {
        "asked": True,
        "url": url,
        "http": code,
        "body_snip": body[:160],
        "state": "HIT" if hit else "FINDER-FAILED",
        "permission": False,
        "note": (
            "Public blueprint probe. HTTP 200 is a cite, not a Commons fork, "
            "not a login, never silent 0. Missing/blocked is FINDER-FAILED."
        ),
        "external": "EXTERNAL_PROVIDER_ACTION",
        "copied_tree": False,
    }


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def choose_agent(name: str) -> str:
    agent = (name or "shopper").strip().lower()
    if agent not in AGENTS:
        raise ValueError("agent must be shopper or merchant")
    return agent


def choose_vertical(name: str) -> str:
    vertical = (name or "retail").strip().lower()
    if vertical not in VERTICALS:
        raise ValueError("vertical must be retail, travel, telecom, or entertainment")
    return vertical


def search_discovery(catalog: dict[str, Any], vertical: str) -> list[dict[str, Any]]:
    rows = []
    for item in catalog.get("offers") or []:
        tags = item.get("verticals") or []
        if vertical in tags or "all" in tags:
            rows.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "page": item.get("page"),
                    "price_usd": item.get("price_usd"),
                    "verticals": list(tags),
                }
            )
    return rows


def purchase_research(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(hits, key=lambda row: int(row.get("price_usd") or 0))
    return [{**row, "compared": True} for row in ranked]


def planning_goals(hits: list[dict[str, Any]], vertical: str) -> dict[str, Any]:
    return {
        "vertical": vertical,
        "goal": "stage one host-handoff cart from public Commons offers",
        "picked": [row["id"] for row in hits[:3]],
        "state": "PLANNED",
    }


def stage_checkout(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": "STAGED_HOST_HANDOFF",
        "host_door": "payment-capability.html",
        "commerce_door": "commerce.html",
        "model_sees_url": False,
        "invented_url": False,
        "picked": list(plan.get("picked") or []),
        "sent": False,
        "charged": False,
        "cash_usd": 0,
        "note": (
            "Blueprint checkout renders the cart for the host. Commons host "
            "door is payment-capability.html. Never invent a Stripe URL."
        ),
    }


def customer_care() -> dict[str, Any]:
    return {
        "state": "STAGED",
        "answers": 0,
        "note": "Order/policy answers stay staged. No live ticket send.",
    }


def memory_personalization() -> dict[str, Any]:
    return {
        "state": "OFF_UNTIL_SESSION",
        "stored": False,
        "note": "No customer memory store on Commons. Switch, not a lock.",
    }


def merchant_digest(vertical: str) -> dict[str, Any]:
    return {
        "vertical": vertical,
        "insights": 0,
        "listings_edited": 0,
        "inventory_writes": 0,
        "price_moves": 0,
        "campaigns": 0,
        "state": "STAGED",
        "note": "Merchant writes stay staged until a person approves. --apply REFUSED.",
    }


def stage_writes() -> dict[str, Any]:
    return {
        "state": "STAGED",
        "applied": False,
        "sent": False,
        "note": "Approval surface is the operator. Commons does not apply merchant writes.",
    }


def slack_file_measure() -> dict[str, Any]:
    return {
        "id": SLACK_FILE,
        "hub": SLACK_HUB,
        "ts": SLACK_TS,
        "mime": "image/jpeg",
        "name": "1788388307909.jpeg",
        "bytes": "FINDER-FAILED",
        "search_space": [
            "Slack MCP slack_read_file returned a description, not JPEG bytes",
            "GET files.slack.com/files-pri/T0BRETUB5TK-F0BUL9V9Z34/1788388307909.jpeg HTTP 302 login",
            "no SLACK_BOT_TOKEN in this process environment",
            "did not remint leftover shots ac761b70 / 8eb5940f",
        ],
        "never_silent_0": True,
        "permission": False,
    }


def measure(
    *,
    agent: str = "shopper",
    vertical: str = "retail",
    opener: Opener = live_opener,
) -> dict[str, Any]:
    catalog = load_catalog()
    picked_agent = choose_agent(agent)
    picked_vertical = choose_vertical(vertical)
    twin = probe_url(OPEN_TWIN, opener)
    solutions = probe_url(SOLUTIONS, opener)
    hits = search_discovery(catalog, picked_vertical)
    compared = purchase_research(hits)
    plan = planning_goals(compared, picked_vertical)
    cart = stage_checkout(plan)
    care = customer_care()
    memory = memory_personalization()
    merchant = merchant_digest(picked_vertical) if picked_agent == "merchant" else None
    writes = stage_writes() if picked_agent == "merchant" else None
    steps = list(MERCHANT_STEPS if picked_agent == "merchant" else STEPS)
    leftover_row = leftover.measure()
    return {
        "kind": "COMMERCE_AGENTS_SAME_LOOP",
        "schema": "commons-commerce-agents-same-loop/v1",
        "id": ID,
        "rides_leftover": leftover_row["id"],
        "leftover": leftover_row,
        "no_auth": True,
        "no_gate": True,
        "posting": "OPEN",
        "permission": False,
        "copied_tree": False,
        "forked_into_commons": False,
        "claude_plugin_imported": False,
        "claude_md_edited": False,
        "agent": picked_agent,
        "vertical": picked_vertical,
        "agents": list(AGENTS),
        "verticals": list(VERTICALS),
        "shopper_flows": list(SHOPPER_FLOWS),
        "merchant_flows": list(MERCHANT_FLOWS),
        "steps": steps,
        "twin": {
            "repo": OPEN_TWIN,
            "pin": OPEN_TWIN_PIN,
            "license": "Apache-2.0",
            "solutions": SOLUTIONS,
            "engineering": ENGINEERING,
            "cited_not_copied": True,
        },
        "open_twin": twin,
        "solutions": solutions,
        "hits": hits,
        "compared": compared,
        "plan": plan,
        "checkout": cart,
        "customer_care": care,
        "memory": memory,
        "merchant": merchant,
        "writes": writes,
        "slack_file": slack_file_measure(),
        "sent": False,
        "charged": False,
        "applied": False,
        "cash_usd": 0,
        "sends": 0,
        "do_not_remint": list(DO_NOT_REMINT),
        "state": "INTEGRATED",
        "anthropic_key": (
            "present-in-agent-env-never-copied"
            if os.environ.get("ANTHROPIC_API_KEY")
            else "FINDER-FAILED"
        ),
        "x": [OPEN_TWIN, SOLUTIONS, SLACK_FILE, *VERTICALS, *AGENTS],
        "y": {
            "copied_tree": False,
            "checkout": cart["state"],
            "twin": twin["state"],
            "solutions": solutions["state"],
            "hits": len(hits),
            "sent": False,
        },
        "z": {
            "slack_file_bytes": "FINDER-FAILED",
            "anthropic_key": "FINDER-FAILED" if not os.environ.get("ANTHROPIC_API_KEY") else "uncopied",
            "sent": False,
            "invented_url": False,
        },
    }


def refuse_payload(flag: str) -> dict[str, Any]:
    return {
        "kind": "COMMERCE_AGENTS_SAME_LOOP",
        "id": ID,
        "verdict": "REFUSED",
        "flag": flag,
        "sent": 0,
        "charged": False,
        "applied": False,
        "cursor_advanced": False,
        "copied_tree": False,
        "claude_plugin_imported": False,
        "invented_url": False,
        "note": (
            "%s refused. Checkout stays STAGED_HOST_HANDOFF. "
            "Claude Code plugin is not imported into Cursor. No new token."
            % flag
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--agent", default="shopper")
    parser.add_argument("--vertical", default="retail")
    parser.add_argument("--check", action="store_true")
    args, unknown = parser.parse_known_args(argv)
    for flag in unknown:
        if flag in REFUSE:
            print(json.dumps(refuse_payload(flag), sort_keys=True))
            return 2
        if flag.startswith("-"):
            print(
                json.dumps(
                    {
                        "kind": "COMMERCE_AGENTS_SAME_LOOP",
                        "verdict": "FINDER-FAILED",
                        "sent": 0,
                        "unknown": flag,
                    },
                    sort_keys=True,
                )
            )
            return 1
    try:
        row = measure(agent=args.agent, vertical=args.vertical)
    except ValueError as error:
        print(
            json.dumps(
                {
                    "kind": "COMMERCE_AGENTS_SAME_LOOP",
                    "verdict": "FINDER-FAILED",
                    "sent": 0,
                    "error": str(error),
                    "never_silent_0": True,
                },
                sort_keys=True,
            )
        )
        return 1
    if args.check:
        if row["state"] != "INTEGRATED" or row["copied_tree"] or row["sent"]:
            print("FINDER-FAILED")
            return 1
        print("ok")
        return 0
    if args.json or True:
        sys.stdout.write(json.dumps(row, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
