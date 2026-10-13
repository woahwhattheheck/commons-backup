#!/usr/bin/env python3
"""host/grok_harness_gap.py — Grok inspect vs canonical harness sources.

Slack 1787634541.520949 (DEMON): Grok harness reports 0 MCP, 0 LSP,
0 loaded permissions policy. DIO+JOJO were asked to claim the named
parity lane. This leftover measures. It does not mutate ~/.grok. It
does not restart Grok. It does not launch a duplicate MCP or LSP.

Local / Slack inspect is evidence until source, generator, SHA, and
live-session agree. Ambiguity is QUARANTINED. A permissions-policy
zero is not an order to add a lock. Never a gate.

  python3 host/grok_harness_gap.py
  python3 host/grok_harness_gap.py --root .
  python3 host/grok_harness_gap.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


CANONICAL_MCP = (
    {
        "kind": "mcp",
        "path": "mcp_server/cursor_config.json",
        "coordinator": "GROK / PLAYER1 / PLAYER2",
    },
    {
        "kind": "mcp",
        "path": "independent_commons_mcp/cursor.mcp.example.json",
        "coordinator": "GROK / PLAYER1 / PLAYER2",
    },
)
DEFAULT_INSPECT = os.path.join("ground", "GROK_HARNESS_INSPECT.json")
DEFAULT_CATALOG = os.path.join("ground", "GROK_HARNESS_GAP.json")
DEFAULT_PATCH = os.path.join("ground", "GROK_HARNESS_PATCH.json")


def mcp_names_from_text(text):
    """Return sorted mcpServers keys. Invalid JSON is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return []
    names = []
    seen = set()
    for key in servers:
        name = str(key or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return sorted(names)


def load_inspect(text):
    """Parse an inspect snapshot. Invalid JSON is an empty claim."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "inspect is not JSON"}
    if not isinstance(data, dict):
        return {"error": "inspect is not an object"}
    return {
        "source": str(data.get("source") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "binary": str(data.get("binary") or "").strip(),
        "version": str(data.get("version") or "").strip(),
        "mcp_count": int(data.get("mcp_count") or 0),
        "lsp_count": int(data.get("lsp_count") or 0),
        "permissions_policy": int(data.get("permissions_policy") or 0),
        "skills_count": int(data.get("skills_count") or 0),
        "hooks_count": int(data.get("hooks_count") or 0),
        "home_present": bool(data.get("home_present")),
        "inspect_ran": bool(data.get("inspect_ran")),
        "source_sha": str(data.get("source_sha") or "").strip(),
        "live_session": str(data.get("live_session") or "").strip(),
        "note": str(data.get("note") or "").strip(),
    }


def preconditions_agree(inspect):
    """Local config is evidence until source/generator/SHA/session agree."""
    row = inspect or {}
    return bool(
        row.get("source") == "grok-inspect"
        and row.get("inspect_ran")
        and row.get("home_present")
        and row.get("source_sha")
        and row.get("live_session")
    )


def compare(canonical, inspect):
    """Diff canonical MCP names against a reported inspect count."""
    inspect = inspect or {}
    names = []
    sources = []
    for row in canonical or []:
        for name in row.get("names") or []:
            if name not in names:
                names.append(name)
        sources.append(
            {
                "kind": row.get("kind"),
                "path": row.get("path"),
                "present": bool(row.get("present")),
                "names": list(row.get("names") or []),
                "coordinator": row.get("coordinator") or "",
            }
        )
    gaps = []
    if names and int(inspect.get("mcp_count") or 0) == 0:
        gaps.append(
            {
                "kind": "mcp",
                "canonical": names,
                "reported": 0,
                "relay": "existing Grok coordinators (PLAYER1 / PLAYER2 / GROK_BUILD). No new launch.",
            }
        )
    if int(inspect.get("lsp_count") or 0) == 0:
        gaps.append(
            {
                "kind": "lsp",
                "canonical": [],
                "reported": 0,
                "note": "no canonical LSP source in this repo. Do not invent a server.",
            }
        )
    if int(inspect.get("permissions_policy") or 0) == 0:
        gaps.append(
            {
                "kind": "permissions_policy",
                "action": "do_not_add",
                "reported": 0,
                "note": "a zero is not an order to add a lock. Never a gate.",
            }
        )
    return {
        "canonical_mcp": names,
        "sources": sources,
        "gaps": gaps,
        "gap_count": len(gaps),
    }


def smallest_safe_patch(canonical):
    """Candidate MCP wiring only. apply stays false. No secrets. No restart."""
    servers = {}
    for row in canonical or []:
        if not row.get("present"):
            continue
        for name in row.get("names") or []:
            if name in servers:
                continue
            servers[name] = {
                "from": row.get("path"),
                "command": "python3",
                "args_note": "copy from the named example. Do not invent credentials.",
            }
    return {
        "apply": False,
        "mutate_grok": False,
        "restart_grok": False,
        "mcpServers": servers,
        "lsp": {},
        "permissions_policy": None,
        "note": (
            "CANDIDATE only. Do not apply while revenue/deep-research lanes "
            "run. Relay to existing Grok coordinators. Never a gate."
        ),
    }


def classify(row):
    """Turn a measured compare into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "grok harness compare not read. Absence was not stillness.",
        }
    if not row.get("catalog"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "gap catalog missing. Harness-gap / 0-MCP / 0-LSP talk is "
                "CLAIMED until the leftover ships."
            ),
        }
    inspect = row.get("inspect") or {}
    if not preconditions_agree(inspect):
        return {
            "state": "QUARANTINED",
            "note": (
                "local or Slack inspect is evidence until source, generator, "
                "SHA, and live-session agree. Do not mutate or restart Grok. "
                "Search space: ~/.grok, grok inspect, owner-PC live session."
            ),
        }
    gaps = list(row.get("gaps") or [])
    if gaps:
        return {
            "state": "CANDIDATE",
            "note": (
                "live grok inspect agrees with the gap count. Patch is "
                "unapplied. Do not restart Grok from this leftover."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "live grok inspect agrees with canonical MCP sources. "
            "Talk is not a land."
        ),
    }


def measure_from_rows(canonical, inspect, extras=None):
    """Pure compare so tests do not need the live tree."""
    extras = extras or {}
    compared = compare(canonical, inspect)
    catalog = bool(extras.get("catalog"))
    patch = extras.get("patch") or smallest_safe_patch(canonical)
    home_exists = bool(extras.get("home_exists"))
    binary_exists = bool(extras.get("binary_exists"))
    inspect_ran = bool((inspect or {}).get("inspect_ran"))
    row = {
        "measured": True,
        "catalog": catalog,
        "inspect": inspect or {},
        "canonical_mcp": compared["canonical_mcp"],
        "sources": compared["sources"],
        "gaps": compared["gaps"],
        "gap_count": compared["gap_count"],
        "patch": patch,
        "home_exists": home_exists,
        "binary_exists": binary_exists,
        "inspect_ran": inspect_ran,
        "preconditions_agree": preconditions_agree(inspect),
        "titan": "NOT_WRITTEN",
        "mutate_grok": False,
        "restart_grok": False,
    }
    return row


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def measure_root(root, inspect_path=None, grok_home=None):
    root = os.path.abspath(root)
    inspect_path = inspect_path or os.path.join(root, DEFAULT_INSPECT)
    inspect_text = _read_text(inspect_path)
    inspect = load_inspect(inspect_text) if inspect_text else {}
    canonical = []
    for spec in CANONICAL_MCP:
        path = os.path.join(root, spec["path"])
        present = os.path.isfile(path)
        names = mcp_names_from_text(_read_text(path)) if present else []
        canonical.append(
            {
                "kind": spec["kind"],
                "path": spec["path"],
                "present": present,
                "names": names,
                "coordinator": spec["coordinator"],
            }
        )
    home = grok_home or os.path.expanduser("~/.grok")
    binary_candidates = (
        os.path.join(home, "bin", "grok.exe"),
        os.path.join(home, "bin", "grok"),
    )
    binary_exists = any(os.path.isfile(path) for path in binary_candidates)
    extras = {
        "catalog": os.path.isfile(os.path.join(root, DEFAULT_CATALOG)),
        "home_exists": os.path.isdir(home),
        "binary_exists": binary_exists,
        "patch": smallest_safe_patch(canonical),
    }
    row = measure_from_rows(canonical, inspect, extras)
    row["root"] = root
    row["inspect_path"] = inspect_path
    row["grok_home"] = home
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare Grok inspect against canonical harness sources"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--inspect", default="")
    parser.add_argument("--grok-home", default="")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(
        args.root,
        inspect_path=args.inspect or None,
        grok_home=args.grok_home or None,
    )
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    slack = load_inspect(
        json.dumps(
            {
                "source": "slack-claim",
                "mcp_count": 0,
                "lsp_count": 0,
                "permissions_policy": 0,
                "skills_count": 30,
                "hooks_count": 14,
                "home_present": False,
                "inspect_ran": False,
            }
        )
    )
    assert slack["mcp_count"] == 0
    assert not preconditions_agree(slack)
    canonical = [
        {
            "kind": "mcp",
            "path": "mcp_server/cursor_config.json",
            "present": True,
            "names": ["commons"],
            "coordinator": "GROK",
        }
    ]
    measured = measure_from_rows(
        canonical,
        slack,
        {"catalog": True, "home_exists": False, "binary_exists": False},
    )
    assert measured["gap_count"] >= 1
    assert measured["mutate_grok"] is False
    assert measured["restart_grok"] is False
    assert measured["patch"]["apply"] is False
    assert classify(measured)["state"] == "QUARANTINED"
    missing = measure_from_rows(canonical, slack, {"catalog": False})
    assert classify(missing)["state"] == "NOT_LANDED"
    live = dict(slack)
    live["source"] = "grok-inspect"
    live["inspect_ran"] = True
    live["home_present"] = True
    live["source_sha"] = "abc123"
    live["live_session"] = "owner-pc"
    live_row = measure_from_rows(canonical, live, {"catalog": True})
    assert preconditions_agree(live)
    assert classify(live_row)["state"] == "CANDIDATE"
    live["mcp_count"] = 1
    live["lsp_count"] = 1
    live["permissions_policy"] = 1
    parity = measure_from_rows(canonical, live, {"catalog": True})
    assert classify(parity)["state"] == "INTEGRATED"
    assert mcp_names_from_text('{"mcpServers":{"commons":{}}}') == ["commons"]
    assert mcp_names_from_text("not-json") == []
    return True


if __name__ == "__main__":
    sys.exit(main())
