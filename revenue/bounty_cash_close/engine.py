from __future__ import annotations

import hashlib
from typing import Any

from .chain import _order_chain, _validate_event, _validate_semantics
from .core import (
    INPUT_SCHEMA, MAX_BOUNTIES, MAX_RECEIPTS, OUTPUT_SCHEMA, RECEIPT_SCHEMA, ZERO_SHA256,
    CloseBoardError, _int, _keys, _sha, _text, _validate_value, canonical_bounty_key,
    canonical_json_bytes, format_utc, mint_receipt, parse_utc, sha256_obj,
)
from .decision import _row, render_markdown

def validate_input(document: Any) -> dict[str, Any]:
    top = _keys(document, {"schema", "board_id", "policy", "bounties"}, "input")
    if top["schema"] != INPUT_SCHEMA:
        raise CloseBoardError("unsupported input schema")
    policy = _keys(top["policy"], {"gate_followup_after_seconds", "compensation_followup_after_seconds"}, "policy")
    normalized_policy = {
        "gate_followup_after_seconds": _int(policy["gate_followup_after_seconds"], "policy.gate_followup_after_seconds", lo=1, hi=31_536_000),
        "compensation_followup_after_seconds": _int(policy["compensation_followup_after_seconds"], "policy.compensation_followup_after_seconds", lo=1, hi=31_536_000),
    }
    raw_bounties = top["bounties"]
    if type(raw_bounties) is not list or not raw_bounties or len(raw_bounties) > MAX_BOUNTIES:
        raise CloseBoardError("bounties must be non-empty bounded list")
    normalized: list[dict[str, Any]] = []
    keys_seen: set[str] = set()
    for index, raw in enumerate(raw_bounties):
        label = f"bounties[{index}]"
        obj = _keys(
            raw,
            {
                "sponsor_ref", "program_ref", "bounty_ref", "claimant_ref",
                "source_revision", "work_fingerprint_sha256", "advertised_value", "receipts",
            },
            label,
        )
        receipts_raw = obj["receipts"]
        if type(receipts_raw) is not list or len(receipts_raw) > MAX_RECEIPTS:
            raise CloseBoardError(f"{label}.receipts must be bounded list")
        receipt_list = [_validate_event(item, f"{label}.receipts[{i}]") for i, item in enumerate(receipts_raw)]
        ordered = _order_chain(receipt_list, f"{label}.receipts")
        _validate_semantics(ordered)
        bounty = {
            "sponsor_ref": _text(obj["sponsor_ref"], f"{label}.sponsor_ref"),
            "program_ref": _text(obj["program_ref"], f"{label}.program_ref"),
            "bounty_ref": _text(obj["bounty_ref"], f"{label}.bounty_ref"),
            "claimant_ref": _text(obj["claimant_ref"], f"{label}.claimant_ref"),
            "source_revision": _text(obj["source_revision"], f"{label}.source_revision"),
            "work_fingerprint_sha256": _sha(obj["work_fingerprint_sha256"], f"{label}.work_fingerprint_sha256"),
            "advertised_value": _validate_value(obj["advertised_value"], f"{label}.advertised_value"),
            "receipts": ordered,
        }
        key = canonical_bounty_key(bounty)
        if key in keys_seen:
            raise CloseBoardError("duplicate canonical bounty key")
        keys_seen.add(key)
        bounty["canonical_bounty_key"] = key
        normalized.append(bounty)
    normalized.sort(key=lambda item: item["canonical_bounty_key"])
    return {
        "schema": INPUT_SCHEMA,
        "board_id": _text(top["board_id"], "board_id"),
        "policy": normalized_policy,
        "bounties": normalized,
    }

def compile_board(document: Any, trusted_as_of_utc: str) -> tuple[dict[str, Any], str, dict[str, Any]]:
    normalized = validate_input(document)
    as_of_epoch = parse_utc(trusted_as_of_utc, "trusted_as_of_utc")
    rows = [_row(bounty, normalized["policy"], as_of_epoch) for bounty in normalized["bounties"]]
    rows.sort(key=lambda row: row["canonical_bounty_key"])
    output: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "board_id": normalized["board_id"],
        "evaluated_at_utc": format_utc(as_of_epoch),
        "policy": normalized["policy"],
        "counts": {
            "total": len(rows),
            "settled": sum(row["state"] == "SETTLED" for row in rows),
            "accepted_unpaid": sum(row["technical_acceptance_observed"] and not row["settlement_observed"] for row in rows),
            "actionable_now": sum(row["next_action"] not in {"WAIT_DNR", "CLOSE_SETTLED"} for row in rows),
        },
        "rows": rows,
        "authority": {
            "external_contact_authorized": False,
            "submission_authorized": False,
            "invoice_or_payment_mutation_authorized": False,
            "revenue_recognition_authorized": False,
        },
    }
    output["output_sha256"] = sha256_obj(output)
    markdown = render_markdown(output)
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "board_id": normalized["board_id"],
        "evaluated_at_utc": format_utc(as_of_epoch),
        "normalized_input_sha256": sha256_obj(normalized),
        "output_sha256": output["output_sha256"],
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "authority": output["authority"],
    }
    receipt["receipt_sha256"] = sha256_obj(receipt)
    return output, markdown, receipt

def verify_bundle(document: Any, output: Any, markdown: Any, receipt: Any) -> dict[str, Any]:
    if type(output) is not dict or type(markdown) is not str or type(receipt) is not dict:
        raise CloseBoardError("bundle types invalid")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise CloseBoardError("receipt schema invalid")
    evaluated_at = receipt.get("evaluated_at_utc")
    parse_utc(evaluated_at, "receipt.evaluated_at_utc")
    expected_output, expected_markdown, expected_receipt = compile_board(document, evaluated_at)
    if output != expected_output:
        raise CloseBoardError("output mismatch")
    if markdown != expected_markdown:
        raise CloseBoardError("markdown mismatch")
    if receipt != expected_receipt:
        raise CloseBoardError("receipt mismatch")
    return {
        "status": "VERIFIED_HISTORICAL_DECISION_SUPPORT",
        "board_id": expected_output["board_id"],
        "output_sha256": expected_output["output_sha256"],
        "receipt_sha256": expected_receipt["receipt_sha256"],
        **expected_output["authority"],
    }
