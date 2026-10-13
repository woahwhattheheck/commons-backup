#!/usr/bin/env python3
"""host/foreign_main.py — a Slack SHIP_RECEIPT is not foreign official main.

Slack 1787642211.512289 (JOJO SHIP_RECEIPT):
id jojo-muhlnickel-subagent-protocol-20260825-01 claimed LocalDeviceAgent
official main fb0b0b2f59f8ca81741371b6ddd8036b164e77e8 plus named blobs.

Independent measure this run:
- GitHub contents/commit sha=main = fb0b0b2f59f8ca81741371b6ddd8036b164e77e8
- host/muhl_subagent_protocol.py blob f4a58a0e5241eff482a58cfadc112914237944f4
- host/test_muhl_subagent_protocol.py blob 0f9f739c4d4e418554890119ab4fddd1a09430b5
- .github/workflows/muhlnickel-subagent-protocol.yml blob 06371d5605562e2f81e54788a20a58a7ddd64120
- docs/MUHL_SUBAGENT_PROTOCOL.md blob ae7a6973b5bdf2d43a56b38694b715ed5a578a03
- Commons p/jojo-muhlnickel-subagent-protocol-20260825-01.md 404
- public git ls-remote LDA 404 (private)
- gh CLI refs/heads/main 404
- Actions run 32820731505 FINDER-UNVERIFIED via public gh
- next substrate (wider published entries) FINDER-UNVERIFIED

A Slack land brag is CARRIER_ONLY on Commons. Foreign official main
with independently matched blobs is FOREIGN_INTEGRATED. The leftover
ships the desk that keeps those two facts apart. Do not remint the
JOJO id. Do not copy private LDA source onto Commons. No host
inference. No titan write. No auth. No gate. Miss is FINDER-FAILED /
FINDER-UNVERIFIED. Never 0.

  python3 host/foreign_main.py
  python3 host/foreign_main.py --root .
  python3 host/foreign_main.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys

if __package__:
    from .carrier_projection import CARRIER_ONLY, DURABLE_ON_MAIN, measure_slack_projection
else:
    from carrier_projection import CARRIER_ONLY, DURABLE_ON_MAIN, measure_slack_projection


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "FOREIGN_MAIN.json")
DEFAULT_CARD = os.path.join("ground", "FOREIGN_MAIN.md")
SLACK_TS = "1787642211.512289"
JOJO_ID = "jojo-muhlnickel-subagent-protocol-20260825-01"
JOJO_RECEIPT_SHA256 = "0b72a2bec00ef74add9b67dd57e623ff70ee5d9a7a3ab424dc9558f035cf8f5f"
FOREIGN_REPO = "woahwhattheheck/LocalDeviceAgent"
CLAIMED_MAIN = "fb0b0b2f59f8ca81741371b6ddd8036b164e77e8"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "foreign_main.py"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "foreign official main",
    "slack ship_receipt",
    "talk is not a land",
    "finder-unverified",
    "finder-failed",
    "never 0",
    "do not remint",
    "no host inference",
    "no auth",
    "no gate",
    "localdeviceagent",
    "muhl_subagent_protocol",
)
DEFAULT_BLOBS = (
    {
        "path": "host/muhl_subagent_protocol.py",
        "claimed": "f4a58a0e5241eff482a58cfadc112914237944f4",
        "measured": "f4a58a0e5241eff482a58cfadc112914237944f4",
    },
    {
        "path": "host/test_muhl_subagent_protocol.py",
        "claimed": "0f9f739c4d4e418554890119ab4fddd1a09430b5",
        "measured": "0f9f739c4d4e418554890119ab4fddd1a09430b5",
    },
    {
        "path": ".github/workflows/muhlnickel-subagent-protocol.yml",
        "claimed": "06371d5605562e2f81e54788a20a58a7ddd64120",
        "measured": "06371d5605562e2f81e54788a20a58a7ddd64120",
    },
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


def receipt_path(source_id):
    name = str(source_id or "").strip()
    if not name:
        return ""
    return os.path.join("p", name + ".md")


def load_blobs(raw):
    blobs = []
    seen = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip().replace("\\", "/")
        claimed = str(item.get("claimed") or item.get("sha") or "").strip().lower()
        measured = str(item.get("measured") or item.get("live") or "").strip().lower()
        if not path or path in seen:
            continue
        seen.add(path)
        blobs.append({"path": path, "claimed": claimed, "measured": measured})
    return blobs


def load_catalog(text):
    """Parse the foreign-main catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    live = data.get("live_measure") if isinstance(data.get("live_measure"), dict) else {}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "source_id": str(data.get("source_id") or data.get("jojo_id") or "").strip() or JOJO_ID,
        "foreign_repo": str(data.get("foreign_repo") or "").strip() or FOREIGN_REPO,
        "claimed_main": str(data.get("claimed_main") or "").strip().lower(),
        "official_main": str(
            live.get("official_main") or data.get("official_main") or ""
        ).strip().lower(),
        "blobs": load_blobs(data.get("blobs") or data.get("claimed_blobs")),
        "actions_run": str(data.get("actions_run") or "").strip(),
        "actions_state": str(
            live.get("actions_state") or data.get("actions_state") or ""
        ).strip().upper(),
        "next_substrate": str(
            live.get("next_substrate") or data.get("next_substrate") or ""
        ).strip().upper(),
        "public_git": str(live.get("public_git") or data.get("public_git") or "").strip().upper(),
        "copied_source": bool(data.get("copied_source")),
        "host_inference": bool(data.get("host_inference")),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip().upper(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "error": "",
    }


def blob_matches(blobs):
    """Y: independently measured blob SHAs that equal the claimed SHAs."""
    claimed = 0
    matched = 0
    unverified = 0
    for item in blobs or []:
        want = str(item.get("claimed") or "").strip().lower()
        got = str(item.get("measured") or "").strip().lower()
        if not want:
            continue
        claimed += 1
        if not got:
            unverified += 1
        elif got == want:
            matched += 1
    return {
        "claimed_count": claimed,
        "matched_count": matched,
        "unverified_count": unverified,
    }


def measure_from_rows(facts):
    """Classify measured leftover facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "receipt_present": bool(facts.get("receipt_present")),
        "receipt_state": str(
            facts.get("receipt_state")
            or (DURABLE_ON_MAIN if facts.get("receipt_present") else CARRIER_ONLY)
        ).strip().upper(),
        "receipt_provenance_ok": bool(facts.get("receipt_provenance_ok")),
        "receipt_provenance_mismatches": list(
            facts.get("receipt_provenance_mismatches") or []
        ),
        "source_id": str(facts.get("source_id") or JOJO_ID),
        "foreign_repo": str(facts.get("foreign_repo") or FOREIGN_REPO),
        "claimed_main": str(facts.get("claimed_main") or "").lower(),
        "official_main": str(facts.get("official_main") or "").lower(),
        "claimed_count": int(facts.get("claimed_count") or 0),
        "matched_count": int(facts.get("matched_count") or 0),
        "unverified_count": int(facts.get("unverified_count") or 0),
        "actions_state": str(facts.get("actions_state") or "FINDER-UNVERIFIED").upper(),
        "next_substrate": str(facts.get("next_substrate") or "FINDER-UNVERIFIED").upper(),
        "public_git": str(facts.get("public_git") or "FINDER-UNVERIFIED").upper(),
        "found_phrases": list(facts.get("found_phrases") or []),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "copied_source": bool(facts.get("copied_source")),
        "host_inference": bool(facts.get("host_inference")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
    }


def classify(row):
    """Turn a measured foreign-main leftover into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "foreign-main leftover not read. Absence was not stillness. "
                "A Slack SHIP_RECEIPT is not official main. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence proof. "
                "FINDER-FAILED. Never 0."
            ),
            "z": "FINDER-FAILED",
        }
    misses = list(row.get("misses") or [])
    if not row.get("card_present") or not row.get("catalog_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog"])
                + ". LocalDeviceAgent / muhl_subagent_protocol / SHIP_RECEIPT talk "
                "is CLAIMED until the leftover ships. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in (row.get("found_phrases") or [])]
    claimed = int(row.get("claimed_count") or 0)
    matched = int(row.get("matched_count") or 0)
    official = str(row.get("official_main") or "")
    want = str(row.get("claimed_main") or "")
    receipt_present = bool(row.get("receipt_present"))
    receipt = str(row.get("receipt_state") or CARRIER_ONLY).strip().upper()
    receipt_ok = (
        receipt == CARRIER_ONLY and not receipt_present
    ) or (
        receipt == DURABLE_ON_MAIN
        and receipt_present
        and bool(row.get("receipt_provenance_ok"))
    )
    if (
        needed
        or not row.get("posting_open")
        or not row.get("no_auth")
        or not row.get("no_gate")
        or row.get("copied_source")
        or row.get("host_inference")
        or claimed < 3
        or matched != claimed
        or not official
        or official != want
        or str(row.get("source_id") or "") != JOJO_ID
        or not receipt_ok
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Need independently matched blobs on official foreign main. "
                "Do not copy private source. Commons receipt must be absent or an "
                "exact Slack carrier projection. Talk is CLAIMED. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "foreign-main leftover is on this tree. Official LocalDeviceAgent main "
            + official
            + " independently matched "
            + str(matched)
            + "/"
            + str(claimed)
            + " claimed blobs. Commons p/"
            + str(row.get("source_id") or JOJO_ID)
            + ".md is "
            + receipt
            + ". A Slack SHIP_RECEIPT is still not the file. Actions run and next "
            "substrate stay FINDER-UNVERIFIED."
        ),
        "z": "",
        "foreign_repo_state": "FOREIGN_INTEGRATED",
        "commons_receipt_state": receipt,
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = []
    search_hits = {}
    for rel in SEARCH_SPACE:
        text = _read(root, rel)
        if not text:
            misses.append(rel)
        search_hits[rel] = text
    card_text = search_hits.get(DEFAULT_CARD, "")
    catalog_text = search_hits.get(DEFAULT_CATALOG, "")
    instrument_text = search_hits.get(os.path.join("host", "foreign_main.py"), "")
    catalog = load_catalog(catalog_text) if catalog_text else {}
    counts = blob_matches(catalog.get("blobs") or [])
    source_id = catalog.get("source_id") or JOJO_ID
    path = receipt_path(JOJO_ID)
    receipt = measure_slack_projection(
        root,
        path,
        post_id=JOJO_ID,
        carrier_ts=SLACK_TS,
        sender="JOJO",
        inner_kind="SHIP_RECEIPT",
        expected_sha256=JOJO_RECEIPT_SHA256,
    )
    blob = "\n".join([card_text, catalog_text, instrument_text]).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = {
        "card_present": bool(card_text) and "foreign official main" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "receipt_present": receipt["present"],
        "receipt_state": receipt["state"],
        "receipt_provenance_ok": receipt["provenance_ok"],
        "receipt_provenance_mismatches": receipt["mismatches"],
        "source_id": source_id,
        "foreign_repo": catalog.get("foreign_repo") or FOREIGN_REPO,
        "claimed_main": catalog.get("claimed_main") or CLAIMED_MAIN,
        "official_main": catalog.get("official_main") or "",
        "claimed_count": counts["claimed_count"],
        "matched_count": counts["matched_count"],
        "unverified_count": counts["unverified_count"],
        "actions_state": catalog.get("actions_state") or "FINDER-UNVERIFIED",
        "next_substrate": catalog.get("next_substrate") or "FINDER-UNVERIFIED",
        "public_git": catalog.get("public_git") or "FINDER-UNVERIFIED",
        "found_phrases": found,
        "posting_open": str(catalog.get("posting") or "") == "OPEN",
        "no_auth": bool(catalog.get("no_auth")),
        "no_gate": bool(catalog.get("no_gate")),
        "copied_source": bool(catalog.get("copied_source")),
        "host_inference": bool(catalog.get("host_inference")),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "receipt_path": path,
        "actions_run": catalog.get("actions_run") or "",
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "receipt_path": path,
            "actions_run": facts["actions_run"],
        }
    )
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure a Slack SHIP_RECEIPT against foreign official main"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
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
    payload["x"] = {
        "foreign_repo": row.get("foreign_repo"),
        "claimed_main": row.get("claimed_main"),
        "search_space": row.get("search_space") or [],
        "receipt_path": row.get("receipt_path") or receipt_path(row.get("source_id")),
    }
    payload["y"] = {
        "official_main": row.get("official_main"),
        "claimed_count": row.get("claimed_count"),
        "matched_count": row.get("matched_count"),
        "unverified_count": row.get("unverified_count"),
        "receipt_present": row.get("receipt_present"),
        "actions_state": row.get("actions_state"),
        "next_substrate": row.get("next_substrate"),
        "public_git": row.get("public_git"),
        "calibration_hits": row.get("calibration_hits") or [],
    }
    if not payload.get("z"):
        payload["z"] = row.get("misses") or []
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict.get("state") == "INTEGRATED" else 1


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    assert empty["z"] == "FINDER-FAILED"
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
    assert "instrument failure" in failed_cal["note"]
    assert "Never 0" in failed_cal["note"]
    missing = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": False,
            "catalog_present": False,
            "misses": [DEFAULT_CARD],
        }
    )
    assert missing["state"] == "NOT_LANDED"
    assert missing["z"] == "FINDER-FAILED"
    counts = blob_matches(list(DEFAULT_BLOBS))
    assert counts["claimed_count"] == 3
    assert counts["matched_count"] == 3
    mismatch = blob_matches(
        [{"path": "host/x.py", "claimed": "aaaa", "measured": "bbbb"}]
    )
    assert mismatch["matched_count"] == 0
    assert mismatch["claimed_count"] == 1
    ok = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "receipt_present": False,
            "source_id": JOJO_ID,
            "found_phrases": list(REQUIRED_PHRASES),
            "posting_open": True,
            "no_auth": True,
            "no_gate": True,
            "copied_source": False,
            "host_inference": False,
            "claimed_count": 3,
            "matched_count": 3,
            "official_main": CLAIMED_MAIN,
            "claimed_main": CLAIMED_MAIN,
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert ok["foreign_repo_state"] == "FOREIGN_INTEGRATED"
    assert ok["commons_receipt_state"] == "CARRIER_ONLY"
    assert "still not the file" in ok["note"]
    parsed = load_catalog(
        json.dumps(
            {
                "source_id": JOJO_ID,
                "claimed_main": CLAIMED_MAIN,
                "blobs": list(DEFAULT_BLOBS),
                "live_measure": {"official_main": CLAIMED_MAIN},
                "posting": "OPEN",
                "no_auth": True,
                "no_gate": True,
            }
        )
    )
    assert parsed["source_id"] == JOJO_ID
    assert parsed["official_main"] == CLAIMED_MAIN
    return True


if __name__ == "__main__":
    sys.exit(main())
