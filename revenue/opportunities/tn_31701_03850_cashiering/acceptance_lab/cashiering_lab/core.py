"""Deterministic reconciliation over normalized, owner-supplied closed-period data.

This is a real offline review utility, not a cashiering/ERP/payment platform.
Input integrity is not source authenticity, completeness, or regulatory compliance.
All money is integer minor units; no floating-point arithmetic is used.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any

VERSION = "0.1.1"
SCHEMA = "cashiering-acceptance/1"
MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 20_000
MAX_MONEY = 10**15
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}\Z")
TENDERS = {"CASH", "CHECK", "CARD", "ACH", "OTHER"}
SCOPE = ("agency", "business_unit", "department", "location", "bank_account", "currency")
AUTHORITY = {"payment_processing": False, "money_movement": False,
             "erp_posting": False, "external_contact": False,
             "source_authenticity_attested": False, "compliance_certified": False}


class InputError(ValueError):
    """Malformed, ambiguous, or unsupported input; no usable report is issued."""


def _fail(path: str, message: str) -> None:
    raise InputError(f"{path}: {message}")


def _object(value: Any, keys: set[str], path: str) -> dict:
    if type(value) is not dict:
        _fail(path, "must be an object")
    if set(value) != keys:
        _fail(path, f"fields must be exactly {', '.join(sorted(keys))}")
    return value


def _text(value: Any, path: str, *, identifier: bool = False) -> str:
    if type(value) is not str or not 1 <= len(value) <= 240:
        _fail(path, "must be a nonempty string of at most 240 characters")
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        _fail(path, "control characters and unpaired surrogates are unsupported")
    if identifier and not ID.fullmatch(value):
        _fail(path, "must be a stable ASCII identifier of at most 80 characters")
    return value


def _money(value: Any, path: str, *, nonnegative: bool = False, nullable: bool = False) -> int | None:
    if nullable and value is None:
        return None
    if type(value) is not int or abs(value) > MAX_MONEY:
        _fail(path, "must be integer minor units within the documented bound (not bool/float)")
    if nonnegative and value < 0:
        _fail(path, "must not be negative")
    return value


def _rows(value: Any, path: str, *, empty: bool = True) -> list:
    if type(value) is not list or len(value) > MAX_ROWS or (not empty and not value):
        _fail(path, f"must be a {'possibly empty ' if empty else 'nonempty '}list of at most {MAX_ROWS} rows")
    return value


def _time(value: Any, path: str) -> dt.datetime:
    _text(value, path)
    # Deliberate RFC3339-style subset; seconds mandatory, up to six fractional digits.
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)", value):
        _fail(path, "requires an explicit UTC offset and seconds")
    if value[-1] != "Z" and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        _fail(path, "numeric offset hours/minutes must be in 00..23/00..59")
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(dt.timezone.utc)
    except (ValueError, OverflowError):
        _fail(path, "invalid timestamp")


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON", f"duplicate key {key!r}")
        result[key] = value
    return result


def parse(raw: bytes) -> dict:
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        _fail("input", f"requires UTF-8 bytes no larger than {MAX_BYTES}")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda v: _fail("JSON", f"unsupported constant {v}"))
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, InputError):
            raise
        raise InputError(f"input is not supported strict UTF-8 JSON: {type(exc).__name__}") from exc
    validate(data)
    return data


def _unique(rows: list, path: str) -> dict[str, dict]:
    result = {}
    for i, row in enumerate(rows):
        if type(row) is not dict or "id" not in row:
            _fail(f"{path}[{i}]", "object with id required")
        key = _text(row["id"], f"{path}[{i}].id", identifier=True)
        if key in result:
            _fail(path, f"duplicate id {key}")
        result[key] = row
    return result


def validate(data: Any) -> None:
    _object(data, {"schema", "case_id", "period", "currency_scale", "variance_reason_threshold_minor",
                   "batches", "transactions", "deposits"}, "input")
    if data["schema"] != SCHEMA:
        _fail("schema", f"must equal {SCHEMA}")
    _text(data["case_id"], "case_id", identifier=True)
    period = _object(data["period"], {"start", "end"}, "period")
    start, end = _time(period["start"], "period.start"), _time(period["end"], "period.end")
    if end <= start:
        _fail("period", "end must be after start; interval is [start,end)")
    scales = data["currency_scale"]
    if type(scales) is not dict or not scales or len(scales) > 20:
        _fail("currency_scale", "requires 1 to 20 explicit currency scales")
    for currency, scale in scales.items():
        if not re.fullmatch("[A-Z]{3}", currency) or type(scale) is not int or not 0 <= scale <= 4:
            _fail("currency_scale", "requires three uppercase letters and integer scale 0..4")
    _money(data["variance_reason_threshold_minor"], "threshold", nonnegative=True)
    batches = _rows(data["batches"], "batches", empty=False)
    transactions = _rows(data["transactions"], "transactions")
    deposits = _rows(data["deposits"], "deposits")
    if len(batches) + len(transactions) + len(deposits) > MAX_ROWS:
        _fail("input", f"combined top-level row count exceeds {MAX_ROWS}")
    batch_by_id = _unique(batches, "batches")
    _unique(transactions, "transactions")
    _unique(deposits, "deposits")
    for b in batches:
        p = f"batch[{b['id']}]"
        _object(b, {"id", *SCOPE, "cashier", "opened_at", "closed_at", "opening_cash_minor",
                    "counted_cash_minor", "retained_cash_minor", "declared_total_minor", "variance_reason"}, p)
        for key in ("id", *SCOPE, "cashier"):
            _text(b[key], f"{p}.{key}", identifier=True)
        if b["currency"] not in scales:
            _fail(p, "currency must have an explicitly supplied scale")
        opened, closed = _time(b["opened_at"], p), _time(b["closed_at"], p)
        if not start <= opened < closed <= end:
            _fail(p, "batch must open and close within the review period")
        for key in ("opening_cash_minor", "retained_cash_minor"):
            _money(b[key], f"{p}.{key}", nonnegative=True)
        _money(b["counted_cash_minor"], p, nonnegative=True, nullable=True)
        _money(b["declared_total_minor"], p, nullable=True)
        if b["variance_reason"] is not None:
            _text(b["variance_reason"], p)
    total_components = 0
    for t in transactions:
        p = f"transaction[{t['id']}]"
        _object(t, {"id", "batch_id", "kind", "timestamp", "original_id", "original_minor",
                   "rounding_minor", "collected_minor", "tenders", "allocations", "evidence_ref"}, p)
        _text(t["batch_id"], p, identifier=True)
        if t["batch_id"] not in batch_by_id:
            _fail(p, "unknown batch_id")
        if type(t["kind"]) is not str or t["kind"] not in {"RECEIPT", "REFUND", "REVERSAL"}:
            _fail(p, "unsupported kind")
        _time(t["timestamp"], p)
        if t["original_id"] is not None:
            _text(t["original_id"], p, identifier=True)
        _text(t["evidence_ref"], p, identifier=True)
        for key in ("original_minor", "rounding_minor", "collected_minor"):
            _money(t[key], f"{p}.{key}")
        for key, codekey in (("tenders", "type"), ("allocations", "account_id")):
            parts = _rows(t[key], f"{p}.{key}", empty=False)
            total_components += len(parts)
            if len(parts) > 100:
                _fail(p, "at most 100 components per collection")
            codes = set()
            for part in parts:
                _object(part, {codekey, "amount_minor"}, p)
                code = _text(part[codekey], p, identifier=True)
                if code in codes:
                    _fail(p, f"duplicate {codekey}")
                codes.add(code)
                if key == "tenders" and code not in TENDERS:
                    _fail(p, "unsupported tender type")
                _money(part["amount_minor"], p)
    if total_components > 4 * MAX_ROWS:
        _fail("input", "too many tender/allocation components")
    for d in deposits:
        p = f"deposit[{d['id']}]"
        _object(d, {"id", *SCOPE, "tender", "batch_ids", "observed_minor", "variance_reason", "evidence_ref"}, p)
        for key in ("id", *SCOPE, "evidence_ref"):
            _text(d[key], p, identifier=True)
        if d["currency"] not in scales or type(d["tender"]) is not str or d["tender"] not in TENDERS:
            _fail(p, "unknown currency or tender")
        ids = _rows(d["batch_ids"], p, empty=False)
        for bid in ids:
            _text(bid, p, identifier=True)
            if bid not in batch_by_id:
                _fail(p, "unknown batch id")
        if len(ids) != len(set(ids)):
            _fail(p, "duplicate batch in deposit")
        _money(d["observed_minor"], p, nullable=True)
        if d["variance_reason"] is not None:
            _text(d["variance_reason"], p)


def _amount_map(t: dict, field: str, key: str) -> dict[str, int]:
    return {row[key]: row["amount_minor"] for row in t[field]}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def reconcile(raw: bytes) -> dict:
    data = parse(raw)
    findings = []
    threshold = data["variance_reason_threshold_minor"]
    batches = {b["id"]: b for b in data["batches"]}
    transactions = {t["id"]: t for t in data["transactions"]}
    by_batch: dict[str, list] = defaultdict(list)
    spent: dict[str, dict] = {}
    evidence_seen: dict[str, str] = {}

    def finding(code: str, entity: str, message: str, variance: int | None = None, currency: str | None = None):
        findings.append({"code": code, "entity": entity, "message": message,
                         "variance_minor": variance, "currency": currency})

    # Semantic order, not input row order. Simultaneous linked refunds are excluded explicitly.
    for t in sorted(transactions.values(), key=lambda x: (_time(x["timestamp"], "timestamp"), x["id"])):
        bid, tid = t["batch_id"], t["id"]
        b = batches[bid]
        by_batch[bid].append(t)
        stamp = _time(t["timestamp"], tid)
        if not _time(b["opened_at"], bid) <= stamp < _time(b["closed_at"], bid):
            finding("TRANSACTION_OUTSIDE_BATCH", tid, "Transaction is outside the half-open batch window.")
        source = t["evidence_ref"]
        if source in evidence_seen:
            finding("REUSED_TRANSACTION_EVIDENCE", tid, f"Evidence row also names {evidence_seen[source]}.")
        else:
            evidence_seen[source] = tid
        if t["original_minor"] + t["rounding_minor"] != t["collected_minor"]:
            finding("ROUNDING_CONSERVATION", tid, "Original plus rounding does not equal collected.")
        tm = _amount_map(t, "tenders", "type")
        am = _amount_map(t, "allocations", "account_id")
        for label, vals in (("TENDER", tm), ("ALLOCATION", am)):
            delta = sum(vals.values()) - t["collected_minor"]
            if delta:
                finding(f"{label}_CONSERVATION", tid, f"{label.title()} components do not equal collected.", delta, b["currency"])
        sign = 1 if t["kind"] == "RECEIPT" else -1
        if sign * t["collected_minor"] <= 0 or sign * t["original_minor"] <= 0:
            finding("TRANSACTION_SIGN", tid, "Receipt must be positive; refund/reversal must be negative.")
        if any(sign * v < 0 for v in list(tm.values()) + list(am.values())):
            finding("COMPONENT_SIGN", tid, "Offsetting opposite-sign components are unsupported.")
        if t["kind"] == "RECEIPT":
            if t["original_id"] is not None:
                finding("RECEIPT_HAS_ORIGINAL", tid, "A receipt must not link an original transaction.")
            continue
        original = transactions.get(t["original_id"])
        if original is None or original["kind"] != "RECEIPT":
            finding("INVALID_ORIGINAL", tid, "Refund/reversal needs a retained original receipt.")
            continue
        ob = batches[original["batch_id"]]
        if any(b[k] != ob[k] for k in SCOPE):
            finding("ORIGINAL_SCOPE_MISMATCH", tid, "Original and refund/reversal scopes differ.")
        if _time(original["timestamp"], "original") >= stamp:
            finding("ORIGINAL_NOT_EARLIER", tid, "Original must strictly precede the linked transaction.")
        state = spent.setdefault(original["id"], {"collected": 0, "original": 0, "rounding": 0,
                                                  "tenders": Counter(), "allocations": Counter(), "count": 0})
        if t["kind"] == "REVERSAL":
            exact = all(t[k] == -original[k] for k in ("original_minor", "rounding_minor", "collected_minor"))
            exact = exact and tm == {k: -v for k, v in _amount_map(original, "tenders", "type").items()}
            exact = exact and am == {k: -v for k, v in _amount_map(original, "allocations", "account_id").items()}
            if not exact or state["count"]:
                finding("FULL_REVERSAL_MISMATCH", tid, "Full reversal must exactly negate an untouched original, including rounding and components.")
        state["count"] += 1
        state["collected"] -= t["collected_minor"]
        state["original"] -= t["original_minor"]
        state["rounding"] -= t["rounding_minor"]
        state["tenders"].update({k: -v for k, v in tm.items()})
        state["allocations"].update({k: -v for k, v in am.items()})
        for key in ("collected", "original"):
            if state[key] > original[f"{key}_minor"]:
                finding("REFUND_EXCEEDS_ORIGINAL", tid, f"Cumulative {key} refund exceeds original.")
        # Partial refunds may return any not-yet-returned integer portion of the original rounding;
        # the cumulative adjustment must remain on the original interval, including negative rounding.
        r = original["rounding_minor"]
        if not min(0, r) <= state["rounding"] <= max(0, r):
            finding("REFUND_ROUNDING_EXCEEDS_ORIGINAL", tid, "Cumulative refund rounding is outside the original adjustment interval.")
        for field, codekey in (("tenders", "type"), ("allocations", "account_id")):
            allowance = _amount_map(original, field, codekey)
            if any(v < 0 or v > allowance.get(k, 0) for k, v in state[field].items()):
                finding("REFUND_COMPONENT_EXCEEDS_ORIGINAL", tid, f"Cumulative {field} refund exceeds an original component.")

    batch_rows = []
    batch_available = {}
    for bid, b in sorted(batches.items()):
        tx = by_batch[bid]
        tenders = Counter()
        for t in tx:
            tenders.update(_amount_map(t, "tenders", "type"))
        net = sum(t["collected_minor"] for t in tx)
        expected_cash = b["opening_cash_minor"] + tenders.get("CASH", 0)
        counted = b["counted_cash_minor"]
        drawer = None if counted is None else counted - expected_cash
        available_cash = None if counted is None else counted - b["retained_cash_minor"]
        if expected_cash < 0:
            finding("NEGATIVE_EXPECTED_DRAWER", bid, "Recorded cash activity exceeds available opening cash and receipts.")
        if counted is None:
            finding("MISSING_CASH_COUNT", bid, "Missing drawer evidence is not zero.")
        elif drawer:
            finding("DRAWER_VARIANCE", bid, "Counted drawer differs from opening cash plus recorded cash activity.", drawer, b["currency"])
            if abs(drawer) > threshold and b["variance_reason"] is None:
                finding("DRAWER_REASON_MISSING", bid, "Above-threshold drawer variance lacks a supplied reason.")
        if available_cash is not None and available_cash < 0:
            finding("RETAINED_CASH_EXCEEDS_COUNT", bid, "Retained float exceeds physically counted cash.")
        declared = b["declared_total_minor"]
        if declared is None:
            finding("MISSING_BATCH_DECLARATION", bid, "A declared total is required to compare to normalized rows.")
        elif declared != net:
            finding("BATCH_TOTAL_VARIANCE", bid, "Declared total differs from transaction total.", declared-net, b["currency"])
        batch_available[bid] = {**{k: v for k, v in tenders.items() if k != "CASH"}, "CASH": available_cash}
        batch_rows.append({"batch_id": bid, **{k: b[k] for k in SCOPE}, "cashier": b["cashier"],
                           "transaction_count": len(tx), "net_collected_minor": net,
                           "gross_receipts_minor": sum(t["collected_minor"] for t in tx if t["kind"] == "RECEIPT"),
                           "refund_reversal_minor": sum(t["collected_minor"] for t in tx if t["kind"] != "RECEIPT"),
                           "original_minor": sum(t["original_minor"] for t in tx),
                           "rounding_minor": sum(t["rounding_minor"] for t in tx),
                           "tender_totals_minor": dict(sorted(tenders.items())), "declared_total_minor": declared,
                           "expected_drawer_minor": expected_cash, "counted_drawer_minor": counted,
                           "drawer_variance_minor": drawer, "retained_cash_minor": b["retained_cash_minor"],
                           "available_cash_for_deposit_minor": available_cash, "variance_reason": b["variance_reason"]})

    deposit_rows = []
    coverage = {}
    deposit_evidence = {}
    for d in sorted(data["deposits"], key=lambda x: x["id"]):
        did, tender = d["id"], d["tender"]
        ref = d["evidence_ref"]
        if ref in deposit_evidence:
            finding("REUSED_DEPOSIT_EVIDENCE", did, f"Deposit evidence also names {deposit_evidence[ref]}.")
        else:
            deposit_evidence[ref] = did
        amounts = []
        scope_valid = True
        for bid in sorted(d["batch_ids"]):
            key = (bid, tender)
            if key in coverage:
                finding("BATCH_TENDER_REUSED", did, f"{bid}/{tender} is also allocated to {coverage[key]}; partial deposits are unsupported.")
            else:
                coverage[key] = did
            if any(d[k] != batches[bid][k] for k in SCOPE):
                finding("DEPOSIT_SCOPE_MISMATCH", did, f"Deposit scope differs from batch {bid}.")
                scope_valid = False
            amounts.append(batch_available[bid].get(tender, 0))
        expected = None if not scope_valid or any(a is None for a in amounts) else sum(amounts)
        observed = d["observed_minor"]
        variance = None if expected is None or observed is None else observed - expected
        if expected is None:
            finding("DEPOSIT_EXPECTATION_UNAVAILABLE", did, "Missing drawer evidence or mixed scope prevents a meaningful deposit comparison.")
        if observed is None:
            finding("MISSING_DEPOSIT_EVIDENCE", did, "No observed amount supplied; absence is not zero.")
        if variance:
            finding("DEPOSIT_VARIANCE", did, "Observed deposit differs from counted-minus-retained cash or recorded noncash activity.", variance, d["currency"])
            if abs(variance) > threshold and d["variance_reason"] is None:
                finding("DEPOSIT_REASON_MISSING", did, "Above-threshold deposit variance lacks a supplied reason.")
        deposit_rows.append({"deposit_id": did, **{k: d[k] for k in SCOPE}, "tender": tender,
                             "batch_ids": sorted(d["batch_ids"]), "expected_minor": expected,
                             "observed_minor": observed, "deposit_variance_minor": variance,
                             "variance_reason": d["variance_reason"], "evidence_ref": ref})
    for bid, available in sorted(batch_available.items()):
        for tender, amount in sorted(available.items()):
            if amount is not None and amount != 0 and (bid, tender) not in coverage:
                finding("UNASSIGNED_BATCH_TENDER", bid, f"No complete deposit assignment for {tender}.", amount, batches[bid]["currency"])

    findings.sort(key=lambda f: (f["entity"], f["code"], f["message"]))
    currency_totals = []
    for currency in sorted({b["currency"] for b in batches.values()}):
        rows = [r for r in batch_rows if r["currency"] == currency]
        currency_totals.append({"currency": currency, "scale": data["currency_scale"][currency],
                                "candidate_net_collected_minor": sum(r["net_collected_minor"] for r in rows),
                                "drawer_variances_minor": [r["drawer_variance_minor"] for r in rows],
                                "note": "Candidate row arithmetic; invalid rows are not silently removed. No cross-currency total."})
    transaction_rows = [{**t, "tenders": sorted(t["tenders"], key=lambda p: p["type"]),
                         "allocations": sorted(t["allocations"], key=lambda p: p["account_id"]),
                         "currency": batches[t["batch_id"]]["currency"]}
                        for t in sorted(transactions.values(), key=lambda x: x["id"])]
    return {"schema": "cashiering-review/1", "engine_version": VERSION,
            "case_id": data["case_id"], "input_sha256": hashlib.sha256(raw).hexdigest(),
            "status": "EXCEPTIONS" if findings else "NO_EXCEPTIONS_IN_SUPPLIED_DATA",
            "evidence_boundary": "NORMALIZED_INPUT_ONLY_NOT_SOURCE_AUTHENTICITY_OR_COMPLETENESS",
            "authority": dict(AUTHORITY), "currency_scale": data["currency_scale"],
            "period": data["period"], "findings_count": len(findings),
            "currency_totals": currency_totals, "batches": batch_rows, "deposits": deposit_rows,
            "transactions": transaction_rows, "findings": findings}
