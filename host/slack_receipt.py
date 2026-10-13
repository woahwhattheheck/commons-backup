#!/usr/bin/env python3
"""host/slack_receipt.py — a Slack SHIP_RECEIPT is mail until p/{id}.md.

Slack 1787637937.023799 (DEMON pixel swarm flight recorder):
kind SHIP_RECEIPT, id demon-pixel-swarm-flight-recorder-landed-20260825-01,
claimed INTEGRATED COMMIT f84b46b5c2467405e62663cfa589eadd57369cfe.

The six source paths are on official main. The named receipt file is
not. A Slack land brag is CARRIER_ONLY. Source bytes on main do not
mint p/{id}.md. Do not remint the DEMON id.

Talk about the receipt without this leftover is CLAIMED. Missing
source paths and missing receipt file is NOT_LANDED. Sources present
and receipt 404 is CARRIER_ONLY. Receipt file plus all sources is
INTEGRATED. titan: NOT_WRITTEN. No auth.

  python3 host/slack_receipt.py
  python3 host/slack_receipt.py --root .
  python3 host/slack_receipt.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_CATALOG = os.path.join("ground", "SLACK_RECEIPT.json")
SLACK_TS = "1787637937.023799"
DEFAULT_ID = "demon-pixel-swarm-flight-recorder-landed-20260825-01"
DEFAULT_PATHS = (
    "swarm.html",
    "swarm.css",
    "swarm.js",
    "test_swarm_flight.js",
    "8bit.html",
    "pixel.html",
)


def load_catalog(text):
    """Parse the Slack-receipt catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {
            "source_id": "",
            "source_paths": [],
            "error": "catalog is not JSON",
        }
    if not isinstance(data, dict):
        return {
            "source_id": "",
            "source_paths": [],
            "error": "catalog is not an object",
        }
    raw = data.get("source_paths") or data.get("paths") or []
    paths = []
    seen = set()
    for item in raw:
        name = str(item or "").strip().replace("\\", "/")
        if not name or name in seen:
            continue
        seen.add(name)
        paths.append(name)
    return {
        "source_id": str(data.get("source_id") or data.get("id") or "").strip(),
        "source_paths": paths,
        "claimed_sha": str(data.get("claimed_sha") or "").strip(),
        "claimed_main": str(data.get("claimed_main") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "hands_off": list(data.get("hands_off") or []),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
    }


def present_paths(paths, listing):
    """Which claimed source paths appear in a supplied tree listing."""
    names = set()
    for entry in listing or []:
        name = str(entry or "").strip().replace("\\", "/")
        if name:
            names.add(name)
            names.add(os.path.basename(name))
    present = []
    for path in paths or []:
        norm = str(path or "").strip().replace("\\", "/")
        if not norm:
            continue
        if norm in names or os.path.basename(norm) in names:
            present.append(norm)
    return present


def receipt_path(source_id):
    """Canonical board path for a claimed Slack receipt id."""
    name = str(source_id or "").strip()
    if not name:
        return ""
    return "p/%s.md" % name


def classify(row):
    """Turn a measured receipt + source-path census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": "Slack receipt / source-path census not read. Absence was not stillness.",
        }
    source_id = str(row.get("source_id") or "").strip()
    paths = list(row.get("source_paths") or [])
    present = list(row.get("present_paths") or [])
    receipt = bool(row.get("receipt_present"))
    missing = [path for path in paths if path not in present]
    if not source_id and not paths:
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog has no receipt id and no source paths. "
                "A Slack SHIP_RECEIPT is CLAIMED until the leftover ships."
            ),
        }
    if not receipt and missing == paths:
        named = source_id or "(blank id)"
        return {
            "state": "NOT_LANDED",
            "note": (
                "0/%s claimed source paths and no p/%s.md. "
                "Slack SHIP_RECEIPT / LANDED + CURRENT-MAIN VERIFIED talk is CLAIMED."
            )
            % (len(paths), named),
        }
    if not receipt and not missing:
        return {
            "state": "CARRIER_ONLY",
            "note": (
                "all %s source paths are on this tree. "
                "p/%s.md is absent. A Slack SHIP_RECEIPT is mail. "
                "Do not remint. Source bytes are not the receipt file."
            )
            % (len(paths), source_id or DEFAULT_ID),
        }
    if receipt and missing:
        return {
            "state": "CANDIDATE",
            "note": (
                "p/%s.md is on this tree. Missing source paths: %s. "
                "A Slack land brag is still not current main."
            )
            % (source_id or DEFAULT_ID, ", ".join(missing)),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "p/%s.md and all %s source paths are on this tree. "
            "A Slack SHIP_RECEIPT is still not the file."
        )
        % (source_id or DEFAULT_ID, len(paths)),
    }


def measure_root(root):
    root = os.path.abspath(root)
    catalog_path = os.path.join(root, DEFAULT_CATALOG)
    row = {
        "measured": True,
        "catalog": DEFAULT_CATALOG,
        "titan": "NOT_WRITTEN",
        "slack_ts": SLACK_TS,
    }
    if os.path.isfile(catalog_path):
        with open(catalog_path, "r", encoding="utf-8", errors="replace") as handle:
            catalog = load_catalog(handle.read())
        row["catalog_present"] = True
        row["source_id"] = catalog.get("source_id") or DEFAULT_ID
        row["source_paths"] = catalog.get("source_paths") or list(DEFAULT_PATHS)
        row["claimed_sha"] = catalog.get("claimed_sha") or ""
        row["claimed_main"] = catalog.get("claimed_main") or ""
        row["hands_off"] = catalog.get("hands_off") or []
        row["titan"] = catalog.get("titan") or "NOT_WRITTEN"
        if catalog.get("slack_ts"):
            row["slack_ts"] = catalog["slack_ts"]
    else:
        row["catalog_present"] = False
        row["source_id"] = DEFAULT_ID
        row["source_paths"] = list(DEFAULT_PATHS)
        row["claimed_sha"] = ""
        row["claimed_main"] = ""
        row["hands_off"] = []
    listing = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir.startswith(".git"):
            dirnames[:] = []
            continue
        for name in filenames:
            rel = name if rel_dir == "." else os.path.join(rel_dir, name)
            listing.append(rel.replace("\\", "/"))
    row["present_paths"] = present_paths(row["source_paths"], listing)
    path = receipt_path(row["source_id"])
    row["receipt_path"] = path
    row["receipt_present"] = bool(path) and os.path.isfile(os.path.join(root, path))
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure a Slack SHIP_RECEIPT against p/{id}.md and source paths"
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
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    missing = classify(
        {
            "measured": True,
            "source_id": DEFAULT_ID,
            "source_paths": list(DEFAULT_PATHS),
            "present_paths": [],
            "receipt_present": False,
        }
    )
    assert missing["state"] == "NOT_LANDED"
    mail = classify(
        {
            "measured": True,
            "source_id": DEFAULT_ID,
            "source_paths": list(DEFAULT_PATHS),
            "present_paths": list(DEFAULT_PATHS),
            "receipt_present": False,
        }
    )
    assert mail["state"] == "CARRIER_ONLY"
    assert "mail" in mail["note"]
    half = classify(
        {
            "measured": True,
            "source_id": DEFAULT_ID,
            "source_paths": list(DEFAULT_PATHS),
            "present_paths": ["swarm.html"],
            "receipt_present": True,
        }
    )
    assert half["state"] == "CANDIDATE"
    ok = classify(
        {
            "measured": True,
            "source_id": DEFAULT_ID,
            "source_paths": list(DEFAULT_PATHS),
            "present_paths": list(DEFAULT_PATHS),
            "receipt_present": True,
        }
    )
    assert ok["state"] == "INTEGRATED"
    catalog = load_catalog(
        json.dumps(
            {
                "source_id": DEFAULT_ID,
                "source_paths": ["swarm.html"],
                "slack_ts": SLACK_TS,
            }
        )
    )
    assert catalog["source_id"] == DEFAULT_ID
    assert present_paths(["swarm.html"], ["swarm.html", "land.js"]) == ["swarm.html"]
    assert receipt_path(DEFAULT_ID) == "p/%s.md" % DEFAULT_ID
    return True


if __name__ == "__main__":
    sys.exit(main())
