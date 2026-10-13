#!/usr/bin/env python3
"""Read-only conversion attribution compiler.

Binds owner-retained offers, hashed leads, provider payment events, and
fulfillment generations into deterministic states without double-counting
or asserting cash/revenue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = 1
MAX_MINOR = 9_000_000_000_000_000
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CUR_RE = re.compile(r"^[A-Z]{3}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

OFFER_STATES = {"ACTIVE", "READY", "NOT_READY", "SOURCE_RED"}
LEAD_STAGES = {"ACQUIRED", "QUALIFIED", "DISQUALIFIED"}
PAYMENT_STATUS = {"SETTLED", "PENDING", "FAILED", "REVERSED"}
FULFILLMENT_READINESS = {"READY", "BLOCKED", "UNKNOWN", "STALE"}
PUBLIC_STATES = {
    "PAID_ATTRIBUTED_READY",
    "PAID_FULFILLMENT_BLOCKED",
    "ATTRIBUTION_REVIEW",
    "UNPAID_PIPELINE",
}
BLOCKING_OFFER_STATES = {"SOURCE_RED", "NOT_READY"}
READY_FULFILLMENT = "READY"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _dict(value: Any, context: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{context} must be an object")
    return value


def _list(value: Any, context: str) -> list[Any]:
    if type(value) is not list:
        raise ValueError(f"{context} must be a list")
    return value


def _text(value: Any, context: str, pattern: re.Pattern[str] | None = None) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{context} must be non-empty text without surrounding whitespace")
    if pattern and not pattern.fullmatch(value):
        raise ValueError(f"{context} has invalid format")
    return value


def _id(value: Any, context: str) -> str:
    return _text(value, context, ID_RE)


def _utc(value: Any, context: str) -> str:
    return _text(value, context, UTC_RE)


def _digest(value: Any, context: str) -> str:
    return _text(value, context, SHA_RE)


def _money(value: Any, context: str) -> int:
    if type(value) is bool or type(value) is not int:
        raise ValueError(f"{context} must be an integer minor-unit amount")
    if not 0 < value <= MAX_MINOR:
        raise ValueError(f"{context} outside safe bounds")
    return value


def _enum(value: Any, allowed: set[str], context: str) -> str:
    text = _text(value, context)
    if text not in allowed:
        raise ValueError(f"{context}: invalid value {text!r}")
    return text


def _keys(obj: dict[str, Any], required: set[str], optional: set[str], context: str) -> None:
    missing = required - set(obj)
    unknown = set(obj) - required - optional
    if missing:
        raise ValueError(f"{context}: missing fields {sorted(missing)}")
    if unknown:
        raise ValueError(f"{context}: unknown fields {sorted(unknown)}")


def _unique(rows: list[dict[str, Any]], context: str) -> None:
    seen: set[str] = set()
    for row in rows:
        ident = _id(row.get("id"), f"{context}.id")
        if ident in seen:
            raise ValueError(f"duplicate {context} id: {ident}")
        seen.add(ident)


def _optional_id(value: Any, context: str) -> str | None:
    if value is None or value == "":
        return None
    return _id(value, context)


def validate_packet(packet: Any) -> dict[str, Any]:
    raw = _dict(packet, "packet")
    _keys(raw, {"schema_version", "portfolio", "offers", "leads", "payments", "fulfillment"}, set(), "packet")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != SCHEMA_VERSION:
        raise ValueError("schema_version must be integer 1")
    portfolio = _dict(raw["portfolio"], "portfolio")
    _keys(portfolio, {"name"}, set(), "portfolio")
    _text(portfolio["name"], "portfolio.name")

    offers = [_dict(row, "offers[]") for row in _list(raw["offers"], "offers")]
    leads = [_dict(row, "leads[]") for row in _list(raw["leads"], "leads")]
    payments = [_dict(row, "payments[]") for row in _list(raw["payments"], "payments")]
    fulfillment = [_dict(row, "fulfillment[]") for row in _list(raw["fulfillment"], "fulfillment")]
    _unique(offers, "offer")
    _unique(leads, "lead")
    _unique(payments, "payment")

    offer_ids: set[str] = set()
    for offer in offers:
        _keys(
            offer,
            {"id", "source_ref", "source_sha256", "commercial_state", "currency", "created_at"},
            set(),
            f"offer {offer.get('id', '?')}",
        )
        oid = _id(offer["id"], "offer.id")
        offer_ids.add(oid)
        _text(offer["source_ref"], f"offer {oid}.source_ref")
        _digest(offer["source_sha256"], f"offer {oid}.source_sha256")
        _enum(offer["commercial_state"], OFFER_STATES, f"offer {oid}.commercial_state")
        _text(offer["currency"], f"offer {oid}.currency", CUR_RE)
        _utc(offer["created_at"], f"offer {oid}.created_at")

    lead_ids: set[str] = set()
    for lead in leads:
        _keys(
            lead,
            {"id", "identity_sha256", "stage", "created_at", "source_ref"},
            set(),
            f"lead {lead.get('id', '?')}",
        )
        lid = _id(lead["id"], "lead.id")
        lead_ids.add(lid)
        _digest(lead["identity_sha256"], f"lead {lid}.identity_sha256")
        _enum(lead["stage"], LEAD_STAGES, f"lead {lid}.stage")
        _utc(lead["created_at"], f"lead {lid}.created_at")
        _text(lead["source_ref"], f"lead {lid}.source_ref")

    provider_events: dict[str, str] = {}
    for payment in payments:
        _keys(
            payment,
            {
                "id",
                "provider_event_id",
                "offer_id",
                "lead_id",
                "amount_minor",
                "currency",
                "occurred_at",
                "status",
                "source_sha256",
            },
            set(),
            f"payment {payment.get('id', '?')}",
        )
        pid = _id(payment["id"], "payment.id")
        provider_event_id = _id(payment["provider_event_id"], f"payment {pid}.provider_event_id")
        payment["offer_id"] = _optional_id(payment["offer_id"], f"payment {pid}.offer_id")
        payment["lead_id"] = _optional_id(payment["lead_id"], f"payment {pid}.lead_id")
        _money(payment["amount_minor"], f"payment {pid}.amount_minor")
        _text(payment["currency"], f"payment {pid}.currency", CUR_RE)
        _utc(payment["occurred_at"], f"payment {pid}.occurred_at")
        _enum(payment["status"], PAYMENT_STATUS, f"payment {pid}.status")
        _digest(payment["source_sha256"], f"payment {pid}.source_sha256")
        fingerprint = _sha256(
            {
                "provider_event_id": provider_event_id,
                "offer_id": payment["offer_id"],
                "lead_id": payment["lead_id"],
                "amount_minor": payment["amount_minor"],
                "currency": payment["currency"],
                "status": payment["status"],
            }
        )
        prior = provider_events.get(provider_event_id)
        if prior is not None:
            raise ValueError(
                f"duplicate economic payment event {provider_event_id}: {prior} and {pid}"
            )
        provider_events[provider_event_id] = pid

    fulfillment_seen: set[tuple[str, int]] = set()
    for row in fulfillment:
        _keys(
            row,
            {"offer_id", "generation", "source_commit", "readiness", "evidence_ref", "captured_at"},
            set(),
            "fulfillment[]",
        )
        oid = _id(row["offer_id"], "fulfillment.offer_id")
        if type(row["generation"]) is bool or type(row["generation"]) is not int:
            raise ValueError("fulfillment.generation must be an integer")
        if row["generation"] < 1:
            raise ValueError("fulfillment.generation must be >= 1")
        key = (oid, row["generation"])
        if key in fulfillment_seen:
            raise ValueError(f"duplicate fulfillment generation for offer {oid}: {row['generation']}")
        fulfillment_seen.add(key)
        _text(row["source_commit"], "fulfillment.source_commit", COMMIT_RE)
        _enum(row["readiness"], FULFILLMENT_READINESS, "fulfillment.readiness")
        _text(row["evidence_ref"], "fulfillment.evidence_ref")
        _utc(row["captured_at"], "fulfillment.captured_at")
        if oid not in offer_ids:
            raise ValueError(f"fulfillment: unknown offer_id {oid}")
    return raw


def _latest_fulfillment(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        current = latest.get(row["offer_id"])
        if current is None or row["generation"] > current["generation"]:
            latest[row["offer_id"]] = row
    return latest


def _safe_add(total: int, amount: int, context: str) -> int:
    result = total + amount
    if result > MAX_MINOR:
        raise ValueError(f"{context}: unsafe integer total")
    return result


def compile_ledger(packet: Any) -> dict[str, Any]:
    raw = validate_packet(packet)
    offers = {row["id"]: row for row in raw["offers"]}
    leads = {row["id"]: row for row in raw["leads"]}
    latest_fulfillment = _latest_fulfillment(raw["fulfillment"])
    rows: list[dict[str, Any]] = []
    paid_lead_ids: set[str] = set()

    for payment in sorted(raw["payments"], key=lambda row: row["id"]):
        if payment["status"] != "SETTLED":
            continue
        offer = offers.get(payment["offer_id"]) if payment["offer_id"] else None
        lead = leads.get(payment["lead_id"]) if payment["lead_id"] else None
        reasons: list[str] = []
        if offer is None:
            reasons.append("MISSING_OR_UNKNOWN_OFFER")
        if lead is None:
            reasons.append("MISSING_OR_UNKNOWN_LEAD")
        if offer is not None and offer["currency"] != payment["currency"]:
            raise ValueError(f"payment {payment['id']}: currency mismatch with offer")
        if reasons:
            rows.append(
                {
                    "row_id": f"pay:{payment['id']}",
                    "state": "ATTRIBUTION_REVIEW",
                    "payment_id": payment["id"],
                    "provider_event_id": payment["provider_event_id"],
                    "offer_id": payment["offer_id"],
                    "lead_id": payment["lead_id"],
                    "currency": payment["currency"],
                    "settled_payment_minor": 0,
                    "reasons": reasons,
                }
            )
            continue

        fulfillment = latest_fulfillment.get(offer["id"])
        blocked_reasons: list[str] = []
        if offer["commercial_state"] in BLOCKING_OFFER_STATES:
            blocked_reasons.append(f"OFFER_{offer['commercial_state']}")
        if fulfillment is None:
            blocked_reasons.append("FULFILLMENT_MISSING")
        else:
            if fulfillment["readiness"] != READY_FULFILLMENT:
                blocked_reasons.append(f"FULFILLMENT_{fulfillment['readiness']}")
            if fulfillment["captured_at"] < offer["created_at"]:
                blocked_reasons.append("FULFILLMENT_PREDATES_OFFER")
        state = "PAID_FULFILLMENT_BLOCKED" if blocked_reasons else "PAID_ATTRIBUTED_READY"
        paid_lead_ids.add(lead["id"])
        rows.append(
            {
                "row_id": f"pay:{payment['id']}",
                "state": state,
                "payment_id": payment["id"],
                "provider_event_id": payment["provider_event_id"],
                "offer_id": offer["id"],
                "lead_id": lead["id"],
                "currency": payment["currency"],
                "settled_payment_minor": payment["amount_minor"],
                "reasons": blocked_reasons,
                "offer_commercial_state": offer["commercial_state"],
                "fulfillment_generation": None if fulfillment is None else fulfillment["generation"],
                "fulfillment_readiness": None if fulfillment is None else fulfillment["readiness"],
                "fulfillment_source_commit": None if fulfillment is None else fulfillment["source_commit"],
            }
        )

    for lead in sorted(raw["leads"], key=lambda row: row["id"]):
        if lead["stage"] != "QUALIFIED" or lead["id"] in paid_lead_ids:
            continue
        rows.append(
            {
                "row_id": f"lead:{lead['id']}",
                "state": "UNPAID_PIPELINE",
                "payment_id": None,
                "provider_event_id": None,
                "offer_id": None,
                "lead_id": lead["id"],
                "currency": None,
                "settled_payment_minor": 0,
                "reasons": ["UNPAID_QUALIFIED_LEAD"],
            }
        )

    rows.sort(key=lambda row: row["row_id"])
    state_counts = {state: 0 for state in sorted(PUBLIC_STATES)}
    buckets: dict[str, dict[str, int]] = {}
    for row in rows:
        state_counts[row["state"]] += 1
        if row["settled_payment_minor"] and row["currency"]:
            bucket = buckets.setdefault(
                row["currency"],
                {"row_count": 0, "settled_payment_minor": 0},
            )
            bucket["row_count"] += 1
            bucket["settled_payment_minor"] = _safe_add(
                bucket["settled_payment_minor"],
                row["settled_payment_minor"],
                f"{row['currency']} settled_payment_minor",
            )

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "portfolio": {"name": raw["portfolio"]["name"]},
        "offers": sorted(raw["offers"], key=lambda row: row["id"]),
        "leads": sorted(raw["leads"], key=lambda row: row["id"]),
        "payments": sorted(raw["payments"], key=lambda row: row["id"]),
        "fulfillment": sorted(
            raw["fulfillment"],
            key=lambda row: (row["offer_id"], row["generation"]),
        ),
    }
    core = {
        "schema_version": SCHEMA_VERSION,
        "portfolio": {"name": raw["portfolio"]["name"]},
        "input_sha256": _sha256(normalized),
        "summary": {
            "row_count": len(rows),
            "state_counts": state_counts,
            "currency_buckets": dict(sorted(buckets.items())),
            "cross_currency_total_prohibited": True,
            "cash_collected": False,
            "revenue_recognized": False,
            "settled_payment_facts_only": True,
        },
        "rows": rows,
        "authority_boundary": {
            "read_only": True,
            "no_provider_write": True,
            "no_outbound_send": True,
            "no_stripe_mutation": True,
            "no_fulfillment_action": True,
            "review_rows_excluded_from_totals": True,
            "ambiguous_bindings_never_counted": True,
            "cash_collected_never_asserted": True,
            "revenue_recognized_never_asserted": True,
        },
    }
    out = dict(core)
    out["ledger_sha256"] = _sha256(core)
    return out


def render_markdown(ledger: Mapping[str, Any]) -> str:
    lines = [
        "# Conversion attribution ledger",
        "",
        f"**Portfolio:** {ledger['portfolio']['name']}  ",
        f"**Input SHA-256:** `{ledger['input_sha256']}`  ",
        f"**Ledger SHA-256:** `{ledger['ledger_sha256']}`  ",
        "",
        "> Read-only decision support. Settled provider-payment facts are summarized as `settled_payment_minor`. This is not cash collected and not recognized revenue.",
        "",
        "## Rows",
        "",
        "| Row | State | Payment | Offer | Lead | Currency | Settled minor | Reasons |",
        "|---|---|---|---|---|---|---:|---|",
    ]
    for row in ledger["rows"]:
        lines.append(
            "| {row_id} | **{state}** | {payment_id} | {offer_id} | {lead_id} | {currency} | {settled_payment_minor} | {reasons} |".format(
                row_id=row["row_id"],
                state=row["state"],
                payment_id=row["payment_id"] or "—",
                offer_id=row["offer_id"] or "—",
                lead_id=row["lead_id"] or "—",
                currency=row["currency"] or "—",
                settled_payment_minor=row["settled_payment_minor"],
                reasons=", ".join(row["reasons"]) or "—",
            )
        )
    lines += ["", "## Currency buckets", ""]
    if not ledger["summary"]["currency_buckets"]:
        lines.append("- none")
    for currency, bucket in ledger["summary"]["currency_buckets"].items():
        lines.append(
            f"- **{currency}** — rows {bucket['row_count']}; settled_payment_minor {bucket['settled_payment_minor']}"
        )
    lines += [
        "",
        "## Authority boundary",
        "",
        "Ambiguous or missing offer/lead bindings stay `ATTRIBUTION_REVIEW` and never enter totals. "
        "Paid-but-blocked offers stay `PAID_FULFILLMENT_BLOCKED`. Unpaid qualified leads stay `UNPAID_PIPELINE`. "
        "The compiler never contacts a provider, mutates Stripe, recognizes revenue, or claims collected cash.",
        "",
    ]
    return "\n".join(lines)


def verify_ledger(packet: Any, candidate: Any) -> tuple[bool, str]:
    ok = type(candidate) is dict and candidate == compile_ledger(packet)
    return ok, "verified" if ok else "candidate ledger does not match deterministic recomputation"


def _load_json_strict(path: str) -> Any:
    def pairs(rows: list[tuple[Any, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in rows:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(
            handle,
            object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(ValueError(f"invalid JSON constant {item}")),
        )


def _write_exclusive(path: str, text: str) -> None:
    target = Path(path)
    if target.is_symlink():
        raise FileExistsError(f"refusing symlink output: {target}")
    with target.open("x", encoding="utf-8", newline="") as handle:
        handle.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("--input", required=True)
    compile_cmd.add_argument("--json-out", required=True)
    compile_cmd.add_argument("--markdown-out")
    compile_cmd.add_argument("--fail-on-review", action="store_true")
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("--input", required=True)
    verify_cmd.add_argument("--ledger", required=True)
    args = parser.parse_args(argv)
    if args.command == "compile":
        ledger = compile_ledger(_load_json_strict(args.input))
        _write_exclusive(
            args.json_out,
            json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        if args.markdown_out:
            _write_exclusive(args.markdown_out, render_markdown(ledger))
        review = ledger["summary"]["state_counts"]["ATTRIBUTION_REVIEW"]
        return 2 if args.fail_on_review and review else 0
    ok, message = verify_ledger(_load_json_strict(args.input), _load_json_strict(args.ledger))
    print(message)
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
