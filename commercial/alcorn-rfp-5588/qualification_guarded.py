#!/usr/bin/env python3
"""Canonical Addendum-aware qualification entrypoint for Alcorn State RFP #5588.

The original qualification engine remains the low-level evidence evaluator. This layer
source-binds buyer Addendum #1 and records its bounded semantic effect without inventing
new buyer requirements or inheriting NVIDIA/OEM authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from . import qualification as base
except ImportError:  # direct script execution
    import qualification as base

ADDENDUM_ID = "addendum_1"
ADDENDUM_GMAIL_MESSAGE_ID = "1a0a703662d0e19f"
ADDENDUM_FILENAME = "Addendum1 RFP5588.docx"
ADDENDUM_SHA256 = "82a26f82092e9de91f3e10f985bf9811983f122127fb15d35c9b2f746da72886"
ADDENDUM_DOCUMENT_DATE = "2026-09-10"
ADDENDUM_RECEIVED_AT = "2026-09-15T21:40:09+00:00"
ADDENDUM_TOPIC = "consulting_prime_with_disclosed_hardware_software_or_lab_delivery_partners"
ADDENDUM_EFFECT = "PROPOSAL_STRUCTURE_DISCRETION_MINIMUM_SPEC_FLOOR"


def _validated_addendum(spec: Mapping[str, Any]) -> dict[str, Any]:
    rows = base._list(spec.get("buyer_addenda"), "spec.buyer_addenda")
    matches = []
    for idx, raw in enumerate(rows):
        row = base._obj(raw, f"spec.buyer_addenda[{idx}]")
        if row.get("id") == ADDENDUM_ID:
            matches.append(row)
    if len(matches) != 1:
        raise base.EvidenceError(f"spec must contain exactly one {ADDENDUM_ID!r} source binding")

    row = matches[0]
    allowed = {
        "id", "gmail_message_id", "filename", "sha256", "document_date",
        "received_at", "question_topic", "normalized_effect", "policy",
    }
    base._assert_keys(row, allowed=allowed, required=allowed, name="spec.buyer_addenda.addendum_1")

    expected = {
        "id": ADDENDUM_ID,
        "gmail_message_id": ADDENDUM_GMAIL_MESSAGE_ID,
        "filename": ADDENDUM_FILENAME,
        "sha256": ADDENDUM_SHA256,
        "document_date": ADDENDUM_DOCUMENT_DATE,
        "received_at": ADDENDUM_RECEIVED_AT,
        "question_topic": ADDENDUM_TOPIC,
        "normalized_effect": ADDENDUM_EFFECT,
    }
    for key, value in expected.items():
        if row.get(key) != value:
            raise base.EvidenceError(f"Addendum #1 source binding mismatch for {key}")

    base._source_id(row["gmail_message_id"], "addendum_1.gmail_message_id")
    base._source_id(row["filename"], "addendum_1.filename")
    base._sha(row["sha256"], "addendum_1.sha256")
    base._date(row["document_date"], "addendum_1.document_date")
    base._when(row["received_at"], "addendum_1.received_at")
    base._source_id(row["question_topic"], "addendum_1.question_topic")
    base._source_id(row["normalized_effect"], "addendum_1.normalized_effect")
    base._str(row["policy"], "addendum_1.policy")
    return row


def _with_source_finding(result: dict[str, Any], addendum: Mapping[str, Any]) -> None:
    result["source_findings"] = {
        ADDENDUM_ID: {
            "gmail_message_id": addendum["gmail_message_id"],
            "filename": addendum["filename"],
            "sha256": addendum["sha256"],
            "document_date": addendum["document_date"],
            "received_at": addendum["received_at"],
            "question_topic": addendum["question_topic"],
            "normalized_effect": addendum["normalized_effect"],
            "vendor_proposal_structure_discretion": True,
            "minimum_specifications_still_required": True,
            "nvidia_oem_authority_granted": False,
            "partner_credentials_inherited": False,
        }
    }


def evaluate(spec: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    addendum = _validated_addendum(spec)
    result = base.evaluate(spec, evidence)
    _with_source_finding(result, addendum)
    return result


def canonical_digest(value: Mapping[str, Any]) -> str:
    return base.canonical_digest(value)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--spec", type=Path, default=Path(__file__).with_name("qualification_spec.json"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    spec = base.load_json_strict(args.spec)
    evidence = base.load_json_strict(args.evidence)
    result = evaluate(spec, evidence)
    result["receipt_sha256"] = canonical_digest(result)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
