#!/usr/bin/env python3
"""Fail closed when Grok discovers an active Claude compatibility payload."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys


SCHEMA = "grok-claude-hygiene/v1"


def _claude_path(value):
    text = str(value or "").replace("\\", "/").lower()
    return "/.claude/" in text or "claude-plugins-official" in text


def evaluate_inspection(inspection):
    """Return a receipt. Listed-but-disabled rows are evidence, not violations."""
    inspection = inspection or {}
    violations = []
    cells = ((inspection.get("externalCompat") or {}).get("cells") or [])
    for cell in cells:
        if cell.get("vendor") == "claude" and cell.get("enabled") is True:
            violations.append({
                "surface": "compat",
                "name": cell.get("surface") or "unknown",
                "reason": "Claude compatibility cell is enabled",
            })
    instructions = inspection.get("projectInstructions") or []
    for row in instructions:
        if row.get("vendor") == "claude" and row.get("disabled") is not True:
            violations.append({
                "surface": "instruction",
                "name": row.get("path") or "unknown",
                "reason": "Claude instruction is active",
            })
    skills = inspection.get("skills") or []
    for row in skills:
        source = row.get("source") or {}
        is_claude = row.get("vendor") == "claude" or _claude_path(source.get("path"))
        if is_claude and row.get("disabled") is not True:
            violations.append({
                "surface": "skill",
                "name": row.get("name") or "unknown",
                "reason": "Claude-derived skill is active",
            })
        if row.get("name") == "resume-claude" and row.get("disabled") is not True:
            violations.append({
                "surface": "session_import",
                "name": "resume-claude",
                "reason": "Claude session import is active",
            })
    plugins = inspection.get("plugins") or []
    for row in plugins:
        if row.get("enabled") is True and _claude_path(row.get("path")):
            violations.append({
                "surface": "plugin",
                "name": row.get("name") or "unknown",
                "reason": "Claude plugin is enabled",
            })
    mcps = inspection.get("mcpServers") or []
    for row in mcps:
        if "claude" in json.dumps(row, sort_keys=True).lower():
            violations.append({
                "surface": "mcp",
                "name": row.get("name") or "unknown",
                "reason": "Claude-derived MCP server is active",
            })
    hooks = inspection.get("hooks") or []
    return {
        "schema": SCHEMA,
        "grok_version": inspection.get("grokVersion") or "UNKNOWN",
        "status": "PASS" if not violations else "BLOCKED",
        "claude_compat_cells_enabled": sum(
            1 for row in cells
            if row.get("vendor") == "claude" and row.get("enabled") is True
        ),
        "claude_instructions_enabled": sum(
            1 for row in instructions
            if row.get("vendor") == "claude" and row.get("disabled") is not True
        ),
        "claude_skills_enabled": sum(
            1 for row in skills
            if (row.get("vendor") == "claude" or _claude_path((row.get("source") or {}).get("path")))
            and row.get("disabled") is not True
        ),
        "claude_plugins_enabled": sum(
            1 for row in plugins
            if row.get("enabled") is True and _claude_path(row.get("path"))
        ),
        "claude_hooks_discovered_but_compat_disabled": sum(
            1 for row in hooks if _claude_path((row.get("source") or {}).get("path"))
        ),
        "mcp_servers_total": len(mcps),
        "violations": violations,
    }


def _default_grok():
    found = shutil.which("grok")
    if found:
        return found
    candidate = os.path.join(os.path.expanduser("~"), ".grok", "bin", "grok.exe")
    return candidate if os.path.isfile(candidate) else ""


def inspect_live(executable, cwd):
    if not executable:
        raise RuntimeError("grok executable not found")
    run = subprocess.run(
        [executable, "inspect", "--json"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if run.returncode:
        raise RuntimeError("grok inspect failed: %s" % (run.stderr.strip() or run.returncode))
    return json.loads(run.stdout)


def _self_test():
    clean = {
        "grokVersion": "test",
        "externalCompat": {"cells": [{"vendor": "claude", "surface": "skills", "enabled": False}]},
        "projectInstructions": [{"vendor": "claude", "path": "/u/.claude/CLAUDE.md", "disabled": True}],
        "skills": [{"name": "resume-claude", "source": {"type": "bundled"}, "disabled": True}],
        "plugins": [],
        "hooks": [],
        "mcpServers": [],
    }
    assert evaluate_inspection(clean)["status"] == "PASS"
    contaminated = json.loads(json.dumps(clean))
    contaminated["plugins"] = [{
        "name": "frontend-design",
        "path": "/u/.claude/plugins/frontend-design",
        "enabled": True,
    }]
    result = evaluate_inspection(contaminated)
    assert result["status"] == "BLOCKED"
    assert result["claude_plugins_enabled"] == 1
    active = json.loads(json.dumps(clean))
    active["externalCompat"]["cells"][0]["enabled"] = True
    active["skills"].append({
        "name": "foreign",
        "vendor": "claude",
        "source": {"path": "/u/.claude/skills/foreign/SKILL.md"},
    })
    assert len(evaluate_inspection(active)["violations"]) == 2
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="saved grok inspect --json receipt")
    parser.add_argument("--grok", default="", help="Grok executable")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    try:
        if args.input:
            with open(args.input, encoding="utf-8") as handle:
                inspection = json.load(handle)
        else:
            inspection = inspect_live(args.grok or _default_grok(), os.path.abspath(args.cwd))
        result = evaluate_inspection(inspection)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        result = {
            "schema": SCHEMA,
            "status": "FINDER-FAILED",
            "error": str(error),
            "violations": [],
        }
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["status"] == "PASS" else 42


if __name__ == "__main__":
    sys.exit(main())
