#!/usr/bin/env python3
"""host/verify_cite.py — a Slack cite is Commons HEAD, or it is talk.

Slack 1787634746.313679: independent verification of the open-access
revenue instrument. First numbers, then one evidence message. The
taking cited host/muhl_revenue.py + host/test_muhl_revenue.py at
cd7d4f864f0c04143a573173e0b42f61f3c65533.

That SHA is not a Commons object. Those paths are absent on official
Commons main. A Slack readout is CLAIMED. Missing cited paths are
NOT_LANDED. An unknown cite SHA is not current main. LocalDeviceAgent
is private; this public instrument does not fetch or copy those bytes.
It does not take the titan --check / submit / payment audit.

  python3 host/verify_cite.py
  python3 host/verify_cite.py --catalog ground/VERIFY_CITE.json --tree-root .
  python3 host/verify_cite.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

if __package__:
    from .finder_zero import (
        FINDER_UNVERIFIED,
        calibrate,
        report_find,
        search_space,
    )
else:
    from finder_zero import (
        FINDER_UNVERIFIED,
        calibrate,
        report_find,
        search_space,
    )


DEFAULT_CATALOG = os.path.join("ground", "VERIFY_CITE.json")
CALIBRATION_PATH = os.path.join("host", "verify_cite.py")
TREE_PATTERN = "<tree-root>/<cited-path> regular-file probe"


def load_catalog(text):
    """Parse the cite catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {
            "cited_sha": "",
            "cited_paths": [],
            "source_id": "",
            "error": "catalog is not JSON",
        }
    if not isinstance(data, dict):
        return {
            "cited_sha": "",
            "cited_paths": [],
            "source_id": "",
            "error": "catalog is not an object",
        }
    raw = data.get("cited_paths") or data.get("paths") or []
    paths = []
    seen = set()
    for item in raw:
        name = str(item or "").strip().replace("\\", "/")
        if not name or name in seen:
            continue
        seen.add(name)
        paths.append(name)
    return {
        "cited_sha": str(data.get("cited_sha") or data.get("sha") or "").strip(),
        "cited_paths": paths,
        "source_id": str(data.get("source_id") or "").strip(),
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "hands_off": list(data.get("hands_off") or []),
    }


def present_paths(paths, listing):
    """Which cited paths appear in a supplied tree listing."""
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


def probe_git_sha(sha, cwd=None):
    """True if git knows the object, False if it does not, None if unprobed."""
    sha = str(sha or "").strip()
    if not sha:
        return None
    try:
        env = dict(os.environ)
        # A partial clone may otherwise ask its promisor remote for an unknown
        # object.  This probe is local evidence and must finish deterministically.
        env["GIT_NO_LAZY_FETCH"] = "1"
        proc = subprocess.run(
            ["git", "cat-file", "-t", sha],
            cwd=cwd or os.getcwd(),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 0:
        return True
    return False


def classify(row):
    """Turn a measured cite census into a land-desk state."""
    row = row or {}
    if row.get("finder_state") == FINDER_UNVERIFIED:
        return {
            "state": FINDER_UNVERIFIED,
            "note": row.get("finder_note")
            or "tree finder failed execution or calibration. Absence is unverified.",
        }
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "cite catalog / tree listing not read. "
                "Absence was not measured."
            ),
        }
    paths = list(row.get("cited_paths") or [])
    present = list(row.get("present") or [])
    sha = str(row.get("cited_sha") or "").strip()
    sha_known = row.get("sha_known")
    if not paths and not sha:
        return {
            "state": "NOT_LANDED",
            "note": (
                "cite catalog has no SHA or paths. A Slack first-numbers "
                "taking is CLAIMED until the cite is named on current main."
            ),
        }
    missing = [item for item in paths if item not in present]
    sha_note = ""
    if sha and sha_known is None:
        sha_note = (
            " Cited SHA %s was not probed — UNMEASURED, not stillness."
            % sha[:12]
        )
    elif sha and sha_known is False:
        sha_note = (
            " Cited SHA %s is not a Commons object."
            % sha[:12]
        )
    elif sha and sha_known is True:
        sha_note = " Cited SHA is a Commons object."
    if sha and sha_known is False:
        return {
            "state": "NOT_LANDED",
            "note": (
                "cited SHA is not a Commons object. Slack first-numbers / "
                "independent-verification talk is CLAIMED. Do not copy "
                "private LDA bytes onto Commons. Do not remint."
                + (
                    " Cited paths present on this tree: %s/%s."
                    % (len(present), len(paths))
                    if paths
                    else ""
                )
            ),
        }
    if paths and missing and not present:
        if row.get("find_state") == FINDER_UNVERIFIED:
            note = (
                "FINDER UNVERIFIED: none of the %s cited paths are on this "
                "calibrated Commons tree. query=%r path=%r pattern=%r. "
                "Independent-verification / first-numbers talk is CLAIMED. "
                "Do not remint. Leave the titan audit to the taking."
                % (
                    len(paths),
                    (row.get("search_space") or {}).get("query") or "",
                    (row.get("search_space") or {}).get("path") or "",
                    (row.get("search_space") or {}).get("pattern") or "",
                )
            )
        else:
            note = (
                "0/%s cited paths are on this Commons tree. Independent-"
                "verification / first-numbers talk is CLAIMED. Do not "
                "remint. Leave the titan audit to the taking."
                % len(paths)
            )
        return {
            "state": "NOT_LANDED",
            "note": note + sha_note,
        }
    if paths and missing:
        return {
            "state": "CANDIDATE",
            "note": (
                "%s/%s cited paths on this tree. Missing: %s. A Slack "
                "readout is not current main."
                % (len(present), len(paths), ", ".join(missing))
            )
            + sha_note,
        }
    if paths and not missing:
        return {
            "state": "INTEGRATED",
            "note": (
                "all %s cited paths are on this Commons tree. A Slack "
                "first-numbers readout is still not the file."
                % len(paths)
            )
            + sha_note,
        }
    return {
        "state": "CANDIDATE",
        "note": (
            "cite named a SHA with no paths. Measure the object on "
            "current main. A Slack taking is not the file."
        )
        + sha_note,
    }


def measure_from_parts(catalog_text, listing, sha_known=None):
    """Pure measurer so tests do not need the live board."""
    catalog = load_catalog(catalog_text)
    paths = list(catalog.get("cited_paths") or [])
    present = present_paths(paths, listing)
    return {
        "measured": True,
        "cited_sha": catalog.get("cited_sha") or "",
        "cited_paths": paths,
        "present": present,
        "missing": [item for item in paths if item not in present],
        "present_count": len(present),
        "missing_count": len(paths) - len(present),
        "sha_known": sha_known,
        "source_id": catalog.get("source_id") or "",
        "slack_ts": catalog.get("slack_ts") or "",
        "hands_off": list(catalog.get("hands_off") or []),
        "titan": "NOT_WRITTEN",
    }


def listing_from_root(root, paths):
    """Which cited paths exist under root. Does not walk the private LDA tree."""
    names = []
    base = os.path.abspath(root)
    for path in paths or []:
        norm = str(path or "").strip().replace("\\", "/")
        if not norm:
            continue
        full = os.path.join(base, *norm.split("/"))
        if os.path.isfile(full):
            names.append(norm)
    return names


def cite_search_space(paths, tree_root):
    """Name the exact public-tree search space for this cite finder."""
    named = [
        str(item or "").strip().replace("\\", "/")
        for item in (paths or [])
        if str(item or "").strip()
    ]
    return search_space(
        query="verify-cite cited_paths %s plus known-present %s"
        % (" ".join(named) if named else "(empty catalog)", CALIBRATION_PATH),
        path=str(tree_root or ""),
        pattern=TREE_PATTERN,
    )


def _finder_failure(catalog_path, root, space, note, calibration=None):
    calibration = calibration or {}
    return {
        "measured": False,
        "catalog": catalog_path,
        "tree_root": root,
        "finder_state": FINDER_UNVERIFIED,
        "finder_note": str(note or "tree finder failed"),
        "search_space": space,
        "calibrated": False,
        "calibration_id": CALIBRATION_PATH,
        "calibration_state": calibration.get("state") or FINDER_UNVERIFIED,
        "calibration_missed": list(calibration.get("missed") or []),
        "observed": None,
        "miss_behavior": FINDER_UNVERIFIED,
        "titan": "NOT_WRITTEN",
    }


def measure_paths(catalog_path, tree_root=None, git_cwd=None):
    path = os.path.abspath(catalog_path)
    if not os.path.isfile(path):
        return {
            "measured": False,
            "error": "catalog missing: %s" % path,
            "titan": "NOT_WRITTEN",
        }
    with open(path, "r", encoding="utf-8") as handle:
        catalog_text = handle.read()
    catalog = load_catalog(catalog_text)
    root = os.path.abspath(tree_root) if tree_root else ""
    space = cite_search_space(catalog.get("cited_paths") or [], root)
    if not root:
        return _finder_failure(
            path,
            root,
            space,
            "tree root not supplied; absence is FINDER UNVERIFIED, never 0",
        )
    if not os.path.isdir(root):
        return _finder_failure(
            path,
            root,
            space,
            "tree root unavailable: %s; absence is FINDER UNVERIFIED, never 0"
            % root,
        )

    calibration_hits = listing_from_root(root, [CALIBRATION_PATH])
    calibration = calibrate(calibration_hits, [CALIBRATION_PATH])
    if not calibration.get("calibrated"):
        return _finder_failure(
            path,
            root,
            space,
            calibration.get("note") or "known-present tree calibration failed",
            calibration,
        )

    listing = listing_from_root(root, catalog.get("cited_paths") or [])
    find = report_find(listing, space, True)
    sha_known = None
    if catalog.get("cited_sha"):
        sha_known = probe_git_sha(catalog["cited_sha"], cwd=git_cwd or root)
    row = measure_from_parts(catalog_text, listing, sha_known=sha_known)
    row.update(
        catalog=path,
        tree_root=root,
        finder_state="CALIBRATED",
        search_space=space,
        calibrated=True,
        calibration_id=CALIBRATION_PATH,
        calibration_state=calibration.get("state") or "CALIBRATED",
        calibration_missed=[],
        find_state=find.get("state"),
        find_count=find.get("count"),
        find_note=find.get("note"),
        observed={
            "calibration_hits": list(calibration_hits),
            "cited_path_hits": len(listing),
            "cited_path_count": len(catalog.get("cited_paths") or []),
        },
        miss_behavior=(
            "CALIBRATED_ABSENCE"
            if (catalog.get("cited_paths") and not listing)
            else ("CALIBRATED_PARTIAL" if row["missing_count"] else "FOUND")
        ),
    )
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure a Slack cite against the Commons tree"
    )
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument(
        "--tree-root",
        default=".",
        help="optional Commons tree to test cited paths against",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the stdlib fixtures and exit",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if _self_test() else 1
    row = measure_paths(args.catalog, args.tree_root or None)
    verdict = classify(row)
    payload = dict(row)
    payload.update(verdict)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    none = measure_from_parts('{"cited_paths":[]}', [])
    assert none["cited_paths"] == []
    assert classify(none)["state"] == "NOT_LANDED"
    catalog = json.dumps(
        {
            "cited_sha": "cd7d4f864f0c04143a573173e0b42f61f3c65533",
            "cited_paths": [
                "host/muhl_revenue.py",
                "host/test_muhl_revenue.py",
            ],
        }
    )
    unknown = measure_from_parts(catalog, [], sha_known=False)
    assert unknown["present_count"] == 0
    assert classify(unknown)["state"] == "NOT_LANDED"
    assert "not a Commons object" in classify(unknown)["note"]
    missing = measure_from_parts(catalog, [], sha_known=None)
    assert classify(missing)["state"] == "NOT_LANDED"
    half = measure_from_parts(
        catalog, ["host/muhl_revenue.py"], sha_known=True
    )
    assert half["present"] == ["host/muhl_revenue.py"]
    assert classify(half)["state"] == "CANDIDATE"
    both = measure_from_parts(
        catalog,
        ["host/muhl_revenue.py", "host/test_muhl_revenue.py"],
        sha_known=True,
    )
    assert classify(both)["state"] == "INTEGRATED"
    assert both["titan"] == "NOT_WRITTEN"
    return True


if __name__ == "__main__":
    sys.exit(main())
