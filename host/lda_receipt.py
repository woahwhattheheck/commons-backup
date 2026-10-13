#!/usr/bin/env python3
"""host/lda_receipt.py — LDA request-protocol receipt validator.

Slack 1787646655.408039 (JOJO PROFITABILITY_HANDOFF
jojo-model-work-profitability-bridge-20260825-02):

  receipt validator for the landed LDA request protocol

That Slack body is CLAIMED until this leftover measures a receipt
against the public protocol pin. It does not remint the JOJO
profitability id. It does not remint
jojo-muhlnickel-subagent-protocol-20260825-01. It does not copy
private LocalDeviceAgent source. It does not remint FOREIGN_MAIN.
It does not write titan. It does not smash commons.mno. No auth.
No gate. Miss is FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

VALID_RECEIPT means the receipt is well-formed. It is not proof
that a named Commons post exists. Existence is a separate HEAD
measure. A Slack / ntfy body stays CARRIER_ONLY.

  python3 host/lda_receipt.py
  python3 host/lda_receipt.py --root .
  python3 host/lda_receipt.py --self-test
  python3 host/lda_receipt.py --receipt ground/lda_receipt/jojo-taking.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

if __package__:
    from .carrier_projection import (
        CARRIER_ONLY, DURABLE_ON_MAIN, UNVERIFIED_PRESENT, measure_slack_projection,
    )
else:
    from carrier_projection import (
        CARRIER_ONLY, DURABLE_ON_MAIN, UNVERIFIED_PRESENT, measure_slack_projection,
    )


DEFAULT_ROOT = "."
DEFAULT_CARD = os.path.join("ground", "LDA_RECEIPT.md")
DEFAULT_CATALOG = os.path.join("ground", "LDA_RECEIPT.json")
DEFAULT_DOOR = "lda-receipt.html"
FIXTURE_DIR = os.path.join("ground", "lda_receipt")
SLACK_TS = "1787646655.408039"
TAKING_ID = "jojo-model-work-profitability-bridge-20260825-02"
JOJO_PROTOCOL_ID = "jojo-muhlnickel-subagent-protocol-20260825-01"
JOJO_PROTOCOL_SLACK_TS = "1787642211.512289"
JOJO_PROTOCOL_SHA256 = "0b72a2bec00ef74add9b67dd57e623ff70ee5d9a7a3ab424dc9558f035cf8f5f"
PROTOCOL_MAIN = "fb0b0b2f59f8ca81741371b6ddd8036b164e77e8"
FOREIGN_CARD = os.path.join("ground", "FOREIGN_MAIN.md")
FOREIGN_CATALOG = os.path.join("ground", "FOREIGN_MAIN.json")
CALIBRATION_POST = os.path.join(
    "p", "bryce-action-pad-open-door-directive-20260822-01.md"
)
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "lda_receipt.py"),
    DEFAULT_DOOR,
    os.path.join(FIXTURE_DIR, "jojo-taking.json"),
    os.path.join(FIXTURE_DIR, "valid-complete.json"),
    os.path.join(FIXTURE_DIR, "invalid-host-inference.json"),
    os.path.join(FIXTURE_DIR, "invalid-wrong-sha.json"),
    os.path.join(FIXTURE_DIR, "invalid-missing-fields.json"),
    FOREIGN_CARD,
    FOREIGN_CATALOG,
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    CALIBRATION_POST,
)
REQUIRED_PHRASES = (
    "lda request protocol",
    "receipt validator",
    "valid_receipt",
    "carrier_only",
    "talk is not a land",
    "do not remint",
    "no host inference",
    "no auth",
    "no gate",
    "never 0",
    "finder-failed",
    "finder-unverified",
    "foreign_integrated",
    "fb0b0b2f59f8ca81741371b6ddd8036b164e77e8",
)
REQUIRED_FIELDS = (
    "kind",
    "protocol_main",
    "request_id",
    "receiver",
    "result_state",
    "foreign_state",
    "commons_state",
)
VALID_RESULT = (
    "RESULT_PRESENT",
    "RESULT_PENDING",
    "RESULT_ABSENT",
    "FINDER-FAILED",
    "FINDER-UNVERIFIED",
)
VALID_FOREIGN = ("FOREIGN_INTEGRATED", "FINDER-UNVERIFIED", "FINDER-FAILED")
VALID_COMMONS = ("DURABLE_ON_MAIN", "CARRIER_ONLY", "NOT_LANDED")
EXPECTED_FIXTURES = {
    "jojo-taking.json": "CARRIER_ONLY",
    "valid-complete.json": "VALID_RECEIPT",
    "invalid-host-inference.json": "NOT_LANDED",
    "invalid-wrong-sha.json": "NOT_LANDED",
    "invalid-missing-fields.json": "NOT_LANDED",
}


def _read(root, rel):
    path = os.path.join(root, rel)
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _exists(root, rel):
    return os.path.isfile(os.path.join(root, rel))


def load_json(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "not JSON"}
    if not isinstance(data, dict):
        return {"error": "not an object"}
    return data


def load_catalog(text):
    """Parse the leftover catalog. Invalid is measured empty."""
    data = load_json(text)
    if data.get("error"):
        return {"error": data["error"], "fixtures": []}
    fixtures = []
    for item in data.get("fixtures") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        fixtures.append(
            {
                "name": name,
                "expect": str(item.get("expect") or "").strip().upper(),
            }
        )
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "taking_id": str(data.get("taking_id") or "").strip() or TAKING_ID,
        "protocol_main": str(data.get("protocol_main") or "").strip().lower(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper()
        or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip().upper(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "copied_source": bool(data.get("copied_source")),
        "host_inference": bool(data.get("host_inference")),
        "fixtures": fixtures,
        "error": "",
    }


def _blob_mismatch(blobs):
    for item in blobs or []:
        if not isinstance(item, dict):
            continue
        claimed = str(item.get("claimed") or item.get("sha") or "").strip().lower()
        measured = str(item.get("measured") or item.get("live") or "").strip().lower()
        if claimed and measured and claimed != measured:
            return True
    return False


def validate_receipt(obj, root=None):
    """Classify one LDA request-protocol receipt. Never print a silent 0."""
    if not isinstance(obj, dict) or not obj:
        return {
            "state": "UNMEASURED",
            "note": (
                "receipt body not read. Absence was not stillness. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    kind = str(obj.get("kind") or "").strip()
    if kind != "LDA_REQUEST_RECEIPT":
        return {
            "state": "NOT_LANDED",
            "note": (
                "kind is not LDA_REQUEST_RECEIPT. A Slack profitability "
                "handoff is not a receipt. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    missing = [
        field for field in REQUIRED_FIELDS if not str(obj.get(field) or "").strip()
    ]
    if missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing required field(s): "
                + ", ".join(missing)
                + ". FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    protocol = str(obj.get("protocol_main") or "").strip().lower()
    if protocol != PROTOCOL_MAIN:
        return {
            "state": "NOT_LANDED",
            "note": (
                "protocol_main is not the landed LDA pin "
                + PROTOCOL_MAIN
                + ". FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    result_state = str(obj.get("result_state") or "").strip().upper()
    foreign_state = str(obj.get("foreign_state") or "").strip().upper()
    commons_state = str(obj.get("commons_state") or "").strip().upper()
    if result_state not in VALID_RESULT:
        return {
            "state": "NOT_LANDED",
            "note": (
                "result_state "
                + result_state
                + " is not in the public result set. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if foreign_state not in VALID_FOREIGN:
        return {
            "state": "NOT_LANDED",
            "note": (
                "foreign_state "
                + foreign_state
                + " is not in the public foreign set. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if commons_state not in VALID_COMMONS:
        return {
            "state": "NOT_LANDED",
            "note": (
                "commons_state "
                + commons_state
                + " is not in the public Commons set. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if obj.get("host_inference") is True:
        return {
            "state": "NOT_LANDED",
            "note": (
                "host_inference is true. Local-model work stays on the "
                "addressed request/receiver/result path. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if obj.get("copied_source") is True:
        return {
            "state": "NOT_LANDED",
            "note": (
                "copied_source is true. Do not copy private LDA source onto "
                "Commons. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    titan = str(obj.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN"
    if titan != "NOT_WRITTEN":
        return {
            "state": "NOT_LANDED",
            "note": (
                "titan is "
                + titan
                + ". Live Titan stays untouched. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if obj.get("no_auth") is False or obj.get("no_gate") is False:
        return {
            "state": "NOT_LANDED",
            "note": (
                "receipt closed the door. no_auth and no_gate must stay true. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if _blob_mismatch(obj.get("blobs")):
        return {
            "state": "NOT_LANDED",
            "note": (
                "named blob claimed SHA does not equal measured SHA. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    post_id = str(obj.get("commons_post_id") or "").strip()
    if commons_state == "DURABLE_ON_MAIN":
        if not post_id:
            return {
                "state": "NOT_LANDED",
                "note": (
                    "DURABLE_ON_MAIN requires commons_post_id. "
                    "FINDER-FAILED, never 0."
                ),
                "z": "FINDER-FAILED",
            }
        if root is not None:
            rel = os.path.join("p", post_id + ".md")
            if not _exists(root, rel):
                return {
                    "state": "NOT_LANDED",
                    "note": (
                        "receipt claims DURABLE_ON_MAIN but "
                        + rel
                        + " is missing. FINDER-FAILED, never 0."
                    ),
                    "z": "FINDER-FAILED",
                }
        return {
            "state": "VALID_RECEIPT",
            "note": (
                "well-formed LDA request receipt. VALID_RECEIPT is schema, "
                "not a second land of "
                + post_id
                + ". Talk is not a land."
            ),
            "z": "",
        }
    if commons_state == "CARRIER_ONLY":
        return {
            "state": "CARRIER_ONLY",
            "note": (
                "receipt is well-formed and names Commons as CARRIER_ONLY. "
                "Slack / ntfy / SHIP_RECEIPT is mail, not p/{id}.md. "
                "Do not remint "
                + (post_id or JOJO_PROTOCOL_ID)
                + "."
            ),
            "z": "CARRIER_ONLY",
        }
    return {
        "state": "NOT_LANDED",
        "note": (
            "receipt is well-formed and names Commons as NOT_LANDED. "
            "FINDER-FAILED, never 0."
        ),
        "z": "FINDER-FAILED",
    }


def measure_from_rows(facts):
    """Classify measured leftover facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "door_present": bool(facts.get("door_present")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "fixture_hits": list(facts.get("fixture_hits") or []),
        "fixture_misses": list(facts.get("fixture_misses") or []),
        "protocol_main_ok": bool(facts.get("protocol_main_ok")),
        "foreign_present": bool(facts.get("foreign_present")),
        "jojo_protocol_reminted": bool(facts.get("jojo_protocol_reminted")),
        "jojo_protocol_present": bool(facts.get("jojo_protocol_present")),
        "jojo_protocol_state": str(
            facts.get("jojo_protocol_state")
            or (UNVERIFIED_PRESENT if facts.get("jojo_protocol_present") else CARRIER_ONLY)
        ).strip().upper(),
        "jojo_protocol_provenance_ok": bool(
            facts.get("jojo_protocol_provenance_ok")
        ),
        "jojo_protocol_provenance_mismatches": list(
            facts.get("jojo_protocol_provenance_mismatches") or []
        ),
        "copied_source": bool(facts.get("copied_source")),
        "host_inference": bool(facts.get("host_inference")),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
    }


def classify(row):
    """Turn a measured leftover census into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "LDA receipt leftover not read. Absence was not stillness. "
                "A profitability handoff is not a land."
            ),
            "z": "FINDER-FAILED",
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
            "z": "FINDER-FAILED",
        }
    misses = list(row.get("misses") or [])
    if (
        not row.get("card_present")
        or not row.get("catalog_present")
        or not row.get("door_present")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog/door"])
                + ". PROFITABILITY_HANDOFF / LDA request protocol talk is "
                "CLAIMED until the leftover ships. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    protocol_present = bool(row.get("jojo_protocol_present"))
    protocol_state = str(row.get("jojo_protocol_state") or CARRIER_ONLY).strip().upper()
    protocol_ok = (
        protocol_state == CARRIER_ONLY and not protocol_present
    ) or (
        protocol_state == DURABLE_ON_MAIN
        and protocol_present
        and bool(row.get("jojo_protocol_provenance_ok"))
    )
    if row.get("jojo_protocol_reminted") or not protocol_ok:
        return {
            "state": "NOT_LANDED",
            "note": (
                "p/"
                + JOJO_PROTOCOL_ID
                + ".md lacks exact Slack carrier provenance. Do not remint that id. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if not row.get("foreign_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "FOREIGN_MAIN leftover missing. Do not remint it. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if not row.get("protocol_main_ok"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog protocol_main is not "
                + PROTOCOL_MAIN
                + ". FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    fixture_misses = list(row.get("fixture_misses") or [])
    if fixture_misses:
        return {
            "state": "NOT_LANDED",
            "note": (
                "fixture miss(es): "
                + ", ".join(fixture_misses)
                + ". FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("copied_source") or row.get("host_inference"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover claims copied LDA source or host inference. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    needed = [
        phrase
        for phrase in REQUIRED_PHRASES
        if phrase not in (row.get("found_phrases") or [])
    ]
    if needed or not row.get("posting_open") or not row.get("no_auth") or not row.get("no_gate"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Open door + no auth + no gate required. Talk is CLAIMED. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "LDA receipt-validator leftover is on this tree. Fixtures "
            "classify CARRIER_ONLY / VALID_RECEIPT / NOT_LANDED. JOJO "
            "protocol source state is "
            + protocol_state
            + ". FOREIGN_MAIN stays. A Slack profitability handoff without "
            "an exact carrier projection is still not the file."
        ),
        "z": "",
    }


def _measure_fixtures(root):
    hits = []
    misses = []
    for name, expect in EXPECTED_FIXTURES.items():
        rel = os.path.join(FIXTURE_DIR, name)
        data = load_json(_read(root, rel))
        if data.get("error"):
            misses.append(name + "=not JSON")
            continue
        got = validate_receipt(data, root=root)
        if got.get("state") != expect:
            misses.append(name + "=" + str(got.get("state") or "EMPTY"))
        else:
            hits.append(name + "=" + expect)
    return hits, misses


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
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    fixture_hits, fixture_misses = _measure_fixtures(root)
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    if not calibration_ok:
        for rel in CALIBRATION:
            if rel not in calibration_hits and rel not in misses:
                misses.append("calibration:" + rel)
    posting_open = (
        catalog.get("posting") == "OPEN"
        and "open door" in hay
        and "unseated" in hay
    )
    protocol = measure_slack_projection(
        root,
        os.path.join("p", JOJO_PROTOCOL_ID + ".md"),
        post_id=JOJO_PROTOCOL_ID,
        carrier_ts=JOJO_PROTOCOL_SLACK_TS,
        sender="JOJO",
        inner_kind="SHIP_RECEIPT",
        expected_sha256=JOJO_PROTOCOL_SHA256,
    )
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "door_present": _exists(root, DEFAULT_DOOR),
        "found_phrases": found,
        "fixture_hits": fixture_hits,
        "fixture_misses": fixture_misses,
        "protocol_main_ok": catalog.get("protocol_main") == PROTOCOL_MAIN,
        "foreign_present": _exists(root, FOREIGN_CARD) and _exists(root, FOREIGN_CATALOG),
        "jojo_protocol_reminted": protocol["state"] == UNVERIFIED_PRESENT,
        "jojo_protocol_present": protocol["present"],
        "jojo_protocol_state": protocol["state"],
        "jojo_protocol_provenance_ok": protocol["provenance_ok"],
        "jojo_protocol_provenance_mismatches": protocol["mismatches"],
        "copied_source": bool(catalog.get("copied_source")),
        "host_inference": bool(catalog.get("host_inference")),
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
                "fixture_hits": fixture_hits,
                "protocol_main": catalog.get("protocol_main") or "",
            },
            "z": (
                "misses "
                + json.dumps(misses + fixture_misses)
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
                "door_present": False,
                "misses": [DEFAULT_CARD],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    bad_kind = validate_receipt({"kind": "TALK"})
    assert bad_kind["state"] == "NOT_LANDED", bad_kind
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate LDA request-protocol receipts"
    )
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--receipt", default="")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    if args.receipt:
        text = _read(args.root, args.receipt)
        data = load_json(text)
        if data.get("error"):
            print(json.dumps({"state": "UNMEASURED", "note": data["error"]}, indent=2))
            return 1
        verdict = validate_receipt(data, root=args.root)
        print(json.dumps(verdict, indent=2, sort_keys=True))
        return 0 if verdict["state"] in ("VALID_RECEIPT", "CARRIER_ONLY") else 1
    row = measure_root(args.root)
    verdict = classify(row)
    payload = {"verdict": verdict, "row": row}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if verdict["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
