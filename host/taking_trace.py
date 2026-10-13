#!/usr/bin/env python3
"""host/taking_trace.py — Slack TAKING ids are files, or they are talk.

Slack 1787634411.405189 (DEMON rolling utilization report): four
responsive grok.exe sessions and three claimed TAKING ids. Trace those
ids against official Commons main. LocalDeviceAgent is a private repo;
this public instrument does not fetch or copy those bytes.

A Slack capacity report is CLAIMED. Missing Commons p/{id}.md is
NOT_LANDED. A private LDA path without a supplied listing is
UNMEASURED. Do not remint the grok46 ids. Do not take the revenue
jobs. Do not remint fleet_ids / unused_invoke leftovers.

BD084 / DETAIL 36 adoption wrap (cite, do not remint host/finder_zero.py):
listing OSError / missing p/ is FINDER UNVERIFIED, never [] → 0/N.
Exact X/Y search space + same-run known-present calibration.

  python3 host/taking_trace.py
  python3 host/taking_trace.py --catalog ground/TAKING_TRACE.json --posts-dir p
  python3 host/taking_trace.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys

if __package__:
    from .finder_zero import (
        FINDER_UNVERIFIED,
        calibrate,
        collision_clearance,
        report_find,
        search_space,
    )
else:
    from finder_zero import (
        FINDER_UNVERIFIED,
        calibrate,
        collision_clearance,
        report_find,
        search_space,
    )


DEFAULT_CATALOG = os.path.join("ground", "TAKING_TRACE.json")
CALIBRATION_ID = "rivet-ship-taking-trace-20260825-01"
LISTING_PATTERN = "p/{id}.md"


def load_catalog(text):
    """Parse the taking-id catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {
            "commons_ids": [],
            "source_id": "",
            "error": "catalog is not JSON",
        }
    if not isinstance(data, dict):
        return {
            "commons_ids": [],
            "source_id": "",
            "error": "catalog is not an object",
        }
    raw = data.get("commons_ids") or data.get("ids") or []
    ids = []
    seen = set()
    for item in raw:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        ids.append(name)
    lda = data.get("lda") if isinstance(data.get("lda"), dict) else {}
    return {
        "commons_ids": ids,
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "hands_off": list(data.get("hands_off") or []),
        "lda_repo": str(lda.get("repo") or "").strip(),
        "lda_claimed_sha": str(lda.get("claimed_sha") or "").strip(),
        "lda_claimed_paths": [
            str(path or "").strip()
            for path in (lda.get("claimed_paths") or [])
            if str(path or "").strip()
        ],
        "lda_visibility": str(lda.get("visibility") or "").strip(),
    }


def present_ids(ids, listing):
    """Which catalog ids have a matching p/{id}.md name in listing."""
    names = set()
    for entry in listing or []:
        name = str(entry or "").strip()
        if name.endswith(".md"):
            name = name[:-3]
        if name:
            names.add(name)
    return [item for item in ids if item in names]


def present_paths(paths, listing):
    """Which claimed paths appear in a supplied listing."""
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
            present.append(path)
    return present


def list_posts_dir(posts_dir):
    """List p/ names. Missing dir or OSError is unverified, never []."""
    root = os.path.abspath(posts_dir) if posts_dir else ""
    if not root:
        return {
            "listing_ok": False,
            "listing": None,
            "error": "posts dir not named. FINDER UNVERIFIED, never [].",
            "posts_dir": "",
        }
    if not os.path.isdir(root):
        return {
            "listing_ok": False,
            "listing": None,
            "error": (
                "posts dir missing: %s. FINDER UNVERIFIED, never []." % root
            ),
            "posts_dir": root,
        }
    try:
        listing = os.listdir(root)
    except OSError as exc:
        return {
            "listing_ok": False,
            "listing": None,
            "error": (
                "posts dir OSError: %s. FINDER UNVERIFIED, never []." % exc
            ),
            "posts_dir": root,
        }
    return {
        "listing_ok": True,
        "listing": listing,
        "error": "",
        "posts_dir": root,
    }


def host_pair_hits(posts_dir, ids):
    """Pair listing search with host file existence. Search-only is not clearance."""
    root = os.path.abspath(posts_dir) if posts_dir else ""
    hits = []
    if not root or not os.path.isdir(root):
        return hits
    seen = set()
    for item in list(ids or []) + [CALIBRATION_ID]:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if os.path.isfile(os.path.join(root, name + ".md")):
            hits.append(name)
    return hits


def taking_search_space(ids, posts_dir="p"):
    """Exact X/Y space for this finder. Incomplete space is void."""
    named = [str(item or "").strip() for item in (ids or []) if str(item or "").strip()]
    return search_space(
        query="taking-trace commons_ids %s"
        % (" ".join(named) if named else "(empty catalog)"),
        path=str(posts_dir or "p"),
        pattern=LISTING_PATTERN,
    )


def classify(row):
    """Turn a measured Commons + LDA census into a land-desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "taking catalog / p/{id}.md listing not read. "
                "Absence was not measured."
            ),
        }
    space = row.get("search_space") or {}
    if row.get("listing_ok") is False:
        return {
            "state": FINDER_UNVERIFIED,
            "note": (
                "p/ listing failed. FINDER UNVERIFIED, never 0. "
                "query=%r path=%r pattern=%r. %s"
                % (
                    space.get("query") or "",
                    space.get("path") or "",
                    space.get("pattern") or "",
                    row.get("listing_error") or "listing_ok=false",
                )
            ),
        }
    ids = list(row.get("commons_ids") or [])
    present = list(row.get("commons_present") or [])
    if not ids:
        return {
            "state": "NOT_LANDED",
            "note": (
                "taking catalog has no Commons ids. A Slack utilization "
                "report is CLAIMED until the ids are named on current main."
            ),
        }
    if row.get("calibrated") is False:
        return {
            "state": FINDER_UNVERIFIED,
            "note": (
                "same-run known-present %s missed. Every zero in this run "
                "is void. FINDER UNVERIFIED, never 0. query=%r path=%r "
                "pattern=%r"
                % (
                    row.get("known_present") or CALIBRATION_ID,
                    space.get("query") or "",
                    space.get("path") or "",
                    space.get("pattern") or "",
                )
            ),
        }
    missing = [item for item in ids if item not in present]
    lda_measured = bool(row.get("lda_measured"))
    lda_note = (
        " LDA listing measured."
        if lda_measured
        else (
            " LDA is private/unlisted here — UNMEASURED, not stillness. "
            "Do not copy private bytes onto Commons."
        )
    )
    if not missing:
        if lda_measured:
            lda_paths = list(row.get("lda_claimed_paths") or [])
            lda_present = list(row.get("lda_present") or [])
            lda_missing = [item for item in lda_paths if item not in lda_present]
            if lda_paths and not lda_missing:
                return {
                    "state": "INTEGRATED",
                    "note": (
                        "all %s claimed Commons taking ids are p/{id}.md "
                        "and the supplied LDA listing has the claimed paths. "
                        "A Slack capacity report is still not the file."
                    )
                    % len(ids),
                }
            return {
                "state": "CANDIDATE",
                "note": (
                    "Commons taking ids are durable. LDA listing missing: %s."
                    % (", ".join(lda_missing) or "unnamed")
                ),
            }
        return {
            "state": "CANDIDATE",
            "note": (
                "all %s claimed Commons taking ids are p/{id}.md."
                % len(ids)
            )
            + lda_note,
        }
    if present:
        return {
            "state": "CANDIDATE",
            "note": (
                "%s/%s Commons taking ids durable. Missing: %s. "
                "A Slack utilization report is not current main."
            )
            % (len(present), len(ids), ", ".join(missing))
            + lda_note,
        }
    return {
        "state": "NOT_LANDED",
        "note": (
            "FINDER UNVERIFIED: none of the %s claimed Commons taking ids "
            "are p/{id}.md. query=%r path=%r pattern=%r. Rolling "
            "utilization / grok-capacity-active talk is CLAIMED. Do not "
            "remint. Claim only the verification leftover."
        )
        % (
            len(ids),
            space.get("query") or "",
            space.get("path") or "",
            space.get("pattern") or "",
        )
        + lda_note,
    }


def measure_from_parts(
    catalog_text,
    commons_listing,
    lda_listing=None,
    listing_ok=True,
    listing_error="",
    posts_dir="p",
    pair_hits=None,
    known_present=None,
):
    """Pure measurer so tests do not need a private repo."""
    catalog = load_catalog(catalog_text)
    ids = list(catalog.get("commons_ids") or [])
    space = taking_search_space(ids, posts_dir)
    present = present_ids(ids, commons_listing) if listing_ok else []
    known = str(known_present or CALIBRATION_ID).strip() or CALIBRATION_ID
    calibration_hits = (
        present_ids([known], commons_listing) if listing_ok else []
    )
    calibration = calibrate(calibration_hits, [known])
    find = report_find(
        present, space, bool(calibration.get("calibrated")) and bool(listing_ok)
    )
    collision = collision_clearance(
        present if listing_ok else [],
        pair_hits=pair_hits,
    )
    lda_paths = list(catalog.get("lda_claimed_paths") or [])
    lda_measured = lda_listing is not None
    lda_present = present_paths(lda_paths, lda_listing) if lda_measured else []
    return {
        "measured": True,
        "commons_ids": ids,
        "commons_present": present,
        "commons_missing": [item for item in ids if item not in present],
        "commons_present_count": (
            len(present) if listing_ok and calibration.get("calibrated") else None
        ),
        "commons_missing_count": (
            (len(ids) - len(present))
            if listing_ok and calibration.get("calibrated")
            else None
        ),
        "source_id": catalog.get("source_id") or "",
        "slack_ts": catalog.get("slack_ts") or "",
        "hands_off": list(catalog.get("hands_off") or []),
        "lda_repo": catalog.get("lda_repo") or "",
        "lda_claimed_sha": catalog.get("lda_claimed_sha") or "",
        "lda_claimed_paths": lda_paths,
        "lda_visibility": catalog.get("lda_visibility") or "",
        "lda_measured": lda_measured,
        "lda_present": lda_present,
        "lda_missing": (
            [item for item in lda_paths if item not in lda_present]
            if lda_measured
            else list(lda_paths)
        ),
        "listing_ok": bool(listing_ok),
        "listing_error": str(listing_error or ""),
        "search_space": space,
        "known_present": known,
        "calibrated": bool(calibration.get("calibrated")),
        "calibration_state": calibration.get("state"),
        "calibration_note": calibration.get("note"),
        "find_state": find.get("state"),
        "find_count": find.get("count"),
        "find_note": find.get("note"),
        "collision_state": collision.get("state"),
        "clearance": bool(collision.get("clearance")),
        "collision_note": collision.get("note"),
        "titan": "NOT_WRITTEN",
    }


def measure_paths(catalog_path, posts_dir=None, lda_listing_path=None):
    path = os.path.abspath(catalog_path)
    if not os.path.isfile(path):
        return {
            "measured": False,
            "error": "catalog missing: %s" % path,
            "titan": "NOT_WRITTEN",
        }
    with open(path, "r", encoding="utf-8") as handle:
        catalog_text = handle.read()
    listed = list_posts_dir(posts_dir)
    listing = listed.get("listing") if listed.get("listing_ok") else []
    lda_listing = None
    if lda_listing_path:
        listing_path = os.path.abspath(lda_listing_path)
        if os.path.isfile(listing_path):
            with open(listing_path, "r", encoding="utf-8") as handle:
                lda_listing = [
                    line.strip()
                    for line in handle.read().splitlines()
                    if line.strip()
                ]
        else:
            lda_listing = []
    catalog = load_catalog(catalog_text)
    pair = host_pair_hits(
        listed.get("posts_dir"), catalog.get("commons_ids") or []
    )
    row = measure_from_parts(
        catalog_text,
        listing,
        lda_listing,
        listing_ok=listed.get("listing_ok"),
        listing_error=listed.get("error") or "",
        posts_dir=listed.get("posts_dir") or posts_dir or "p",
        pair_hits=pair,
    )
    row["catalog"] = path
    if listed.get("posts_dir"):
        row["posts_dir"] = listed["posts_dir"]
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Trace claimed TAKING ids against Commons p/{id}.md"
    )
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--posts-dir", default="p", help="optional p/ listing")
    parser.add_argument(
        "--lda-listing",
        default="",
        help="optional path list for private LDA; omit to leave LDA UNMEASURED",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_paths(
        args.catalog, args.posts_dir or None, args.lda_listing or None
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
    none = measure_from_parts('{"commons_ids":[]}', [])
    assert none["commons_ids"] == []
    assert classify(none)["state"] == "NOT_LANDED"
    catalog = json.dumps(
        {
            "source_id": "demon-rolling-utilization-20260825-01",
            "commons_ids": [
                "grok46-revenue-discovery-20260825-01",
                "grok46-open-revenue-desk-20260825-01",
            ],
            "lda": {
                "claimed_paths": ["host/muhl_revenue.py"],
                "visibility": "private",
            },
        }
    )
    cal = CALIBRATION_ID + ".md"
    missing = measure_from_parts(catalog, ["unrelated.md", cal])
    assert missing["commons_present_count"] == 0
    assert missing["lda_measured"] is False
    assert missing["calibrated"] is True
    assert missing["find_state"] == FINDER_UNVERIFIED
    assert missing["find_count"] is None
    miss_note = classify(missing)
    assert miss_note["state"] == "NOT_LANDED"
    assert "0/" not in miss_note["note"]
    assert FINDER_UNVERIFIED in miss_note["note"]
    failed = measure_from_parts(
        catalog, [], listing_ok=False, listing_error="OSError"
    )
    assert failed["listing_ok"] is False
    assert failed["calibrated"] is False
    assert failed["find_count"] is None
    assert classify(failed)["state"] == FINDER_UNVERIFIED
    assert "0/" not in classify(failed)["note"]
    half = measure_from_parts(
        catalog, ["grok46-revenue-discovery-20260825-01.md", cal]
    )
    assert half["commons_present"] == ["grok46-revenue-discovery-20260825-01"]
    assert classify(half)["state"] == "CANDIDATE"
    both = measure_from_parts(
        catalog,
        [
            "grok46-revenue-discovery-20260825-01.md",
            "grok46-open-revenue-desk-20260825-01.md",
            cal,
        ],
        ["host/muhl_revenue.py"],
    )
    assert classify(both)["state"] == "INTEGRATED"
    assert both["titan"] == "NOT_WRITTEN"
    assert both["search_space"]["complete"] is True
    listed = list_posts_dir(os.path.join("no-such-taking-posts", "missing"))
    assert listed["listing_ok"] is False
    assert listed["listing"] is None
    return True


if __name__ == "__main__":
    sys.exit(main())
