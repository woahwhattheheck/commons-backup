#!/usr/bin/env python3
"""Deterministic funded-work revenue underwriter.

Consumes already-collected evidence only. It performs no network I/O and grants no
authority to contact sponsors, claim work, submit changes, spend, or book revenue.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse, urlunparse

SCHEMA = "commons-revenue-underwriter/v1"
FRESHNESS_SCHEMA = "commons-funded-work-freshness/v1"
TRUSTED_SOURCE_CLASSES = frozenset({"canonical", "sponsor", "payment_ledger", "marketplace"})


class UnderwriterInputError(ValueError):
    """Raised when an input packet is malformed or internally contradictory."""


@dataclass(frozen=True)
class Config:
    max_history_age_days: int = 180
    max_freshness_age_hours: int = 24
    min_pursue_cash: Decimal = Decimal("100")
    zero_paid_reject_competitors: int = 3

    def validated(self) -> "Config":
        if self.max_history_age_days <= 0:
            raise UnderwriterInputError("max_history_age_days must be positive")
        if self.max_freshness_age_hours <= 0:
            raise UnderwriterInputError("max_freshness_age_hours must be positive")
        if self.min_pursue_cash < 0:
            raise UnderwriterInputError("min_pursue_cash must be non-negative")
        if self.zero_paid_reject_competitors < 0:
            raise UnderwriterInputError("zero_paid_reject_competitors must be non-negative")
        return self


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise UnderwriterInputError(f"{field} must be a finite non-negative number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise UnderwriterInputError(f"{field} must be a finite non-negative number") from exc
    if not result.is_finite() or result < 0:
        raise UnderwriterInputError(f"{field} must be a finite non-negative number")
    return result


def _count(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UnderwriterInputError(f"{field} must be a non-negative integer")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UnderwriterInputError(f"{field} must be a non-empty string")
    return value.strip()


def _currency(value: Any, field: str = "currency") -> str:
    code = _text(value, field).upper()
    if len(code) != 3 or not code.isalpha() or not code.isascii():
        raise UnderwriterInputError(f"{field} must be a three-letter ASCII currency code")
    return code


def _timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise UnderwriterInputError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise UnderwriterInputError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _http_url(value: Any, field: str) -> str:
    raw = _text(value, field)
    parts = urlparse(raw)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise UnderwriterInputError(f"{field} must be an absolute http(s) URL")
    if parts.username or parts.password:
        raise UnderwriterInputError(f"{field} must not contain credentials")
    hostname = parts.hostname.lower().rstrip(".")
    try:
        port = parts.port
    except ValueError as exc:
        raise UnderwriterInputError(f"{field} contains an invalid port") from exc
    netloc = hostname if port is None else f"{hostname}:{port}"
    return urlunparse((parts.scheme.lower(), netloc, parts.path or "/", "", parts.query, ""))


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _receipt_hash(receipt: Mapping[str, Any]) -> str:
    payload = dict(receipt)
    payload.pop("receipt_sha256", None)
    return _sha256_json(payload)


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise UnderwriterInputError(f"{field} must be an object")
    return value


def _sequence(value: Any, field: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise UnderwriterInputError(f"{field} must be an array")
    return value


def _freshness_evidence(
    packet: Mapping[str, Any], candidate_url: str, candidate_currency: str, advertised: Decimal
) -> dict[str, Any]:
    """Verify and normalize a native funded_work_freshness receipt."""
    receipt = _mapping(packet.get("freshness_receipt"), "freshness_receipt")
    if receipt.get("schema") != FRESHNESS_SCHEMA:
        raise UnderwriterInputError(f"freshness_receipt.schema must be {FRESHNESS_SCHEMA}")
    claimed_hash = _text(receipt.get("receipt_sha256"), "freshness_receipt.receipt_sha256")
    computed_hash = _receipt_hash(receipt)
    if claimed_hash != computed_hash:
        raise UnderwriterInputError("freshness_receipt hash mismatch")

    candidate = _mapping(receipt.get("candidate"), "freshness_receipt.candidate")
    receipt_currency = _currency(candidate.get("currency"), "freshness_receipt.candidate.currency")
    if receipt_currency != candidate_currency:
        raise UnderwriterInputError("freshness receipt currency does not match candidate currency")
    receipt_amount = _decimal(
        candidate.get("advertised_amount"), "freshness_receipt.candidate.advertised_amount"
    )
    if receipt_amount != advertised:
        raise UnderwriterInputError("freshness receipt advertised amount does not match candidate")

    canonical = _mapping(receipt.get("canonical"), "freshness_receipt.canonical")
    canonical_url = _http_url(canonical.get("url"), "freshness_receipt.canonical.url")
    if canonical_url != candidate_url:
        raise UnderwriterInputError("freshness receipt canonical URL does not match candidate")
    canonical_state = _text(canonical.get("state"), "freshness_receipt.canonical.state").lower()

    checks = _mapping(receipt.get("checks"), "freshness_receipt.checks")
    visible_claims = _count(
        checks.get("visible_claim_count", 0), "freshness_receipt.checks.visible_claim_count"
    )
    active_prs = _count(
        checks.get("active_competing_pr_count", 0),
        "freshness_receipt.checks.active_competing_pr_count",
    )
    status = _text(receipt.get("freshness_status"), "freshness_receipt.freshness_status").lower()
    return {
        "status": status,
        "canonical_state": canonical_state,
        "observed_at": _timestamp(receipt.get("generated_at"), "freshness_receipt.generated_at"),
        "visible_claims": visible_claims,
        "active_competing_prs": active_prs,
        "receipt_sha256": claimed_hash,
        "route": str(receipt.get("route") or ""),
    }


def _history_evidence(packet: Mapping[str, Any], candidate_currency: str) -> list[dict[str, Any]]:
    rows = _sequence(packet.get("payout_history"), "payout_history")
    if not rows:
        raise UnderwriterInputError("payout_history must contain at least one observation")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"payout_history[{index}]")
        currency = _currency(row.get("currency"), f"payout_history[{index}].currency")
        if currency != candidate_currency:
            raise UnderwriterInputError(
                f"payout_history[{index}] currency {currency} does not match candidate currency {candidate_currency}"
            )
        source_class = _text(row.get("source_class"), f"payout_history[{index}].source_class").lower()
        if source_class not in TRUSTED_SOURCE_CLASSES:
            raise UnderwriterInputError(
                f"payout_history[{index}].source_class must be one of {sorted(TRUSTED_SOURCE_CLASSES)}"
            )
        normalized.append(
            {
                "source_url": _http_url(row.get("source_url"), f"payout_history[{index}].source_url"),
                "source_class": source_class,
                "observed_at": _timestamp(row.get("observed_at"), f"payout_history[{index}].observed_at"),
                "currency": currency,
                "paid_total": _decimal(row.get("paid_total"), f"payout_history[{index}].paid_total"),
                "award_count": _count(row.get("award_count"), f"payout_history[{index}].award_count"),
                "completed_count": _count(
                    row.get("completed_count", row.get("award_count")),
                    f"payout_history[{index}].completed_count",
                ),
                "open_pool": _decimal(row.get("open_pool", 0), f"payout_history[{index}].open_pool"),
            }
        )
    return normalized


def _validate_history_monotonic(history: Iterable[Mapping[str, Any]]) -> None:
    by_source: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in history:
        by_source.setdefault((str(row["source_url"]), str(row["currency"])), []).append(row)
    for (source_url, currency), rows in by_source.items():
        ordered = sorted(rows, key=lambda row: row["observed_at"])
        prior: Mapping[str, Any] | None = None
        for row in ordered:
            if row["completed_count"] > row["award_count"]:
                raise UnderwriterInputError(
                    f"completed_count exceeds award_count for {source_url} ({currency})"
                )
            if row["paid_total"] > 0 and row["award_count"] == 0:
                raise UnderwriterInputError(
                    f"paid_total is positive but award_count is zero for {source_url} ({currency})"
                )
            if prior is not None:
                # A source cannot report different numbers for the exact same instant.
                # Independent providers are not required to report equal totals.
                if row["observed_at"] == prior["observed_at"]:
                    snapshot_fields = (
                        "source_class", "paid_total", "award_count",
                        "completed_count", "open_pool",
                    )
                    if any(row[field] != prior[field] for field in snapshot_fields):
                        raise UnderwriterInputError(
                            f"conflicting simultaneous payout snapshots for {source_url} ({currency})"
                        )
                    continue
                if row["paid_total"] < prior["paid_total"]:
                    raise UnderwriterInputError(f"paid_total regressed for {source_url} ({currency})")
                if row["award_count"] < prior["award_count"]:
                    raise UnderwriterInputError(f"award_count regressed for {source_url} ({currency})")
                if row["completed_count"] < prior["completed_count"]:
                    raise UnderwriterInputError(f"completed_count regressed for {source_url} ({currency})")
            prior = row


def _latest_history(history: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    latest: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in history:
        key = (str(row["source_url"]), str(row["currency"]))
        previous = latest.get(key)
        if previous is None or row["observed_at"] > previous["observed_at"]:
            latest[key] = row
    return sorted(latest.values(), key=lambda row: (str(row["source_url"]), row["observed_at"]))


def _history_band(advertised: Decimal, paid_total: Decimal, award_count: int) -> tuple[Decimal, Decimal, str]:
    """Return a conservative planning-multiplier band, explicitly not a probability."""
    if paid_total == 0 or award_count == 0:
        return Decimal("0"), Decimal("0.05"), "no_realized_payout_observed"
    if paid_total < advertised or award_count == 1:
        return Decimal("0.05"), Decimal("0.20"), "limited_realized_payout_history"
    if award_count < 5 or paid_total < advertised * 2:
        return Decimal("0.10"), Decimal("0.35"), "realized_payout_history"
    return Decimal("0.15"), Decimal("0.50"), "repeated_realized_payout_history"


def _conservative_history_band(
    advertised: Decimal, latest: Sequence[Mapping[str, Any]]
) -> tuple[Decimal, Decimal, str]:
    """Combine source-local bands without inventing a cross-source payout snapshot."""
    bands = [_history_band(advertised, row["paid_total"], row["award_count"]) for row in latest]
    low = min(band[0] for band in bands)
    high = min(band[1] for band in bands)
    bases = {band[2] for band in bands}
    basis = next(iter(bases)) if len(bases) == 1 else "conservative_multi_source_history"
    return low, high, basis


def underwrite(
    packet: Mapping[str, Any], *, observed_at: datetime | None = None, config: Config | None = None
) -> dict[str, Any]:
    """Underwrite one funded-work candidate from already-collected evidence."""
    config = (config or Config()).validated()
    now = observed_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise UnderwriterInputError("observed_at must be timezone-aware")
    now = now.astimezone(timezone.utc)

    packet = _mapping(packet, "packet")
    candidate_id = _text(packet.get("candidate_id"), "candidate_id")
    canonical_url = _http_url(packet.get("canonical_url"), "canonical_url")
    currency = _currency(packet.get("currency"))
    advertised = _decimal(packet.get("advertised_amount"), "advertised_amount")
    if advertised == 0:
        raise UnderwriterInputError("advertised_amount must be greater than zero")

    freshness = _freshness_evidence(packet, canonical_url, currency, advertised)
    history = _history_evidence(packet, currency)
    _validate_history_monotonic(history)
    latest = _latest_history(history)

    reasons: list[str] = []
    hard_reject = False
    if freshness["status"] != "actionable":
        reasons.append(f"freshness_{freshness['status']}")
        hard_reject = True
    if freshness["canonical_state"] != "open":
        reasons.append(f"canonical_state_{freshness['canonical_state']}")
        hard_reject = True
    if freshness["observed_at"] > now + timedelta(minutes=5):
        reasons.append("freshness_observation_in_future")
        hard_reject = True
    freshness_cutoff = now - timedelta(hours=config.max_freshness_age_hours)
    if freshness["observed_at"] < freshness_cutoff:
        reasons.append("freshness_observation_stale")
        hard_reject = True

    history_cutoff = now - timedelta(days=config.max_history_age_days)
    stale_history = [row for row in latest if row["observed_at"] < history_cutoff]
    future_history = [row for row in latest if row["observed_at"] > now + timedelta(minutes=5)]
    if stale_history:
        reasons.append("payout_history_stale")
        hard_reject = True
    if future_history:
        reasons.append("payout_history_in_future")
        hard_reject = True

    # Keep maxima as descriptive evidence only. Planning is composed from coherent
    # source-local snapshots below so independent fields can never form a synthetic
    # payout history that no source actually reported.
    paid_total = max((row["paid_total"] for row in latest), default=Decimal("0"))
    award_count = max((row["award_count"] for row in latest), default=0)
    completed_count = max((row["completed_count"] for row in latest), default=0)
    open_pool = max((row["open_pool"] for row in latest), default=Decimal("0"))

    visible_claims = freshness["visible_claims"]
    active_prs = freshness["active_competing_prs"]
    competitors = visible_claims + active_prs
    if (
        any(row["paid_total"] == 0 for row in latest)
        and competitors >= config.zero_paid_reject_competitors
    ):
        reasons.append("zero_paid_high_competition_pool")
        hard_reject = True

    history_low, history_high, history_basis = _conservative_history_band(advertised, latest)
    dilution = Decimal(1) / Decimal(1 + competitors)
    lower = advertised * history_low * dilution
    upper = advertised * history_high * dilution

    if hard_reject:
        disposition = "reject"
    elif paid_total > 0 and lower >= config.min_pursue_cash:
        disposition = "pursue"
        reasons.append("planning_floor_meets_pursue_threshold")
    else:
        disposition = "watch"
        if paid_total == 0:
            reasons.append("no_realized_payout_observed")
        elif lower < config.min_pursue_cash:
            reasons.append("planning_floor_below_pursue_threshold")

    evidence = {
        "freshness_receipt": {
            "schema": FRESHNESS_SCHEMA,
            "receipt_sha256": freshness["receipt_sha256"],
            "observed_at": _iso(freshness["observed_at"]),
            "status": freshness["status"],
            "route": freshness["route"],
        },
        "payout_history": [
            {
                **{k: v for k, v in row.items() if k not in {"observed_at", "paid_total", "open_pool"}},
                "observed_at": _iso(row["observed_at"]),
                "paid_total": _money(row["paid_total"]),
                "open_pool": _money(row["open_pool"]),
            }
            for row in latest
        ],
    }

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "candidate_id": candidate_id,
        "canonical_url": canonical_url,
        "observed_at": _iso(now),
        "currency": currency,
        "advertised_amount": _money(advertised),
        "disposition": disposition,
        "reasons": sorted(set(reasons)),
        "realized_payout_evidence": {
            "paid_total_max_observed": _money(paid_total),
            "award_count_max_observed": award_count,
            "completed_count_max_observed": completed_count,
            "open_pool_max_observed": _money(open_pool),
            "source_count": len(latest),
        },
        "competition": {
            "visible_claims": visible_claims,
            "active_competing_prs": active_prs,
            "planning_competitors": competitors,
        },
        "expected_cash_planning_range": {"lower": _money(lower), "upper": _money(upper)},
        "assumptions": {
            "history_multiplier_band": [_money(history_low), _money(history_high)],
            "history_basis": history_basis,
            "competition_dilution": str(
                dilution.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            ),
            "competition_definition": "visible_claims + active_competing_prs; one equal-share planning denominator, not a win probability",
            "range_semantics": "conservative planning allocation range; not a forecast, probability, booking, or payment claim",
            "pursue_floor": _money(config.min_pursue_cash),
            "max_freshness_age_hours": config.max_freshness_age_hours,
        },
        "evidence": evidence,
        "input_sha256": _sha256_json(packet),
        "booking_authority": False,
        "external_action_authority": False,
    }
    receipt["receipt_sha256"] = _receipt_hash(receipt)
    return receipt


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Underwrite funded work from already-collected payout evidence."
    )
    parser.add_argument("input", type=Path, help="candidate evidence JSON")
    parser.add_argument("--output", type=Path, help="write receipt JSON atomically")
    parser.add_argument("--observed-at", help="fixed ISO-8601 time for deterministic replay")
    parser.add_argument("--max-history-age-days", type=int, default=180)
    parser.add_argument("--max-freshness-age-hours", type=int, default=24)
    parser.add_argument("--min-pursue-cash", default="100")
    parser.add_argument("--zero-paid-reject-competitors", type=int, default=3)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        packet = json.loads(args.input.read_text(encoding="utf-8"))
        fixed_time = _timestamp(args.observed_at, "--observed-at") if args.observed_at else None
        config = Config(
            max_history_age_days=args.max_history_age_days,
            max_freshness_age_hours=args.max_freshness_age_hours,
            min_pursue_cash=_decimal(args.min_pursue_cash, "--min-pursue-cash"),
            zero_paid_reject_competitors=args.zero_paid_reject_competitors,
        ).validated()
        receipt = underwrite(packet, observed_at=fixed_time, config=config)
    except (OSError, json.JSONDecodeError, UnderwriterInputError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        try:
            write_atomic(args.output, rendered)
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        print(rendered, end="")
    return {"pursue": 0, "watch": 3, "reject": 4}[receipt["disposition"]]


if __name__ == "__main__":
    raise SystemExit(main())
