#!/usr/bin/env python3
"""Fold commons-network beside commons-grok-cloud. One public /mcp.

Validates the Codex marketplace compose leftover named in
ground/WIRE_SUPER_MCP.md. Does not mint a second MCP or copy vendor kits.

  python3 host/wire_super_mcp_marketplace.py validate
  python3 host/wire_super_mcp_marketplace.py --self-test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MARKET = ROOT / ".agents" / "plugins" / "marketplace.json"
PUBLIC_MCP = "https://commons-spark-mcp.vercel.app/mcp"
GROK_CLOUD = "commons-grok-cloud"
NETWORK = "commons-network"
GROK_PATH = "plugins/commons-grok-cloud"
NETWORK_PATH = "integrations/commons_network_plugin"
CITE = "wire-super-mcp-fold-20260902-01"
SILOED = (
    "Sales",
    "Marketing",
    "Customer Support",
    "Product Management",
    "Small Business",
    "Twilio",
    "Desktop Commander",
)


class MarketplaceFoldError(RuntimeError):
    """Typed marketplace fold failure."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MarketplaceFoldError("cannot read %s: %s" % (path, exc)) from exc
    if not isinstance(payload, dict):
        raise MarketplaceFoldError("%s is not an object" % path)
    return payload


def marketplace() -> dict[str, Any]:
    return load_json(MARKET)


def _plugin_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = data.get("plugins")
    if not isinstance(rows, list):
        raise MarketplaceFoldError("marketplace plugins must be a list")
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("name"):
            raise MarketplaceFoldError("plugin row missing name")
        name = str(row["name"])
        if name in out:
            raise MarketplaceFoldError("duplicate plugin name %s" % name)
        out[name] = row
    return out


def validate(data: dict[str, Any] | None = None) -> dict[str, Any]:
    data = data if data is not None else marketplace()
    errors: list[str] = []
    if data.get("name") != "commons":
        errors.append("marketplace name must stay commons")
    plugins = _plugin_map(data)
    for name, rel in ((GROK_CLOUD, GROK_PATH), (NETWORK, NETWORK_PATH)):
        row = plugins.get(name)
        if row is None:
            errors.append("missing marketplace plugin %s" % name)
            continue
        source = row.get("source") or {}
        path = str(source.get("path") or "").lstrip("./")
        if path != rel:
            errors.append("%s path must stay ./%s" % (name, rel))
        if not (ROOT / rel).is_dir():
            errors.append("missing fold target %s" % rel)
        policy = row.get("policy") or {}
        if policy.get("installation") != "AVAILABLE":
            errors.append("%s installation must stay AVAILABLE" % name)
        manifest = ROOT / rel / ".codex-plugin" / "plugin.json"
        if not manifest.is_file():
            errors.append("missing %s" % manifest.relative_to(ROOT))

    grok_mcp = load_json(ROOT / GROK_PATH / ".mcp.json")
    commons = (grok_mcp.get("mcpServers") or {}).get("commons") or {}
    if commons.get("url") != PUBLIC_MCP:
        errors.append("grok-cloud public MCP drifted from %s" % PUBLIC_MCP)
    if commons.get("type") != "http":
        errors.append("grok-cloud public MCP must stay type http")

    names = " ".join(plugins)
    for silo in SILOED:
        if silo in names:
            errors.append("siloed pack %s must stay out of the marketplace" % silo)

    if NETWORK in plugins:
        auth = (plugins[NETWORK].get("policy") or {}).get("authentication")
        if auth not in (None, "", "none"):
            errors.append("commons-network must not add an authentication lock")

    if errors:
        raise MarketplaceFoldError("; ".join(errors))
    return {
        "ok": True,
        "cite": CITE,
        "url": PUBLIC_MCP,
        "plugins": [GROK_CLOUD, NETWORK],
        "marketplace": str(MARKET.relative_to(ROOT)),
        "compose": "network beside grok-cloud; one public /mcp",
    }


def self_test() -> dict[str, Any]:
    receipt = validate()
    if receipt["plugins"] != [GROK_CLOUD, NETWORK]:
        raise MarketplaceFoldError("self-test plugin pair drifted")
    if not (ROOT / "ground" / "WIRE_SUPER_MCP.md").is_file():
        raise MarketplaceFoldError("missing ground/WIRE_SUPER_MCP.md")
    if not (ROOT / "p" / ("%s.md" % CITE)).is_file():
        raise MarketplaceFoldError("missing fold receipt %s" % CITE)
    receipt["self_test"] = "PASS"
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="validate",
        choices=("validate",),
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = self_test() if args.self_test else validate()
    except MarketplaceFoldError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
