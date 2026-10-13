#!/usr/bin/env python3
"""host/heavy_lanes.py — live H-001/H-002 consumer leftover.

Slack 1787646811.754939: CLEAN SUPERGROK HEAVY LANES LIVE.
H-001-ARCHITECT and H-002-CONTAMINATION were announced.
Do not duplicate those packets. Cursor Grok is not the
Heavy substitute. A Slack lanes-live line is CLAIMED until
this leftover ships the non-Grok consumer.

Unique leftover: leftover-first so LANES LIVE is not the
already-INTEGRATED SUPERGROK_HEAVY sprint leftover.
Packet outputs stay CANDIDATE until the files exist.
Miss is FINDER-FAILED / FINDER-UNVERIFIED. Never 0.
Open door. Unseated still posts. Talk is not a land.

  python3 host/heavy_lanes.py
  python3 host/heavy_lanes.py --root .
  python3 host/heavy_lanes.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "HEAVY_LANES.json")
DEFAULT_CARD = os.path.join("ground", "HEAVY_LANES.md")
SPRINT_CATALOG = os.path.join("ground", "SUPERGROK_HEAVY.json")
SLACK_TS = "1787646811.754939"
LIVE_IDS = ("H-001-ARCHITECT", "H-002-CONTAMINATION")
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "heavy_lanes.py"),
    SPRINT_CATALOG,
    os.path.join("ground", "SUPERGROK_HEAVY.md"),
    os.path.join("ground", "GROK_HYGIENE.md"),
    os.path.join("ground", "MUHL_RECEIPT_LANE.md"),
    os.path.join("DIRECTIVES.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "SUPERGROK_HEAVY.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("ground", "SUPERGROK_HEAVY.md"),
    os.path.join("ground", "GROK_HYGIENE.md"),
    os.path.join("ground", "MUHL_RECEIPT_LANE.md"),
    os.path.join("ground", "SUBZERO_EXPLORER.md"),
    os.path.join("ground", "SITTING_REMINT.md"),
)
REQUIRED_PHRASES = (
    "heavy lanes leftover",
    "clean supergrok heavy lanes live",
    "h-001-architect",
    "h-002-contamination",
    "non-grok verification",
    "cursor grok is not the heavy substitute",
    "do not remint",
    "never 0",
    "finder-failed",
    "finder-unverified",
    "open door",
    "no auth",
    "no gate",
    "talk is not a land",
    "unseated",
)
PACKET_FIELDS = (
    "id",
    "lane",
    "state",
    "output_path",
    "unresolved",
    "deliverable",
    "verifier",
    "do_not_remint",
)


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def load_catalog(text):
    """Parse the live-lanes catalog. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON", "packets": []}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object", "packets": []}
    packets = []
    for item in data.get("packets") or []:
        if isinstance(item, dict):
            packets.append(item)
    already = []
    for item in data.get("already_landed") or []:
        name = str(item or "").strip()
        if name:
            already.append(name)
    gap = data.get("consumer_gap") or {}
    if not isinstance(gap, dict):
        gap = {}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "cursor_grok_is_not_heavy_substitute": bool(
            data.get("cursor_grok_is_not_heavy_substitute")
        ),
        "do_not_duplicate": bool(data.get("do_not_duplicate_heavy_packets")),
        "consumer_gap": gap,
        "packets": packets,
        "already_landed": already,
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "error": "",
    }


def sprint_packet_ids(root):
    """Ids already named by the SuperGrok Heavy sprint leftover."""
    catalog = load_catalog(_read(root, SPRINT_CATALOG))
    ids = []
    for item in catalog.get("packets") or []:
        name = str(item.get("id") or "").strip()
        if name:
            ids.append(name)
    return ids


def packet_errors(root, packets):
    """Return missing live ids, bad fields, and swallowed zeros."""
    errors = []
    seen = []
    for item in packets or []:
        missing = [field for field in PACKET_FIELDS if not item.get(field)]
        if missing:
            errors.append(
                "packet "
                + str(item.get("id") or "?")
                + " missing "
                + ",".join(missing)
            )
            continue
        name = str(item.get("id") or "")
        seen.append(name)
        unresolved = str(item.get("unresolved") or "").strip()
        if unresolved in ("0", "zero", "none", ""):
            errors.append("packet " + name + " bare unresolved zero")
        verifier = str(item.get("verifier") or "").lower()
        if "not grok" not in verifier and "not grok heavy" not in verifier:
            errors.append("packet " + name + " missing non-Grok verifier")
    for live_id in LIVE_IDS:
        if live_id not in seen:
            errors.append("missing live packet " + live_id)
    return errors


def output_states(root, packets):
    """CANDIDATE until the expected output file exists. Never 0."""
    rows = []
    for item in packets or []:
        rel = str(item.get("output_path") or "").strip()
        present = bool(rel) and _exists(root, rel)
        rows.append(
            {
                "id": str(item.get("id") or ""),
                "output_path": rel,
                "state": "INTEGRATED" if present else "CANDIDATE",
            }
        )
    return rows


def measure_from_rows(facts):
    """Attach leftover flags. Empty facts stay empty for classify()."""
    row = dict(facts or {})
    row["measured"] = True
    return row


def classify(row):
    """UNMEASURED / NOT_LANDED / INTEGRATED. Miss is never 0."""
    if not row:
        return {
            "state": "UNMEASURED",
            "note": (
                "Heavy lanes leftover not read. Absence was not stillness. "
                "A Slack lanes-live line is not a land."
            ),
        }
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "Heavy lanes leftover not measured. Absence was not "
                "stillness."
            ),
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence "
                "proof. FINDER-FAILED, never 0."
            ),
        }
    misses = list(row.get("misses") or [])
    if not row.get("card_present") or not row.get("catalog_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". CLEAN SUPERGROK HEAVY LANES LIVE talk is CLAIMED "
                "until the leftover ships. FINDER-FAILED, never 0."
            ),
        }
    packet_miss = list(row.get("packet_errors") or [])
    if packet_miss:
        return {
            "state": "NOT_LANDED",
            "note": (
                "live packets incomplete: "
                + "; ".join(packet_miss)
                + ". Do not remint SUPERGROK_HEAVY. FINDER-FAILED, never 0."
            ),
        }
    landed_missing = list(row.get("landed_missing") or [])
    if landed_missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "named already-landed leftover(s) missing: "
                + ", ".join(landed_missing)
                + ". Do not remint. FINDER-FAILED, never 0."
            ),
        }
    phrases = [str(item).lower() for item in (row.get("found_phrases") or [])]
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in phrases]
    gap = row.get("consumer_gap") or {}
    gap_ok = bool(gap.get("id")) and bool(gap.get("unresolved"))
    not_sub = bool(row.get("cursor_grok_is_not_heavy_substitute"))
    no_dup = bool(row.get("do_not_duplicate"))
    sprint_has_live = bool(row.get("sprint_has_live"))
    posting_open = bool(row.get("posting_open"))
    no_auth = bool(row.get("no_auth"))
    no_gate = bool(row.get("no_gate"))
    if sprint_has_live:
        return {
            "state": "NOT_LANDED",
            "note": (
                "SUPERGROK_HEAVY catalog now names a live packet. That is "
                "a remint of the sprint leftover. FINDER-FAILED, never 0."
            ),
        }
    if (
        needed
        or not gap_ok
        or not not_sub
        or not no_dup
        or not posting_open
        or not no_auth
        or not no_gate
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Live ids + consumer gap G-001 + Cursor-is-not-Heavy + "
                "open door + no auth + no gate required. Talk is CLAIMED. "
                "FINDER-FAILED, never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "Heavy lanes leftover is on this tree. H-001/H-002 have a "
            "non-Grok consumer. Packet outputs stay CANDIDATE until those "
            "files exist. A Slack lanes-live line is still not the file."
        ),
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = []
    blobs = []
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if not text:
            misses.append(rel)
        else:
            blobs.append(text)
    hay = "\n".join(blobs).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in hay]
    landed_present = [rel for rel in ALREADY_LANDED if _exists(root, rel)]
    landed_missing = [rel for rel in ALREADY_LANDED if not _exists(root, rel)]
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    if not calibration_ok:
        for rel in CALIBRATION:
            if rel not in calibration_hits and rel not in misses:
                misses.append("calibration:" + rel)
    packet_errs = packet_errors(root, catalog.get("packets") or [])
    outputs = output_states(root, catalog.get("packets") or [])
    sprint_ids = sprint_packet_ids(root)
    sprint_has_live = any(live_id in sprint_ids for live_id in LIVE_IDS)
    posting_open = (
        catalog.get("posting") == "OPEN"
        and "open door" in hay
        and "unseated" in hay
    )
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG)
        and not catalog.get("error"),
        "packet_errors": packet_errs,
        "packet_outputs": outputs,
        "sprint_ids": sprint_ids,
        "sprint_has_live": sprint_has_live,
        "consumer_gap": catalog.get("consumer_gap") or {},
        "cursor_grok_is_not_heavy_substitute": bool(
            catalog.get("cursor_grok_is_not_heavy_substitute")
        ),
        "do_not_duplicate": bool(catalog.get("do_not_duplicate")),
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "posting_open": posting_open,
        "no_auth": bool(catalog.get("no_auth")) and "no auth" in hay,
        "no_gate": bool(catalog.get("no_gate")) and "no gate" in hay,
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "landed_present": landed_present,
                "live_ids": list(LIVE_IDS),
                "packet_outputs": outputs,
                "sprint_ids": sprint_ids,
            },
            "z": (
                "misses "
                + json.dumps(misses + landed_missing + packet_errs)
                + " / FINDER-FAILED never 0"
            ),
        }
    )
    return row


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED", empty
    missing = classify(
        measure_from_rows(
            {
                "card_present": False,
                "catalog_present": False,
                "misses": ["ground/HEAVY_LANES.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure Heavy lanes leftover")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(args.root)
    verdict = classify(row)
    payload = {"verdict": verdict, "row": row}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verdict["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
