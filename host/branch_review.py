#!/usr/bin/env python3
"""host/branch_review.py — public-branch review + RETRACTED families.

Slack 1787640071.636039 (DEMON P0 impact ledger):
durable Commons context-integrity/retraction rule + public-branch
review coordination. Talk that restates the ledger is CLAIMED until
this leftover measures ten RETRACTED families and the public-branch
coordinator.

RETRACTED stays RETRACTED. Softening it to UNVERIFIED is NOT_LANDED.
A miss is FINDER-UNVERIFIED. It is never 0. This leftover does not
write titan. It does not smash commons.mno. It does not add a gate.
It does not dump secrets. It does not delete or rewrite history.

  python3 host/branch_review.py
  python3 host/branch_review.py --root .
  python3 host/branch_review.py --self-test

X = ten family ids + named branches + packet + PFC census
Y = family statuses / branch presence / name-class counts found
Z = missing family / softened RETRACTED / CLEAN/0 / failed calibration
Calibration = known-present HEAD.md + EXECUTE.md must be found in
the same run or the measure is UNMEASURED. A miss never prints 0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "BRANCH_REVIEW.json")
DEFAULT_CARD = os.path.join("ground", "BRANCH_REVIEW.md")
SLACK_TS = "1787640071.636039"
SOURCE_ID = "demon-p0-impact-ledger-20260825-01"
PACKET_PATH = os.path.join("excerpts", "20260823", "titan_move_packet.json")
PFC_CENSUS_PATH = os.path.join("docs", "PFC_BAKE_CENSUS.md")
SQUASH_2128 = "49c12302d557facc21b69a85e12c92e0740956c0"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "branch_review.py"),
    PACKET_PATH,
    PFC_CENSUS_PATH,
)
CALIBRATION = (
    os.path.join("ground", "HEAD.md"),
    os.path.join("ground", "EXECUTE.md"),
)
REQUIRED_PHRASES = (
    "branch_review",
    "do not soften retracted",
    "retracted stays retracted",
    "public-branch review",
    "planted-canary",
    "owner_hold",
    "finder-unverified",
    "never 0",
    "do not remint",
)
REQUIRED_FAMILIES = (
    "pfc_raw_a_zero",
    "titan_packet_root_404",
    "no_active_claim",
    "zero_deletions_zero_secrets",
    "fleet_silence_zero_replies",
    "five_builds_vapor",
    "claude_slack_path_dead",
    "zero_mcp_lsp_permissions",
    "pfc_0_of_0",
    "nothing_unpushed",
)
REQUIRED_BRANCHES = (
    "sd-wx",
    "player1-publish",
    "vent-final",
    "vent-fix",
    "kite-help",
)
ALLOWED_FAMILY_STATUS = frozenset({"RETRACTED"})
FORBIDDEN_FAMILY_STATUS = frozenset({"UNVERIFIED", "CLEAN", "0", "CLEARED"})
ALLOWED_BRANCH_STATUS = frozenset({"UNSCANNED", "REVIEW_QUEUED"})
FORBIDDEN_BRANCH_STATUS = frozenset({"CLEAN", "0", "CLEARED"})


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
    """Parse the branch-review catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    families = []
    for item in data.get("families") or []:
        if not isinstance(item, dict):
            continue
        family_id = str(item.get("id") or "").strip()
        status = str(item.get("status") or "").strip().upper()
        if family_id:
            families.append(
                {
                    "id": family_id,
                    "status": status or "RETRACTED",
                    "x": str(item.get("x") or "").strip(),
                    "y": str(item.get("y") or "").strip(),
                    "z": str(item.get("z") or "").strip().upper(),
                }
            )
    branches = []
    for item in data.get("branches") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            branches.append(
                {
                    "name": name,
                    "origin_head": str(item.get("origin_head") or "").strip().upper(),
                    "status": str(item.get("status") or "").strip().upper()
                    or "UNSCANNED",
                    "delete_rewrite": str(item.get("delete_rewrite") or "").strip().upper(),
                    "tree_files": item.get("tree_files"),
                    "claimed_258": str(item.get("claimed_258") or "").strip().upper(),
                }
            )
    routes = []
    for item in data.get("allowed_remeasurers") or []:
        name = str(item or "").strip()
        if name:
            routes.append(name)
    packet = data.get("packet") if isinstance(data.get("packet"), dict) else {}
    pfc = data.get("pfc_census") if isinstance(data.get("pfc_census"), dict) else {}
    squash = data.get("squash_2128") if isinstance(data.get("squash_2128"), dict) else {}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "kind": str(data.get("kind") or "").strip().upper(),
        "source_id": str(data.get("source_id") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "retracted_stays_retracted": bool(data.get("retracted_stays_retracted", True)),
        "soften_retracted_to_unverified": bool(
            data.get("soften_retracted_to_unverified", False)
        ),
        "xyz_required": bool(data.get("xyz_required", True)),
        "remeasurement_owner": str(data.get("remeasurement_owner") or "").strip(),
        "allowed_remeasurers": routes,
        "delete_rewrite": str(data.get("delete_rewrite") or "").strip().upper(),
        "secret_dump": bool(data.get("secret_dump", False)),
        "families": families,
        "branches": branches,
        "packet": {
            "path": str(packet.get("path") or PACKET_PATH).strip(),
            "cat_file": str(packet.get("cat_file") or "").strip().upper(),
        },
        "pfc_census": {
            "path": str(pfc.get("path") or PFC_CENSUS_PATH).strip(),
            "cat_file": str(pfc.get("cat_file") or "").strip().upper(),
            "clearance_sentence": str(pfc.get("clearance_sentence") or "").strip().upper(),
        },
        "squash_2128": {
            "sha": str(squash.get("sha") or SQUASH_2128).strip(),
            "object": str(squash.get("object") or "").strip().upper(),
        },
        "do_not_remint": [
            str(item).strip()
            for item in (data.get("do_not_remint") or [])
            if str(item).strip()
        ],
        "error": "",
    }


def measure_from_rows(facts):
    """Classify measured file/family/branch facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "families": list(facts.get("families") or []),
        "branches": list(facts.get("branches") or []),
        "packet_present": bool(facts.get("packet_present")),
        "pfc_census_present": bool(facts.get("pfc_census_present")),
        "clearance_retracted": bool(facts.get("clearance_retracted")),
        "retracted_stays_retracted": bool(facts.get("retracted_stays_retracted")),
        "soften_retracted_to_unverified": bool(
            facts.get("soften_retracted_to_unverified")
        ),
        "secret_dump": bool(facts.get("secret_dump")),
        "delete_rewrite": str(facts.get("delete_rewrite") or "").strip().upper(),
        "remeasurement_owner": str(facts.get("remeasurement_owner") or "").strip(),
        "allowed_remeasurers": list(facts.get("allowed_remeasurers") or []),
        "xyz_required": bool(facts.get("xyz_required")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
    }


def classify(row):
    """Turn a measured leftover census into a desk state.

    RETRACTED stays RETRACTED. A miss is FINDER-UNVERIFIED. It is never 0.
    """
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "branch-review leftover not read. Absence was not stillness. "
                "A Slack ledger is not the file. Z=FINDER-UNVERIFIED."
            ),
            "z": "FINDER-UNVERIFIED",
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence proof. "
                "Z=FINDER-UNVERIFIED. Never 0."
            ),
            "z": "FINDER-UNVERIFIED",
        }
    misses = list(row.get("misses") or [])
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    phrases = list(row.get("found_phrases") or [])
    families = list(row.get("families") or [])
    branches = list(row.get("branches") or [])
    owner = str(row.get("remeasurement_owner") or "").strip()
    routes = list(row.get("allowed_remeasurers") or [])
    xyz = bool(row.get("xyz_required"))
    packet_ok = bool(row.get("packet_present"))
    pfc_ok = bool(row.get("pfc_census_present"))
    clearance = bool(row.get("clearance_retracted"))
    stays = bool(row.get("retracted_stays_retracted"))
    softened = bool(row.get("soften_retracted_to_unverified"))
    dumped = bool(row.get("secret_dump"))
    hold = str(row.get("delete_rewrite") or "").strip().upper()
    if not card or not catalog:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". Branch-review / P0-impact-ledger talk is CLAIMED until the leftover ships. "
                "Z=FINDER-UNVERIFIED. Never 0."
            ),
            "z": "FINDER-UNVERIFIED",
        }
    needed = [item for item in REQUIRED_PHRASES if item not in phrases]
    by_id = {str(item.get("id") or ""): item for item in families}
    missing_ids = [item for item in REQUIRED_FAMILIES if item not in by_id]
    bad_family = [
        item
        for item in families
        if str(item.get("status") or "").upper() in FORBIDDEN_FAMILY_STATUS
        or str(item.get("status") or "").upper() not in ALLOWED_FAMILY_STATUS
    ]
    by_branch = {str(item.get("name") or ""): item for item in branches}
    missing_branches = [item for item in REQUIRED_BRANCHES if item not in by_branch]
    bad_branch = [
        item
        for item in branches
        if str(item.get("status") or "").upper() in FORBIDDEN_BRANCH_STATUS
        or str(item.get("status") or "").upper() not in ALLOWED_BRANCH_STATUS
    ]
    sd_wx = by_branch.get("sd-wx") or {}
    claimed_258_as_tree = str(sd_wx.get("claimed_258") or "").upper() == "CURRENT_TREE"
    if (
        needed
        or missing_ids
        or bad_family
        or missing_branches
        or bad_branch
        or softened
        or not stays
        or dumped
        or hold != "OWNER_HOLD"
        or "Codex / Grok Build" not in owner
        or len(routes) < 4
        or not xyz
        or not packet_ok
        or not pfc_ok
        or not clearance
        or claimed_258_as_tree
    ):
        extra = []
        if missing_ids:
            extra.append("missing families " + ", ".join(missing_ids))
        if bad_family:
            extra.append("RETRACTED softened or forbidden")
        if missing_branches:
            extra.append("missing branches " + ", ".join(missing_branches))
        if bad_branch:
            extra.append("CLEAN/0 forbidden on branches")
        if softened or not stays:
            extra.append("RETRACTED must not become UNVERIFIED")
        if dumped:
            extra.append("secret dump forbidden")
        if hold != "OWNER_HOLD":
            extra.append("delete/rewrite must stay OWNER_HOLD")
        if not packet_ok:
            extra.append("packet path FINDER-UNVERIFIED")
        if not pfc_ok:
            extra.append("PFC census FINDER-UNVERIFIED")
        if not clearance:
            extra.append("clearance sentence not RETRACTED")
        if claimed_258_as_tree:
            extra.append("258 is not the current sd-wx tree")
        return {
            "state": "NOT_LANDED",
            "note": (
                "card/catalog present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". "
                + "; ".join(extra)
                + ". Ten families must stay RETRACTED. "
                "XYZ + Codex/Grok Build owner required. Talk is CLAIMED. "
                "Z=FINDER-UNVERIFIED. Never 0."
            ),
            "z": "FINDER-UNVERIFIED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "branch-review leftover is on this tree. Ten families RETRACTED, "
            "not UNVERIFIED. Public branches coordinated, not cleaned. "
            "sd-wx measured; kite-help ABSENT_ON_COMMONS. "
            "No deletion/history rewrite. Packet + PFC census preserved. "
            "A Slack ledger is still not the file."
        ),
        "z": "",
    }


def measure_root(root):
    root = os.path.abspath(root)
    card_text = _read(root, DEFAULT_CARD)
    catalog_text = _read(root, DEFAULT_CATALOG)
    catalog = load_catalog(catalog_text) if catalog_text else {}
    packet = catalog.get("packet") if isinstance(catalog.get("packet"), dict) else {}
    pfc = catalog.get("pfc_census") if isinstance(catalog.get("pfc_census"), dict) else {}
    packet_path = str(packet.get("path") or PACKET_PATH).strip() or PACKET_PATH
    pfc_census_path = str(pfc.get("path") or PFC_CENSUS_PATH).strip() or PFC_CENSUS_PATH
    search_space = (
        DEFAULT_CARD,
        DEFAULT_CATALOG,
        os.path.join("host", "branch_review.py"),
        packet_path,
        pfc_census_path,
    )
    misses = []
    search_hits = {}
    for rel in search_space:
        text = _read(root, rel)
        if not text:
            misses.append(rel)
        search_hits[rel] = text
    blob = "\n".join(
        [
            card_text,
            catalog_text,
            search_hits.get(os.path.join("host", "branch_review.py"), ""),
        ]
    ).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = {
        "card_present": bool(card_text) and "branch_review" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "found_phrases": found,
        "families": catalog.get("families") or [],
        "branches": catalog.get("branches") or [],
        "packet_present": bool(search_hits.get(packet_path)),
        "pfc_census_present": bool(search_hits.get(pfc_census_path)),
        "clearance_retracted": str(pfc.get("clearance_sentence") or "").upper()
        == "RETRACTED",
        "retracted_stays_retracted": bool(catalog.get("retracted_stays_retracted")),
        "soften_retracted_to_unverified": bool(
            catalog.get("soften_retracted_to_unverified")
        ),
        "secret_dump": bool(catalog.get("secret_dump")),
        "delete_rewrite": catalog.get("delete_rewrite") or "",
        "remeasurement_owner": catalog.get("remeasurement_owner") or "",
        "allowed_remeasurers": catalog.get("allowed_remeasurers") or [],
        "xyz_required": bool(catalog.get("xyz_required")),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(search_space),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
    }
    row = measure_from_rows(facts)
    row["slack_ts"] = facts["slack_ts"]
    row["catalog"] = DEFAULT_CATALOG
    row["source_id"] = SOURCE_ID
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the DEMON public-branch review leftover"
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
    payload["x"] = list(SEARCH_SPACE) + list(REQUIRED_FAMILIES) + list(REQUIRED_BRANCHES)
    payload["y"] = {
        "found_phrases": row.get("found_phrases") or [],
        "families": row.get("families") or [],
        "branches": row.get("branches") or [],
        "packet_present": row.get("packet_present"),
        "pfc_census_present": row.get("pfc_census_present"),
        "clearance_retracted": row.get("clearance_retracted"),
        "calibration_hits": row.get("calibration_hits") or [],
        "remeasurement_owner": row.get("remeasurement_owner") or "",
    }
    if not payload.get("z"):
        payload["z"] = row.get("misses") or []
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    assert empty["z"] == "FINDER-UNVERIFIED"
    failed_cal = classify(
        {
            "measured": True,
            "calibration_ok": False,
            "calibration_hits": [],
            "card_present": True,
            "catalog_present": True,
        }
    )
    assert failed_cal["state"] == "UNMEASURED"
    assert "Never 0" in failed_cal["note"]
    missing = classify(
        measure_from_rows(
            {
                "card_present": False,
                "catalog_present": False,
                "misses": [DEFAULT_CARD],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED"
    assert missing["z"] == "FINDER-UNVERIFIED"
    return True


if __name__ == "__main__":
    sys.exit(main())
