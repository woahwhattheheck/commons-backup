#!/usr/bin/env python3
"""Validate provider-authorized settled USD cash evidence.

Candidate cash rows are never authoritative by themselves.  Trusted cash truth
requires an exact match against a separately retained provider-authority
registry whose canonical root is pinned in this module.  This keeps a caller
from minting settled USD by merely writing receipt-shaped JSON.

The authority registry records retained provider evidence.  It is not a live
provider re-query and it does not assert bank availability or withdrawability.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = "commons-settled-cash/v1"
SUMMARY_SCHEMA_VERSION = "commons-settled-cash-summary/v2"
AUTHORITY_SCHEMA_VERSION = "commons-settled-cash-authority/v1"
KIND = "SETTLED_CASH_LEDGER"
AUTHORITY_KIND = "SETTLED_CASH_PROVIDER_AUTHORITY"
ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = ROOT / "revenue" / "right_now" / "settled_cash_authority.json"
TRUSTED_AUTHORITY_ROOT = "57f731e6999ec9740dd4c82cf3567b7f9ff72bbad748691c9f05979ab08ddfe3"

SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
GITHUB_HANDLE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
CANONICAL_AMOUNT = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
FRANTIC_RECEIPT = re.compile(r"^r/[a-f0-9]{8,64}$")
FRANTIC_CLAIM = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
GITHUB_PR_PATH = re.compile(r"^/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*$")
SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")
FRANTIC_AGENT_PATH = re.compile(r"^/a/[A-Za-z0-9._-]{3,128}$")

AUTHORIZED_FIELDS = (
    "provider",
    "provider_url",
    "bounty_number",
    "program",
    "result_url",
    "claimant",
    "amount_usd",
    "payment_state",
    "evidenced_at",
    "provider_claim_id",
    "provider_receipt_id",
)


class CashSettlementError(ValueError):
    """A settled-cash artifact violates the evidence contract."""


def canonical_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _reject_constant(value: str) -> None:
    raise CashSettlementError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CashSettlementError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads_strict(text: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except CashSettlementError:
        raise
    except json.JSONDecodeError as error:
        raise CashSettlementError(f"invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise CashSettlementError("settled-cash artifact must contain one JSON object")
    return value


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        return loads_strict(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CashSettlementError(f"cannot read {label} {path}: {error}") from error


def read_ledger(path: Path) -> dict[str, Any]:
    return _read_object(path, "ledger")


def read_authority(path: Path = AUTHORITY_PATH) -> dict[str, Any]:
    return _read_object(path, "authority")


def _exact_fields(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CashSettlementError(f"{where} must be an object")
    if set(value) != expected:
        raise CashSettlementError(f"{where} fields differ from the settled-cash contract")
    return value


def _bounded_text(value: Any, where: str, *, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise CashSettlementError(f"{where} must be a non-empty trimmed string")
    if len(value) > limit or any(ord(char) < 32 for char in value):
        raise CashSettlementError(f"{where} is not bounded printable text")
    return value


def _safe_id(value: Any, where: str) -> str:
    text = _bounded_text(value, where, limit=128)
    if SAFE_ID.fullmatch(text) is None:
        raise CashSettlementError(f"{where} must be a lowercase safe identifier")
    return text


def _positive_integer(value: Any, where: str) -> int:
    if type(value) is not int or value <= 0:
        raise CashSettlementError(f"{where} must be a positive integer")
    return value


def _utc_timestamp(value: Any, where: str) -> datetime:
    text = _bounded_text(value, where, limit=32)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise CashSettlementError(f"{where} must be canonical UTC seconds") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise CashSettlementError(f"{where} must be canonical UTC seconds")
    return parsed


def _amount(value: Any, where: str) -> Decimal:
    if not isinstance(value, str) or CANONICAL_AMOUNT.fullmatch(value) is None:
        raise CashSettlementError(f"{where} must be a canonical positive decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise CashSettlementError(f"{where} must be a canonical positive decimal string") from error
    if not amount.is_finite() or amount <= 0:
        raise CashSettlementError(f"{where} must be greater than zero")
    return amount


def _format_amount(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _public_url(value: Any, where: str, *, host: str, path_pattern: re.Pattern[str]) -> str:
    text = _bounded_text(value, where, limit=300)
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError as error:
        raise CashSettlementError(f"{where} must be a clean public HTTPS URL") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != host
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or path_pattern.fullmatch(parsed.path) is None
    ):
        raise CashSettlementError(f"{where} must be a clean public HTTPS URL")
    return text


def _provider_url(value: Any, where: str) -> str:
    text = _bounded_text(value, where, limit=64)
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError as error:
        raise CashSettlementError(f"{where} must be the canonical Frantic root") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != "gofrantic.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path != "/"
        or parsed.query
        or parsed.fragment
    ):
        raise CashSettlementError(f"{where} must be the canonical Frantic root")
    return text


def _source_evidence_ref(value: Any, where: str) -> str:
    return _public_url(value, where, host="gofrantic.com", path_pattern=FRANTIC_AGENT_PATH)


def _validate_provider_fields(row: dict[str, Any], where: str, *, as_of: datetime) -> None:
    if row["provider"] != "Frantic":
        raise CashSettlementError(f"{where}.provider is unsupported")
    _provider_url(row["provider_url"], f"{where}.provider_url")
    _positive_integer(row["bounty_number"], f"{where}.bounty_number")
    _bounded_text(row["program"], f"{where}.program", limit=120)
    _public_url(
        row["result_url"],
        f"{where}.result_url",
        host="github.com",
        path_pattern=GITHUB_PR_PATH,
    )
    claimant = _bounded_text(row["claimant"], f"{where}.claimant", limit=39)
    if GITHUB_HANDLE.fullmatch(claimant) is None:
        raise CashSettlementError(f"{where}.claimant must be a GitHub handle")
    _amount(row["amount_usd"], f"{where}.amount_usd")
    if row["payment_state"] != "PAID":
        raise CashSettlementError(f"{where}.payment_state must be PAID")
    evidenced_at = _utc_timestamp(row["evidenced_at"], f"{where}.evidenced_at")
    if evidenced_at > as_of:
        raise CashSettlementError(f"{where}.evidenced_at is later than artifact as_of")
    claim_id = _bounded_text(row["provider_claim_id"], f"{where}.provider_claim_id", limit=36)
    if FRANTIC_CLAIM.fullmatch(claim_id) is None:
        raise CashSettlementError(f"{where}.provider_claim_id must be a Frantic UUID")
    receipt_id = _bounded_text(row["provider_receipt_id"], f"{where}.provider_receipt_id", limit=66)
    if FRANTIC_RECEIPT.fullmatch(receipt_id) is None:
        raise CashSettlementError(f"{where}.provider_receipt_id must be a Frantic receipt id")


def validate_ledger(value: dict[str, Any]) -> dict[str, Any]:
    _exact_fields(value, {"schema_version", "kind", "as_of", "receipts"}, "ledger")
    if value["schema_version"] != SCHEMA_VERSION:
        raise CashSettlementError("unsupported settled-cash schema_version")
    if value["kind"] != KIND:
        raise CashSettlementError("unsupported settled-cash kind")
    as_of = _utc_timestamp(value["as_of"], "as_of")
    receipts = value["receipts"]
    if not isinstance(receipts, list) or not receipts:
        raise CashSettlementError("receipts must be a non-empty list")

    expected = {
        "cash_id",
        "provider",
        "provider_url",
        "bounty_number",
        "program",
        "result_url",
        "claimant",
        "amount_usd",
        "payment_state",
        "evidenced_at",
        "provider_claim_id",
        "provider_receipt_id",
        "idempotency_key",
        "bank_availability_state",
        "withdrawability_state",
        "collection_action",
    }
    seen_cash: set[str] = set()
    seen_claims: set[str] = set()
    seen_receipts: set[str] = set()
    seen_idempotency: set[str] = set()
    order: list[tuple[str, str]] = []

    for index, raw in enumerate(receipts):
        where = f"receipts[{index}]"
        row = _exact_fields(raw, expected, where)
        cash_id = _safe_id(row["cash_id"], f"{where}.cash_id")
        idempotency = _safe_id(row["idempotency_key"], f"{where}.idempotency_key")
        if cash_id in seen_cash:
            raise CashSettlementError(f"duplicate cash_id: {cash_id}")
        if idempotency in seen_idempotency:
            raise CashSettlementError(f"duplicate idempotency_key: {idempotency}")
        seen_cash.add(cash_id)
        seen_idempotency.add(idempotency)

        _validate_provider_fields(row, where, as_of=as_of)
        order.append((row["evidenced_at"], cash_id))

        claim_id = row["provider_claim_id"]
        if claim_id in seen_claims:
            raise CashSettlementError(f"duplicate provider_claim_id: {claim_id}")
        seen_claims.add(claim_id)

        receipt_id = row["provider_receipt_id"]
        if receipt_id in seen_receipts:
            raise CashSettlementError(f"duplicate provider_receipt_id: {receipt_id}")
        seen_receipts.add(receipt_id)

        if row["bank_availability_state"] != "NOT_ASSERTED":
            raise CashSettlementError(f"{where}.bank_availability_state must remain NOT_ASSERTED")
        if row["withdrawability_state"] != "NOT_ASSERTED":
            raise CashSettlementError(f"{where}.withdrawability_state must remain NOT_ASSERTED")
        if row["collection_action"] != "NONE_DO_NOT_RESEND":
            raise CashSettlementError(f"{where}.collection_action must remain NONE_DO_NOT_RESEND")

    if order != sorted(order):
        raise CashSettlementError("receipts must be ordered by evidenced_at then cash_id")
    return value


def _source_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": row["provider"],
        "provider_claim_id": row["provider_claim_id"],
        "provider_receipt_id": row["provider_receipt_id"],
        "payment_state": row["payment_state"],
        "amount_usd": row["amount_usd"],
        "result_url": row["result_url"],
        "claimant": row["claimant"],
        "evidenced_at": row["evidenced_at"],
        "source_evidence_ref": row["source_evidence_ref"],
    }


def source_evidence_sha256(row: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_text(_source_projection(row)).encode("utf-8")).hexdigest()


def validate_authority(value: dict[str, Any]) -> dict[str, Any]:
    _exact_fields(value, {"schema_version", "kind", "as_of", "records"}, "authority")
    if value["schema_version"] != AUTHORITY_SCHEMA_VERSION:
        raise CashSettlementError("unsupported settled-cash authority schema_version")
    if value["kind"] != AUTHORITY_KIND:
        raise CashSettlementError("unsupported settled-cash authority kind")
    as_of = _utc_timestamp(value["as_of"], "authority.as_of")
    records = value["records"]
    if not isinstance(records, list) or not records:
        raise CashSettlementError("authority.records must be a non-empty list")

    expected = set(AUTHORIZED_FIELDS) | {"source_evidence_ref", "source_evidence_sha256"}
    seen_claims: set[str] = set()
    seen_receipts: set[str] = set()
    seen_sources: set[str] = set()
    order: list[tuple[str, str]] = []
    for index, raw in enumerate(records):
        where = f"authority.records[{index}]"
        row = _exact_fields(raw, expected, where)
        _validate_provider_fields(row, where, as_of=as_of)
        source_ref = _source_evidence_ref(row["source_evidence_ref"], f"{where}.source_evidence_ref")
        source_hash = _bounded_text(row["source_evidence_sha256"], f"{where}.source_evidence_sha256", limit=64)
        if SHA256_HEX.fullmatch(source_hash) is None:
            raise CashSettlementError(f"{where}.source_evidence_sha256 must be lowercase sha256")
        actual_source_hash = source_evidence_sha256(row)
        if not hmac.compare_digest(source_hash, actual_source_hash):
            raise CashSettlementError(f"{where}.source_evidence_sha256 does not bind the retained observation")
        claim_id = row["provider_claim_id"]
        receipt_id = row["provider_receipt_id"]
        if claim_id in seen_claims:
            raise CashSettlementError(f"duplicate authority provider_claim_id: {claim_id}")
        if receipt_id in seen_receipts:
            raise CashSettlementError(f"duplicate authority provider_receipt_id: {receipt_id}")
        if source_ref in seen_sources:
            raise CashSettlementError(f"duplicate authority source_evidence_ref: {source_ref}")
        seen_claims.add(claim_id)
        seen_receipts.add(receipt_id)
        seen_sources.add(source_ref)
        order.append((row["evidenced_at"], receipt_id))

    if order != sorted(order):
        raise CashSettlementError("authority records must be ordered by evidenced_at then provider_receipt_id")
    return value


def authority_root(value: dict[str, Any]) -> str:
    validate_authority(value)
    return hashlib.sha256(canonical_text(value).encode("utf-8")).hexdigest()


def _authorized_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row[field] for field in AUTHORIZED_FIELDS}


def reconcile_authority(
    ledger: dict[str, Any], authority: dict[str, Any], expected_authority_root: str
) -> str:
    """Require the complete candidate cash universe to match pinned authority."""
    validate_ledger(ledger)
    validate_authority(authority)
    if SHA256_HEX.fullmatch(expected_authority_root) is None:
        raise CashSettlementError("expected authority root must be lowercase sha256")
    actual_root = authority_root(authority)
    if not hmac.compare_digest(actual_root, expected_authority_root):
        raise CashSettlementError("settled-cash authority root does not match the trusted pinned root")

    candidate_by_claim = {
        row["provider_claim_id"]: row for row in ledger["receipts"]
    }
    authority_by_claim = {
        row["provider_claim_id"]: row for row in authority["records"]
    }
    if set(candidate_by_claim) != set(authority_by_claim):
        raise CashSettlementError("candidate cash universe differs from the trusted authority universe")

    candidate_receipts = {row["provider_receipt_id"] for row in ledger["receipts"]}
    authority_receipts = {row["provider_receipt_id"] for row in authority["records"]}
    if candidate_receipts != authority_receipts:
        raise CashSettlementError("candidate receipt universe differs from the trusted authority universe")

    for claim_id in sorted(candidate_by_claim):
        candidate = _authorized_projection(candidate_by_claim[claim_id])
        authorized = _authorized_projection(authority_by_claim[claim_id])
        if candidate != authorized:
            changed = sorted(key for key in candidate if candidate[key] != authorized[key])
            raise CashSettlementError(
                "candidate cash row differs from trusted provider authority: " + ", ".join(changed)
            )
    return actual_root


def summarize_ledger(value: dict[str, Any]) -> dict[str, Any]:
    """Return trusted cash truth using the repo-pinned authority universe.

    Callers intentionally cannot supply their own authority path or expected root.
    Structural-only callers should use :func:`validate_ledger` directly.
    """
    authority = read_authority()
    root = reconcile_authority(value, authority, TRUSTED_AUTHORITY_ROOT)
    total = Decimal(0)
    public: list[dict[str, Any]] = []
    authority_by_claim = {row["provider_claim_id"]: row for row in authority["records"]}
    for row in value["receipts"]:
        total += Decimal(row["amount_usd"])
        authority_row = authority_by_claim[row["provider_claim_id"]]
        public.append(
            {
                "cash_id": row["cash_id"],
                "provider": row["provider"],
                "provider_url": row["provider_url"],
                "bounty_number": row["bounty_number"],
                "program": row["program"],
                "result_url": row["result_url"],
                "claimant": row["claimant"],
                "amount_usd": row["amount_usd"],
                "payment_state": row["payment_state"],
                "evidenced_at": row["evidenced_at"],
                "provider_receipt_id": row["provider_receipt_id"],
                "source_evidence_ref": authority_row["source_evidence_ref"],
                "bank_availability_state": row["bank_availability_state"],
                "withdrawability_state": row["withdrawability_state"],
                "collection_action": row["collection_action"],
            }
        )
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "as_of": max(value["as_of"], authority["as_of"]),
        "authority_state": "PINNED_RETAINED_PROVIDER_EVIDENCE",
        "authority_root_sha256": root,
        "settled_receipts": len(public),
        "settled_usd": _format_amount(total),
        "bank_availability_asserted": False,
        "withdrawability_asserted": False,
        "receipts": public,
    }


def inspect_ledger(value: dict[str, Any]) -> dict[str, Any]:
    """Return format-only candidate facts without asserting settled cash."""
    validate_ledger(value)
    total = sum((Decimal(row["amount_usd"]) for row in value["receipts"]), Decimal(0))
    return {
        "schema_version": "commons-settled-cash-inspection/v1",
        "as_of": value["as_of"],
        "authority_state": "UNVERIFIED_FORMAT_ONLY",
        "candidate_receipts": len(value["receipts"]),
        "candidate_usd": _format_amount(total),
        "settled_cash_asserted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "summary", "inspect"))
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args()
    try:
        value = read_ledger(args.ledger)
        if args.command == "inspect":
            sys.stdout.write(canonical_text(inspect_ledger(value)))
        else:
            summary = summarize_ledger(value)
            if args.command == "summary":
                sys.stdout.write(canonical_text(summary))
            else:
                print(
                    f"VALID AUTHORIZED {summary['settled_receipts']} settled receipt(s) · "
                    f"USD {summary['settled_usd']} PAID · pinned authority "
                    f"{summary['authority_root_sha256']} · bank availability and "
                    "withdrawability not asserted"
                )
    except CashSettlementError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
