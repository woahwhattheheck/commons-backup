from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INPUT_SCHEMA = "commons.service-deal-economics.input/v1"
REPORT_SCHEMA = "commons.service-deal-economics.report/v1"
VERIFY_SCHEMA = "commons.service-deal-economics.current-verification/v1"
MAX_INPUT_BYTES = 1024 * 1024
MAX_SAFE_INT = 9_000_000_000_000_000
MAX_ITEMS = 256
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class DealEconomicsError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise DealEconomicsError(f"non-finite JSON number is not allowed: {value}")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DealEconomicsError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def parse_strict_json(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except DealEconomicsError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DealEconomicsError(f"invalid JSON: {exc}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _plain_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise DealEconomicsError(f"{label} must be a plain object")
    return value


def _plain_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise DealEconomicsError(f"{label} must be a plain array")
    return value


def _exact_keys(value: dict[str, Any], keys: set[str], label: str) -> None:
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise DealEconomicsError(f"{label} keys mismatch; missing={missing}, extra={extra}")


def _safe_int(value: Any, label: str, minimum: int = 0, maximum: int = MAX_SAFE_INT) -> int:
    if type(value) is not int:
        raise DealEconomicsError(f"{label} must be an integer")
    if value < minimum or value > maximum:
        raise DealEconomicsError(f"{label} outside allowed range")
    return value


def _text(value: Any, label: str, max_len: int = 128) -> str:
    if type(value) is not str or not value or len(value) > max_len or not ID_RE.fullmatch(value):
        raise DealEconomicsError(f"{label} must be an opaque identifier")
    return value


def _sha(value: Any, label: str) -> str:
    if type(value) is not str or not SHA256_RE.fullmatch(value):
        raise DealEconomicsError(f"{label} must be lowercase SHA-256 hex")
    return value


def _currency(value: Any, label: str) -> str:
    if type(value) is not str or not CURRENCY_RE.fullmatch(value):
        raise DealEconomicsError(f"{label} must be an ISO-style three-letter uppercase currency")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if type(value) is not str or not UTC_RE.fullmatch(value):
        raise DealEconomicsError(f"{label} must be canonical whole-second UTC")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise DealEconomicsError(f"{label} is not a valid timestamp") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise DealEconomicsError(f"{label} must be canonical whole-second UTC")
    return dt


def _utc_string(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise DealEconomicsError("trusted time must be timezone-aware")
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def trusted_time(value: datetime | str, label: str = "as_of") -> tuple[datetime, str]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise DealEconomicsError(f"{label} must be timezone-aware")
        dt = value.astimezone(timezone.utc).replace(microsecond=0)
        return dt, _utc_string(dt)
    if type(value) is str:
        dt = _timestamp(value, label)
        return dt, value
    raise DealEconomicsError(f"{label} must be datetime or canonical UTC string")


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def ceil_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise DealEconomicsError("division denominator must be positive")
    return (numerator + denominator - 1) // denominator


def _source_fields(obj: dict[str, Any], label: str) -> tuple[str, str, datetime]:
    return (
        _text(obj["source_ref"], f"{label}.source_ref"),
        _sha(obj["source_sha256"], f"{label}.source_sha256"),
        _timestamp(obj["observed_at"], f"{label}.observed_at"),
    )


def _validate_input(packet: Any) -> dict[str, Any]:
    packet = _plain_dict(packet, "input")
    _exact_keys(packet, {"schema", "policy", "deal", "capacity"}, "input")
    if packet["schema"] != INPUT_SCHEMA:
        raise DealEconomicsError("input schema mismatch")

    policy = _plain_dict(packet["policy"], "policy")
    _exact_keys(
        policy,
        {
            "policy_id", "generation", "currency", "minimum_gross_margin_bps", "risk_reserve_bps",
            "snapshot_max_age_hours", "quote_validity_hours", "source_ref", "source_sha256", "observed_at",
        },
        "policy",
    )
    _text(policy["policy_id"], "policy.policy_id")
    _safe_int(policy["generation"], "policy.generation", 1, 1_000_000)
    _currency(policy["currency"], "policy.currency")
    margin = _safe_int(policy["minimum_gross_margin_bps"], "policy.minimum_gross_margin_bps", 0, 9500)
    risk = _safe_int(policy["risk_reserve_bps"], "policy.risk_reserve_bps", 0, 50_000)
    _safe_int(policy["snapshot_max_age_hours"], "policy.snapshot_max_age_hours", 1, 24 * 365)
    _safe_int(policy["quote_validity_hours"], "policy.quote_validity_hours", 1, 24 * 90)
    _source_fields(policy, "policy")
    if margin >= 10_000:
        raise DealEconomicsError("minimum gross margin must be below 10000 bps")
    if risk > 50_000:
        raise DealEconomicsError("risk reserve too large")

    deal = _plain_dict(packet["deal"], "deal")
    _exact_keys(
        deal,
        {
            "deal_id", "scope_id", "scope_revision", "currency", "target_price_cents", "delivery_start",
            "delivery_end", "source_ref", "source_sha256", "observed_at", "items",
        },
        "deal",
    )
    _text(deal["deal_id"], "deal.deal_id")
    _text(deal["scope_id"], "deal.scope_id")
    _safe_int(deal["scope_revision"], "deal.scope_revision", 1, 1_000_000)
    _currency(deal["currency"], "deal.currency")
    _safe_int(deal["target_price_cents"], "deal.target_price_cents", 1, MAX_SAFE_INT)
    delivery_start = _timestamp(deal["delivery_start"], "deal.delivery_start")
    delivery_end = _timestamp(deal["delivery_end"], "deal.delivery_end")
    if delivery_end <= delivery_start:
        raise DealEconomicsError("delivery_end must be after delivery_start")
    _source_fields(deal, "deal")
    items = _plain_list(deal["items"], "deal.items")
    if not items or len(items) > MAX_ITEMS:
        raise DealEconomicsError("deal.items must contain 1..256 entries")
    seen_ids: set[str] = set()
    for index, item_value in enumerate(items):
        item = _plain_dict(item_value, f"deal.items[{index}]")
        _exact_keys(
            item,
            {"item_id", "planned_minutes", "internal_rate_cents_per_hour", "external_cost_cents", "source_ref", "source_sha256", "observed_at"},
            f"deal.items[{index}]",
        )
        item_id = _text(item["item_id"], f"deal.items[{index}].item_id")
        if item_id in seen_ids:
            raise DealEconomicsError(f"duplicate item_id: {item_id}")
        seen_ids.add(item_id)
        _safe_int(item["planned_minutes"], f"deal.items[{index}].planned_minutes", 1, 10_000_000)
        _safe_int(item["internal_rate_cents_per_hour"], f"deal.items[{index}].internal_rate_cents_per_hour", 1, 100_000_000)
        _safe_int(item["external_cost_cents"], f"deal.items[{index}].external_cost_cents", 0, MAX_SAFE_INT)
        _source_fields(item, f"deal.items[{index}]")

    capacity = _plain_dict(packet["capacity"], "capacity")
    _exact_keys(
        capacity,
        {"snapshot_id", "window_start", "window_end", "total_minutes", "reserved_minutes", "source_ref", "source_sha256", "observed_at"},
        "capacity",
    )
    _text(capacity["snapshot_id"], "capacity.snapshot_id")
    _timestamp(capacity["window_start"], "capacity.window_start")
    _timestamp(capacity["window_end"], "capacity.window_end")
    _safe_int(capacity["total_minutes"], "capacity.total_minutes", 0, 100_000_000)
    _safe_int(capacity["reserved_minutes"], "capacity.reserved_minutes", 0, 100_000_000)
    _source_fields(capacity, "capacity")

    return packet


def _evidence_findings(packet: dict[str, Any], as_of: datetime) -> list[str]:
    policy = packet["policy"]
    deal = packet["deal"]
    capacity = packet["capacity"]
    max_age = timedelta(hours=policy["snapshot_max_age_hours"])
    findings: list[str] = []

    if policy["currency"] != deal["currency"]:
        findings.append("CURRENCY_MISMATCH")
    if capacity["window_start"] != deal["delivery_start"] or capacity["window_end"] != deal["delivery_end"]:
        findings.append("CAPACITY_WINDOW_MISMATCH")
    if capacity["reserved_minutes"] > capacity["total_minutes"]:
        findings.append("CAPACITY_OVERDRAWN")

    evidence_rows: list[tuple[str, datetime]] = [
        ("POLICY", _timestamp(policy["observed_at"], "policy.observed_at")),
        ("DEAL", _timestamp(deal["observed_at"], "deal.observed_at")),
        ("CAPACITY", _timestamp(capacity["observed_at"], "capacity.observed_at")),
    ]
    for item in deal["items"]:
        evidence_rows.append((f"ITEM:{item['item_id']}", _timestamp(item["observed_at"], f"item:{item['item_id']}.observed_at")))

    for name, observed in evidence_rows:
        if observed > as_of:
            findings.append(f"FUTURE_EVIDENCE:{name}")
        elif as_of - observed > max_age:
            findings.append(f"STALE_EVIDENCE:{name}")

    delivery_start = _timestamp(deal["delivery_start"], "deal.delivery_start")
    if delivery_start <= as_of:
        findings.append("DELIVERY_WINDOW_ALREADY_STARTED")

    return sorted(set(findings))


def _canonical_input(packet: dict[str, Any]) -> dict[str, Any]:
    # Input line-item order is not economic meaning. Canonicalize it before
    # content addressing so harmless serialization order cannot fork receipts.
    return {
        "schema": packet["schema"],
        "policy": dict(packet["policy"]),
        "deal": {**packet["deal"], "items": sorted((dict(item) for item in packet["deal"]["items"]), key=lambda item: item["item_id"])},
        "capacity": dict(packet["capacity"]),
    }


def _semantic_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "input_sha256": report["input_sha256"],
        "deal": report["deal"],
        "economics": report["economics"],
        "capacity": report["capacity"],
        "disposition": report["disposition"],
        "reasons": report["reasons"],
        "authority": report["authority"],
    }


def compile_report(packet: Any, as_of: datetime | str) -> dict[str, Any]:
    packet = _validate_input(packet)
    as_of_dt, as_of_text = trusted_time(as_of)
    policy = packet["policy"]
    deal = packet["deal"]
    capacity = packet["capacity"]

    line_results: list[dict[str, Any]] = []
    labor_cost_total = 0
    external_cost_total = 0
    demand_minutes = 0
    for item in sorted(deal["items"], key=lambda row: row["item_id"]):
        labor_cost = ceil_div(item["planned_minutes"] * item["internal_rate_cents_per_hour"], 60)
        direct_item_cost = labor_cost + item["external_cost_cents"]
        if direct_item_cost > MAX_SAFE_INT:
            raise DealEconomicsError("item cost overflow")
        labor_cost_total += labor_cost
        external_cost_total += item["external_cost_cents"]
        demand_minutes += item["planned_minutes"]
        if max(labor_cost_total, external_cost_total, demand_minutes) > MAX_SAFE_INT:
            raise DealEconomicsError("aggregate overflow")
        line_results.append(
            {
                "item_id": item["item_id"],
                "planned_minutes": item["planned_minutes"],
                "internal_rate_cents_per_hour": item["internal_rate_cents_per_hour"],
                "labor_cost_cents": labor_cost,
                "external_cost_cents": item["external_cost_cents"],
                "direct_cost_cents": direct_item_cost,
                "source_ref": item["source_ref"],
                "source_sha256": item["source_sha256"],
            }
        )

    direct_cost = labor_cost_total + external_cost_total
    risk_reserve = ceil_div(direct_cost * policy["risk_reserve_bps"], 10_000) if direct_cost else 0
    loaded_cost = direct_cost + risk_reserve
    if loaded_cost > MAX_SAFE_INT:
        raise DealEconomicsError("loaded cost overflow")
    margin_denominator = 10_000 - policy["minimum_gross_margin_bps"]
    minimum_price = ceil_div(loaded_cost * 10_000, margin_denominator)
    if minimum_price > MAX_SAFE_INT:
        raise DealEconomicsError("minimum price overflow")
    target_price = deal["target_price_cents"]
    margin_numerator = (target_price - loaded_cost) * 10_000
    modeled_margin_bps = margin_numerator // target_price

    available_minutes = max(capacity["total_minutes"] - capacity["reserved_minutes"], 0)
    shortfall_minutes = max(demand_minutes - available_minutes, 0)

    evidence_findings = _evidence_findings(packet, as_of_dt)
    margin_hold = target_price < minimum_price
    capacity_hold = shortfall_minutes > 0
    reasons: list[str] = list(evidence_findings)
    if not evidence_findings:
        if margin_hold:
            reasons.append("TARGET_PRICE_BELOW_MARGIN_FLOOR")
        if capacity_hold:
            reasons.append("DELIVERY_CAPACITY_SHORTFALL")
        if margin_hold and capacity_hold:
            disposition = "HOLD_MARGIN_AND_CAPACITY"
        elif margin_hold:
            disposition = "HOLD_MARGIN"
        elif capacity_hold:
            disposition = "HOLD_CAPACITY"
        else:
            disposition = "READY_FOR_OWNER_QUOTE_REVIEW"
    else:
        disposition = "HOLD_EVIDENCE"

    quote_valid_until_dt = min(
        as_of_dt + timedelta(hours=policy["quote_validity_hours"]),
        _timestamp(deal["delivery_start"], "deal.delivery_start"),
    )

    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "input_sha256": digest(_canonical_input(packet)),
        "evaluated_at": as_of_text,
        "quote_valid_until": _utc_string(quote_valid_until_dt),
        "deal": {
            "deal_id": deal["deal_id"],
            "scope_id": deal["scope_id"],
            "scope_revision": deal["scope_revision"],
            "currency": deal["currency"],
            "target_price_cents": target_price,
            "delivery_start": deal["delivery_start"],
            "delivery_end": deal["delivery_end"],
            "quote_state": "PROPOSED_NOT_COMMITTED",
        },
        "economics": {
            "line_items": line_results,
            "labor_cost_cents": labor_cost_total,
            "external_cost_cents": external_cost_total,
            "direct_cost_cents": direct_cost,
            "risk_reserve_bps": policy["risk_reserve_bps"],
            "risk_reserve_cents": risk_reserve,
            "loaded_delivery_cost_cents": loaded_cost,
            "minimum_gross_margin_bps": policy["minimum_gross_margin_bps"],
            "minimum_price_cents": minimum_price,
            "modeled_margin_bps_at_target": modeled_margin_bps,
            "target_price_delta_to_floor_cents": target_price - minimum_price,
        },
        "capacity": {
            "snapshot_id": capacity["snapshot_id"],
            "total_minutes": capacity["total_minutes"],
            "already_reserved_minutes": capacity["reserved_minutes"],
            "available_minutes": available_minutes,
            "proposed_demand_minutes": demand_minutes,
            "shortfall_minutes": shortfall_minutes,
            "reservation_created": False,
        },
        "disposition": disposition,
        "reasons": sorted(reasons),
        "authority": {
            "buyer_contact": False,
            "quote_sent_or_committed": False,
            "buyer_acceptance": False,
            "capacity_reserved": False,
            "contract_signed": False,
            "payment_received": False,
            "cash_available": False,
            "revenue_booked_or_recognized": False,
            "staffing_committed": False,
        },
    }
    report["semantic_sha256"] = digest(_semantic_report(report))
    report["receipt_sha256"] = digest(report)
    return report


def verify_historical(packet: Any, report: Any) -> bool:
    report = _plain_dict(report, "report")
    if report.get("schema") != REPORT_SCHEMA:
        return False
    evaluated_at = report.get("evaluated_at")
    try:
        expected = compile_report(packet, evaluated_at)
    except DealEconomicsError:
        return False
    return canonical_json(expected) == canonical_json(report)


def verify_current(packet: Any, report: Any, current_as_of: datetime | str) -> dict[str, Any]:
    current_dt, current_text = trusted_time(current_as_of, "current_as_of")
    historical_ok = verify_historical(packet, report)
    report_obj = _plain_dict(report, "report")
    if not historical_ok:
        state = "INVALID_HISTORICAL_RECEIPT"
        current_report = None
    else:
        evaluated_dt = _timestamp(report_obj["evaluated_at"], "report.evaluated_at")
        valid_until = _timestamp(report_obj["quote_valid_until"], "report.quote_valid_until")
        if evaluated_dt > current_dt:
            state = "FUTURE_RECEIPT"
            current_report = None
        else:
            current_report = compile_report(packet, current_dt)
            if current_dt > valid_until:
                state = "STALE_OR_DRIFTED"
            elif current_report["semantic_sha256"] != report_obj["semantic_sha256"]:
                state = "STALE_OR_DRIFTED"
            else:
                state = "CURRENT_VERIFIED"
    result = {
        "schema": VERIFY_SCHEMA,
        "verified_at": current_text,
        "historical_receipt_valid": historical_ok,
        "state": state,
        "report_receipt_sha256": report_obj.get("receipt_sha256"),
        "current_semantic_sha256": None if current_report is None else current_report["semantic_sha256"],
        "authority": {
            "buyer_contact": False,
            "quote_sent_or_committed": False,
            "buyer_acceptance": False,
            "capacity_reserved": False,
            "payment_received": False,
            "revenue_booked_or_recognized": False,
        },
    }
    result["receipt_sha256"] = digest(result)
    return result


def render_markdown(report: Any) -> str:
    report = _plain_dict(report, "report")
    if report.get("schema") != REPORT_SCHEMA:
        raise DealEconomicsError("report schema mismatch")
    econ = report["economics"]
    cap = report["capacity"]
    deal = report["deal"]
    reasons = ", ".join(report["reasons"]) if report["reasons"] else "none"
    lines = [
        "# Service Deal Economics Desk",
        "",
        f"- Deal: `{deal['deal_id']}` / scope `{deal['scope_id']}` rev {deal['scope_revision']}",
        f"- Disposition: **{report['disposition']}**",
        f"- Currency: `{deal['currency']}`",
        f"- Target price: {deal['target_price_cents']} cents",
        f"- Minimum price at policy margin: {econ['minimum_price_cents']} cents",
        f"- Loaded delivery cost: {econ['loaded_delivery_cost_cents']} cents",
        f"- Modeled margin at target: {econ['modeled_margin_bps_at_target']} bps",
        f"- Capacity: {cap['proposed_demand_minutes']} proposed / {cap['available_minutes']} available minutes; shortfall {cap['shortfall_minutes']}",
        f"- Reasons: {reasons}",
        f"- Evaluated: `{report['evaluated_at']}`; quote evidence valid until `{report['quote_valid_until']}`",
        "",
        "## Authority ceiling",
        "",
        "This packet is owner decision support only. It does not send or commit a quote, reserve delivery capacity, establish buyer acceptance, move money, or recognize/book revenue.",
        "",
        f"Receipt: `{report['receipt_sha256']}`",
        "",
    ]
    return "\n".join(lines)


def read_json_file(path: str | os.PathLike[str]) -> Any:
    path = os.fspath(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise DealEconomicsError(f"cannot open input safely: {exc.strerror}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise DealEconomicsError("input must be a regular file")
        if before.st_size > MAX_INPUT_BYTES:
            raise DealEconomicsError("input exceeds maximum size")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                raise DealEconomicsError("input exceeds maximum size")
            chunks.append(chunk)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise DealEconomicsError("input changed during read")
        try:
            text = b"".join(chunks).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DealEconomicsError("input must be UTF-8") from exc
        return parse_strict_json(text)
    finally:
        os.close(fd)


def write_exclusive(path: str | os.PathLike[str], text: str) -> None:
    path = Path(path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise DealEconomicsError("output final path may not be a symlink")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise DealEconomicsError("output already exists") from exc
    except OSError as exc:
        raise DealEconomicsError(f"cannot create output safely: {exc.strerror}") from exc
    try:
        data = text.encode("utf-8")
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
