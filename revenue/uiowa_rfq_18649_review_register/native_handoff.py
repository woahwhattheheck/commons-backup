#!/usr/bin/env python3
"""Preserve native/legacy workbench cells while adapting draft review intake.

This is a vocabulary adapter, not a compiler verifier or evidence authenticator.
No network requests, automatic findings, report changes, or external actions.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

import review_register as rr

SCHEMA = "uiowa-rfq18649-native-review-intake-draft/v1"
NATIVE_SOFTWARE = "software"
LEGACY_SOFTWARE = "software_development"


def convert(handoff: dict[str, Any], reviewer: str) -> dict[str, Any]:
    """Accept one complete vocabulary; retain original cell names and payload.

    The original payload's canonical hash and supplied report receipt remain the
    bindings. Vocabulary is not proof that an input came from a specific producer.
    """
    if not isinstance(handoff, dict):
        rr.fail("handoff", "expected an object")
    original = deepcopy(handoff)
    notes = rr.array(original.get("cell_notes"), "handoff.cell_notes")
    dimensions: set[str] = set()
    for i, note in enumerate(notes):
        if not isinstance(note, dict):
            rr.fail(f"handoff.cell_notes[{i}]", "expected an object")
        dimension = rr.string(note.get("dimension"), f"handoff.cell_notes[{i}].dimension")
        dimensions.add(dimension)
    if {NATIVE_SOFTWARE, LEGACY_SOFTWARE} <= dimensions:
        rr.fail("handoff.cell_notes", "mixed software/software_development vocabularies")
    native = NATIVE_SOFTWARE in dimensions
    normalized = deepcopy(original)
    for note in normalized["cell_notes"]:
        if note["dimension"] == NATIVE_SOFTWARE:
            note["dimension"] = LEGACY_SOFTWARE
    # Existing strict validator establishes the complete envelope and twelve-cell
    # contract after the explicit, narrow translation. Nothing is inferred.
    intake = rr.handoff_intake(normalized, reviewer)
    originals = {
        (note["group"], LEGACY_SOFTWARE if note["dimension"] == NATIVE_SOFTWARE else note["dimension"]): note
        for note in notes
    }
    comments = []
    for item in intake["comments"]:
        original_note = originals[(item["cell"]["group"], item["cell"]["dimension"])]
        item = deepcopy(item)
        item["register_cell"] = item["cell"]
        item["cell"] = {"group": original_note["group"], "dimension": original_note["dimension"]}
        item["intake_id"] = "INTAKE-" + rr.sha({
            "schema": SCHEMA, "report_receipt_sha256": original["report_receipt_sha256"],
            "reviewer": reviewer, "synthetic_demo": original["synthetic_demo"], "source_note": original_note,
        })[:24]
        comments.append(item)
    output = {
        "schema": SCHEMA, "status": "DRAFT_NON_AUTHORITATIVE", "reviewer": reviewer,
        "synthetic_demo": original["synthetic_demo"],
        "report_receipt_sha256": original["report_receipt_sha256"],
        "source_handoff_sha256": rr.sha(original), "source_handoff": original,
        "input_dimension_vocabulary": NATIVE_SOFTWARE if native else LEGACY_SOFTWARE,
        "dimension_translation": [{"input": NATIVE_SOFTWARE, "register": LEGACY_SOFTWARE}] if native else [],
        "comments": sorted(comments, key=lambda item: item["intake_id"]),
        "authority": dict(rr.AUTHORITY),
        "next_step": "Bind intake to a published finding ID and classify it explicitly; no finding or resolution is inferred.",
        "limits": [
            "Vocabulary labels describe input field names, not an authenticated producer.",
            "The supplied report receipt is preserved but no parent-compiler integrity check is performed.",
            "Source payload hash binds canonical JSON content, not original file formatting or evidence authenticity.",
            "Register-cell aliases are explicit; original cells and all twelve source notes remain available.",
        ],
    }
    output["receipt_sha256"] = rr.sha(output)
    return output


def verify(handoff: dict[str, Any], reviewer: str, intake: dict[str, Any]) -> None:
    """Recompute from original inputs, not merely trust a self-resealed digest."""
    expected = convert(handoff, reviewer)
    try:
        matches = rr.canonical(expected) == rr.canonical(intake)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        rr.fail("intake", "cannot encode the supplied intake as canonical JSON")
    if not matches:
        rr.fail("intake", "does not match recomputed source-bound draft intake")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("convert", help="Write new draft intake; never overwrite")
    build.add_argument("handoff", type=Path)
    build.add_argument("--reviewer", required=True)
    build.add_argument("--out", required=True, type=Path)
    check = commands.add_parser("verify", help="Recompute draft intake from the original handoff")
    check.add_argument("handoff", type=Path)
    check.add_argument("intake", type=Path)
    check.add_argument("--reviewer", required=True)
    args = parser.parse_args(argv)
    try:
        source = rr.strict_load(args.handoff)
        if args.command == "convert":
            result = convert(source, args.reviewer)
            payload = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
            with args.out.open("x", encoding="utf-8", newline="") as stream:
                stream.write(payload)
            print(f"DRAFT_INTAKE {len(result['comments'])} comments; vocabulary={result['input_dimension_vocabulary']}")
        else:
            verify(source, args.reviewer, rr.strict_load(args.intake))
            print("SOURCE_BOUND_DRAFT_INTAKE_VERIFIED; no evidence authenticity or approval established")
        return 0
    except (rr.ValidationError, OSError, TypeError, ValueError, RecursionError) as exc:
        print(f"native_handoff: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
