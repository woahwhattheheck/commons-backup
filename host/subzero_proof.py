#!/usr/bin/env python3
"""host/subzero_proof.py — Subzero Explorer v2 proof-classification.

Slack 1787648254.904309 (JOJO SHIP JOJO): next slot is Subzero
Explorer v2 proof-classification hardening on fresh current main.

v1 Artifact Explorer leftover is already on main. Do not remint
rivet-ship-subzero-explorer-20260825-01, SUBZERO_EXPLORER,
SUBZERO_TECH, or SUBZERO_BUYERS. This leftover classifies each
proof claim. Hash-match stays STRUCTURAL_ONLY. It cannot promote
to RUNTIME_MEASURED, CROSS_PROCESS, or CUSTOMER_READY. Missing
bindings are UNRESOLVED, never 0. Titan status is recorded and
does not decide this leftover. Grok Heavy audits stay
CANDIDATE_PENDING_NON_GROK_SYNTHESIS. This leftover does not
synthesize them.

Open door. No auth. No gate. titan NOT_WRITTEN.
Talk is not a land. FINDER-FAILED / FINDER-UNVERIFIED, never 0.

  python3 host/subzero_proof.py
  python3 host/subzero_proof.py --root .
  python3 host/subzero_proof.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "SUBZERO_PROOF.json")
DEFAULT_CARD = os.path.join("ground", "SUBZERO_PROOF.md")
DEFAULT_DOOR = "subzero-proof.html"
V1_CATALOG = os.path.join("ground", "SUBZERO_EXPLORER.json")
V1_CARD = os.path.join("ground", "SUBZERO_EXPLORER.md")
V1_INSTRUMENT = os.path.join("host", "subzero_explorer.py")
V1_RECEIPT = os.path.join("p", "rivet-ship-subzero-explorer-20260825-01.md")
SLACK_TS = "1787648254.904309"
JOB = "subzero-explorer-v2-proof-classification"
STEP = "classify-public-excerpts"
ORDER = 1
V1_PIN = "dd8da6c23497fe9f05cccd1c604b0a78a89c5ae3"
RUNNER = "host/subzero_proof.py"
HEAVY_STATE = "CANDIDATE_PENDING_NON_GROK_SYNTHESIS"
EXPECTED_EXCERPTS = 31
PROOF_CLASSES = (
    "STRUCTURAL_ONLY",
    "RUNTIME_MEASURED",
    "CROSS_PROCESS",
    "CUSTOMER_READY",
    "UNRESOLVED",
    "CLAIMED",
    "FINDER-FAILED",
    "FINDER-UNVERIFIED",
)
REQUIRED_BINDINGS = ("job", "step", "order", "sha", "runner", "receipt")
REFUSED_PROMOTIONS = ("RUNTIME_MEASURED", "CROSS_PROCESS", "CUSTOMER_READY")
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "subzero_proof.py"),
    DEFAULT_DOOR,
    V1_CATALOG,
    V1_CARD,
    V1_INSTRUMENT,
    V1_RECEIPT,
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "HEAD.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    V1_CARD,
    V1_CATALOG,
    V1_INSTRUMENT,
    V1_RECEIPT,
    os.path.join("ground", "SUBZERO_TECH.md"),
    os.path.join("ground", "SUBZERO_BUYERS.md"),
)
REQUIRED_PHRASES = (
    "subzero explorer v2",
    "proof-classification",
    "structural_only",
    "unresolved",
    "never 0",
    "finder-failed",
    "finder-unverified",
    "open door",
    "no auth",
    "no gate",
    "talk is not a land",
    "do not remint",
    "1787648254.904309",
    "candidate_pending_non_grok_synthesis",
    "titan status does not decide",
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


def _load_json(text):
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "not JSON"}
    if not isinstance(data, dict):
        return {"error": "not an object"}
    return data


def strict_bool(data, key):
    """JSON boolean must be an actual bool. Missing is UNRESOLVED, never 0."""
    if not isinstance(data, dict) or key not in data:
        return "UNRESOLVED"
    value = data[key]
    if not isinstance(value, bool):
        return "NOT_BOOL"
    return value


def count_or_unresolved(rows, present):
    """A missing or empty search is UNRESOLVED. Never print 0 as an answer."""
    if not present:
        return "UNRESOLVED"
    count = len(list(rows or []))
    if count == 0:
        return "UNRESOLVED"
    return count


def load_catalog(text):
    """Parse the v2 proof catalog. Invalid is measured empty."""
    data = _load_json(text)
    if data.get("error"):
        return {"error": data["error"], "rows": []}
    binding = {
        "job": str(data.get("job") or "").strip(),
        "step": str(data.get("step") or "").strip(),
        "order": data.get("order"),
        "sha": str(data.get("sha") or "").strip().lower(),
        "runner": str(data.get("runner") or "").strip(),
        "receipt": str(data.get("receipt") or "").strip(),
    }
    if binding["order"] is not None and not isinstance(binding["order"], int):
        try:
            binding["order"] = int(binding["order"])
        except (TypeError, ValueError):
            binding["order"] = None
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip() or SLACK_TS,
        "job": binding["job"] or JOB,
        "step": binding["step"] or STEP,
        "order": binding["order"] if binding["order"] is not None else ORDER,
        "sha": binding["sha"] or V1_PIN,
        "runner": binding["runner"] or RUNNER,
        "receipt": binding["receipt"],
        "label": str(data.get("label") or "").strip().upper(),
        "heavy_audits": str(data.get("heavy_audits") or "").strip().upper(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip().upper() or "NOT_WRITTEN",
        "titan_in_verdict": strict_bool(data, "titan_in_verdict"),
        "no_auth": strict_bool(data, "no_auth"),
        "no_gate": strict_bool(data, "no_gate"),
        "posting_open": strict_bool(data, "posting_open"),
        "runtime_measured": strict_bool(data, "runtime_measured"),
        "copy_private_lda": strict_bool(data, "copy_private_lda"),
        "refused_promotions": [
            str(item or "").strip().upper()
            for item in (data.get("refused_promotions") or [])
            if str(item or "").strip()
        ],
        "binding": binding,
        "error": "",
    }


def classify_claim(claim):
    """Classify one proof claim. Unbound is UNRESOLVED, never 0."""
    claim = dict(claim or {})
    if not claim:
        return {
            "state": "UNRESOLVED",
            "note": "empty claim. Absence was not stillness. UNRESOLVED, never 0.",
        }
    missing = []
    for key in REQUIRED_BINDINGS:
        value = claim.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(key)
    if missing:
        return {
            "state": "UNRESOLVED",
            "note": "missing bindings: " + ",".join(missing) + ". UNRESOLVED, never 0.",
            "missing_bindings": missing,
        }
    claimed = str(claim.get("class") or claim.get("label") or "").strip().upper()
    if not claimed:
        return {
            "state": "UNRESOLVED",
            "note": "no proof class. UNRESOLVED, never 0.",
        }
    if claimed not in PROOF_CLASSES:
        return {
            "state": "UNRESOLVED",
            "note": "unknown proof class %s. UNRESOLVED, never 0." % claimed,
        }
    measured = str(claim.get("measured_class") or "STRUCTURAL_ONLY").strip().upper()
    if claimed in REFUSED_PROMOTIONS and measured == "STRUCTURAL_ONLY":
        return {
            "state": "NOT_LANDED",
            "note": (
                "refused promotion %s -> %s. Hash-match stays STRUCTURAL_ONLY. "
                "FINDER-FAILED, never 0." % (measured, claimed)
            ),
        }
    if claimed in REFUSED_PROMOTIONS and not claim.get("runtime_receipt"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "%s requires a runtime/device receipt this leftover does not have. "
                "FINDER-FAILED, never 0." % claimed
            ),
        }
    if claimed == "STRUCTURAL_ONLY":
        if "hash_match" not in claim:
            return {
                "state": "UNRESOLVED",
                "note": "hash_match missing. UNRESOLVED, never 0.",
            }
        if claim.get("hash_match") is not True:
            return {
                "state": "NOT_LANDED",
                "note": "STRUCTURAL_ONLY without hash-match. FINDER-FAILED, never 0.",
            }
        return {
            "state": "STRUCTURAL_ONLY",
            "note": "hash-match + header parse. Not runtime. Not customer-ready.",
            "bindings": {key: claim.get(key) for key in REQUIRED_BINDINGS},
        }
    return {"state": claimed, "note": "classified " + claimed}


def claims_from_v1(v1_text, binding):
    """Turn v1 catalog rows into bound proof claims."""
    data = _load_json(v1_text)
    rows = data.get("rows") if isinstance(data, dict) else []
    claims = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        claim = {
            "name": name,
            "class": str(item.get("label") or "STRUCTURAL_ONLY").strip().upper(),
            "measured_class": "STRUCTURAL_ONLY",
            "hash_match": bool(item.get("hash_match")),
            "runtime_measured": bool(item.get("runtime_measured")),
        }
        claim.update(binding)
        claims.append(claim)
    return claims


def measure_from_rows(facts):
    """Fold pre-measured rows. Missing keys stay unknown, never 0."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "door_present": bool(facts.get("door_present")),
        "v1_present": bool(facts.get("v1_present")),
        "landed_present": list(facts.get("landed_present") or []),
        "landed_missing": list(facts.get("landed_missing") or []),
        "found_phrases": list(facts.get("found_phrases") or []),
        "excerpt_count": facts.get("excerpt_count", "UNRESOLVED"),
        "structural_count": facts.get("structural_count", "UNRESOLVED"),
        "unresolved_claims": list(facts.get("unresolved_claims") or []),
        "promoted": bool(facts.get("promoted")),
        "bools_ok": bool(facts.get("bools_ok")),
        "bindings_ok": bool(facts.get("bindings_ok")),
        "heavy_audits": str(facts.get("heavy_audits") or ""),
        "titan_in_verdict": facts.get("titan_in_verdict"),
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
    """Turn a measured proof census into a desk state. Titan does not decide."""
    row = row or {}
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "Subzero Explorer v2 leftover not read. Absence was not stillness. "
                "A Slack assignment is not a land."
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
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    misses = list(row.get("misses") or [])
    landed_missing = list(row.get("landed_missing") or [])
    unresolved = list(row.get("unresolved_claims") or [])
    if not row.get("card_present") or not row.get("catalog_present") or not row.get("door_present"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog/door"])
                + ". JOJO v2 assignment / proof-classification talk is CLAIMED "
                "until the leftover ships. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if not row.get("v1_present") or landed_missing:
        return {
            "state": "NOT_LANDED",
            "note": (
                "named already-landed leftover(s) missing: "
                + ", ".join(landed_missing or ["v1 explorer"])
                + ". Do not remint SUBZERO_EXPLORER. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("promoted"):
        return {
            "state": "NOT_LANDED",
            "note": (
                "catalog sold RUNTIME_MEASURED, CROSS_PROCESS, or CUSTOMER_READY "
                "from a STRUCTURAL_ONLY hash-match. That is not this leftover. "
                "FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("heavy_audits") != HEAVY_STATE:
        return {
            "state": "NOT_LANDED",
            "note": (
                "Grok Heavy audits must stay "
                + HEAVY_STATE
                + ". This leftover does not synthesize them. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if row.get("titan_in_verdict") is True:
        return {
            "state": "NOT_LANDED",
            "note": (
                "titan status must not decide this leftover. "
                "titan_in_verdict must be JSON false. FINDER-FAILED, never 0."
            ),
            "z": "FINDER-FAILED",
        }
    if (
        row.get("excerpt_count") != EXPECTED_EXCERPTS
        or row.get("structural_count") != EXPECTED_EXCERPTS
        or unresolved
        or not row.get("bools_ok")
        or not row.get("bindings_ok")
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "proof packet incomplete: excerpts %s, STRUCTURAL_ONLY %s, "
                "unresolved %s. FINDER-FAILED, never 0."
                % (
                    row.get("excerpt_count"),
                    row.get("structural_count"),
                    unresolved or "none",
                )
            ),
            "z": "FINDER-FAILED",
        }
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in (row.get("found_phrases") or [])]
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
            "Subzero Explorer v2 proof-classification leftover is on this tree. "
            "31/31 public excerpt claims stay STRUCTURAL_ONLY. Promotions refused. "
            "Grok Heavy audits stay candidate evidence. Titan status does not decide. "
            "A Slack assignment is still not the file."
        ),
        "z": "FINDER-FAILED",
    }


def measure_root(root):
    root = os.path.abspath(root)
    misses = [rel for rel in SEARCH_SPACE if not _exists(root, rel)]
    hay = "\n".join(_read(root, rel) for rel in SEARCH_SPACE if _exists(root, rel)).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in hay]
    landed_present = [rel for rel in ALREADY_LANDED if _exists(root, rel)]
    landed_missing = [rel for rel in ALREADY_LANDED if not _exists(root, rel)]
    catalog = load_catalog(_read(root, DEFAULT_CATALOG))
    binding = {
        "job": catalog.get("job") or JOB,
        "step": catalog.get("step") or STEP,
        "order": catalog.get("order") if catalog.get("order") is not None else ORDER,
        "sha": catalog.get("sha") or V1_PIN,
        "runner": catalog.get("runner") or RUNNER,
        "receipt": catalog.get("receipt") or "",
    }
    claims = claims_from_v1(_read(root, V1_CATALOG), binding)
    classified = [classify_claim(claim) for claim in claims]
    unresolved = [
        str(claim.get("name") or verdict.get("note") or "unnamed")
        for claim, verdict in zip(claims, classified)
        if verdict.get("state") == "UNRESOLVED"
    ]
    promoted = any(
        verdict.get("state") == "NOT_LANDED" and "refused promotion" in str(verdict.get("note") or "")
        for verdict in classified
    ) or catalog.get("label") in REFUSED_PROMOTIONS or catalog.get("runtime_measured") is True
    structural = [
        verdict for verdict in classified if verdict.get("state") == "STRUCTURAL_ONLY"
    ]
    bools_ok = (
        catalog.get("no_auth") is True
        and catalog.get("no_gate") is True
        and catalog.get("posting_open") is True
        and catalog.get("runtime_measured") is False
        and catalog.get("copy_private_lda") is False
        and catalog.get("titan_in_verdict") is False
        and set(catalog.get("refused_promotions") or []) >= set(REFUSED_PROMOTIONS)
    )
    bindings_ok = all(
        binding.get(key) not in (None, "") for key in REQUIRED_BINDINGS
    ) and str(binding.get("sha") or "").lower() == V1_PIN
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    calibration_ok = len(calibration_hits) == len(CALIBRATION)
    if not calibration_ok:
        for rel in CALIBRATION:
            if rel not in calibration_hits and rel not in misses:
                misses.append("calibration:" + rel)
    v1_present = all(_exists(root, rel) for rel in (V1_CARD, V1_CATALOG, V1_INSTRUMENT, V1_RECEIPT))
    posting_open = (
        catalog.get("posting_open") is True
        and "open door" in hay
        and "unseated" in hay
    )
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG) and not catalog.get("error"),
        "door_present": _exists(root, DEFAULT_DOOR),
        "v1_present": v1_present,
        "landed_present": landed_present,
        "landed_missing": landed_missing,
        "found_phrases": found,
        "excerpt_count": count_or_unresolved(claims, bool(claims) or v1_present),
        "structural_count": count_or_unresolved(structural, bool(structural)),
        "unresolved_claims": unresolved,
        "promoted": promoted,
        "bools_ok": bools_ok,
        "bindings_ok": bindings_ok,
        "heavy_audits": catalog.get("heavy_audits") or "",
        "titan_in_verdict": catalog.get("titan_in_verdict"),
        "posting_open": posting_open,
        "no_auth": catalog.get("no_auth") is True and "no auth" in hay,
        "no_gate": catalog.get("no_gate") is True and "no gate" in hay,
        "calibration_ok": calibration_ok,
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
    }
    row = measure_from_rows(facts)
    row.update(
        {
            "slack_ts": catalog.get("slack_ts") or SLACK_TS,
            "binding": binding,
            "classified": classified,
            "x": [rel for rel in SEARCH_SPACE if _exists(root, rel)],
            "y": {
                "calibration_hits": calibration_hits,
                "found_phrases": found,
                "excerpt_count": row.get("excerpt_count"),
                "structural_count": row.get("structural_count"),
            },
            "z": "FINDER-FAILED never 0 / unresolved " + json.dumps(unresolved or ["none"]),
        }
    )
    return row


def self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED", empty
    unbound = classify_claim({"class": "STRUCTURAL_ONLY", "hash_match": True})
    assert unbound["state"] == "UNRESOLVED", unbound
    sold = classify_claim(
        {
            "class": "RUNTIME_MEASURED",
            "measured_class": "STRUCTURAL_ONLY",
            "hash_match": True,
            "job": JOB,
            "step": STEP,
            "order": ORDER,
            "sha": V1_PIN,
            "runner": RUNNER,
            "receipt": "pending-this-leftover",
        }
    )
    assert sold["state"] == "NOT_LANDED", sold
    assert "refused promotion" in sold["note"], sold
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure Subzero Explorer v2 proof-classification")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    row = measure_root(args.root)
    verdict = classify(row)
    print(json.dumps({"verdict": verdict, "row": row}, indent=2, sort_keys=True))
    return 0 if verdict["state"] == "INTEGRATED" else 1


if __name__ == "__main__":
    sys.exit(main())
