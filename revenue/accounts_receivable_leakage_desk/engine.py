from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

SCHEMA = "commons-ar-leakage-desk/v1"
REPORT_SCHEMA = "commons-ar-leakage-report/v1"
PILOT_PRICE_USD_MINOR = 250_000
PILOT_MAX_INVOICES = 5_000
MAX_PAYMENTS = 10_000
MAX_CREDITS = 10_000
MAX_DISPUTE_EVENTS = 10_000
MAX_GRACE_DAYS = 90
SUPPORTED_CURRENCY = "USD"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class InputError(ValueError):
    pass


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise InputError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise InputError(f"non-finite JSON number: {value}")


def loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_dupes,
            parse_constant=_reject_constant,
        )
    except InputError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise InputError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InputError(f"not canonicalizable: {exc}") from exc


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exact_keys(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise InputError(f"{where}: expected object")
    got = set(value)
    if got != keys:
        raise InputError(
            f"{where}: key mismatch missing={sorted(keys - got)} extra={sorted(got - keys)}"
        )
    return value


def _string(value: Any, where: str, *, max_len: int = 256) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise InputError(f"{where}: expected non-empty string <= {max_len}")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise InputError(f"{where}: control characters forbidden")
    return value


def _id(value: Any, where: str) -> str:
    text = _string(value, where, max_len=64)
    if not _ID_RE.fullmatch(text) or "@" in text:
        raise InputError(f"{where}: expected opaque safe identifier")
    return text


def _sha(value: Any, where: str) -> str:
    text = _string(value, where, max_len=64)
    if not _SHA_RE.fullmatch(text):
        raise InputError(f"{where}: expected lowercase SHA-256")
    return text


def _currency(value: Any, where: str) -> str:
    text = _string(value, where, max_len=3)
    if not _CURRENCY_RE.fullmatch(text):
        raise InputError(f"{where}: expected ISO-like uppercase 3-letter currency")
    return text


def _integer(value: Any, where: str, *, low: int, high: int) -> int:
    if type(value) is not int or value < low or value > high:
        raise InputError(f"{where}: expected integer in [{low}, {high}]")
    return value


def _date(value: Any, where: str) -> date:
    text = _string(value, where, max_len=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise InputError(f"{where}: expected YYYY-MM-DD") from exc
    if parsed.isoformat() != text:
        raise InputError(f"{where}: non-canonical date")
    return parsed


def _utc(value: Any, where: str) -> datetime:
    text = _string(value, where, max_len=20)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", text):
        raise InputError(f"{where}: expected canonical UTC whole seconds")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise InputError(f"{where}: invalid UTC timestamp") from exc


def _enum(value: Any, allowed: set[str], where: str) -> str:
    text = _string(value, where, max_len=32)
    if text not in allowed:
        raise InputError(f"{where}: expected one of {sorted(allowed)}")
    return text


def _validate_packet(packet: Any) -> dict[str, Any]:
    root = _exact_keys(
        packet,
        {
            "schema",
            "analysis_date",
            "currency",
            "grace_days",
            "invoices",
            "payments",
            "credits",
            "disputes",
        },
        "packet",
    )
    if root["schema"] != SCHEMA:
        raise InputError(f"packet.schema: expected {SCHEMA}")

    analysis = _date(root["analysis_date"], "packet.analysis_date")
    currency = _currency(root["currency"], "packet.currency")
    if currency != SUPPORTED_CURRENCY:
        raise InputError(
            f"packet.currency: v1 supports {SUPPORTED_CURRENCY} minor units only"
        )
    grace = _integer(
        root["grace_days"], "packet.grace_days", low=0, high=MAX_GRACE_DAYS
    )

    for key, limit in (
        ("invoices", PILOT_MAX_INVOICES),
        ("payments", MAX_PAYMENTS),
        ("credits", MAX_CREDITS),
        ("disputes", MAX_DISPUTE_EVENTS),
    ):
        if type(root[key]) is not list:
            raise InputError(f"packet.{key}: expected array")
        if len(root[key]) > limit:
            raise InputError(f"packet.{key}: limit {limit} exceeded")

    invoices: list[dict[str, Any]] = []
    invoice_ids: set[str] = set()
    evidence_seen: set[str] = set()
    for idx, raw in enumerate(root["invoices"]):
        where = f"packet.invoices[{idx}]"
        row = _exact_keys(
            raw,
            {
                "invoice_id",
                "account_id",
                "issue_date",
                "due_date",
                "amount_minor",
                "state",
                "evidence_sha256",
            },
            where,
        )
        invoice_id = _id(row["invoice_id"], f"{where}.invoice_id")
        if invoice_id in invoice_ids:
            raise InputError(f"{where}.invoice_id: duplicate {invoice_id}")
        invoice_ids.add(invoice_id)
        issue = _date(row["issue_date"], f"{where}.issue_date")
        due = _date(row["due_date"], f"{where}.due_date")
        if due < issue:
            raise InputError(f"{where}: due_date precedes issue_date")
        evidence = _sha(row["evidence_sha256"], f"{where}.evidence_sha256")
        if evidence in evidence_seen:
            raise InputError(f"{where}.evidence_sha256: evidence replay")
        evidence_seen.add(evidence)
        invoices.append(
            {
                "invoice_id": invoice_id,
                "account_id": _id(row["account_id"], f"{where}.account_id"),
                "issue_date": issue.isoformat(),
                "due_date": due.isoformat(),
                "amount_minor": _integer(
                    row["amount_minor"],
                    f"{where}.amount_minor",
                    low=1,
                    high=10**15,
                ),
                "state": _enum(
                    row["state"], {"OPEN", "VOID"}, f"{where}.state"
                ),
                "evidence_sha256": evidence,
            }
        )

    def event_evidence(raw_sha: Any, where: str) -> str:
        digest = _sha(raw_sha, where)
        if digest in evidence_seen:
            raise InputError(f"{where}: evidence replay across rows")
        evidence_seen.add(digest)
        return digest

    payments: list[dict[str, Any]] = []
    payment_ids: set[str] = set()
    for idx, raw in enumerate(root["payments"]):
        where = f"packet.payments[{idx}]"
        row = _exact_keys(
            raw,
            {
                "payment_id",
                "account_id",
                "invoice_id",
                "amount_minor",
                "currency",
                "observed_at",
                "evidence_sha256",
            },
            where,
        )
        payment_id = _id(row["payment_id"], f"{where}.payment_id")
        if payment_id in payment_ids:
            raise InputError(f"{where}.payment_id: duplicate {payment_id}")
        payment_ids.add(payment_id)
        invoice_id = (
            None
            if row["invoice_id"] is None
            else _id(row["invoice_id"], f"{where}.invoice_id")
        )
        payments.append(
            {
                "payment_id": payment_id,
                "account_id": _id(row["account_id"], f"{where}.account_id"),
                "invoice_id": invoice_id,
                "amount_minor": _integer(
                    row["amount_minor"],
                    f"{where}.amount_minor",
                    low=1,
                    high=10**15,
                ),
                "currency": _currency(row["currency"], f"{where}.currency"),
                "observed_at": _utc(
                    row["observed_at"], f"{where}.observed_at"
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "evidence_sha256": event_evidence(
                    row["evidence_sha256"], f"{where}.evidence_sha256"
                ),
            }
        )

    credits: list[dict[str, Any]] = []
    credit_ids: set[str] = set()
    for idx, raw in enumerate(root["credits"]):
        where = f"packet.credits[{idx}]"
        row = _exact_keys(
            raw,
            {
                "credit_id",
                "account_id",
                "invoice_id",
                "amount_minor",
                "currency",
                "observed_at",
                "evidence_sha256",
            },
            where,
        )
        credit_id = _id(row["credit_id"], f"{where}.credit_id")
        if credit_id in credit_ids:
            raise InputError(f"{where}.credit_id: duplicate {credit_id}")
        credit_ids.add(credit_id)
        credits.append(
            {
                "credit_id": credit_id,
                "account_id": _id(row["account_id"], f"{where}.account_id"),
                "invoice_id": _id(row["invoice_id"], f"{where}.invoice_id"),
                "amount_minor": _integer(
                    row["amount_minor"],
                    f"{where}.amount_minor",
                    low=1,
                    high=10**15,
                ),
                "currency": _currency(row["currency"], f"{where}.currency"),
                "observed_at": _utc(
                    row["observed_at"], f"{where}.observed_at"
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "evidence_sha256": event_evidence(
                    row["evidence_sha256"], f"{where}.evidence_sha256"
                ),
            }
        )

    disputes: list[dict[str, Any]] = []
    dispute_event_ids: set[str] = set()
    for idx, raw in enumerate(root["disputes"]):
        where = f"packet.disputes[{idx}]"
        row = _exact_keys(
            raw,
            {
                "event_id",
                "dispute_id",
                "account_id",
                "invoice_id",
                "state",
                "observed_at",
                "evidence_sha256",
            },
            where,
        )
        event_id = _id(row["event_id"], f"{where}.event_id")
        if event_id in dispute_event_ids:
            raise InputError(f"{where}.event_id: duplicate {event_id}")
        dispute_event_ids.add(event_id)
        disputes.append(
            {
                "event_id": event_id,
                "dispute_id": _id(row["dispute_id"], f"{where}.dispute_id"),
                "account_id": _id(row["account_id"], f"{where}.account_id"),
                "invoice_id": _id(row["invoice_id"], f"{where}.invoice_id"),
                "state": _enum(
                    row["state"], {"OPEN", "RESOLVED"}, f"{where}.state"
                ),
                "observed_at": _utc(
                    row["observed_at"], f"{where}.observed_at"
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "evidence_sha256": event_evidence(
                    row["evidence_sha256"], f"{where}.evidence_sha256"
                ),
            }
        )

    return {
        "schema": SCHEMA,
        "analysis_date": analysis.isoformat(),
        "currency": currency,
        "grace_days": grace,
        "invoices": sorted(invoices, key=lambda row: row["invoice_id"]),
        "payments": sorted(payments, key=lambda row: row["payment_id"]),
        "credits": sorted(credits, key=lambda row: row["credit_id"]),
        "disputes": sorted(disputes, key=lambda row: row["event_id"]),
    }


def _conflict(
    conflicts: list[dict[str, Any]],
    code: str,
    row_kind: str,
    row_id: str,
    invoice_id: str | None,
) -> None:
    conflicts.append(
        {
            "code": code,
            "row_kind": row_kind,
            "row_id": row_id,
            "invoice_id": invoice_id,
        }
    )


def compile_report(packet: Any) -> dict[str, Any]:
    normalized = _validate_packet(packet)
    analysis = date.fromisoformat(normalized["analysis_date"])
    currency = normalized["currency"]
    grace = normalized["grace_days"]
    invoices = {row["invoice_id"]: row for row in normalized["invoices"]}
    applied_payments = {invoice_id: 0 for invoice_id in invoices}
    applied_credits = {invoice_id: 0 for invoice_id in invoices}
    conflict_invoice_ids: set[str] = set()
    future_invoice_ids: set[str] = set()
    conflicts: list[dict[str, Any]] = []
    valid_unapplied: list[dict[str, Any]] = []

    def event_date(row: dict[str, Any]) -> date:
        return datetime.strptime(row["observed_at"], "%Y-%m-%dT%H:%M:%SZ").date()

    for invoice_id, invoice in invoices.items():
        if date.fromisoformat(invoice["issue_date"]) > analysis:
            future_invoice_ids.add(invoice_id)
            conflict_invoice_ids.add(invoice_id)
            _conflict(
                conflicts,
                "INVOICE_AFTER_ANALYSIS_DATE",
                "INVOICE",
                invoice_id,
                invoice_id,
            )

    for row in normalized["payments"]:
        target = row["invoice_id"]
        observed = event_date(row)
        if row["currency"] != currency:
            _conflict(
                conflicts,
                "PAYMENT_CURRENCY_MISMATCH",
                "PAYMENT",
                row["payment_id"],
                target,
            )
            if target in invoices:
                conflict_invoice_ids.add(target)
            continue
        if observed > analysis:
            _conflict(
                conflicts,
                "PAYMENT_AFTER_ANALYSIS_DATE",
                "PAYMENT",
                row["payment_id"],
                target,
            )
            if target in invoices:
                conflict_invoice_ids.add(target)
            continue
        if target is None:
            valid_unapplied.append(row)
            continue
        invoice = invoices.get(target)
        if invoice is None:
            _conflict(
                conflicts,
                "PAYMENT_UNKNOWN_INVOICE",
                "PAYMENT",
                row["payment_id"],
                target,
            )
            continue
        if observed < date.fromisoformat(invoice["issue_date"]):
            _conflict(
                conflicts,
                "PAYMENT_BEFORE_INVOICE",
                "PAYMENT",
                row["payment_id"],
                target,
            )
            conflict_invoice_ids.add(target)
            continue
        if row["account_id"] != invoice["account_id"]:
            _conflict(
                conflicts,
                "PAYMENT_ACCOUNT_MISMATCH",
                "PAYMENT",
                row["payment_id"],
                target,
            )
            conflict_invoice_ids.add(target)
            continue
        if invoice["state"] == "VOID":
            _conflict(
                conflicts,
                "PAYMENT_TO_VOID_INVOICE",
                "PAYMENT",
                row["payment_id"],
                target,
            )
            conflict_invoice_ids.add(target)
            continue
        applied_payments[target] += row["amount_minor"]

    for row in normalized["credits"]:
        target = row["invoice_id"]
        observed = event_date(row)
        if row["currency"] != currency:
            _conflict(
                conflicts,
                "CREDIT_CURRENCY_MISMATCH",
                "CREDIT",
                row["credit_id"],
                target,
            )
            if target in invoices:
                conflict_invoice_ids.add(target)
            continue
        if observed > analysis:
            _conflict(
                conflicts,
                "CREDIT_AFTER_ANALYSIS_DATE",
                "CREDIT",
                row["credit_id"],
                target,
            )
            if target in invoices:
                conflict_invoice_ids.add(target)
            continue
        invoice = invoices.get(target)
        if invoice is None:
            _conflict(
                conflicts,
                "CREDIT_UNKNOWN_INVOICE",
                "CREDIT",
                row["credit_id"],
                target,
            )
            continue
        if observed < date.fromisoformat(invoice["issue_date"]):
            _conflict(
                conflicts,
                "CREDIT_BEFORE_INVOICE",
                "CREDIT",
                row["credit_id"],
                target,
            )
            conflict_invoice_ids.add(target)
            continue
        if row["account_id"] != invoice["account_id"]:
            _conflict(
                conflicts,
                "CREDIT_ACCOUNT_MISMATCH",
                "CREDIT",
                row["credit_id"],
                target,
            )
            conflict_invoice_ids.add(target)
            continue
        if invoice["state"] == "VOID":
            _conflict(
                conflicts,
                "CREDIT_TO_VOID_INVOICE",
                "CREDIT",
                row["credit_id"],
                target,
            )
            conflict_invoice_ids.add(target)
            continue
        applied_credits[target] += row["amount_minor"]

    case_latest: dict[tuple[str, str], dict[str, Any]] = {}
    case_same_time_conflict: set[tuple[str, str]] = set()
    for row in normalized["disputes"]:
        target = row["invoice_id"]
        observed = event_date(row)
        if observed > analysis:
            _conflict(
                conflicts,
                "DISPUTE_AFTER_ANALYSIS_DATE",
                "DISPUTE",
                row["event_id"],
                target,
            )
            if target in invoices:
                conflict_invoice_ids.add(target)
            continue
        invoice = invoices.get(target)
        if invoice is None:
            _conflict(
                conflicts,
                "DISPUTE_UNKNOWN_INVOICE",
                "DISPUTE",
                row["event_id"],
                target,
            )
            continue
        if observed < date.fromisoformat(invoice["issue_date"]):
            _conflict(
                conflicts,
                "DISPUTE_BEFORE_INVOICE",
                "DISPUTE",
                row["event_id"],
                target,
            )
            conflict_invoice_ids.add(target)
            continue
        if row["account_id"] != invoice["account_id"]:
            _conflict(
                conflicts,
                "DISPUTE_ACCOUNT_MISMATCH",
                "DISPUTE",
                row["event_id"],
                target,
            )
            conflict_invoice_ids.add(target)
            continue
        key = (target, row["dispute_id"])
        prior = case_latest.get(key)
        if prior is None or row["observed_at"] > prior["observed_at"]:
            case_latest[key] = row
        elif (
            row["observed_at"] == prior["observed_at"]
            and row["state"] != prior["state"]
        ):
            case_same_time_conflict.add(key)
            conflict_invoice_ids.add(target)
            _conflict(
                conflicts,
                "DISPUTE_SAME_TIME_CONFLICT",
                "DISPUTE",
                row["event_id"],
                target,
            )

    open_disputes = {
        invoice_id
        for (invoice_id, dispute_id), row in case_latest.items()
        if (invoice_id, dispute_id) not in case_same_time_conflict
        and row["state"] == "OPEN"
    }

    invoice_rows: list[dict[str, Any]] = []
    totals = {
        "billed_minor": 0,
        "applied_payment_minor": 0,
        "applied_credit_minor": 0,
        "known_outstanding_minor": 0,
        "recovery_candidate_minor": 0,
        "disputed_outstanding_minor": 0,
        "unapplied_payment_minor": sum(
            row["amount_minor"] for row in valid_unapplied
        ),
        "conflicted_face_value_minor": 0,
    }

    for invoice_id in sorted(invoices):
        invoice = invoices[invoice_id]
        amount = invoice["amount_minor"]
        paid = applied_payments[invoice_id]
        credited = applied_credits[invoice_id]
        economic_eligible = invoice_id not in future_invoice_ids

        if invoice["state"] == "OPEN" and economic_eligible:
            totals["billed_minor"] += amount
            totals["applied_payment_minor"] += paid
            totals["applied_credit_minor"] += credited
        if (
            invoice["state"] == "OPEN"
            and economic_eligible
            and paid + credited > amount
        ):
            conflict_invoice_ids.add(invoice_id)
            _conflict(
                conflicts,
                "INVOICE_OVER_APPLIED",
                "INVOICE",
                invoice_id,
                invoice_id,
            )

        balance = (
            max(amount - paid - credited, 0)
            if invoice["state"] == "OPEN" and economic_eligible
            else 0
        )
        dispute_open = invoice_id in open_disputes

        if invoice_id in conflict_invoice_ids:
            status = "CONFLICT"
            totals["conflicted_face_value_minor"] += amount
        elif invoice["state"] == "VOID":
            status = "VOID"
        elif balance == 0:
            status = "PAID"
        elif dispute_open:
            status = "DISPUTED_HOLD"
            totals["known_outstanding_minor"] += balance
            totals["disputed_outstanding_minor"] += balance
        else:
            overdue = analysis > (
                date.fromisoformat(invoice["due_date"]) + timedelta(days=grace)
            )
            touched = paid + credited > 0
            status = (
                "PARTIAL_OVERDUE"
                if overdue and touched
                else "OVERDUE"
                if overdue
                else "PARTIAL"
                if touched
                else "OPEN"
            )
            totals["known_outstanding_minor"] += balance
            if status in {"OVERDUE", "PARTIAL_OVERDUE"}:
                totals["recovery_candidate_minor"] += balance

        review = (
            "RECONCILE_INTEGRITY_CONFLICT"
            if status == "CONFLICT"
            else "OWNER_REVIEW_DISPUTE"
            if status == "DISPUTED_HOLD"
            else "OWNER_REVIEW_POTENTIAL_LEAKAGE"
            if status in {"OVERDUE", "PARTIAL_OVERDUE"}
            else "NO_ACTION_FROM_DIAGNOSTIC"
        )
        invoice_rows.append(
            {
                "invoice_id": invoice_id,
                "account_id": invoice["account_id"],
                "status": status,
                "face_value_minor": amount,
                "applied_payment_minor": paid,
                "applied_credit_minor": credited,
                "balance_minor": balance,
                "open_dispute": dispute_open,
                "review": review,
            }
        )

    core = {
        "schema": REPORT_SCHEMA,
        "source_schema": SCHEMA,
        "source_sha256": sha256_hex(canonical_bytes(normalized)),
        "analysis_date": normalized["analysis_date"],
        "currency": currency,
        "grace_days": grace,
        "commercial_reference": {
            "pilot_price_usd_minor": PILOT_PRICE_USD_MINOR,
            "pilot_max_invoices": PILOT_MAX_INVOICES,
            "state": "REFERENCE_NOT_ACCEPTED",
        },
        "summary": {
            "invoice_count": len(normalized["invoices"]),
            "payment_count": len(normalized["payments"]),
            "credit_count": len(normalized["credits"]),
            "dispute_event_count": len(normalized["disputes"]),
            "conflict_count": len(conflicts),
            **totals,
        },
        "invoices": invoice_rows,
        "unapplied_payments": [
            {
                "payment_id": row["payment_id"],
                "account_id": row["account_id"],
                "amount_minor": row["amount_minor"],
                "review": "RECONCILE_UNAPPLIED_PAYMENT",
            }
            for row in sorted(valid_unapplied, key=lambda row: row["payment_id"])
        ],
        "integrity_conflicts": sorted(
            conflicts,
            key=lambda row: (row["code"], row["row_kind"], row["row_id"]),
        ),
        "authority": {
            "customer_contact_authorized": False,
            "collections_authorized": False,
            "accounting_write_authorized": False,
            "payment_provider_write_authorized": False,
            "legal_debt_determined": False,
            "revenue_recognized": False,
            "cash_received_inferred": False,
        },
        "truth_boundary": (
            "Evidence-only reconciliation. Balances and recovery candidates are "
            "diagnostic findings, not legal debt, collection authority, recognized "
            "revenue, or cash receipt."
        ),
    }
    return {**core, "receipt_sha256": sha256_hex(canonical_bytes(core))}


def verify_report(packet: Any, report: Any) -> bool:
    if type(report) is not dict:
        return False
    try:
        expected = compile_report(packet)
    except InputError:
        return False
    return canonical_bytes(expected) == canonical_bytes(report)


def _money(minor: int, currency: str) -> str:
    if currency != SUPPORTED_CURRENCY:
        raise InputError(
            f"report currency {currency!r} is unsupported by the v1 Markdown renderer"
        )
    return f"USD {minor // 100:,}.{minor % 100:02d}"


def render_markdown(report: dict[str, Any]) -> str:
    if report.get("schema") != REPORT_SCHEMA:
        raise InputError("report schema mismatch")
    currency = report["currency"]
    if currency != SUPPORTED_CURRENCY:
        raise InputError(
            f"report currency {currency!r} is unsupported by the v1 Markdown renderer"
        )
    summary = report["summary"]
    lines = [
        "# Accounts Receivable Leakage Desk",
        "",
        f"Analysis date: `{report['analysis_date']}`  ",
        f"Receipt: `{report['receipt_sha256']}`  ",
        f"Source: `{report['source_sha256']}`",
        "",
        "## Evidence summary",
        "",
        f"- Invoices: **{summary['invoice_count']}**",
        f"- Known outstanding: **{_money(summary['known_outstanding_minor'], currency)}**",
        f"- Potential leakage queue: **{_money(summary['recovery_candidate_minor'], currency)}**",
        f"- Disputed outstanding (HOLD): **{_money(summary['disputed_outstanding_minor'], currency)}**",
        f"- Unapplied payment evidence: **{_money(summary['unapplied_payment_minor'], currency)}**",
        f"- Integrity conflicts: **{summary['conflict_count']}**",
        "",
        "## Invoice review queue",
        "",
        "| Invoice | Account | State | Balance | Review |",
        "|---|---|---:|---:|---|",
    ]
    review_rows = [
        row
        for row in report["invoices"]
        if row["review"] != "NO_ACTION_FROM_DIAGNOSTIC"
    ]
    lines.extend(
        f"| `{row['invoice_id']}` | `{row['account_id']}` | {row['status']} | "
        f"{_money(row['balance_minor'], currency)} | {row['review']} |"
        for row in review_rows
    )
    if not review_rows:
        lines.append("| — | — | — | — | No diagnostic review rows |")

    lines.extend(["", "## Integrity conflicts", ""])
    conflicts = report["integrity_conflicts"]
    if conflicts:
        lines.extend(
            [
                "| Code | Row kind | Row ID | Invoice |",
                "|---|---|---|---|",
            ]
        )
        for conflict in conflicts:
            invoice_id = conflict["invoice_id"]
            invoice_cell = f"`{invoice_id}`" if invoice_id is not None else "—"
            lines.append(
                f"| `{conflict['code']}` | {conflict['row_kind']} | "
                f"`{conflict['row_id']}` | {invoice_cell} |"
            )
    else:
        lines.append("- None in this packet.")

    lines.extend(["", "## Unapplied payments", ""])
    if report["unapplied_payments"]:
        lines.extend(
            f"- `{row['payment_id']}` / `{row['account_id']}`: "
            f"{_money(row['amount_minor'], currency)} — reconcile; do not guess an invoice."
            for row in report["unapplied_payments"]
        )
    else:
        lines.append("- None in this packet.")

    lines.extend(
        [
            "",
            "## Truth boundary",
            "",
            report["truth_boundary"],
            "",
            (
                "Reference service scope: $2,500 fixed diagnostic for one sanitized "
                "USD export generation up to 5,000 invoices. Integration, writeback "
                "and collections are excluded unless separately scoped and accepted."
            ),
            "",
        ]
    )
    return "\n".join(lines)
