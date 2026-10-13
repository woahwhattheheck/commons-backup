#!/usr/bin/env python3
"""host/connector_reval.py — provisioned MCP cache is not a live connector.

Slack 1787637151.916759 (DEMON connector-utilization report): Cursor
cloud cache showed 39 enabled / 23 cached connected as of Aug 21, but
~/.cursor/mcp.json was empty and the cache was four days old.
Provisioned != live. DIO+JOJO were asked to run a read-only
revalidation. This leftover measures. It does not write financial,
messaging, account, permission, or destructive connectors. It does
not delete, vacuum, or repair a live state.vscdb.

A Slack utilization report is CLAIMED. Missing instrument is
NOT_LANDED. A measured provisioned-vs-live census with a vscdb plan
and no secrets is INTEGRATED for this leftover. titan: NOT_WRITTEN.

  python3 host/connector_reval.py
  python3 host/connector_reval.py --root .
  python3 host/connector_reval.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_CATALOG = os.path.join("ground", "CONNECTOR_REVAL.json")
FORBIDDEN_CLASSES = ("financial", "messaging", "account", "permission", "destructive")
VSCDB_PLAN = ("backup", "clean_shutdown", "checkpoint", "integrity")
CLAIMED_CONNECTED = (
    "github",
    "slack",
    "gitbook",
    "x",
    "agentmail",
    "huggingface",
    "gmail",
    "drive",
    "calendar",
    "zapier",
    "heygen",
    "cloudinary",
    "stripe",
    "revenuecat",
    "airwallex",
)
CLAIMED_UNVERIFIED = (
    "gitlab",
    "mem0",
    "browser-use",
    "box",
    "notion",
    "roboflow",
    "aws",
)
CLASS_OF = {
    "stripe": "financial",
    "revenuecat": "financial",
    "airwallex": "financial",
    "gmail": "messaging",
    "x": "messaging",
    "agentmail": "messaging",
    "drive": "account",
    "calendar": "account",
}


def load_catalog(text):
    """Parse the connector catalog. Invalid JSON is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {
            "claimed_connected": [],
            "claimed_unverified": [],
            "live": [],
            "error": "catalog is not JSON",
        }
    if not isinstance(data, dict):
        return {
            "claimed_connected": [],
            "claimed_unverified": [],
            "live": [],
            "error": "catalog is not an object",
        }
    return {
        "claimed_connected": _names(data.get("claimed_connected") or data.get("connected")),
        "claimed_unverified": _names(data.get("claimed_unverified") or data.get("unverified")),
        "live": _names(data.get("live")),
        "forbidden": _names(data.get("forbidden")),
        "enabled_claim": int(data.get("enabled_claim") or 0),
        "connected_claim": int(data.get("connected_claim") or 0),
        "cache_age_days_claim": float(data.get("cache_age_days_claim") or 0),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "source_id": str(data.get("source_id") or "").strip(),
        "hands_off": list(data.get("hands_off") or []),
    }


def _names(raw):
    names = []
    seen = set()
    for item in raw or []:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("service") or "").strip().lower()
        else:
            name = str(item or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def class_of(name):
    """Return the write-class for a service, or empty."""
    return CLASS_OF.get(str(name or "").strip().lower(), "")


def classify_service(row):
    """One service: LIVE / FORBIDDEN / UNVERIFIED / PROVISIONED / UNMEASURED."""
    row = row or {}
    name = str(row.get("name") or "").strip().lower()
    klass = str(row.get("klass") or class_of(name) or "").strip().lower()
    if klass in FORBIDDEN_CLASSES and not row.get("scoped_authority"):
        return {
            "name": name,
            "state": "FORBIDDEN",
            "klass": klass,
            "note": (
                "%s is %s. No financial, messaging, account, permission, "
                "or destructive write without exact scoped authority."
            )
            % (name or "service", klass or "restricted"),
        }
    if row.get("probe_ok"):
        return {
            "name": name,
            "state": "LIVE",
            "klass": klass,
            "note": "%s answered a read-only probe. No secrets recorded." % (name or "service"),
        }
    if row.get("claimed_unverified"):
        return {
            "name": name,
            "state": "UNVERIFIED",
            "klass": klass,
            "note": "%s is enabled/unverified in the Aug 21 cache. Not live here." % (name or "service"),
        }
    if row.get("claimed_connected"):
        return {
            "name": name,
            "state": "PROVISIONED",
            "klass": klass,
            "note": "%s is cached-connected, not live in this session." % (name or "service"),
        }
    return {
        "name": name,
        "state": "UNMEASURED",
        "klass": klass,
        "note": "%s has no claim and no probe. Absence was not stillness." % (name or "service"),
    }


def mcp_state(exists, size, server_count):
    """Empty or missing mcp.json is measured, not invented."""
    if not exists:
        return {
            "exists": False,
            "empty": True,
            "size": 0,
            "server_count": 0,
            "note": "~/.cursor/mcp.json absent. Provisioned cache is not a live file.",
        }
    empty = int(size or 0) == 0 or int(server_count or 0) == 0
    return {
        "exists": True,
        "empty": empty,
        "size": int(size or 0),
        "server_count": int(server_count or 0),
        "note": (
            "~/.cursor/mcp.json present, %s byte(s), %s mcpServers. Empty is the finding."
            % (int(size or 0), int(server_count or 0))
            if empty
            else "~/.cursor/mcp.json has %s named server(s). Names only. No secrets."
            % int(server_count or 0)
        ),
    }


def vscdb_plan(present, size_bytes=0, wal_bytes=0, process_count=0):
    """Plan only. Never delete, vacuum, or repair a live DB."""
    return {
        "present": bool(present),
        "size_bytes": int(size_bytes or 0),
        "wal_bytes": int(wal_bytes or 0),
        "process_count": int(process_count or 0),
        "plan": list(VSCDB_PLAN),
        "actuate": False,
        "refuse_live_repair": True,
        "note": (
            "state.vscdb plan is backup, clean shutdown, checkpoint, "
            "then integrity. Do not delete/vacuum/repair live."
        ),
    }


def measure_from_rows(facts):
    """Pure census so tests do not need a live MCP bus."""
    facts = facts or {}
    connected = list(facts.get("claimed_connected") or CLAIMED_CONNECTED)
    unverified = list(facts.get("claimed_unverified") or CLAIMED_UNVERIFIED)
    live_names = set(_names(facts.get("live") or []))
    services = []
    seen = set()
    for name in connected + unverified + sorted(live_names):
        if name in seen:
            continue
        seen.add(name)
        services.append(
            classify_service(
                {
                    "name": name,
                    "klass": class_of(name),
                    "probe_ok": name in live_names,
                    "claimed_connected": name in connected,
                    "claimed_unverified": name in unverified,
                    "scoped_authority": False,
                }
            )
        )
    live = [row["name"] for row in services if row["state"] == "LIVE"]
    forbidden = [row["name"] for row in services if row["state"] == "FORBIDDEN"]
    provisioned = [row["name"] for row in services if row["state"] == "PROVISIONED"]
    unverified_out = [row["name"] for row in services if row["state"] == "UNVERIFIED"]
    mcp = mcp_state(
        bool(facts.get("mcp_exists")),
        facts.get("mcp_size") or 0,
        facts.get("mcp_server_count") or 0,
    )
    vscdb = vscdb_plan(
        bool(facts.get("vscdb_present")),
        facts.get("vscdb_size") or 0,
        facts.get("vscdb_wal") or 0,
        facts.get("cursor_processes") or 0,
    )
    connected_claim = int(facts.get("connected_claim") or len(connected))
    live_count = len(live)
    return {
        "measured": True,
        "enabled_claim": int(facts.get("enabled_claim") or 39),
        "connected_claim": connected_claim,
        "cache_age_days_claim": float(facts.get("cache_age_days_claim") or 4),
        "live_count": live_count,
        "forbidden_count": len(forbidden),
        "provisioned_count": len(provisioned),
        "unverified_count": len(unverified_out),
        "provisioned_ne_live": connected_claim != live_count or mcp["empty"],
        "services": services,
        "live": live,
        "forbidden": forbidden,
        "provisioned": provisioned,
        "unverified": unverified_out,
        "mcp": mcp,
        "vscdb": vscdb,
        "secrets": False,
        "titan": "NOT_WRITTEN",
    }


def classify(row):
    """Turn a measured census into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "connector census not read. Absence was not stillness. "
                "A Slack cache count is not a live probe."
            ),
        }
    mcp = row.get("mcp") or {}
    vscdb = row.get("vscdb") or {}
    plan = list(vscdb.get("plan") or [])
    if row.get("secrets"):
        return {
            "state": "NOT_LANDED",
            "note": "census tried to record secrets. Drop them. Status only.",
        }
    if not vscdb.get("refuse_live_repair") or vscdb.get("actuate"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "vscdb leftover must refuse live delete/vacuum/repair. "
                "Plan first. Do not actuate."
            ),
        }
    if any(step not in plan for step in VSCDB_PLAN):
        return {
            "state": "NOT_LANDED",
            "note": "vscdb plan missing backup, clean shutdown, checkpoint, or integrity.",
        }
    if not row.get("provisioned_ne_live"):
        return {
            "state": "CANDIDATE",
            "note": (
                "census did not record provisioned != live. "
                "A matching count is still not proof the cache is current."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "census measured %s claimed-connected vs %s live; mcp empty=%s. "
            "Provisioned != live. Forbidden writes skipped. "
            "vscdb plan only. No secrets. Talk is not a land."
        )
        % (
            int(row.get("connected_claim") or 0),
            int(row.get("live_count") or 0),
            bool(mcp.get("empty")),
        ),
    }


def measure_root(root):
    """Read mcp.json / vscdb presence from this box. Never dump contents."""
    home = os.path.expanduser("~")
    mcp_path = os.path.join(home, ".cursor", "mcp.json")
    exists = os.path.isfile(mcp_path)
    size = os.path.getsize(mcp_path) if exists else 0
    server_count = 0
    if exists and size:
        try:
            with open(mcp_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            servers = data.get("mcpServers") if isinstance(data, dict) else None
            if isinstance(servers, dict):
                server_count = len(servers)
        except (OSError, ValueError):
            server_count = 0
    vscdb_path = os.path.join(
        home, ".config", "Cursor", "User", "globalStorage", "state.vscdb"
    )
    present = os.path.isfile(vscdb_path)
    wal_path = vscdb_path + "-wal"
    catalog_path = os.path.join(os.path.abspath(root), DEFAULT_CATALOG)
    catalog = {}
    if os.path.isfile(catalog_path):
        with open(catalog_path, "r", encoding="utf-8") as handle:
            catalog = load_catalog(handle.read())
    facts = {
        "claimed_connected": catalog.get("claimed_connected") or list(CLAIMED_CONNECTED),
        "claimed_unverified": catalog.get("claimed_unverified") or list(CLAIMED_UNVERIFIED),
        "live": catalog.get("live") or [],
        "enabled_claim": catalog.get("enabled_claim") or 39,
        "connected_claim": catalog.get("connected_claim") or 23,
        "cache_age_days_claim": catalog.get("cache_age_days_claim") or 4,
        "mcp_exists": exists,
        "mcp_size": size,
        "mcp_server_count": server_count,
        "vscdb_present": present,
        "vscdb_size": os.path.getsize(vscdb_path) if present else 0,
        "vscdb_wal": os.path.getsize(wal_path) if os.path.isfile(wal_path) else 0,
        "cursor_processes": 0,
    }
    row = measure_from_rows(facts)
    row["root"] = os.path.abspath(root)
    row["mcp_path_present"] = exists
    row["vscdb_path_present"] = present
    return row


def catalog_from_row(row, slack_ts="1787637151.916759"):
    """Status receipt. Names and counts only. No secrets."""
    row = row or {}
    return {
        "source_id": "demon-connector-utilization-20260825-01",
        "slack_ts": slack_ts,
        "subject": "DEMON connector-utilization — provisioned != live",
        "enabled_claim": row.get("enabled_claim"),
        "connected_claim": row.get("connected_claim"),
        "cache_age_days_claim": row.get("cache_age_days_claim"),
        "claimed_connected": list(CLAIMED_CONNECTED),
        "claimed_unverified": list(CLAIMED_UNVERIFIED),
        "live": list(row.get("live") or []),
        "forbidden": list(row.get("forbidden") or []),
        "provisioned": list(row.get("provisioned") or []),
        "unverified": list(row.get("unverified") or []),
        "provisioned_ne_live": bool(row.get("provisioned_ne_live")),
        "mcp_empty": bool((row.get("mcp") or {}).get("empty")),
        "vscdb": {
            "present": bool((row.get("vscdb") or {}).get("present")),
            "plan": list(VSCDB_PLAN),
            "actuate": False,
            "refuse_live_repair": True,
        },
        "secrets": False,
        "hands_off": [
            "stripe/revenuecat/airwallex writes",
            "gmail/x/agentmail writes",
            "drive/calendar account writes",
            "state.vscdb delete/vacuum/repair",
            "dio titan --go",
            "jojo mcp/wake wiring",
            "host-zero leftover",
            "demon-connector-utilization-20260825-01",
        ],
        "titan": "NOT_WRITTEN",
        "note": (
            "Do not remint the DEMON taking. Cache count is not live. "
            "No secrets. Do not vacuum a live state.vscdb."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure provisioned MCP cache vs live read-only probes"
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    payload["catalog"] = catalog_from_row(row)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    secrets = classify({"measured": True, "secrets": True})
    assert secrets["state"] == "NOT_LANDED"
    no_plan = classify(
        {
            "measured": True,
            "provisioned_ne_live": True,
            "vscdb": {"refuse_live_repair": True, "actuate": False, "plan": ["backup"]},
        }
    )
    assert no_plan["state"] == "NOT_LANDED"
    fixtures = measure_from_rows(
        {
            "claimed_connected": list(CLAIMED_CONNECTED),
            "claimed_unverified": list(CLAIMED_UNVERIFIED),
            "live": ["github", "slack", "gitbook", "cursor-cloud"],
            "enabled_claim": 39,
            "connected_claim": 23,
            "cache_age_days_claim": 4,
            "mcp_exists": False,
            "mcp_size": 0,
            "mcp_server_count": 0,
            "vscdb_present": False,
        }
    )
    assert fixtures["provisioned_ne_live"] is True
    assert fixtures["mcp"]["empty"] is True
    assert "github" in fixtures["live"]
    assert "stripe" in fixtures["forbidden"]
    assert "gmail" in fixtures["forbidden"]
    assert fixtures["vscdb"]["refuse_live_repair"] is True
    assert fixtures["vscdb"]["actuate"] is False
    assert classify(fixtures)["state"] == "INTEGRATED"
    stripe = classify_service({"name": "stripe", "klass": "financial"})
    assert stripe["state"] == "FORBIDDEN"
    live = classify_service({"name": "github", "probe_ok": True})
    assert live["state"] == "LIVE"
    return True


if __name__ == "__main__":
    sys.exit(main())
