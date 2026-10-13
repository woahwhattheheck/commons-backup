#!/usr/bin/env python3
"""Shared super MCP catalog — fold, do not remint.

One public MCP, one composed plugin, one catalog surface. Validates the
checked-in catalog against live fold targets and prints thin-harness routes
for pc / files / slack / stripe / browser.

Examples:

  python3 host/super_mcp.py validate
  python3 host/super_mcp.py tools
  python3 host/super_mcp.py connectors
  python3 host/super_mcp.py route --need browser
  python3 host/super_mcp.py --self-test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CATALOG = ROOT / "super-mcp" / "catalog.json"
CARRIERS = ROOT / "carriers" / "catalog.json"
HARNESSES = ROOT / "harnesses" / "catalog.json"
SCHEMA = "commons-shared-super-mcp/v1"
PUBLIC_MCP = "https://commons-spark-mcp.vercel.app/mcp"
RESIDUALS = ("pc", "files", "slack", "stripe", "browser")
REQUIRED_REACH_KEYS = ("plain", "preferred", "thin", "local_when_stdio", "do_not")
SILOED = (
    "Sales",
    "Marketing",
    "Customer Support",
    "Product Management",
    "Small Business",
    "Twilio",
    "Desktop Commander",
)


class SuperMcpError(RuntimeError):
    """Typed catalog or fold failure."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SuperMcpError("cannot read %s: %s" % (path, exc)) from exc
    if not isinstance(payload, dict):
        raise SuperMcpError("%s is not an object" % path)
    return payload


def catalog() -> dict[str, Any]:
    return load_json(CATALOG)


def _must_exist(rel: str, errors: list[str]) -> None:
    path = ROOT / rel
    if not path.exists():
        errors.append("missing fold target %s" % rel)


def validate(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data if data is not None else catalog()
    errors: list[str] = []
    if data.get("schema") != SCHEMA:
        errors.append("schema must be %s" % SCHEMA)
    if data.get("authentication") != "none":
        errors.append("authentication must stay none")
    if data.get("open_door") is not True:
        errors.append("open_door must be true")
    trio = data.get("trio") or {}
    mcp = (trio.get("super_mcp") or {}).get("url")
    if mcp != PUBLIC_MCP:
        errors.append("super_mcp url must stay %s" % PUBLIC_MCP)
    if data.get("cite_fold_door") != "wire-super-mcp-fold-20260902-01":
        errors.append("must cite wire-super-mcp-fold-20260902-01")

    carriers = load_json(CARRIERS)
    if carriers.get("mcp_url") != PUBLIC_MCP:
        errors.append("carriers/catalog.json mcp_url drifted")
    tools = (data.get("tools") or {}).get("public_mcp") or []
    shared = carriers.get("shared_tools") or []
    if tools != shared:
        errors.append("public_mcp tools must match carriers/catalog.json shared_tools")

    fold = data.get("fold_do_not_remint") or {}
    for rel in (
        fold.get("public_mcp", {}).get("adapter"),
        fold.get("public_mcp", {}).get("core"),
        fold.get("gemini_carriers", {}).get("catalog"),
        fold.get("gemini_carriers", {}).get("door"),
        fold.get("hall_pass", {}).get("skill"),
        fold.get("tools_manual_job", {}).get("door"),
        trio.get("custom_surface", {}).get("fold_door"),
        trio.get("custom_surface", {}).get("catalog_door"),
        trio.get("super_plugin", {}).get("marketplace"),
        *(trio.get("super_plugin", {}).get("packs_folded") or []),
        "ground/WIRE_SUPER_MCP.md",
        "p/wire-super-mcp-fold-20260902-01.md",
        "docs/TITAN_HANDS_PEERS.md",
        "payment-capability.html",
        "ground/STRIPE.md",
        "ground/PAYMENT_CAPABILITY.md",
    ):
        if rel:
            _must_exist(str(rel), errors)

    reach = data.get("thin_harness_reach") or {}
    for residual in RESIDUALS:
        row = reach.get(residual)
        if not isinstance(row, dict):
            errors.append("missing thin_harness_reach.%s" % residual)
            continue
        for key in REQUIRED_REACH_KEYS:
            if not row.get(key):
                errors.append("thin_harness_reach.%s.%s is empty" % (residual, key))

    rejected = data.get("siloed_packs_rejected") or []
    for name in SILOED:
        if name not in rejected:
            errors.append("siloed pack %s must stay rejected" % name)

    if errors:
        raise SuperMcpError("; ".join(errors))
    return {
        "ok": True,
        "schema": SCHEMA,
        "url": PUBLIC_MCP,
        "tools": len(tools),
        "connectors": len(data.get("who_connects") or []),
        "residuals": list(RESIDUALS),
        "cite": data.get("cite_fold_door"),
    }


def route(need: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    residual = need.strip().lower()
    if residual not in RESIDUALS:
        raise SuperMcpError("need must be one of %s" % ",".join(RESIDUALS))
    data = data if data is not None else catalog()
    row = dict((data.get("thin_harness_reach") or {}).get(residual) or {})
    if not row:
        raise SuperMcpError("no route for %s" % residual)
    row["need"] = residual
    row["mcp"] = PUBLIC_MCP
    row["call_first"] = "discover_commons_capabilities"
    return row


def tools_list(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data if data is not None else catalog()
    return data.get("tools") or {}


def connectors(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = data if data is not None else catalog()
    rows = data.get("who_connects") or []
    if not isinstance(rows, list):
        raise SuperMcpError("who_connects must be a list")
    return rows


def self_test() -> dict[str, Any]:
    receipt = validate()
    for need in RESIDUALS:
        row = route(need)
        if not row.get("preferred") or not row.get("thin"):
            raise SuperMcpError("self-test route %s incomplete" % need)
    if "hands" not in (tools_list().get("local_stdio") or []):
        raise SuperMcpError("local_stdio must keep hands")
    if len(connectors()) < 4:
        raise SuperMcpError("who_connects too thin")
    receipt["self_test"] = "PASS"
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="validate",
        choices=("validate", "tools", "connectors", "route"),
    )
    parser.add_argument("--need", default="", help="pc|files|slack|stripe|browser")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            payload = self_test()
        elif args.command == "validate":
            payload = validate()
        elif args.command == "tools":
            payload = tools_list()
        elif args.command == "connectors":
            payload = connectors()
        else:
            payload = route(args.need)
    except SuperMcpError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
