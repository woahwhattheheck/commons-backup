#!/usr/bin/env python3
"""host/stranded_map.py — Slack map is not a land.

Slack 1787635487.642039 (DEMON rolling utilization / REAL-BUT-STRANDED MAP):
six current-main leftovers were named. Talk that lists them is CLAIMED
until this leftover measures the six items on the tree.

This leftover does not place Android CI (DIO). It does not wire MCP/wake
(JOJO). It does not take White Box / Bazaar commercial next steps. It
does not write titan.gguf. It does not smash commons.mno.

  python3 host/stranded_map.py
  python3 host/stranded_map.py --root .
  python3 host/stranded_map.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "STRANDED_MAP.json")
DEFAULT_PACKET = os.path.join("excerpts", "20260823", "titan_move_packet.json")
DEFAULT_BAZAAR = "bazaar.json"
LDA_ANDROID = os.path.join("lda", "workflows", "android.yml")
GH_ANDROID = os.path.join(".github", "workflows", "android.yml")
WAKE_JOBS = "wake_jobs"
COPY_NODE = os.path.join("bazaar", "nodes", "CURSOR_GROK", "SEED0.mno")
WHITEBOX_SOURCE = os.path.join("muhl", "whitebox", "whitebox.py")
MCP_SURFACES = (
    "commons_mcp.py",
    os.path.join("independent_commons_mcp"),
    os.path.join("door", "src", "mcp.server.ts"),
    "mcp_server",
)
MCP_INVENTORY = os.path.join("ground", "MCP_INVENTORY.json")
SLACK_TS = "1787635487.642039"
PACKET_SIZE = 103812669582
LATER_SIZE = 103831308164
PRODUCTION_CANARY_ID = "specter-watchdog-head-proof-20260825-01"


def _exists(root, rel):
    return os.path.exists(os.path.join(root, rel))


def _wake_job_rows(root):
    """Read every job file. Invalid files stay visible, never silent.

    Executor-queue rows stay in the census. VERIFIED uses canonical canaries.
    """
    folder = os.path.join(root, WAKE_JOBS)
    if not os.path.isdir(folder):
        return []
    rows = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if (
            not name.endswith(".json")
            or name == "_last_tick.json"
            or not os.path.isfile(path)
        ):
            continue
        stem = name[:-5]
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            rows.append({"job_id": stem, "status": "INVALID"})
            continue
        if not isinstance(data, dict):
            rows.append({"job_id": stem, "status": "INVALID"})
            continue
        checkpoint = data.get("checkpoint") if isinstance(data.get("checkpoint"), dict) else {}
        rows.append(
            {
                "job_id": str(data.get("job_id") or stem),
                "status": str(data.get("status") or "UNKNOWN"),
                "owner_claim": str(data.get("owner_claim") or ""),
                "schema": str(data.get("schema") or checkpoint.get("schema") or ""),
            }
        )
    return rows


def _wake_job_census(root):
    """One snapshot: count and rows come from the same listing."""
    rows = _wake_job_rows(root)
    return {"wake_jobs": rows, "wake_job_json": len(rows)}


def _wake_job_json_count(root):
    return _wake_job_census(root)["wake_job_json"]


def is_canonical_wake_job(item):
    """Production canaries are canonical. Live grok.com executor jobs are not.

    wake_jobs/ is one store: watchdog canaries and the grok.com executor queue.
    VERIFIED is the canary lane. A live LEASED/OPEN executor job stays visible
    and does not poison that lane.
    """
    item = item or {}
    claim = str(item.get("owner_claim") or "").strip().upper()
    schema = str(item.get("schema") or "").strip().lower()
    checkpoint = item.get("checkpoint") if isinstance(item.get("checkpoint"), dict) else {}
    checkpoint_schema = str(checkpoint.get("schema") or "").strip().lower()
    if claim == "GROK_EXECUTOR":
        return False
    if schema.startswith("commons-grok-executor"):
        return False
    if checkpoint_schema.startswith("commons-grok-executor"):
        return False
    return True


def _wake_state(wake_json, wake_jobs):
    """VERIFIED only when every canonical row is DONE. Else CANDIDATE/EMPTY."""
    rows = list(wake_jobs or [])
    if wake_json <= 0:
        return "EMPTY"
    if len(rows) != int(wake_json):
        return "CANDIDATE"
    canonical = [item for item in rows if is_canonical_wake_job(item)]
    if not canonical:
        return "CANDIDATE"
    statuses = [
        str((item or {}).get("status") or "UNKNOWN").upper()
        for item in canonical
    ]
    if all(status == "DONE" for status in statuses):
        return "VERIFIED"
    return "CANDIDATE"


def _mcp_present(root):
    found = []
    for rel in MCP_SURFACES:
        if _exists(root, rel):
            found.append(rel.replace("\\", "/"))
    return found


def _bazaar_offer_count(root):
    path = os.path.join(root, DEFAULT_BAZAAR)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return 0
    offers = data.get("offers") if isinstance(data, dict) else None
    if not isinstance(offers, list):
        return 0
    return len(offers)


def _packet_size(root):
    path = os.path.join(root, DEFAULT_PACKET)
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("live_size_after")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_catalog(text):
    """Parse the stranded-map catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "later_size": LATER_SIZE}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "later_size": LATER_SIZE}
    later = data.get("titan_later_size")
    try:
        later_size = int(later)
    except (TypeError, ValueError):
        later_size = LATER_SIZE
    return {
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "later_size": later_size,
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "hands_off": [
            str(item or "").strip()
            for item in (data.get("hands_off") or [])
            if str(item or "").strip()
        ],
    }


def measure_from_rows(facts):
    """Census from already-read filesystem facts. Missing facts stay named."""
    facts = facts or {}
    lda = bool(facts.get("lda_android"))
    gh = bool(facts.get("gh_android"))
    if lda and gh:
        android = "INTEGRATED"
    elif lda and not gh:
        android = "STRANDED"
    else:
        android = "NOT_LANDED"
    wake_jobs = list(facts.get("wake_jobs") or [])
    if "wake_job_json" in facts:
        wake_json = int(facts.get("wake_job_json") or 0)
    else:
        wake_json = len(wake_jobs)
    wake = _wake_state(wake_json, wake_jobs)
    surfaces = list(facts.get("mcp_surfaces") or [])
    inventory = bool(facts.get("mcp_inventory"))
    if surfaces and inventory:
        mcp = "INTEGRATED"
    elif surfaces:
        mcp = "FRAGMENTED"
    else:
        mcp = "NOT_LANDED"
    whitebox_source = bool(facts.get("whitebox_source"))
    customer = bool(facts.get("whitebox_customer_receipt"))
    if customer:
        whitebox = "INTEGRATED"
    elif whitebox_source:
        whitebox = "PROPOSED"
    else:
        whitebox = "NOT_LANDED"
    offers = int(facts.get("bazaar_offers") or 0)
    copy_node = bool(facts.get("bazaar_copy_node"))
    if copy_node:
        bazaar = "INTEGRATED"
    elif offers:
        bazaar = "UNFULFILLED"
    else:
        bazaar = "NOT_LANDED"
    packet_size = facts.get("titan_packet_size")
    later_size = facts.get("titan_later_size")
    if packet_size is None or later_size is None:
        titan = "UNMEASURED"
    elif int(packet_size) == int(later_size):
        titan = "CURRENT"
    else:
        titan = "STALE"
    return {
        "measured": True,
        "android": android,
        "lda_android": lda,
        "gh_android": gh,
        "wake": wake,
        "wake_job_json": wake_json,
        "wake_jobs": wake_jobs,
        "mcp": mcp,
        "mcp_surfaces": surfaces,
        "mcp_inventory": inventory,
        "whitebox": whitebox,
        "whitebox_source": whitebox_source,
        "whitebox_customer_receipt": customer,
        "bazaar": bazaar,
        "bazaar_offers": offers,
        "bazaar_copy_node": copy_node,
        "titan": titan,
        "titan_packet_size": packet_size,
        "titan_later_size": later_size,
        "lane_count": 6,
        "slack_ts": facts.get("slack_ts") or SLACK_TS,
    }


def measure_tree(root, catalog_text=""):
    """Read the current tree and census the six named leftovers."""
    catalog = load_catalog(catalog_text)
    if catalog.get("error"):
        return {
            "measured": False,
            "error": catalog["error"],
            "titan_write": "NOT_WRITTEN",
        }
    census = _wake_job_census(root)
    facts = {
        "lda_android": _exists(root, LDA_ANDROID),
        "gh_android": _exists(root, GH_ANDROID),
        "wake_job_json": census["wake_job_json"],
        "wake_jobs": census["wake_jobs"],
        "mcp_surfaces": _mcp_present(root),
        "mcp_inventory": _exists(root, MCP_INVENTORY),
        "whitebox_source": _exists(root, WHITEBOX_SOURCE),
        "whitebox_customer_receipt": False,
        "bazaar_offers": _bazaar_offer_count(root),
        "bazaar_copy_node": _exists(root, COPY_NODE),
        "titan_packet_size": _packet_size(root),
        "titan_later_size": catalog.get("later_size"),
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row["root"] = root
    row["titan_write"] = catalog.get("titan") or "NOT_WRITTEN"
    row["source_id"] = catalog.get("source_id") or ""
    return row


def classify(row):
    """The map leftover is INTEGRATED when all six items were measured."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "stranded-map catalog / tree listing not read. "
                "Absence was not stillness."
            ),
        }
    lanes = (
        row.get("android"),
        row.get("wake"),
        row.get("mcp"),
        row.get("whitebox"),
        row.get("bazaar"),
        row.get("titan"),
    )
    if any(item in (None, "", "UNMEASURED") for item in lanes):
        return {
            "state": "NOT_LANDED",
            "note": (
                "one or more of the six stranded items was not measured. "
                "A Slack REAL-BUT-STRANDED MAP is CLAIMED until the census "
                "names every leftover."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "six-item stranded map is measured on this tree. "
            "Android CI stays STRANDED until DIO places "
            ".github/workflows/android.yml. wake_jobs state is %s; "
            "VERIFIED only when every canonical row is DONE. Named "
            "idle resume remains unmeasured. MCP stays FRAGMENTED until "
            "one inventory lands. White Box stays PROPOSED. Bazaar "
            "copy-node stays UNFULFILLED. Titan posted size stays STALE. "
            "A Slack map is still not the file."
        )
        % (row.get("wake") or "UNMEASURED"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the six-item REAL-BUT-STRANDED MAP on current main"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    try:
        with open(args.catalog, encoding="utf-8") as handle:
            catalog_text = handle.read()
    except OSError as exc:
        payload = {
            "measured": False,
            "error": str(exc),
            "state": "UNMEASURED",
            "note": "catalog missing. Absence was not stillness.",
        }
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    row = measure_tree(args.root, catalog_text)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    live = measure_from_rows(
        {
            "lda_android": True,
            "gh_android": False,
            "wake_job_json": 0,
            "mcp_surfaces": list(MCP_SURFACES),
            "mcp_inventory": False,
            "whitebox_source": True,
            "whitebox_customer_receipt": False,
            "bazaar_offers": 7,
            "bazaar_copy_node": False,
            "titan_packet_size": PACKET_SIZE,
            "titan_later_size": LATER_SIZE,
        }
    )
    assert live["android"] == "STRANDED"
    assert live["wake"] == "EMPTY"
    assert live["mcp"] == "FRAGMENTED"
    assert live["whitebox"] == "PROPOSED"
    assert live["bazaar"] == "UNFULFILLED"
    assert live["titan"] == "STALE"
    assert live["lane_count"] == 6
    assert classify(live)["state"] == "INTEGRATED"
    placed = dict(live)
    placed["android"] = "INTEGRATED"
    placed["gh_android"] = True
    assert classify(placed)["state"] == "INTEGRATED"
    missing = measure_from_rows({"lda_android": True})
    assert missing["titan"] == "UNMEASURED"
    assert classify(missing)["state"] == "NOT_LANDED"
    mixed = measure_from_rows(
        {
            "wake_job_json": 2,
            "wake_jobs": [
                {"job_id": PRODUCTION_CANARY_ID, "status": "DONE"},
                {"job_id": "other-job", "status": "OPEN"},
            ],
            "titan_packet_size": PACKET_SIZE,
            "titan_later_size": LATER_SIZE,
        }
    )
    assert mixed["wake"] == "CANDIDATE"
    return True


if __name__ == "__main__":
    sys.exit(main())
