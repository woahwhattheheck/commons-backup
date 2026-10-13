#!/usr/bin/env python3
"""host/claude_compute.py — Slack paid-compute farm is not a land.

Slack 1787640367.070179 (DEMON OWNER CLARIFICATION): Claude is
isolated untrusted build compute. Talk that restates compiler-farm
/ paid-compute / CLAUDE_INTERMEDIATE_UNTRUSTED is CLAIMED until this
leftover measures the farm, the packet schema, named non-Claude
adjudicator in advance, token-use, and open door.

This leftover does not lock posting. It does not add a gate. It
does not remint CLAUDE_ROLE or CLAUDE_TESTER. DIO/JOJO keep their
named-builder lanes. A quarantine packet is CANDIDATE, never
canonical.

  python3 host/claude_compute.py
  python3 host/claude_compute.py --root .
  python3 host/claude_compute.py --self-test

X = exact files in SEARCH_SPACE
Y = phrases / packet fields found in those bytes
Z = missing file / missing phrase / failed calibration
Calibration = known-present EXECUTE.md + owner Action Pad directive
must be found in the same run or the measure is UNMEASURED.
"""
from __future__ import annotations

import argparse
import json
import os
import sys


DEFAULT_ROOT = "."
DEFAULT_CATALOG = os.path.join("ground", "CLAUDE_COMPUTE.json")
DEFAULT_CARD = os.path.join("ground", "CLAUDE_COMPUTE.md")
DEFAULT_QUARANTINE = os.path.join("claude_compute", "README.md")
DEFAULT_PACKET = os.path.join("claude_compute", "PACKET.example.json")
SLACK_TS = "1787640367.070179"
SUPERSEDES_BREADTH = "1787640259.137569"
ROLE = "ISOLATED_UNTRUSTED_BUILD_COMPUTE"
LABEL = "CLAUDE_INTERMEDIATE_UNTRUSTED"
TOKEN_USE = (
    "Use Opus 5 for bulk drafting. Never spend Claude tokens deciding "
    "whether its own output is correct."
)
SEARCH_SPACE = (
    DEFAULT_CARD,
    DEFAULT_CATALOG,
    os.path.join("host", "claude_compute.py"),
    DEFAULT_QUARANTINE,
    DEFAULT_PACKET,
)
CALIBRATION = (
    os.path.join("ground", "EXECUTE.md"),
    os.path.join("p", "bryce-action-pad-open-door-directive-20260822-01.md"),
)
REQUIRED_PHRASES = (
    "isolated untrusted",
    "compiler farm",
    "claude_intermediate_untrusted",
    "paid compute",
    "opus 5",
    "adjudicator in advance",
    "named non-claude adjudicator",
    "claude may not self-adjudicate",
    "never spend claude tokens deciding",
    "bulk drafting",
    "open door",
    "no auth",
    "no gate",
    "candidate",
    "scoped work receipts and raw artifact pointers",
    "may not post conclusions",
    "no rehabilitation quota",
)
PACKET_FIELDS = (
    "spec",
    "input_corpus",
    "claimed_paths",
    "acceptance_criteria",
    "output_directory",
    "adjudicator",
)
CLAUDE_ADJUDICATOR = (
    "claude",
    "gauge",
    "anthropic",
    "fable",
    "sonnet",
    "haiku",
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
    """Parse the Claude-compute catalog. Empty or invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "{}")
    except ValueError:
        return {"error": "catalog is not JSON"}
    if not isinstance(data, dict):
        return {"error": "catalog is not an object"}
    token_use = data.get("token_use") or {}
    if not isinstance(token_use, dict):
        token_use = {}
    required = []
    for item in data.get("packet_required") or []:
        name = str(item or "").strip()
        if name:
            required.append(name)
    return {
        "slack_ts": str(data.get("slack_ts") or "").strip(),
        "supersedes_breadth": str(data.get("supersedes_breadth") or "").strip(),
        "role": str(data.get("role") or "").strip(),
        "label": str(data.get("label") or "").strip(),
        "quarantine": str(data.get("quarantine") or "").strip(),
        "titan": str(data.get("titan") or "NOT_WRITTEN").strip() or "NOT_WRITTEN",
        "posting": str(data.get("posting") or "").strip(),
        "no_auth": bool(data.get("no_auth", True)),
        "no_gate": bool(data.get("no_gate", True)),
        "authority": str(data.get("authority") or "").strip(),
        "paid_compute": str(data.get("paid_compute") or "").strip(),
        "adjudicator_in_advance": bool(data.get("adjudicator_in_advance", False)),
        "non_claude_packet_required": bool(
            data.get("non_claude_packet_required", False)
        ),
        "staging_required": bool(data.get("staging_required", False)),
        "receipts_and_pointers_only": bool(
            data.get("scoped_receipts_and_raw_pointers_only", False)
        ),
        "no_shared_context_conclusions": (
            data.get("shared_context_conclusions_from_claude") is False
        ),
        "claude_self_adjudicate": bool(data.get("claude_self_adjudicate", True)),
        "canonical_from_claude": bool(data.get("canonical_from_claude", True)),
        "public_push_from_claude": bool(data.get("public_push_from_claude", True)),
        "opus5_bulk_drafting": bool(token_use.get("opus5_bulk_drafting", False)),
        "claude_decides_correctness": bool(
            token_use.get("claude_decides_correctness", True)
        ),
        "non_claude_verifier_does_bulk_drafting": bool(
            token_use.get("non_claude_verifier_does_bulk_drafting", True)
        ),
        "packet_required": required,
        "error": "",
    }


def packet_ok(data):
    """A quarantine packet is CANDIDATE only when fields and label hold."""
    if not isinstance(data, dict):
        return False, "packet is not an object"
    label = str(data.get("label") or "").strip()
    if label != "CLAUDE_INTERMEDIATE_UNTRUSTED":
        return False, "missing CLAUDE_INTERMEDIATE_UNTRUSTED"
    missing = [field for field in PACKET_FIELDS if not data.get(field)]
    if missing:
        return False, "missing fields: " + ", ".join(missing)
    if data.get("adjudicator_named_in_advance") is not True:
        return False, "non-Claude adjudicator must be named in advance"
    family = str(data.get("adjudicator_family") or data.get("adjudicator") or "")
    family = family.strip().lower()
    if "non-claude" not in family:
        tokens = [
            part
            for part in family.replace("/", " ").replace("-", " ").split()
            if part
        ]
        for banned in CLAUDE_ADJUDICATOR:
            if banned == family or banned in tokens:
                return False, "Claude may not self-adjudicate"
        return False, "adjudicator family must be explicitly non-Claude"
    if data.get("canonical") is True:
        return False, "quarantine packet is not canonical"
    if data.get("public_push") is True:
        return False, "Claude may not public-push"
    output_directory = str(data.get("output_directory") or "").replace("\\", "/")
    if not output_directory.startswith("claude_compute/staging/"):
        return False, "output directory must be quarantine/staging"
    return True, "CANDIDATE"


def measure_from_rows(facts):
    """Classify measured file/phrase facts. Missing calibration is UNMEASURED."""
    facts = facts or {}
    return {
        "measured": True,
        "card_present": bool(facts.get("card_present")),
        "catalog_present": bool(facts.get("catalog_present")),
        "quarantine_present": bool(facts.get("quarantine_present")),
        "packet_present": bool(facts.get("packet_present")),
        "found_phrases": list(facts.get("found_phrases") or []),
        "packet_fields": list(facts.get("packet_fields") or []),
        "posting_open": bool(facts.get("posting_open")),
        "adjudicator_in_advance": bool(facts.get("adjudicator_in_advance")),
        "non_claude_packet_required": bool(
            facts.get("non_claude_packet_required")
        ),
        "staging_required": bool(facts.get("staging_required")),
        "receipts_and_pointers_only": bool(
            facts.get("receipts_and_pointers_only")
        ),
        "no_shared_context_conclusions": bool(
            facts.get("no_shared_context_conclusions")
        ),
        "no_self_adjudicate": bool(facts.get("no_self_adjudicate")),
        "opus5_bulk": bool(facts.get("opus5_bulk")),
        "claude_does_not_decide": bool(facts.get("claude_does_not_decide")),
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
                "Claude-compute leftover not read. Absence was not stillness. "
                "A Slack paid-compute clarification is not the file."
            ),
        }
    if row.get("calibration_ok") is False:
        return {
            "state": "UNMEASURED",
            "note": (
                "known-present calibration failed: "
                + ", ".join(row.get("calibration_hits") or [])
                + ". Search-zero testing is instrument failure, not absence proof."
            ),
        }
    misses = list(row.get("misses") or [])
    card = bool(row.get("card_present"))
    catalog = bool(row.get("catalog_present"))
    quarantine = bool(row.get("quarantine_present"))
    packet = bool(row.get("packet_present"))
    phrases = list(row.get("found_phrases") or [])
    fields = list(row.get("packet_fields") or [])
    posting_open = bool(row.get("posting_open"))
    named = bool(row.get("adjudicator_in_advance"))
    packet_required = bool(row.get("non_claude_packet_required"))
    staging_required = bool(row.get("staging_required"))
    receipts_only = bool(row.get("receipts_and_pointers_only"))
    no_conclusions = bool(row.get("no_shared_context_conclusions"))
    no_self = bool(row.get("no_self_adjudicate"))
    opus5 = bool(row.get("opus5_bulk"))
    no_decide = bool(row.get("claude_does_not_decide"))
    no_auth = bool(row.get("no_auth"))
    no_gate = bool(row.get("no_gate"))
    if not card or not catalog or not quarantine or not packet:
        return {
            "state": "NOT_LANDED",
            "note": (
                "missing leftover path(s): "
                + ", ".join(misses or ["card/catalog/quarantine/packet"])
                + ". Paid-compute / compiler-farm talk is CLAIMED until the leftover ships."
            ),
        }
    needed = [phrase for phrase in REQUIRED_PHRASES if phrase not in phrases]
    missing_fields = [field for field in PACKET_FIELDS if field not in fields]
    if (
        needed
        or missing_fields
        or not posting_open
        or not named
        or not packet_required
        or not staging_required
        or not receipts_only
        or not no_conclusions
        or not no_self
        or not opus5
        or not no_decide
        or not no_auth
        or not no_gate
    ):
        return {
            "state": "NOT_LANDED",
            "note": (
                "farm present but incomplete. Missing phrases: "
                + ", ".join(needed)
                + ". Missing packet fields: "
                + ", ".join(missing_fields)
                + ". Exact non-Claude packet + staging + named adjudicator in advance + labeled receipts/raw pointers only + Opus 5 bulk drafting + open door required. Talk is CLAIMED."
            ),
        }
    return {
        "state": "INTEGRATED",
        "note": (
            "Claude-compute leftover is on this tree. Isolated untrusted "
            "build farm + quarantine + CLAUDE_INTERMEDIATE_UNTRUSTED + named "
            "non-Claude adjudicator in advance. A Slack clarification is "
            "still not the file. A packet here is CANDIDATE, never canonical."
        ),
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
    instrument_text = search_hits.get(os.path.join("host", "claude_compute.py"), "")
    quarantine_text = search_hits.get(DEFAULT_QUARANTINE, "")
    packet_text = search_hits.get(DEFAULT_PACKET, "")
    catalog = load_catalog(catalog_text) if catalog_text else {}
    blob = "\n".join(
        [card_text, catalog_text, instrument_text, quarantine_text, packet_text]
    ).lower()
    found = [phrase for phrase in REQUIRED_PHRASES if phrase in blob]
    packet_data = {}
    if packet_text:
        try:
            loaded = json.loads(packet_text)
            if isinstance(loaded, dict):
                packet_data = loaded
        except ValueError:
            packet_data = {}
    fields = [field for field in PACKET_FIELDS if packet_data.get(field)]
    calibration_hits = [rel for rel in CALIBRATION if _exists(root, rel)]
    facts = {
        "card_present": bool(card_text) and "compiler farm" in card_text.lower(),
        "catalog_present": bool(catalog) and not catalog.get("error"),
        "quarantine_present": bool(quarantine_text)
        and "claude_intermediate_untrusted" in quarantine_text.lower(),
        "packet_present": bool(packet_data)
        and str(packet_data.get("label") or "") == "CLAUDE_INTERMEDIATE_UNTRUSTED",
        "found_phrases": found,
        "packet_fields": fields,
        "posting_open": str(catalog.get("posting") or "").upper() == "OPEN",
        "adjudicator_in_advance": bool(catalog.get("adjudicator_in_advance")),
        "non_claude_packet_required": bool(
            catalog.get("non_claude_packet_required")
        ),
        "staging_required": bool(catalog.get("staging_required")),
        "receipts_and_pointers_only": bool(
            catalog.get("receipts_and_pointers_only")
        ),
        "no_shared_context_conclusions": bool(
            catalog.get("no_shared_context_conclusions")
        ),
        "no_self_adjudicate": catalog.get("claude_self_adjudicate") is False,
        "opus5_bulk": bool(catalog.get("opus5_bulk_drafting")),
        "claude_does_not_decide": catalog.get("claude_decides_correctness") is False,
        "no_auth": bool(catalog.get("no_auth")),
        "no_gate": bool(catalog.get("no_gate")),
        "calibration_ok": len(calibration_hits) == len(CALIBRATION),
        "calibration_hits": calibration_hits,
        "search_space": list(SEARCH_SPACE),
        "misses": misses,
        "titan": catalog.get("titan") or "NOT_WRITTEN",
        "slack_ts": catalog.get("slack_ts") or SLACK_TS,
        "supersedes_breadth": catalog.get("supersedes_breadth") or SUPERSEDES_BREADTH,
    }
    row = measure_from_rows(facts)
    row["slack_ts"] = facts["slack_ts"]
    row["supersedes_breadth"] = facts["supersedes_breadth"]
    row["catalog"] = DEFAULT_CATALOG
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure the Claude-compute farm leftover"
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
    payload["x"] = list(SEARCH_SPACE)
    payload["y"] = {
        "found_phrases": row.get("found_phrases") or [],
        "packet_fields": row.get("packet_fields") or [],
        "calibration_hits": row.get("calibration_hits") or [],
    }
    payload["z"] = row.get("misses") or []
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if row.get("measured") else 2


def _self_test():
    empty = classify({})
    assert empty["state"] == "UNMEASURED"
    assert "not stillness" in empty["note"]
    failed_cal = classify(
        {
            "measured": True,
            "calibration_ok": False,
            "calibration_hits": [],
            "card_present": True,
            "catalog_present": True,
            "quarantine_present": True,
            "packet_present": True,
        }
    )
    assert failed_cal["state"] == "UNMEASURED"
    assert "instrument failure" in failed_cal["note"]
    missing = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": False,
            "catalog_present": False,
            "quarantine_present": False,
            "packet_present": False,
            "misses": [DEFAULT_CARD],
        }
    )
    assert missing["state"] == "NOT_LANDED"
    incomplete = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "quarantine_present": True,
            "packet_present": True,
            "found_phrases": ["compiler farm"],
            "packet_fields": ["spec"],
            "posting_open": True,
            "adjudicator_in_advance": True,
            "non_claude_packet_required": True,
            "staging_required": True,
            "receipts_and_pointers_only": True,
            "no_shared_context_conclusions": True,
            "no_self_adjudicate": True,
            "opus5_bulk": True,
            "claude_does_not_decide": True,
            "no_auth": True,
            "no_gate": True,
        }
    )
    assert incomplete["state"] == "NOT_LANDED"
    ok = classify(
        {
            "measured": True,
            "calibration_ok": True,
            "card_present": True,
            "catalog_present": True,
            "quarantine_present": True,
            "packet_present": True,
            "found_phrases": list(REQUIRED_PHRASES),
            "packet_fields": list(PACKET_FIELDS),
            "posting_open": True,
            "adjudicator_in_advance": True,
            "non_claude_packet_required": True,
            "staging_required": True,
            "receipts_and_pointers_only": True,
            "no_shared_context_conclusions": True,
            "no_self_adjudicate": True,
            "opus5_bulk": True,
            "claude_does_not_decide": True,
            "no_auth": True,
            "no_gate": True,
        }
    )
    assert ok["state"] == "INTEGRATED"
    assert "still not the file" in ok["note"]
    good, note = packet_ok(
        {
            "label": "CLAUDE_INTERMEDIATE_UNTRUSTED",
            "spec": "x",
            "input_corpus": "y",
            "claimed_paths": ["p"],
            "acceptance_criteria": "z",
            "output_directory": "claude_compute/staging/x/",
            "adjudicator": "RIVET",
            "adjudicator_family": "non-claude",
            "adjudicator_named_in_advance": True,
            "canonical": False,
            "public_push": False,
        }
    )
    assert good and note == "CANDIDATE"
    bad, why = packet_ok(
        {
            "label": "CLAUDE_INTERMEDIATE_UNTRUSTED",
            "spec": "x",
            "input_corpus": "y",
            "claimed_paths": ["p"],
            "acceptance_criteria": "z",
            "output_directory": "out",
            "adjudicator": "GAUGE",
            "adjudicator_named_in_advance": True,
        }
    )
    assert not bad
    assert "self-adjudicate" in why
    catalog = load_catalog(
        json.dumps(
            {
                "slack_ts": SLACK_TS,
                "posting": "OPEN",
                "adjudicator_in_advance": True,
                "non_claude_packet_required": True,
                "staging_required": True,
                "scoped_receipts_and_raw_pointers_only": True,
                "shared_context_conclusions_from_claude": False,
                "claude_self_adjudicate": False,
                "token_use": {
                    "opus5_bulk_drafting": True,
                    "claude_decides_correctness": False,
                },
            }
        )
    )
    assert catalog["slack_ts"] == SLACK_TS
    assert catalog["adjudicator_in_advance"] is True
    assert catalog["non_claude_packet_required"] is True
    assert catalog["staging_required"] is True
    assert catalog["receipts_and_pointers_only"] is True
    assert catalog["no_shared_context_conclusions"] is True
    assert catalog["claude_self_adjudicate"] is False
    return True


if __name__ == "__main__":
    sys.exit(main())
