#!/usr/bin/env python3
"""host/supergrok_heavy.py — SuperGrok Heavy leftover.

Slack 1787645797.029719: shared weekly pool; Grok Build is not a
separate bucket; Cursor Grok is not the Heavy substitute.
A mapping sprint is CLAIMED until this leftover names unfinished
builds with source/unresolved/deliverable/non-Grok verifier.

Measured Heavy packets: heavy-dir9-read-mesh and
heavy-dir19-agent-swarm. Build packets stay named so Heavy compute
is not wasted. Utilization receipt required. Open door. Unseated
still posts. Talk is not a land.

Do not remint GROK_HYGIENE, SITTING_REMINT, BUILD_SWEEP_ACT,
SPECTER_FINAL, or CASH_NOW. titan: NOT_WRITTEN. No auth. No gate.
Miss is FINDER-FAILED / FINDER-UNVERIFIED. Never 0.

  python3 host/supergrok_heavy.py
  python3 host/supergrok_heavy.py --root .
  python3 host/supergrok_heavy.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "SUPERGROK_HEAVY.json")
DEFAULT_CARD = os.path.join("ground", "SUPERGROK_HEAVY.md")
SLACK_TS = "1787645797.029719"
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "supergrok_heavy.py"),
    os.path.join("ground", "GROK_HYGIENE.md"),
    os.path.join("ground", "SITTING_REMINT.md"),
    os.path.join("ground", "BUILD_SWEEP_ACT.md"),
    os.path.join("ground", "SPECTER_FINAL.md"),
    os.path.join("ground", "CASH_NOW.md"),
    os.path.join("DIRECTIVES.md"),
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("ground", "GROK_HYGIENE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
ALREADY_LANDED = (
    os.path.join("ground", "GROK_HYGIENE.md"),
    os.path.join("ground", "SITTING_REMINT.md"),
    os.path.join("ground", "BUILD_SWEEP_ACT.md"),
    os.path.join("ground", "SPECTER_FINAL.md"),
    os.path.join("ground", "CASH_NOW.md"),
    os.path.join("ground", "SITTING_PR.md"),
    os.path.join("ground", "DEVICE_QUEUE_CAP.md"),
)
REQUIRED_PHRASES = (
    "supergrok heavy leftover",
    "shared weekly pool",
    "cursor grok is not the heavy substitute",
    "utilization receipt",
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
    "source_paths",
    "source_sha",
    "unresolved",
    "deliverable",
    "verifier",
    "do_not_remint",
)
VALID_LANES = ("heavy", "build", "not_cursor_as_heavy_substitute")
MIN_HEAVY_PACKETS = 2
RECEIPT_FIELDS = (
    "packet_id",
    "lane",
    "measured_head",
    "unresolved",
    "deliverable",
    "verifier",
    "state",
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
    """Parse the SuperGrok Heavy catalog. Invalid is measured empty."""
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
    receipt = data.get("utilization_receipt") or {}
    if not isinstance(receipt, dict):
        receipt = {}
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "pool": str(data.get("pool") or "").strip(),
        "grok_build_separate_bucket": data.get("grok_build_separate_bucket"),
        "cursor_grok_is_not_heavy_substitute": bool(
            data.get("cursor_grok_is_not_heavy_substitute")
        ),
        "revenue_ideation": str(data.get("revenue_ideation") or "").strip(),
        "direct_build": str(data.get("direct_build") or "").strip(),
        "measured_head": str(data.get("measured_head") or "").strip(),
        "packets": packets,
        "already_landed": already,
        "receipt_required": [
            str(item).strip()
            for item in (receipt.get("required") or [])
            if str(item).strip()
        ],
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "error": "",
    }


def classify_sha(cited, head, is_ancestor):
    """HEAD / ANCESTOR / FOREIGN / UNMEASURED. Never invent stillness."""
    cited = str(cited or "").strip().lower()
    head = str(head or "").strip().lower()
    if len(cited) < 7 or len(head) < 7:
        return "UNMEASURED"
    if cited == head or head.startswith(cited) or cited.startswith(head):
        return "HEAD"
    if is_ancestor:
        return "ANCESTOR"
    return "FOREIGN"


def _git(root, *args):
    try:
        out = subprocess.check_output(
            ["git", "-C", root, *args],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return str(out or "").strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def measure_head(root, cited):
    """Measure official HEAD and whether cited SHA is an ancestor."""
    head = _git(root, "rev-parse", "HEAD")
    if not head:
        return {"official_head": "", "is_ancestor": False, "git": "UNMEASURED"}
    is_ancestor = False
    try:
        subprocess.check_call(
            ["git", "-C", root, "merge-base", "--is-ancestor", cited, "HEAD"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        is_ancestor = True
    except (OSError, subprocess.CalledProcessError):
        is_ancestor = False
    return {
        "official_head": head,
        "is_ancestor": is_ancestor,
        "git": "MEASURED",
    }


def packet_errors(root, packets):
    """Return missing fields, bad lanes, and missing source paths."""
    errors = []
    heavy = 0
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
        lane = str(item.get("lane") or "")
        if lane not in VALID_LANES:
            errors.append("packet " + str(item.get("id")) + " bad lane " + lane)
            continue
        if lane == "heavy":
            heavy += 1
        for rel in item.get("source_paths") or []:
            if not _exists(root, rel):
                errors.append(
                    "packet "
                    + str(item.get("id"))
                    + " missing source "
                    + str(rel)
                )
        unresolved = str(item.get("unresolved") or "").strip()
        if unresolved in ("0", "zero", "none", ""):
            errors.append(
                "packet " + str(item.get("id")) + " bare unresolved zero"
            )
        verifier = str(item.get("verifier") or "").lower()
        if "not grok" not in verifier and "not grok heavy" not in verifier:
            errors.append(
                "packet " + str(item.get("id")) + " missing non-Grok verifier"
            )
    if heavy < MIN_HEAVY_PACKETS:
        errors.append(
            "heavy packets "
            + str(heavy)
            + " < "
            + str(MIN_HEAVY_PACKETS)
        )
    return errors


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
                "SuperGrok Heavy leftover not read. Absence was not stillness. "
                "A Slack mapping sprint is not a land."
            ),
        }
    if not row.get("measured"):
        return {
            "state": "UNMEASURED",
            "note": (
                "SuperGrok Heavy leftover not measured. Absence was not "
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
                + ". SuperGrok Heavy / shared-weekly-pool talk is CLAIMED "
                "until the leftover ships. FINDER-FAILED, never 0."
            ),
        }
    relation = str(row.get("sha_relation") or "UNMEASURED")
    if relation == "UNMEASURED":
        return {
            "state": "UNMEASURED",
            "note": (
                "measured_head vs official HEAD was not measured. "
                "Search space: "
                + ", ".join(row.get("search_space") or list(SEARCH_SPACE))
                + ". FINDER-UNVERIFIED, never 0."
            ),
        }
    if relation == "FOREIGN":
        return {
            "state": "NOT_LANDED",
            "note": (
                "measured_head "
                + str(row.get("measured_head") or "")
                + " is not an ancestor of official HEAD "
                + str(row.get("official_head") or "")
                + ". Slack sprint is CLAIMED. FINDER-FAILED, never 0."
            ),
        }
    packet_miss = list(row.get("packet_errors") or [])
    if packet_miss:
        return {
            "state": "NOT_LANDED",
            "note": (
                "Heavy packets incomplete: "
                + "; ".join(packet_miss)
                + ". A generic idea list is not a packet. FINDER-FAILED, "
                "never 0."
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
    pool_ok = str(row.get("pool") or "") == "shared_weekly"
    not_sub = bool(row.get("cursor_grok_is_not_heavy_substitute"))
    revenue_ok = str(row.get("revenue_ideation") or "") == "refused"
    receipt_ok = bool(row.get("receipt_ok"))
    posting_open = bool(row.get("posting_open"))
    no_auth = bool(row.get("no_auth"))
    no_gate = bool(row.get("no_gate"))
    if (
        needed
        or not pool_ok
        or not not_sub
        or not revenue_ok
        or not receipt_ok
        or not posting_open
        or not no_auth
        or not no_gate
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "leftover present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Shared weekly pool + Cursor-is-not-Heavy + refused "
                "revenue ideation + utilization receipt + open door + no "
                "auth + no gate required. Talk is CLAIMED. FINDER-FAILED, "
                "never 0."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "SuperGrok Heavy leftover is on this tree. Shared weekly pool "
            "is named. Heavy packets cite unfinished builds. Cursor Grok "
            "is not the Heavy substitute. A Slack sprint is still not "
            "the file."
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
    cited = str(catalog.get("measured_head") or "")
    head_row = measure_head(root, cited)
    relation = classify_sha(
        cited,
        head_row.get("official_head") or "",
        bool(head_row.get("is_ancestor")),
    )
    if head_row.get("git") != "MEASURED":
        relation = "UNMEASURED"
    packet_errs = packet_errors(root, catalog.get("packets") or [])
    receipt_ok = all(
        field in (catalog.get("receipt_required") or [])
        for field in RECEIPT_FIELDS
    )
    posting_open = (
        catalog.get("posting") == "OPEN"
        and "open door" in hay
        and "unseated" in hay
    )
    facts = {
        "card_present": _exists(root, DEFAULT_CARD),
        "catalog_present": _exists(root, DEFAULT_CATALOG)
        and not catalog.get("error"),
        "measured_head": cited,
        "official_head": head_row.get("official_head") or "",
        "sha_relation": relation,
        "packet_errors": packet_errs,
        "packet_count": len(catalog.get("packets") or []),
        "heavy_count": sum(
            1
            for item in (catalog.get("packets") or [])
            if str(item.get("lane") or "") == "heavy"
        ),
        "pool": catalog.get("pool") or "",
        "cursor_grok_is_not_heavy_substitute": bool(
            catalog.get("cursor_grok_is_not_heavy_substitute")
        ),
        "revenue_ideation": catalog.get("revenue_ideation") or "",
        "receipt_ok": receipt_ok,
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
                "sha_relation": relation,
                "official_head": facts["official_head"],
                "measured_head": cited,
                "heavy_count": facts["heavy_count"],
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
                "misses": ["ground/SUPERGROK_HEAVY.md"],
                "calibration_ok": True,
            }
        )
    )
    assert missing["state"] == "NOT_LANDED", missing
    foreign = classify(
        measure_from_rows(
            {
                "card_present": True,
                "catalog_present": True,
                "sha_relation": "FOREIGN",
                "measured_head": "deadbeefdeadbeef",
                "official_head": "cafebabecafebabe",
                "packet_errors": [],
                "landed_present": list(ALREADY_LANDED),
                "landed_missing": [],
                "found_phrases": list(REQUIRED_PHRASES),
                "pool": "shared_weekly",
                "cursor_grok_is_not_heavy_substitute": True,
                "revenue_ideation": "refused",
                "receipt_ok": True,
                "posting_open": True,
                "no_auth": True,
                "no_gate": True,
                "calibration_ok": True,
            }
        )
    )
    assert foreign["state"] == "NOT_LANDED", foreign
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure SuperGrok Heavy leftover")
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
