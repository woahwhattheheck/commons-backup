#!/usr/bin/env python3
"""Validate and summarize privacy-safe, multi-currency settled-award evidence.

The ledger records sponsor-confirmed payment facts without converting currencies,
claiming bank or wallet availability, or exposing private receipt locators.  It is
an offline evidence compiler only; it performs no provider, wallet, collection,
or customer action.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = "commons-settled-awards/v1"
SUMMARY_SCHEMA_VERSION = "commons-settled-awards-summary/v1"
KIND = "SETTLED_AWARDS_LEDGER"
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
CURRENCY = re.compile(r"^[A-Z][A-Z0-9]{1,11}$")
CANONICAL_AMOUNT = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
GITHUB_PATH = re.compile(r"^/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(?:issues|pull)/[1-9][0-9]*$")


class SettlementError(ValueError):
    """A settled-awards artifact violates the evidence contract."""


def canonical_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _reject_constant(value: str) -> None:
    raise SettlementError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SettlementError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def loads_strict(text: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except SettlementError:
        raise
    except json.JSONDecodeError as error:
        raise SettlementError(f"invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise SettlementError("settled-awards ledger must contain one JSON object")
    return value


def read_ledger(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SettlementError(f"cannot read {path}: {error}") from error
    return loads_strict(text)


def _exact_fields(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SettlementError(f"{where} must be an object")
    if set(value) != expected:
        raise SettlementError(f"{where} fields differ from the settled-awards contract")
    return value


def _bounded_text(value: Any, where: str, *, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise SettlementError(f"{where} must be a non-empty trimmed string")
    if len(value) > limit or any(ord(char) < 32 for char in value):
        raise SettlementError(f"{where} is not bounded printable text")
    return value


def _safe_id(value: Any, where: str) -> str:
    text = _bounded_text(value, where, limit=128)
    if SAFE_ID.fullmatch(text) is None:
        raise SettlementError(f"{where} must be a lowercase safe identifier")
    return text


def _utc_timestamp(value: Any, where: str) -> datetime:
    text = _bounded_text(value, where, limit=32)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise SettlementError(f"{where} must be canonical UTC seconds") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise SettlementError(f"{where} must be canonical UTC seconds")
    return parsed


def _calendar_date(value: Any, where: str) -> date:
    text = _bounded_text(value, where, limit=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise SettlementError(f"{where} must be an ISO calendar date") from error
    if parsed.isoformat() != text:
        raise SettlementError(f"{where} must be an ISO calendar date")
    return parsed


def _amount(value: Any, where: str) -> Decimal:
    if not isinstance(value, str) or CANONICAL_AMOUNT.fullmatch(value) is None:
        raise SettlementError(f"{where} must be a canonical positive decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise SettlementError(f"{where} must be a canonical positive decimal string") from error
    if not amount.is_finite() or amount <= 0:
        raise SettlementError(f"{where} must be greater than zero")
    return amount


def _format_amount(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _github_issue_url(value: Any, where: str) -> str:
    text = _bounded_text(value, where, limit=300)
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError as error:
        raise SettlementError(
            f"{where} must be a clean public GitHub issue or pull URL"
        ) from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or GITHUB_PATH.fullmatch(parsed.path) is None
    ):
        raise SettlementError(f"{where} must be a clean public GitHub issue or pull URL")
    return text


def validate_ledger(value: dict[str, Any]) -> dict[str, Any]:
    _exact_fields(value, {"schema_version", "kind", "as_of", "awards"}, "ledger")
    if value["schema_version"] != SCHEMA_VERSION:
        raise SettlementError("unsupported settled-awards schema_version")
    if value["kind"] != KIND:
        raise SettlementError("unsupported settled-awards kind")
    as_of = _utc_timestamp(value["as_of"], "as_of")
    awards = value["awards"]
    if not isinstance(awards, list) or not awards:
        raise SettlementError("awards must be a non-empty list")

    expected_award_fields = {
        "award_id",
        "program",
        "task_url",
        "result_url",
        "claimant",
        "amount",
        "currency",
        "payment_state",
        "paid_at",
        "destination_kind",
        "destination_reference",
        "hold",
        "receipt",
        "idempotency_key",
        "usd_equivalent",
        "conversion_state",
        "collection_action",
    }
    seen_awards: set[str] = set()
    seen_idempotency: set[str] = set()
    seen_receipts: set[str] = set()
    order: list[tuple[str, str]] = []

    for index, raw in enumerate(awards):
        where = f"awards[{index}]"
        award = _exact_fields(raw, expected_award_fields, where)
        award_id = _safe_id(award["award_id"], f"{where}.award_id")
        idempotency_key = _safe_id(
            award["idempotency_key"], f"{where}.idempotency_key"
        )
        if award_id in seen_awards:
            raise SettlementError(f"duplicate award_id: {award_id}")
        if idempotency_key in seen_idempotency:
            raise SettlementError(f"duplicate idempotency_key: {idempotency_key}")
        seen_awards.add(award_id)
        seen_idempotency.add(idempotency_key)

        _bounded_text(award["program"], f"{where}.program", limit=100)
        _github_issue_url(award["task_url"], f"{where}.task_url")
        _github_issue_url(award["result_url"], f"{where}.result_url")
        claimant = _bounded_text(award["claimant"], f"{where}.claimant", limit=100)
        _amount(award["amount"], f"{where}.amount")
        currency = _bounded_text(award["currency"], f"{where}.currency", limit=12)
        if CURRENCY.fullmatch(currency) is None:
            raise SettlementError(f"{where}.currency must be an uppercase currency code")
        if award["payment_state"] != "PAID":
            raise SettlementError(f"{where}.payment_state must be PAID")
        paid_at = _calendar_date(award["paid_at"], f"{where}.paid_at")
        if paid_at > as_of.date():
            raise SettlementError(f"{where}.paid_at is later than ledger as_of")
        order.append((paid_at.isoformat(), award_id))

        if award["destination_kind"] != "HOSTED_HANDLE":
            raise SettlementError(f"{where}.destination_kind must be HOSTED_HANDLE")
        destination = _bounded_text(
            award["destination_reference"],
            f"{where}.destination_reference",
            limit=100,
        )
        if destination != claimant:
            raise SettlementError(
                f"{where}.destination_reference must match the public claimant handle"
            )

        hold = _exact_fields(
            award["hold"],
            {"kind", "hours", "availability_state"},
            f"{where}.hold",
        )
        if hold["kind"] != "SPONSOR_STATED_DURATION":
            raise SettlementError(f"{where}.hold.kind is unsupported")
        if type(hold["hours"]) is not int or not 1 <= hold["hours"] <= 8760:
            raise SettlementError(f"{where}.hold.hours must be an integer from 1 to 8760")
        if hold["availability_state"] != "NOT_ASSERTED":
            raise SettlementError(
                f"{where}.hold.availability_state must remain NOT_ASSERTED"
            )

        receipt = _exact_fields(
            award["receipt"],
            {"authority", "reference_visibility", "public_receipt_id"},
            f"{where}.receipt",
        )
        if receipt["authority"] != "SPONSOR_CONFIRMATION":
            raise SettlementError(f"{where}.receipt.authority is unsupported")
        if receipt["reference_visibility"] != "PRIVATE_REDACTED":
            raise SettlementError(
                f"{where}.receipt.reference_visibility must be PRIVATE_REDACTED"
            )
        public_receipt_id = _safe_id(
            receipt["public_receipt_id"], f"{where}.receipt.public_receipt_id"
        )
        if public_receipt_id in seen_receipts:
            raise SettlementError(f"duplicate public_receipt_id: {public_receipt_id}")
        seen_receipts.add(public_receipt_id)

        if award["usd_equivalent"] is not None:
            raise SettlementError(f"{where}.usd_equivalent must remain null")
        if award["conversion_state"] != "NO_USD_CONVERSION_ASSERTED":
            raise SettlementError(
                f"{where}.conversion_state must remain NO_USD_CONVERSION_ASSERTED"
            )
        if award["collection_action"] != "NONE_DO_NOT_RESEND":
            raise SettlementError(
                f"{where}.collection_action must remain NONE_DO_NOT_RESEND"
            )

    if order != sorted(order):
        raise SettlementError("awards must be ordered by paid_at then award_id")
    return value


def summarize_ledger(value: dict[str, Any]) -> dict[str, Any]:
    validate_ledger(value)
    totals: dict[str, Decimal] = {}
    public_awards: list[dict[str, Any]] = []
    for award in value["awards"]:
        currency = award["currency"]
        totals[currency] = totals.get(currency, Decimal(0)) + Decimal(award["amount"])
        public_awards.append(
            {
                "award_id": award["award_id"],
                "program": award["program"],
                "task_url": award["task_url"],
                "result_url": award["result_url"],
                "claimant": award["claimant"],
                "amount": award["amount"],
                "currency": currency,
                "payment_state": award["payment_state"],
                "paid_at": award["paid_at"],
                "destination_kind": award["destination_kind"],
                "destination_reference": award["destination_reference"],
                "hold": award["hold"],
                "public_receipt_id": award["receipt"]["public_receipt_id"],
                "collection_action": award["collection_action"],
            }
        )
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "as_of": value["as_of"],
        "paid_awards": len(public_awards),
        "totals_by_currency": [
            {"currency": currency, "amount": _format_amount(totals[currency])}
            for currency in sorted(totals)
        ],
        "usd_equivalent": None,
        "usd_conversion_asserted": False,
        "bank_availability_asserted": False,
        "withdrawability_asserted": False,
        "awards": public_awards,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "summary"))
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args()
    try:
        value = read_ledger(args.ledger)
        summary = summarize_ledger(value)
        if args.command == "summary":
            sys.stdout.write(canonical_text(summary))
        else:
            totals = ", ".join(
                f"{row['amount']} {row['currency']}"
                for row in summary["totals_by_currency"]
            )
            print(
                f"VALID {summary['paid_awards']} paid award(s) · {totals} · "
                "no USD conversion, bank availability, or withdrawability asserted"
            )
    except SettlementError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
