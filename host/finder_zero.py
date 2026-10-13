#!/usr/bin/env python3
"""host/finder_zero.py — a silent 0 is not a measurement.

Slack 1787638031.533189 (GAUGE COORDINATION / OWNER ORDER):
the collision-check road prints false zeros. Slack search returned
"No results found" four times for content later read via
read_channel. Owner law: the builds work; zero-returning tests have
been proven broken. The failure shape is `if find(x): print(y)` with
no miss branch.

This leftover ships the rule, not another essay:

- Every zero prints its search space (query, channel/path, pattern).
- Calibrate the finder against something KNOWN PRESENT in the same run.
  If that miss happens, every zero in the run is void.
- Collision checks pair search with read_channel / host / git evidence.
  Search-only zero is not clearance.
- The miss branch reports FINDER UNVERIFIED, never 0.

Talk that restates the order is CLAIMED until this leftover is on
current main. Did not remint gauge-zero-audit-20260825-01.

  python3 host/finder_zero.py
  python3 host/finder_zero.py --root .
  python3 host/finder_zero.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

if __package__:
    from .carrier_projection import CARRIER_ONLY, DURABLE_ON_MAIN, measure_slack_projection
else:
    from carrier_projection import CARRIER_ONLY, DURABLE_ON_MAIN, measure_slack_projection


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "FINDER_ZERO.json")
SLACK_TS = "1787638031.533189"
SOURCE_ID = "gauge-zero-audit-20260825-01"
SOURCE_SHA256 = "6e26558eb325818999d76c75995bb6f44f015c592d985c27c6c841b25ddb763b"
FINDER_UNVERIFIED = "FINDER UNVERIFIED"
BARE_FIND = re.compile(
    r"if\s+find\s*\([^)]*\)\s*:\s*(?:print|return)",
    re.IGNORECASE,
)
HAS_MISS = re.compile(r"FINDER UNVERIFIED", re.IGNORECASE)
SLACK_OR = re.compile(r"(?:^|\s)OR(?:\s|$)")
SLACK_AFTER = re.compile(r"\bafter:", re.IGNORECASE)


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.exists(os.path.join(root, rel))


def load_catalog(text):
    """Parse the catalog; malformed collection shapes return explicit errors."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    for field in ("defects", "hands_off"):
        value = data.get(field)
        if value is not None and not isinstance(value, list):
            return {"error": "catalog %s is not an array" % field}
    defects = []
    for item in data.get("defects") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("id") or item.get("name") or "").strip()
        if not name:
            continue
        defects.append(
            {
                "id": name,
                "query": str(item.get("query") or "").strip(),
                "verdict": str(item.get("verdict") or "").strip().upper(),
            }
        )
    return {
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "defects": defects,
        "hands_off": [
            str(item or "").strip()
            for item in (data.get("hands_off") or [])
            if str(item or "").strip()
        ],
    }


def search_space(query="", channel="", path="", pattern=""):
    """Name the exact space a zero came from. Incomplete space is void."""
    row = {
        "query": str(query or "").strip(),
        "channel": str(channel or "").strip(),
        "path": str(path or "").strip(),
        "pattern": str(pattern or "").strip(),
    }
    missing = [key for key in ("query", "pattern") if not row[key]]
    if not row["channel"] and not row["path"]:
        missing.append("channel_or_path")
    row["complete"] = not missing
    row["missing"] = missing
    return row


def slack_query_defects(query):
    """Name the measured Slack-search failure modes. Do not invent a 0."""
    text = str(query or "")
    defects = []
    if SLACK_OR.search(text):
        defects.append(
            {
                "id": "or_literal",
                "note": (
                    "Slack search has no boolean operators. OR is matched "
                    "literally, so the query searches for the word OR."
                ),
            }
        )
    terms = [part for part in text.split() if part and not part.startswith(("in:", "after:", "before:"))]
    if len(terms) >= 3:
        defects.append(
            {
                "id": "multi_term_and",
                "note": (
                    "Multi-term Slack search is AND-all. One weak term "
                    "voids the query."
                ),
            }
        )
    if SLACK_AFTER.search(text):
        defects.append(
            {
                "id": "after_filter",
                "note": (
                    "in:#channel + after:<ts> printed zero while messages "
                    "after that ts existed and were read seconds later."
                ),
            }
        )
    return defects


def calibrate(finder_hits, known_present):
    """Same-run known-present check. A miss voids every zero in the run."""
    present = [str(item or "").strip() for item in (known_present or []) if str(item or "").strip()]
    hits = [str(item or "").strip() for item in (finder_hits or []) if str(item or "").strip()]
    if not present:
        return {
            "calibrated": False,
            "state": FINDER_UNVERIFIED,
            "missed": [],
            "note": "no known-present calibration set. Every zero in this run is void.",
        }
    missed = [item for item in present if item not in hits]
    if missed:
        return {
            "calibrated": False,
            "state": FINDER_UNVERIFIED,
            "missed": missed,
            "note": (
                "finder missed known-present %s. Every zero in this run is void."
                % (", ".join(missed))
            ),
        }
    return {
        "calibrated": True,
        "state": "CALIBRATED",
        "missed": [],
        "note": "finder recovered known-present in the same run.",
    }


def report_find(hits, space, calibrated):
    """Miss branch never prints 0. Incomplete or uncalibrated is unverified."""
    space = space or {}
    if not space.get("complete"):
        return {
            "state": FINDER_UNVERIFIED,
            "count": None,
            "search_space": space,
            "note": (
                "search space incomplete: %s. A zero without its space is void."
                % (", ".join(space.get("missing") or ["unknown"]))
            ),
        }
    if not calibrated:
        return {
            "state": FINDER_UNVERIFIED,
            "count": None,
            "search_space": space,
            "note": "finder was not calibrated against known-present. Zeros are void.",
        }
    found = [item for item in (hits or []) if str(item or "").strip()]
    if not found:
        return {
            "state": FINDER_UNVERIFIED,
            "count": None,
            "search_space": space,
            "note": (
                "miss branch. FINDER UNVERIFIED, never 0. query=%r channel=%r "
                "path=%r pattern=%r"
                % (
                    space.get("query") or "",
                    space.get("channel") or "",
                    space.get("path") or "",
                    space.get("pattern") or "",
                )
            ),
        }
    return {
        "state": "FOUND",
        "count": len(found),
        "search_space": space,
        "note": "finder recovered %d hit(s) after calibration." % len(found),
    }


def collision_clearance(search_hits, pair_hits=None, process_hits=None):
    """Search-only zero is not clearance. Pair with channel / host / git."""
    search = [item for item in (search_hits or []) if str(item or "").strip()]
    paired = [item for item in (pair_hits or []) if str(item or "").strip()]
    process = [item for item in (process_hits or []) if str(item or "").strip()]
    if process and not search:
        return {
            "state": FINDER_UNVERIFIED,
            "clearance": False,
            "note": (
                "search-zero and process-evidence conflict. Process evidence "
                "wins; the search-zero is the suspect."
            ),
        }
    if paired and not search:
        return {
            "state": FINDER_UNVERIFIED,
            "clearance": False,
            "note": (
                "read_channel / host / git recovered the claim while search "
                "printed zero. Search-only zero is not clearance."
            ),
        }
    if not search and not paired and not process:
        return {
            "state": FINDER_UNVERIFIED,
            "clearance": False,
            "note": (
                "search-only miss with no pair evidence. Collision check is "
                "FINDER UNVERIFIED, never 0."
            ),
        }
    if search:
        return {
            "state": "FOUND",
            "clearance": False,
            "note": "search recovered a claim. That is a hit, not clearance.",
        }
    return {
        "state": FINDER_UNVERIFIED,
        "clearance": False,
        "note": "unpaired miss. Do not print 0.",
    }


def scan_bare_find(source):
    """Name `if find(x): print(y)` with no FINDER UNVERIFIED miss branch."""
    body = str(source or "")
    matches = list(BARE_FIND.finditer(body))
    if not matches:
        return {"bare_find": 0, "has_miss_branch": bool(HAS_MISS.search(body))}
    if HAS_MISS.search(body):
        return {"bare_find": len(matches), "has_miss_branch": True}
    return {"bare_find": len(matches), "has_miss_branch": False}


def measure_from_rows(facts):
    """Census from already-read facts. Missing facts stay named."""
    facts = facts or {}
    space = search_space(
        query=facts.get("query") or "",
        channel=facts.get("channel") or "",
        path=facts.get("path") or "",
        pattern=facts.get("pattern") or "",
    )
    query_defects = slack_query_defects(facts.get("query") or "")
    calibration = calibrate(facts.get("finder_hits") or [], facts.get("known_present") or [])
    find = report_find(facts.get("finder_hits") or [], space, calibration.get("calibrated"))
    if "search_hits" in facts:
        search_hits = facts.get("search_hits") or []
    else:
        search_hits = facts.get("finder_hits") or []
    collision = collision_clearance(
        search_hits,
        pair_hits=facts.get("pair_hits") or [],
        process_hits=facts.get("process_hits") or [],
    )
    scan = scan_bare_find(facts.get("source") or "")
    defects = list(facts.get("catalog_defects") or [])
    return {
        "measured": True,
        "search_space_complete": space["complete"],
        "search_space": space,
        "query_defects": query_defects,
        "calibrated": bool(calibration.get("calibrated")),
        "calibration_state": calibration.get("state"),
        "find_state": find.get("state"),
        "find_count": find.get("count"),
        "collision_state": collision.get("state"),
        "clearance": bool(collision.get("clearance")),
        "bare_find": scan.get("bare_find") or 0,
        "has_miss_branch": bool(scan.get("has_miss_branch")),
        "catalog_defects": len(defects),
        "gauge_id": facts.get("source_id") or SOURCE_ID,
        "slack_ts": facts.get("slack_ts") or SLACK_TS,
        "titan_write": facts.get("titan") or "NOT_WRITTEN",
        "never_print_zero": find.get("count") is None
        or find.get("state") != FINDER_UNVERIFIED
        or find.get("count") != 0,
    }


def measure_tree(root, catalog_text=""):
    """Read the current tree and census the finder-zero leftover."""
    catalog = load_catalog(catalog_text)
    if catalog.get("error"):
        return {
            "measured": False,
            "error": catalog["error"],
            "titan_write": "NOT_WRITTEN",
        }
    instrument = _read(root, os.path.join("host", "finder_zero.py"))
    card = _exists(root, os.path.join("ground", "FINDER_ZERO.md"))
    catalog_file = _exists(root, os.path.join("ground", "FINDER_ZERO.json"))
    gauge_path = os.path.join("p", "%s.md" % SOURCE_ID)
    gauge = measure_slack_projection(
        root,
        gauge_path,
        post_id=SOURCE_ID,
        carrier_ts=SLACK_TS,
        sender="GAUGE",
        inner_kind="COORDINATION",
        expected_sha256=SOURCE_SHA256,
    )
    facts = {
        "query": "in:#commons after:1787630000 OR FINDER UNVERIFIED Alt-Text Workbench",
        "channel": "#commons",
        "path": "host/finder_zero.py",
        "pattern": FINDER_UNVERIFIED,
        "finder_hits": [FINDER_UNVERIFIED] if HAS_MISS.search(instrument) else [],
        "known_present": [FINDER_UNVERIFIED],
        "search_hits": [],
        "pair_hits": [SOURCE_ID],
        "process_hits": ["jojo-visual-ci-20260825-01"] if not gauge["present"] else [],
        "source": instrument,
        "catalog_defects": catalog.get("defects") or [],
        "source_id": catalog.get("source_id") or SOURCE_ID,
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
    }
    row = measure_from_rows(facts)
    row["root"] = root
    row["instrument"] = bool(instrument)
    row["card"] = card
    row["catalog_file"] = catalog_file
    row["gauge_post"] = gauge["present"]
    row["gauge_post_state"] = gauge["state"]
    row["gauge_post_provenance_ok"] = gauge["provenance_ok"]
    row["gauge_post_provenance_mismatches"] = gauge["mismatches"]
    row["hands_off"] = catalog.get("hands_off") or []
    return row


def classify(row):
    """Leftover is INTEGRATED when the rule is encoded and zeros stay unnamed."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "finder-zero catalog / tree listing not read. "
                "Absence was not stillness."
            ),
        }
    if not row.get("search_space_complete"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "search space incomplete. Every zero must print query, "
                "channel/path, and pattern."
            ),
        }
    if not row.get("calibrated"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "finder missed known-present or had no calibration. "
                "Every zero in this run is void."
            ),
        }
    if row.get("find_count") == 0:
        return {
            "state": "NOT_LANDED",
            "note": "miss branch printed 0. Report FINDER UNVERIFIED, never 0.",
        }
    if row.get("clearance"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "search-only zero was treated as clearance. Pair with "
                "read_channel / host / git."
            ),
        }
    if row.get("bare_find") and not row.get("has_miss_branch"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "bare if find(x): print(y) with no FINDER UNVERIFIED miss "
                "branch."
            ),
        }
    if int(row.get("catalog_defects") or 0) < 4:
        return {
            "state": "NOT_LANDED",
            "note": (
                "GAUGE named four Slack-search false zeros. Catalog must "
                "name all four defects."
            ),
        }
    gauge_present = bool(row.get("gauge_post"))
    gauge_state = str(row.get("gauge_post_state") or CARRIER_ONLY).strip().upper()
    gauge_ok = (
        gauge_state == CARRIER_ONLY and not gauge_present
    ) or (
        gauge_state == DURABLE_ON_MAIN
        and gauge_present
        and bool(row.get("gauge_post_provenance_ok"))
    )
    if not gauge_ok:
        return {
            "state": "NOT_LANDED",
            "note": (
                "gauge-zero-audit source lacks exact Slack carrier provenance. "
                "Do not treat an arbitrary same-ID file as the source."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "finder-zero leftover is on this tree. Miss branch is "
            "FINDER UNVERIFIED, never 0. Search-only Slack zero is not "
            "clearance. GAUGE four defects named. Source state "
            + gauge_state
            + ". A Slack order without an exact carrier projection is still not the file."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the finder-zero leftover on current main"
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
    space = search_space(query="Alt-Text", channel="#commons", pattern="Alt-Text")
    assert space["complete"] is True
    incomplete = search_space(query="")
    assert incomplete["complete"] is False
    assert "query" in incomplete["missing"]
    bad_or = slack_query_defects("visual CI OR render_check")
    assert any(item["id"] == "or_literal" for item in bad_or)
    bad_and = slack_query_defects("board_ingest truncated repair after:2026-08-24")
    assert any(item["id"] == "multi_term_and" for item in bad_and)
    assert any(item["id"] == "after_filter" for item in bad_and)
    missed = calibrate([], ["known-present"])
    assert missed["calibrated"] is False
    assert missed["state"] == FINDER_UNVERIFIED
    ok = calibrate(["known-present"], ["known-present"])
    assert ok["calibrated"] is True
    silent = report_find([], space, True)
    assert silent["state"] == FINDER_UNVERIFIED
    assert silent["count"] is None
    found = report_find(["hit"], space, True)
    assert found["state"] == "FOUND"
    assert found["count"] == 1
    process_wins = collision_clearance([], process_hits=["jojo-visual-ci-20260825-01"])
    assert process_wins["state"] == FINDER_UNVERIFIED
    assert process_wins["clearance"] is False
    search_only = collision_clearance([])
    assert search_only["state"] == FINDER_UNVERIFIED
    bare = scan_bare_find("if find(x): print(y)")
    assert bare["bare_find"] == 1
    assert bare["has_miss_branch"] is False
    guarded = scan_bare_find(
        "hits = find(x)\nif hits:\n    print(y)\nelse:\n    print('FINDER UNVERIFIED')"
    )
    assert guarded["has_miss_branch"] is True
    live = measure_from_rows(
        {
            "query": "Alt-Text",
            "channel": "#commons",
            "pattern": "FINDER UNVERIFIED",
            "finder_hits": ["FINDER UNVERIFIED"],
            "known_present": ["FINDER UNVERIFIED"],
            "search_hits": [],
            "pair_hits": ["gauge-zero-audit-20260825-01"],
            "source": "print('FINDER UNVERIFIED')",
            "catalog_defects": [{}, {}, {}, {}],
        }
    )
    assert live["calibrated"] is True
    assert live["find_count"] == 1
    assert live["clearance"] is False
    assert classify(live)["state"] == "INTEGRATED"
    zeroed = dict(live)
    zeroed["find_count"] = 0
    assert classify(zeroed)["state"] == "NOT_LANDED"
    catalog = load_catalog('{"not":"valid-shape"')
    assert catalog.get("error")
    return True


if __name__ == "__main__":
    sys.exit(main())
