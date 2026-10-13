#!/usr/bin/env python3
"""host/muhl_receipt_lane.py — a Slack TAKING is not a request/receiver/result receipt.

Slack 1787646761.038429 (JOJO TAKING): LocalDeviceAgent Muhlnickel
subagent receipt lane from current main@fb0b0b2f59f8ca81741371b6ddd8036b164e77e8.
This leftover is the request-receiver-result receipt validator.
Proposed receipt source/test/doc paths were unclaimed. Open LDA PR list
was empty. Scope named a source-only request->receiver->result receipt
validator, synthetic bytes/tests, docs/CI. Will-open-PR-and-leave-unmerged
is CLAIMED until this leftover is on current Commons main.

This desk ships the validator on Commons with synthetic fixtures.
Do not copy private LDA source. Do not copy private LocalDeviceAgent
source. It does not invent or truncate the claimed 175-entry tree. Published synthetic chains are
counted exactly. Claimed 175 with a smaller published count is
FINDER-UNVERIFIED, never a silent 0.

No host inference. No Titan/container/device mutation. No pfc_* paths.
No auth/login/allowlist/approval/identity/action tiers. Miss is
FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

  python3 host/muhl_receipt_lane.py
  python3 host/muhl_receipt_lane.py --root .
  python3 host/muhl_receipt_lane.py --self-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "MUHL_RECEIPT_LANE.json")
DEFAULT_CARD = os.path.join("ground", "MUHL_RECEIPT_LANE.md")
SLACK_TS = "1787646761.038429"
CLAIMED_LDA_MAIN = "fb0b0b2f59f8ca81741371b6ddd8036b164e77e8"
REQUEST_SCHEMA = "MUHL_SUBAGENT_REQUEST.v1"
RECEIVER_SCHEMA = "MUHL_SUBAGENT_RECEIVER.v1"
RESULT_SCHEMA = "MUHL_SUBAGENT_RESULT.v1"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "muhl_receipt_lane.py"),
    os.path.join("ground", "FOREIGN_MAIN.md"),
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
    "request-receiver-result",
    "175-entry tree",
    "leave unmerged",
    "talk is not a land",
    "finder-failed",
    "finder-unverified",
    "never 0",
    "do not remint",
    "do not copy private lda source",
    "no host inference",
    "no auth",
    "no gate",
    "subagent receipt lane",
)
AUTH_GATE_KEYS = (
    "auth",
    "login",
    "allowlist",
    "approval",
    "identity_tier",
    "action_tier",
    "permission",
    "seat",
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


def canonical_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(value):
    return hashlib.sha256(value).hexdigest()


def request_hash(packet):
    body = dict(packet or {})
    body.pop("request_sha256", None)
    return sha256_hex(canonical_bytes(body))


def _integer(value, label, minimum=0):
    if isinstance(value, bool):
        return None, "%s must be an integer" % label
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, "%s must be an integer" % label
    if parsed < minimum:
        return None, "%s must be at least %s" % (label, minimum)
    return parsed, ""


def public_range(entry, label):
    if not isinstance(entry, dict):
        return None, ["%s unpublished" % label]
    name = str(entry.get("name") or "").strip()
    offset, offset_err = _integer(entry.get("offset"), label + ".offset")
    length, length_err = _integer(entry.get("len"), label + ".len", minimum=1)
    blocked = []
    if not name:
        blocked.append(label + ".name unpublished")
    if offset_err:
        blocked.append(offset_err)
    if length_err:
        blocked.append(length_err)
    if blocked:
        return None, blocked
    return {"name": name, "offset": offset, "len": length}, []


def ranges_overlap(left, right):
    if not left or not right:
        return False
    l1 = left["offset"] + left["len"]
    r1 = right["offset"] + right["len"]
    return max(left["offset"], right["offset"]) < min(l1, r1)


def _gate_keys(row):
    if not isinstance(row, dict):
        return []
    return [key for key in AUTH_GATE_KEYS if key in row]


def validate_request(packet):
    """Validate a published request packet. Never write or fire anything."""
    if not isinstance(packet, dict):
        return {
            "ok": False,
            "blocked_reasons": ["request unpublished"],
            "z": "FINDER-FAILED",
        }
    blocked = []
    if packet.get("schema") != REQUEST_SCHEMA:
        blocked.append("request schema unpublished")
    task_id = str(packet.get("task_id") or "").strip()
    if not task_id:
        blocked.append("task_id unpublished")
    incoming, in_err = public_range(packet.get("input"), "input")
    blocked.extend(in_err)
    receiver, rec_err = public_range(packet.get("receiver"), "receiver")
    blocked.extend(rec_err)
    result, res_err = public_range(packet.get("result"), "result")
    blocked.extend(res_err)
    if incoming and receiver and ranges_overlap(incoming, receiver):
        blocked.append("declared_ranges_overlap:input:receiver")
    if incoming and result and ranges_overlap(incoming, result):
        blocked.append("declared_ranges_overlap:input:result")
    if receiver and result and ranges_overlap(receiver, result):
        blocked.append("declared_ranges_overlap:receiver:result")
    blocked.extend("gate:%s" % key for key in _gate_keys(packet))
    digest = request_hash(packet)
    claimed = str(packet.get("request_sha256") or "").strip()
    if claimed and claimed != digest:
        blocked.append("request_sha256 mismatch")
    complete = not blocked and bool(packet.get("contract_complete"))
    return {
        "ok": complete,
        "schema": REQUEST_SCHEMA,
        "task_id": task_id,
        "request_sha256": digest,
        "input": incoming,
        "receiver": receiver,
        "result": result,
        "contract_complete": complete,
        "blocked_reasons": sorted(set(blocked)),
        "z": "" if complete else "FINDER-FAILED",
    }


def validate_receiver(receipt, request):
    """Validate a receiver receipt against a request. Source-only."""
    req = validate_request(request)
    if not isinstance(receipt, dict):
        return {
            "ok": False,
            "blocked_reasons": ["receiver receipt unpublished"],
            "z": "FINDER-FAILED",
        }
    blocked = list(req.get("blocked_reasons") or [])
    if receipt.get("schema") != RECEIVER_SCHEMA:
        blocked.append("receiver schema unpublished")
    claimed = str(receipt.get("request_sha256") or "").strip()
    if claimed != req.get("request_sha256"):
        blocked.append("receiver request_sha256 mismatch")
    published, pub_err = public_range(receipt, "receiver")
    blocked.extend(pub_err)
    want = req.get("receiver")
    if published and want:
        if published["name"] != want["name"] or published["offset"] != want["offset"] or published["len"] != want["len"]:
            blocked.append("receiver range mismatch")
    status = str(receipt.get("status") or "").strip().upper()
    if status != "ADDRESSED":
        blocked.append("receiver not ADDRESSED")
    blocked.extend("gate:%s" % key for key in _gate_keys(receipt))
    ok = not blocked
    return {
        "ok": ok,
        "schema": RECEIVER_SCHEMA,
        "request_sha256": req.get("request_sha256"),
        "receiver": published,
        "status": status or "UNPUBLISHED",
        "blocked_reasons": sorted(set(blocked)),
        "z": "" if ok else "FINDER-FAILED",
    }


def validate_result(receipt, request):
    """Validate a result receipt against a request. Source-only."""
    req = validate_request(request)
    if not isinstance(receipt, dict):
        return {
            "ok": False,
            "blocked_reasons": ["result receipt unpublished"],
            "z": "FINDER-FAILED",
        }
    blocked = list(req.get("blocked_reasons") or [])
    if receipt.get("schema") != RESULT_SCHEMA:
        blocked.append("result schema unpublished")
    claimed = str(receipt.get("request_sha256") or "").strip()
    if claimed != req.get("request_sha256"):
        blocked.append("result request_sha256 mismatch")
    published, pub_err = public_range(receipt, "result")
    blocked.extend(pub_err)
    want = req.get("result")
    if published and want:
        if published["name"] != want["name"] or published["offset"] != want["offset"] or published["len"] != want["len"]:
            blocked.append("result range mismatch")
    status = str(receipt.get("status") or "").strip().upper()
    if status != "SURFACED":
        blocked.append("result not SURFACED")
    blocked.extend("gate:%s" % key for key in _gate_keys(receipt))
    ok = not blocked
    return {
        "ok": ok,
        "schema": RESULT_SCHEMA,
        "request_sha256": req.get("request_sha256"),
        "result": published,
        "status": status or "UNPUBLISHED",
        "blocked_reasons": sorted(set(blocked)),
        "z": "" if ok else "FINDER-FAILED",
    }


def validate_chain(request, receiver, result):
    """Close request -> receiver -> result. Never host inference."""
    req = validate_request(request)
    rec = validate_receiver(receiver, request)
    res = validate_result(result, request)
    blocked = []
    for row in (req, rec, res):
        blocked.extend(row.get("blocked_reasons") or [])
    if req.get("host_inference") or rec.get("host_inference") or res.get("host_inference"):
        blocked.append("host inference refused")
    ok = bool(req.get("ok") and rec.get("ok") and res.get("ok") and not blocked)
    return {
        "ok": ok,
        "request": req,
        "receiver": rec,
        "result": res,
        "blocked_reasons": sorted(set(blocked)),
        "z": "" if ok else "FINDER-FAILED",
        "host_inference": False,
    }


def tree_state(claimed_count, published_count, truncated=False):
    """Name a claimed tree without inventing or silently shrinking it."""
    try:
        claimed = int(claimed_count)
    except (TypeError, ValueError):
        claimed = None
    try:
        published = int(published_count)
    except (TypeError, ValueError):
        published = None
    if claimed is None or published is None:
        return {
            "state": "UNMEASURED",
            "claimed_count": claimed_count,
            "published_count": published_count,
            "truncated": bool(truncated),
            "z": "FINDER-FAILED",
            "note": (
                "175-entry tree not measured. Absence was not stillness. "
                "FINDER-FAILED. Never 0."
            ),
        }
    if truncated:
        return {
            "state": "NOT_LANDED",
            "claimed_count": claimed,
            "published_count": published,
            "truncated": True,
            "z": "FINDER-FAILED",
            "note": (
                "175-entry tree was truncated. Do not invent or shrink the "
                "claimed count. FINDER-FAILED. Never 0."
            ),
        }
    if claimed and published == 0:
        return {
            "state": "NOT_LANDED",
            "claimed_count": claimed,
            "published_count": 0,
            "truncated": False,
            "z": "FINDER-FAILED",
            "note": (
                "claimed "
                + str(claimed)
                + "-entry tree published 0. A silent 0 is instrument failure. "
                "FINDER-FAILED. Never 0."
            ),
        }
    if published != claimed:
        return {
            "state": "FINDER-UNVERIFIED",
            "claimed_count": claimed,
            "published_count": published,
            "truncated": False,
            "z": "FINDER-UNVERIFIED",
            "note": (
                "claimed "
                + str(claimed)
                + "-entry tree; published "
                + str(published)
                + " exact synthetic chains. Not truncated. FINDER-UNVERIFIED."
            ),
        }
    return {
        "state": "INTEGRATED",
        "claimed_count": claimed,
        "published_count": published,
        "truncated": False,
        "z": "",
        "note": "published tree matches claimed count exactly.",
    }


def synthetic_request(task_id="synthetic-canary-01"):
    packet = {
        "schema": REQUEST_SCHEMA,
        "task_id": task_id,
        "input": {"name": "fwd_input", "offset": 100, "len": 16},
        "receiver": {"name": "receiver", "offset": 200, "len": 8},
        "result": {"name": "answer", "offset": 300, "len": 8},
        "contract_complete": True,
        "blocked_reasons": [],
    }
    packet["request_sha256"] = request_hash(packet)
    return packet


def synthetic_receiver(request):
    req = validate_request(request)
    rng = req.get("receiver") or {}
    return {
        "schema": RECEIVER_SCHEMA,
        "request_sha256": req.get("request_sha256"),
        "name": rng.get("name"),
        "offset": rng.get("offset"),
        "len": rng.get("len"),
        "status": "ADDRESSED",
    }


def synthetic_result(request):
    req = validate_request(request)
    rng = req.get("result") or {}
    return {
        "schema": RESULT_SCHEMA,
        "request_sha256": req.get("request_sha256"),
        "name": rng.get("name"),
        "offset": rng.get("offset"),
        "len": rng.get("len"),
        "status": "SURFACED",
    }


def load_catalog(text):
    """Parse the receipt-lane catalog. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    live = data.get("live_measure") if isinstance(data.get("live_measure"), dict) else {}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "kind": str(data.get("kind") or "").strip(),
        "claimed_lda_main": str(data.get("claimed_lda_main") or live.get("claimed_lda_main") or "").strip(),
        "claimed_tree": live.get("claimed_tree", data.get("claimed_tree")),
        "published_tree": live.get("published_tree", data.get("published_tree")),
        "truncated": bool(live.get("truncated", data.get("truncated"))),
        "next_substrate": str(live.get("next_substrate") or data.get("next_substrate") or "FINDER-UNVERIFIED").upper(),
        "copied_source": bool(data.get("copied_source")),
        "host_inference": bool(data.get("host_inference")),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "leave_unmerged": bool(data.get("leave_unmerged")),
    }


def measure_from_rows(facts):
    facts = facts or {}
    tree = tree_state(
        facts.get("claimed_tree"),
        facts.get("published_tree"),
        truncated=bool(facts.get("truncated")),
    )
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "chain_ok": bool(facts.get("chain_ok")),
        "claimed_tree": tree.get("claimed_count"),
        "published_tree": tree.get("published_count"),
        "truncated": bool(tree.get("truncated")),
        "tree_state": tree.get("state"),
        "found_phrases": list(facts.get("found_phrases") or []),
        "posting_open": bool(facts.get("posting_open")),
        "no_auth": bool(facts.get("no_auth")),
        "no_gate": bool(facts.get("no_gate")),
        "copied_source": bool(facts.get("copied_source")),
        "host_inference": bool(facts.get("host_inference")),
        "leave_unmerged": bool(facts.get("leave_unmerged")),
        "calibration_ok": bool(facts.get("calibration_ok")),
        "calibration_hits": list(facts.get("calibration_hits") or []),
        "search_space": list(facts.get("search_space") or SEARCH_SPACE),
        "misses": list(facts.get("misses") or []),
        "titan": str(facts.get("titan") or "NOT_WRITTEN"),
        "slack_ts": str(facts.get("slack_ts") or SLACK_TS),
        "claimed_lda_main": str(facts.get("claimed_lda_main") or CLAIMED_LDA_MAIN),
    }


def classify(row):
    """Turn a measured receipt-lane leftover into a desk state."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "receipt-lane leftover not read. Absence was not stillness. "
                "A Slack TAKING / leave-unmerged is not a land. FINDER-FAILED, never 0."
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
                + ". LocalDeviceAgent / subagent receipt lane / leave-unmerged "
                "talk is CLAIMED until the leftover ships. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in (row.get("found_phrases") or [])]
    if (
        needed
        or not row.get("posting_open")
        or not row.get("no_auth")
        or not row.get("no_gate")
        or row.get("copied_source")
        or row.get("host_inference")
        or not row.get("chain_ok")
        or row.get("truncated")
        or not row.get("leave_unmerged")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Need request-receiver-result synthetic chain, untruncated "
                "175-entry tree, leave unmerged named CLAIMED. Do not copy "
                "private LDA source. Talk is CLAIMED. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    tree = str(row.get("tree_state") or "FINDER-UNVERIFIED")
    return {
        "state": "INTEGRATED",
        "note": (
            "receipt-lane leftover is on this tree. Synthetic "
            "request-receiver-result chain validates. Claimed 175-entry tree "
            "published "
            + str(row.get("published_tree"))
            + " exact chains, not truncated ("
            + tree
            + "). A Slack TAKING / leave-unmerged is still not the file."
        ),
        "z": "",
        "tree_state": tree,
        "taking_state": "CLAIMED",
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
    instrument_text = search_hits.get(os.path.join("host", "muhl_receipt_lane.py"), "")
    catalog = load_catalog(catalog_text) if catalog_text else {}
    blob = "\n".join([card_text, catalog_text, instrument_text]).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    request = synthetic_request()
    chain = validate_chain(request, synthetic_receiver(request), synthetic_result(request))
    facts = {
        "card_present": bool(card_text) and "subagent receipt lane" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "chain_ok": bool(chain.get("ok")),
        "claimed_tree": catalog.get("claimed_tree"),
        "published_tree": catalog.get("published_tree"),
        "truncated": bool(catalog.get("truncated")),
        "found_phrases": found,
        "posting_open": str(catalog.get("posting") or "") == "OPEN",
        "no_auth": bool(catalog.get("no_auth")),
        "no_gate": bool(catalog.get("no_gate")),
        "copied_source": bool(catalog.get("copied_source")),
        "host_inference": bool(catalog.get("host_inference")),
        "leave_unmerged": bool(catalog.get("leave_unmerged")),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "claimed_lda_main": catalog.get("claimed_lda_main") or CLAIMED_LDA_MAIN,
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": facts["slack_ts"],
            "chain": chain,
            "next_substrate": catalog.get("next_substrate") or "FINDER-UNVERIFIED",
        }
    )
    return row


def _self_test():
    request = synthetic_request()
    chain = validate_chain(request, synthetic_receiver(request), synthetic_result(request))
    if not chain.get("ok"):
        return False
    missing = validate_receiver(None, request)
    if missing.get("ok"):
        return False
    silent = tree_state(175, 0)
    if silent.get("z") != "FINDER-FAILED":
        return False
    unverified = tree_state(175, 3)
    if unverified.get("state") != "FINDER-UNVERIFIED" or unverified.get("truncated"):
        return False
    empty = classify({})
    return empty.get("state") == "UNMEASURED"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure a Slack TAKING against a request/receiver/result receipt"
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
        "slack_ts": row.get("slack_ts") or SLACK_TS,
        "claimed_lda_main": row.get("claimed_lda_main") or CLAIMED_LDA_MAIN,
        "search_space": row.get("search_space") or [],
        "claimed_tree": row.get("claimed_tree"),
    }
    payload["y"] = {
        "published_tree": row.get("published_tree"),
        "tree_state": row.get("tree_state"),
        "chain_ok": row.get("chain_ok"),
        "truncated": row.get("truncated"),
        "calibration_hits": row.get("calibration_hits") or [],
    }
    if not payload.get("z"):
        payload["z"] = row.get("misses") or []
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if verdict.get("state") == "INTEGRATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
