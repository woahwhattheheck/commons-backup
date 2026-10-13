#!/usr/bin/env python3
"""Deterministic finished-work -> cash closeout compiler.

Offline only. This module classifies retained evidence and emits owner-review
artifacts. It never authorizes or performs outbound contact, provider/payment
mutations, award claims, or revenue recognition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "finished-work-cash-closeout/v1"
OUTPUT_SCHEMA = "finished-work-cash-closeout/v2"
RECEIPT_SCHEMA = "finished-work-cash-closeout-receipt/v2"
MAX_ITEMS = 500
MAX_TEXT = 2048
MAX_EVIDENCE = 32
MAX_AMOUNT_MINOR = 10**12
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._:/@+\-]{0,159}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
COMPLETION_KINDS = {"MERGED", "DELIVERED", "ACCEPTED", "AWARDED", "SUBMITTED"}
PROVIDER_STATES = {
    "MERGED", "DELIVERED", "ACCEPTED", "AWARDED", "SUBMITTED",
    "REVIEW", "PENDING", "REJECTED", "UNKNOWN",
}
PAYABLE_PROVIDER_STATES = {"MERGED", "DELIVERED", "ACCEPTED", "AWARDED"}
PAYMENT_STATES = {"PAID", "UNPAID", "PENDING", "UNKNOWN"}
ELIGIBILITY_STATES = {"ELIGIBLE", "INELIGIBLE", "UNKNOWN"}
STATUS_ORDER = {
    "PAYMENT_CONFIRMED": 0,
    "READY_FOR_MUSE_ELECTION": 1,
    "WAIT_EXISTING_REQUEST": 2,
    "WAIT_PROVIDER": 3,
    "EVIDENCE_GAP": 4,
    "INELIGIBLE": 5,
    "DNR_NO_SEND": 6,
    "COLLISION_RECONCILE": 7,
}


class CloseoutError(ValueError):
    """Controlled validation/verification failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CloseoutError(message)


def _text(value: Any, field: str) -> str:
    require(isinstance(value, str), f"{field} must be a string")
    require(0 < len(value) <= MAX_TEXT, f"{field} must be non-empty and <= {MAX_TEXT} chars")
    require(value == value.strip(), f"{field} must not have leading/trailing whitespace")
    require("\x00" not in value, f"{field} contains NUL")
    return value


def _key(value: Any, field: str) -> str:
    value = _text(value, field)
    require(KEY_RE.fullmatch(value) is not None, f"{field} is not a canonical key")
    return value


def _enum(value: Any, field: str, allowed: set[str]) -> str:
    value = _text(value, field)
    require(value in allowed, f"{field} unsupported value: {value!r}")
    return value


def _evidence(value: Any, field: str) -> list[str]:
    require(isinstance(value, list), f"{field} must be a list")
    require(len(value) <= MAX_EVIDENCE, f"{field} exceeds {MAX_EVIDENCE} entries")
    out: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(value):
        token = _text(entry, f"{field}[{index}]")
        require(token not in seen, f"{field} contains duplicate entry")
        seen.add(token)
        out.append(token)
    return sorted(out)


def _strict_keys(obj: Mapping[str, Any], required: set[str], field: str) -> None:
    keys = set(obj)
    require(not (required - keys), f"{field} missing keys: {sorted(required - keys)}")
    require(not (keys - required), f"{field} has unsupported keys: {sorted(keys - required)}")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8") + b"\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def authority() -> dict[str, bool]:
    return {
        "outbound_authorized": False,
        "provider_mutation_authorized": False,
        "payment_mutation_authorized": False,
        "award_claim_authorized": False,
        "revenue_recognition_authorized": False,
    }


def normalize_item(raw: Any, index: int) -> dict[str, Any]:
    field = f"items[{index}]"
    require(isinstance(raw, dict), f"{field} must be an object")
    required = {
        "work_id", "payer_key", "opportunity_key", "payment_unit_key", "route_key",
        "currency", "advertised_amount_minor", "advertised_reward_evidence",
        "eligibility_state", "eligibility_evidence", "completion_kind", "completion_receipts",
        "provider_state", "provider_state_evidence", "payment_state", "payment_state_evidence",
        "payment_receipts", "prior_payment_request_receipts", "muse_owner", "dnr",
    }
    _strict_keys(raw, required, field)
    amount = raw["advertised_amount_minor"]
    require(isinstance(amount, int) and not isinstance(amount, bool), f"{field}.advertised_amount_minor must be an integer")
    require(0 < amount <= MAX_AMOUNT_MINOR, f"{field}.advertised_amount_minor out of bounds")
    currency = _text(raw["currency"], f"{field}.currency")
    require(CURRENCY_RE.fullmatch(currency) is not None, f"{field}.currency must be 3 uppercase letters")
    require(isinstance(raw["dnr"], bool), f"{field}.dnr must be boolean")
    owner = None if raw["muse_owner"] is None else _key(raw["muse_owner"], f"{field}.muse_owner")
    item = {
        "work_id": _key(raw["work_id"], f"{field}.work_id"),
        "payer_key": _key(raw["payer_key"], f"{field}.payer_key"),
        "opportunity_key": _key(raw["opportunity_key"], f"{field}.opportunity_key"),
        "payment_unit_key": _key(raw["payment_unit_key"], f"{field}.payment_unit_key"),
        "route_key": _key(raw["route_key"], f"{field}.route_key"),
        "currency": currency,
        "advertised_amount_minor": amount,
        "advertised_reward_evidence": _evidence(raw["advertised_reward_evidence"], f"{field}.advertised_reward_evidence"),
        "eligibility_state": _enum(raw["eligibility_state"], f"{field}.eligibility_state", ELIGIBILITY_STATES),
        "eligibility_evidence": _evidence(raw["eligibility_evidence"], f"{field}.eligibility_evidence"),
        "completion_kind": _enum(raw["completion_kind"], f"{field}.completion_kind", COMPLETION_KINDS),
        "completion_receipts": _evidence(raw["completion_receipts"], f"{field}.completion_receipts"),
        "provider_state": _enum(raw["provider_state"], f"{field}.provider_state", PROVIDER_STATES),
        "provider_state_evidence": _evidence(raw["provider_state_evidence"], f"{field}.provider_state_evidence"),
        "payment_state": _enum(raw["payment_state"], f"{field}.payment_state", PAYMENT_STATES),
        "payment_state_evidence": _evidence(raw["payment_state_evidence"], f"{field}.payment_state_evidence"),
        "payment_receipts": _evidence(raw["payment_receipts"], f"{field}.payment_receipts"),
        "prior_payment_request_receipts": _evidence(raw["prior_payment_request_receipts"], f"{field}.prior_payment_request_receipts"),
        "muse_owner": owner,
        "dnr": raw["dnr"],
    }
    if item["payment_state"] == "PAID":
        require(bool(item["payment_receipts"]), f"{field}: PAID requires retained payment_receipts")
    else:
        require(not item["payment_receipts"], f"{field}: non-PAID may not carry payment_receipts")
    return item


def normalize_ledger(raw: Any) -> dict[str, Any]:
    require(isinstance(raw, dict), "ledger must be an object")
    _strict_keys(raw, {"schema", "items"}, "ledger")
    require(raw["schema"] == SCHEMA, f"ledger.schema must equal {SCHEMA!r}")
    require(isinstance(raw["items"], list), "ledger.items must be a list")
    require(0 < len(raw["items"]) <= MAX_ITEMS, f"ledger.items must contain 1..{MAX_ITEMS} items")
    items = [normalize_item(item, index) for index, item in enumerate(raw["items"])]
    work_ids = [item["work_id"] for item in items]
    require(len(work_ids) == len(set(work_ids)), "ledger contains duplicate work_id")
    items.sort(key=lambda item: item["work_id"])
    return {"schema": SCHEMA, "items": items}


def _slot(item: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(item["payer_key"]), str(item["opportunity_key"]),
        str(item["payment_unit_key"]),
    )


def _slot_key(slot: Sequence[str]) -> str:
    return "sha256:" + sha256("\x1f".join(slot).encode("utf-8"))


def classify_single(item: Mapping[str, Any]) -> tuple[str, list[str], str]:
    if item["dnr"]:
        return "DNR_NO_SEND", ["DNR_TRUE"], "Preserve DNR; no external payment request."
    if item["payment_state"] == "PAID":
        return "PAYMENT_CONFIRMED", ["PAYMENT_RECEIPT_RETAINED"], "Retain payment receipt; no further request."
    if item["eligibility_state"] == "INELIGIBLE" or item["provider_state"] == "REJECTED":
        code = "ELIGIBILITY_INELIGIBLE" if item["eligibility_state"] == "INELIGIBLE" else "PROVIDER_REJECTED"
        return "INELIGIBLE", [code], "Close the candidate unless new provider evidence changes eligibility."
    if item["prior_payment_request_receipts"]:
        return "WAIT_EXISTING_REQUEST", ["PRIOR_PAYMENT_REQUEST_RETAINED"], "Reconcile the existing request and provider response before any new contact."
    if item["muse_owner"] is not None:
        return "COLLISION_RECONCILE", ["MUSE_OWNER_PRESENT"], "Coordinate with the existing Muse-elected owner; do not issue another request."

    reasons: list[str] = []
    if not item["advertised_reward_evidence"]:
        reasons.append("MISSING_ADVERTISED_REWARD_EVIDENCE")
    if item["eligibility_state"] != "ELIGIBLE":
        reasons.append("ELIGIBILITY_NOT_PROVEN")
    if not item["eligibility_evidence"]:
        reasons.append("MISSING_ELIGIBILITY_EVIDENCE")
    if not item["completion_receipts"]:
        reasons.append("MISSING_COMPLETION_RECEIPT")
    if not item["provider_state_evidence"]:
        reasons.append("MISSING_PROVIDER_STATE_EVIDENCE")
    if item["payment_state"] == "UNKNOWN":
        reasons.append("PAYMENT_STATE_UNKNOWN")
    if item["payment_state"] == "UNPAID" and not item["payment_state_evidence"]:
        reasons.append("MISSING_UNPAID_EVIDENCE")
    if item["payment_state"] == "PENDING" and not item["payment_state_evidence"]:
        reasons.append("MISSING_PENDING_PAYMENT_EVIDENCE")
    if reasons:
        return "EVIDENCE_GAP", sorted(reasons), "Fill the listed evidence gaps; do not contact the payer yet."
    if item["provider_state"] in {"SUBMITTED", "REVIEW", "PENDING", "UNKNOWN"}:
        return "WAIT_PROVIDER", ["PROVIDER_NOT_PAYABLE_YET"], "Wait for or verify the next provider state."
    if item["payment_state"] == "PENDING":
        return "WAIT_PROVIDER", ["PAYMENT_PENDING"], "Wait for the pending payment outcome."
    if item["provider_state"] not in PAYABLE_PROVIDER_STATES:
        return "EVIDENCE_GAP", ["PROVIDER_STATE_NOT_PAYABLE"], "Verify provider acceptance/payability."
    if item["payment_state"] != "UNPAID":
        return "EVIDENCE_GAP", ["PAYMENT_STATE_NOT_UNPAID"], "Verify current payment state."
    return (
        "READY_FOR_MUSE_ELECTION",
        ["PAYABLE_EVIDENCE_COMPLETE", "UNPAID_EVIDENCE_RETAINED"],
        "Request exact Muse single-writer election; recheck provider history immediately before any one outbound request.",
    )


def build_closeout(ledger: Mapping[str, Any]) -> dict[str, Any]:
    normalized = normalize_ledger(dict(ledger))
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in normalized["items"]:
        grouped.setdefault(_slot(item), []).append(item)
    groups: list[dict[str, Any]] = []
    for slot in sorted(grouped):
        members = sorted(grouped[slot], key=lambda item: item["work_id"])
        base = members[0]
        if len(members) > 1:
            dnr = any(item["dnr"] for item in members)
            paid_states = {item["payment_state"] for item in members}
            economics = {(item["currency"], item["advertised_amount_minor"]) for item in members}
            if dnr:
                status, reasons, action = (
                    "DNR_NO_SEND", ["DUPLICATE_SLOT", "DNR_TRUE"],
                    "Reconcile duplicate ledger rows while preserving DNR; no external request.",
                )
            elif paid_states == {"PAID"} and len(economics) == 1:
                status, reasons, action = (
                    "PAYMENT_CONFIRMED", ["DUPLICATE_SLOT", "ALL_MEMBERS_PAID"],
                    "Deduplicate ledger rows and retain payment receipts; no further request.",
                )
            else:
                status, reasons, action = (
                    "COLLISION_RECONCILE", ["DUPLICATE_PAYMENT_SLOT"],
                    "Reconcile duplicate records into one authoritative payout unit before any external action.",
                )
        else:
            status, reasons, action = classify_single(base)
        currencies = sorted({item["currency"] for item in members})
        amounts = sorted({item["advertised_amount_minor"] for item in members})
        routes = sorted({item["route_key"] for item in members})
        if len(routes) > 1:
            reasons = [*reasons, "MULTIPLE_CONTACT_ROUTES"]
        groups.append({
            "slot_key": _slot_key(slot),
            "payer_key": slot[0],
            "opportunity_key": slot[1],
            "payment_unit_key": slot[2],
            "route_key": routes[0] if len(routes) == 1 else None,
            "route_keys": routes,
            "work_ids": [item["work_id"] for item in members],
            "currency": currencies[0] if len(currencies) == 1 else None,
            "advertised_amount_minor": amounts[0] if len(amounts) == 1 else None,
            "status": status,
            "reason_codes": sorted(reasons),
            "next_internal_action": action,
            "evidence": {
                "advertised_reward_evidence": sorted({x for item in members for x in item["advertised_reward_evidence"]}),
                "eligibility_evidence": sorted({x for item in members for x in item["eligibility_evidence"]}),
                "completion_receipts": sorted({x for item in members for x in item["completion_receipts"]}),
                "provider_state_evidence": sorted({x for item in members for x in item["provider_state_evidence"]}),
                "payment_state_evidence": sorted({x for item in members for x in item["payment_state_evidence"]}),
                "payment_receipts": sorted({x for item in members for x in item["payment_receipts"]}),
                "prior_payment_request_receipts": sorted({x for item in members for x in item["prior_payment_request_receipts"]}),
            },
            "authority": authority(),
        })
    counts: dict[str, int] = {}
    for group in groups:
        counts[group["status"]] = counts.get(group["status"], 0) + 1
    return {
        "schema": OUTPUT_SCHEMA,
        "summary": {
            "input_items": len(normalized["items"]),
            "payment_slots": len(groups),
            "status_counts": {name: counts[name] for name in sorted(counts)},
        },
        "groups": groups,
        "authority": authority(),
    }


def render_markdown(closeout: Mapping[str, Any]) -> str:
    lines = [
        "# Finished Work → Cash Closeout", "",
        "Offline owner-review output. **This artifact does not authorize contact, provider mutation, payment mutation, award claims, or revenue recognition.**", "",
        f"- Input items: {closeout['summary']['input_items']}",
        f"- Payment slots: {closeout['summary']['payment_slots']}", "",
        "| Status | Payer | Opportunity | Payment unit | Amount | Work | Next internal action |",
        "|---|---|---|---|---:|---|---|",
    ]
    for group in closeout["groups"]:
        amount = "AMBIGUOUS"
        if group["currency"] is not None and group["advertised_amount_minor"] is not None:
            amount = f"{group['currency']} {group['advertised_amount_minor']} minor"
        action = str(group["next_internal_action"]).replace("|", "\\|").replace("\n", " ")
        work = ", ".join(group["work_ids"]).replace("|", "\\|")
        lines.append(
            f"| {group['status']} | `{group['payer_key']}` | `{group['opportunity_key']}` | "
            f"`{group['payment_unit_key']}` | {amount} | {work} | {action} |"
        )
    lines.extend(["", "## Status counts", ""])
    for status, count in sorted(
        closeout["summary"]["status_counts"].items(),
        key=lambda pair: (STATUS_ORDER.get(pair[0], 99), pair[0]),
    ):
        lines.append(f"- `{status}`: {count}")
    lines.append("")
    return "\n".join(lines)


def compile_ledger(raw: Any) -> tuple[bytes, bytes, bytes]:
    normalized = normalize_ledger(raw)
    closeout = build_closeout(normalized)
    input_bytes = canonical_json_bytes(normalized)
    closeout_bytes = canonical_json_bytes(closeout)
    markdown_bytes = render_markdown(closeout).encode("utf-8")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "input_sha256": sha256(input_bytes),
        "closeout_sha256": sha256(closeout_bytes),
        "markdown_sha256": sha256(markdown_bytes),
        "bundle_sha256": sha256(
            b"input\0" + input_bytes + b"closeout\0" + closeout_bytes + b"markdown\0" + markdown_bytes
        ),
        "authority": authority(),
    }
    return closeout_bytes, markdown_bytes, canonical_json_bytes(receipt)


def _reject_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise CloseoutError(f"duplicate JSON object key: {key!r}")
        seen.add(key)
        out[key] = value
    return out


def _reject_nonfinite_json_constant(token: str) -> None:
    raise CloseoutError(f"non-finite JSON constant rejected: {token}")


def load_ledger(path: Path) -> Any:
    require(path.is_file(), f"input is not a regular file: {path}")
    data = path.read_bytes()
    require(0 < len(data) <= 4_000_000, "input size must be 1..4,000,000 bytes")
    try:
        text_value = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CloseoutError("input must be UTF-8") from exc
    try:
        return json.loads(
            text_value,
            object_pairs_hook=_reject_duplicate_object_pairs,
            parse_constant=_reject_nonfinite_json_constant,
        )
    except CloseoutError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise CloseoutError(f"invalid JSON: {exc}") from exc


def _write_exclusive(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(data)
        total = 0
        while total < len(view):
            written = os.write(fd, view[total:])
            if written <= 0:
                raise CloseoutError(f"short write to {path.name}")
            total += written
        os.fsync(fd)
    finally:
        os.close(fd)


def compile_to_dir(input_path: Path, out_dir: Path) -> None:
    closeout_bytes, markdown_bytes, receipt_bytes = compile_ledger(load_ledger(input_path))
    require(not out_dir.exists(), f"output directory already exists: {out_dir}")
    out_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        _write_exclusive(out_dir / "closeout.json", closeout_bytes)
        _write_exclusive(out_dir / "closeout.md", markdown_bytes)
        _write_exclusive(out_dir / "receipt.json", receipt_bytes)
        dir_fd = os.open(out_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        raise


def verify_dir(input_path: Path, out_dir: Path) -> None:
    expected = compile_ledger(load_ledger(input_path))
    require(out_dir.is_dir(), f"output directory missing: {out_dir}")
    for name, expected_bytes in zip(("closeout.json", "closeout.md", "receipt.json"), expected):
        path = out_dir / name
        require(path.is_file(), f"missing output file: {name}")
        require(path.read_bytes() == expected_bytes, f"output mismatch: {name}")


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("input", type=Path)
    compile_parser.add_argument("output_dir", type=Path)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("input", type=Path)
    verify_parser.add_argument("output_dir", type=Path)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "compile":
            compile_to_dir(args.input, args.output_dir)
        elif args.command == "verify":
            verify_dir(args.input, args.output_dir)
        else:
            raise CloseoutError("unsupported command")
    except (CloseoutError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "command": args.command}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
