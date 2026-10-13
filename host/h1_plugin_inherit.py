#!/usr/bin/env python3
"""Live H1 inherit-source probe: Claude enabledPlugins → Grok plugins.

H1 (ground/CLAUDE_PEER_CHECK.md, cite wire-claude-peer-check-20260902-01):
Grok Build inherits active Claude plugins/skills via ~/.claude even when
every [compat.claude] cell is false. Cause named on GROK_CLAUDE_HYGIENE:
Grok imports enabledPlugins=true from ~/.claude/settings.json.

This instrument probes the inherit SOURCE. It does not remint
GROK_CLAUDE_HYGIENE.md, H002, GROK_HYGIENE, WIRE peer-check, or A1–A6.
It composes host/grok_claude_hygiene.evaluate_inspection for the inspect
half. It never writes Claude settings.

Statuses:
  SEAT_CLEAR              — no user-level ~/.claude inherit source
  INHERIT_SOURCE_PRESENT  — official enabledPlugins/installed official
                            plugins exist; Grok effect unmeasured
  H1_HIT                  — inherit source plus inspect-enabled Claude
                            plugins while compat cells are false
  FINDER-FAILED           — unreadable settings / inspect parse fail
                            (never a silent 0)

Cursor public plugin caches that happen to ship a .claude folder are
NOT user-level inherit. Only {home}/.claude counts.

  python3 host/h1_plugin_inherit.py --self-test
  python3 host/h1_plugin_inherit.py --home "$HOME"
  python3 host/h1_plugin_inherit.py --home "$HOME" --inspect grok-inspect.json
  python3 host/h1_plugin_inherit.py --documented-hit
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

from grok_claude_hygiene import evaluate_inspection


SCHEMA = "h1-plugin-inherit/v1"
DOCUMENTED_PLUGINS = (
    "frontend-design@claude-plugins-official",
    "mcp-server-dev@claude-plugins-official",
    "mcp-tunnels@claude-plugins-official",
)
DO_NOT_REMINT = (
    "ground/GROK_CLAUDE_HYGIENE.md",
    "ground/GROK_HYGIENE.md",
    "ground/H002.md",
    "ground/CLAUDE_PEER_CHECK.md",
    "p/wire-claude-peer-check-20260902-01.md",
)


def _official_plugin(name):
    text = str(name or "").lower()
    return "claude-plugins-official" in text


def user_claude_home(home):
    return os.path.join(os.path.abspath(home), ".claude")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle), None
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return None, "FINDER-FAILED: %s: %s" % (path, error)


def enabled_plugins_from_settings(settings):
    raw = (settings or {}).get("enabledPlugins")
    if not isinstance(raw, dict):
        return []
    out = []
    for name, enabled in raw.items():
        if enabled is True:
            out.append(str(name))
    return out


def installed_official_plugins(installed):
    if isinstance(installed, dict):
        rows = installed.get("plugins") or installed.get("installedPlugins") or []
        if isinstance(installed, dict) and not rows:
            rows = [
                {"name": key}
                for key, value in installed.items()
                if key not in ("plugins", "installedPlugins") and value
            ]
    elif isinstance(installed, list):
        rows = installed
    else:
        rows = []
    names = []
    for row in rows:
        if isinstance(row, str):
            name = row
        elif isinstance(row, dict):
            name = row.get("name") or row.get("id") or ""
        else:
            name = ""
        if _official_plugin(name):
            names.append(str(name))
    return names


def probe_inherit_source(home):
    """Read user-level ~/.claude inherit source. Never writes."""
    claude_home = user_claude_home(home)
    present = os.path.isdir(claude_home)
    settings_path = os.path.join(claude_home, "settings.json")
    installed_path = os.path.join(claude_home, "plugins", "installed_plugins.json")
    errors = []
    settings, settings_error = _read_json(settings_path) if os.path.isfile(settings_path) else (None, None)
    if settings_error:
        errors.append(settings_error)
    installed, installed_error = _read_json(installed_path) if os.path.isfile(installed_path) else (None, None)
    if installed_error:
        errors.append(installed_error)
    enabled = enabled_plugins_from_settings(settings)
    official_enabled = [name for name in enabled if _official_plugin(name)]
    official_installed = installed_official_plugins(installed)
    plugin_dirs = []
    plugins_root = os.path.join(claude_home, "plugins")
    if os.path.isdir(plugins_root):
        for name in sorted(os.listdir(plugins_root)):
            path = os.path.join(plugins_root, name)
            if os.path.isdir(path) and _official_plugin(name):
                plugin_dirs.append(name)
    inherit_source = bool(official_enabled or official_installed or plugin_dirs)
    return {
        "home": os.path.abspath(home),
        "claude_home": claude_home,
        "claude_home_present": present,
        "settings_path": settings_path,
        "settings_present": os.path.isfile(settings_path),
        "enabled_plugins": enabled,
        "official_plugins_enabled": official_enabled,
        "official_plugins_installed": official_installed,
        "official_plugin_dirs": plugin_dirs,
        "inherit_source": inherit_source,
        "errors": errors,
    }


def inspect_half(inspection=None, inspect_error=None):
    if inspect_error:
        return {
            "inspect_status": "FINDER-FAILED",
            "inspect_error": str(inspect_error),
            "claude_plugins_enabled": None,
            "claude_compat_cells_enabled": None,
            "violations": [],
        }
    if inspection is None:
        return {
            "inspect_status": "NOT_RUN",
            "inspect_error": None,
            "claude_plugins_enabled": None,
            "claude_compat_cells_enabled": None,
            "violations": [],
        }
    try:
        receipt = evaluate_inspection(inspection)
    except (TypeError, ValueError, KeyError) as error:
        return {
            "inspect_status": "FINDER-FAILED",
            "inspect_error": str(error),
            "claude_plugins_enabled": None,
            "claude_compat_cells_enabled": None,
            "violations": [],
        }
    return {
        "inspect_status": receipt.get("status") or "FINDER-FAILED",
        "inspect_error": None,
        "claude_plugins_enabled": receipt.get("claude_plugins_enabled"),
        "claude_compat_cells_enabled": receipt.get("claude_compat_cells_enabled"),
        "violations": receipt.get("violations") or [],
    }


def classify(source, inspect_row):
    """Return status. A miss is FINDER-FAILED, never silent 0."""
    if source.get("errors"):
        return "FINDER-FAILED"
    if inspect_row.get("inspect_status") == "FINDER-FAILED":
        return "FINDER-FAILED"
    inherit = bool(source.get("inherit_source"))
    plugins = inspect_row.get("claude_plugins_enabled")
    compat = inspect_row.get("claude_compat_cells_enabled")
    inspect_blocked = inspect_row.get("inspect_status") == "BLOCKED"
    if inherit and inspect_blocked and (plugins or 0) > 0 and compat == 0:
        return "H1_HIT"
    if inherit:
        return "INHERIT_SOURCE_PRESENT"
    return "SEAT_CLEAR"


def evaluate(home, inspection=None, inspect_error=None):
    source = probe_inherit_source(home)
    inspect_row = inspect_half(inspection, inspect_error)
    status = classify(source, inspect_row)
    z_bits = [
        "Miss branch: unreadable ~/.claude/settings.json or grok inspect parse fail → FINDER-FAILED, never silent 0.",
        "No grok CLI / inspect not run is NOT_RUN on the inspect half, not clearance of owner-machine Grok Build.",
        "Cursor public plugin caches that ship a .claude folder are not user-level inherit.",
        "Do not rewrite Claude settings to clean Grok. Do not remint GROK_CLAUDE_HYGIENE / WIRE peer-check / A1–A6.",
    ]
    if status == "SEAT_CLEAR":
        y = (
            "No user-level official enabledPlugins inherit source under %s. "
            "This seat is CLEAR for H1 inherit. Documented owner-machine HIT stays flagged."
            % source["home"]
        )
    elif status == "INHERIT_SOURCE_PRESENT":
        y = (
            "Official Claude enabledPlugins/installed plugins present at %s. "
            "Grok inspect half unmeasured or clean; source exists. Not fleet CLEAR."
            % source["claude_home"]
        )
    elif status == "H1_HIT":
        y = (
            "Inherit source plus grok inspect enabled Claude plugins while compat cells are 0. "
            "H1 HIT. Keep direct Grok jobs BLOCKED_BY_HYGIENE_GATE."
        )
    else:
        y = "Finder failed: %s" % ("; ".join(source.get("errors") or []) or inspect_row.get("inspect_error") or "unknown")
    return {
        "schema": SCHEMA,
        "status": status,
        "do_not_rewrite_claude_settings": True,
        "do_not_remint": list(DO_NOT_REMINT),
        "x": {
            "home": source["home"],
            "claude_home": source["claude_home"],
            "settings_path": source["settings_path"],
            "inspect_status": inspect_row["inspect_status"],
        },
        "y": y,
        "z": z_bits,
        "source": source,
        "inspect": inspect_row,
    }


def documented_hit_fixture():
    """Owner-machine shape from GROK_CLAUDE_HYGIENE.json. Read-only. No remint."""
    inspection = {
        "grokVersion": "1.0.5",
        "externalCompat": {"cells": [
            {"vendor": "claude", "surface": "skills", "enabled": False},
            {"vendor": "claude", "surface": "plugins", "enabled": False},
        ]},
        "projectInstructions": [],
        "skills": [],
        "plugins": [
            {
                "name": name.split("@", 1)[0],
                "path": "/u/.claude/plugins/%s" % name.split("@", 1)[0],
                "enabled": True,
            }
            for name in DOCUMENTED_PLUGINS
        ],
        "hooks": [],
        "mcpServers": [],
    }
    settings = {"enabledPlugins": {name: True for name in DOCUMENTED_PLUGINS}}
    return inspection, settings


def _self_test():
    with tempfile.TemporaryDirectory() as empty:
        clean = evaluate(empty)
        assert clean["status"] == "SEAT_CLEAR", clean
        assert clean["source"]["inherit_source"] is False
        assert clean["inspect"]["inspect_status"] == "NOT_RUN"

    with tempfile.TemporaryDirectory() as home:
        claude = user_claude_home(home)
        os.makedirs(os.path.join(claude, "plugins"))
        with open(os.path.join(claude, "settings.json"), "w", encoding="utf-8") as handle:
            json.dump({"enabledPlugins": {DOCUMENTED_PLUGINS[0]: True}}, handle)
        source_only = evaluate(home)
        assert source_only["status"] == "INHERIT_SOURCE_PRESENT", source_only
        inspection, _ = documented_hit_fixture()
        hit = evaluate(home, inspection=inspection)
        assert hit["status"] == "H1_HIT", hit
        assert hit["inspect"]["claude_plugins_enabled"] == 3
        assert hit["inspect"]["claude_compat_cells_enabled"] == 0

    with tempfile.TemporaryDirectory() as home:
        claude = user_claude_home(home)
        os.makedirs(claude)
        with open(os.path.join(claude, "settings.json"), "w", encoding="utf-8") as handle:
            handle.write("{not-json")
        failed = evaluate(home)
        assert failed["status"] == "FINDER-FAILED", failed

    with tempfile.TemporaryDirectory() as home:
        failed_inspect = evaluate(home, inspect_error="grok inspect failed")
        assert failed_inspect["status"] == "FINDER-FAILED", failed_inspect

    with tempfile.TemporaryDirectory() as home:
        decoy = os.path.join(home, ".cursor", "plugins", "cache", "cursor-public", "x", ".claude")
        os.makedirs(decoy)
        with open(os.path.join(decoy, "settings.json"), "w", encoding="utf-8") as handle:
            json.dump({"enabledPlugins": {DOCUMENTED_PLUGINS[0]: True}}, handle)
        decoy_row = evaluate(home)
        assert decoy_row["status"] == "SEAT_CLEAR", decoy_row
        assert decoy_row["source"]["inherit_source"] is False

    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", default="", help="user home to probe (default $HOME)")
    parser.add_argument("--inspect", help="saved grok inspect --json")
    parser.add_argument("--documented-hit", action="store_true", help="evaluate documented owner-machine fixture")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    inspect_error = None
    inspection = None
    home = args.home or os.path.expanduser("~")
    if args.documented_hit:
        inspection, settings = documented_hit_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            claude = user_claude_home(tmp)
            os.makedirs(claude)
            with open(os.path.join(claude, "settings.json"), "w", encoding="utf-8") as handle:
                json.dump(settings, handle)
            result = evaluate(tmp, inspection=inspection)
    else:
        if args.inspect:
            try:
                with open(args.inspect, encoding="utf-8") as handle:
                    inspection = json.load(handle)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                inspect_error = error
        result = evaluate(home, inspection=inspection, inspect_error=inspect_error)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if result["status"] == "FINDER-FAILED":
        return 2
    if result["status"] == "H1_HIT":
        return 42
    return 0


if __name__ == "__main__":
    sys.exit(main())
