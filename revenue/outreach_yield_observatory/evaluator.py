"""Deterministic, read-only outreach cohort evidence evaluator.

This module intentionally has no provider integrations and no outbound actions.
It consumes de-identified event evidence and emits conservative cohort metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping
import json
import re


SCHEMA_VERSION = 1
EVENT_SENT = "SENT"
EVENT_BOUNCE = "BOUNCE"
EVENT_DNR = "DNR"
EVENT_HUMAN_REPLY = "HUMAN_REPLY"
EVENT_POSITIVE_REPLY = "POSITIVE_REPLY"
EVENT_PAID_SCOPE_ACCEPTED = "PAID_SCOPE_ACCEPTED"
EVENT_PAYMENT_EVIDENCED = "PAYMENT_EVIDENCED"

EVENTS = (
    EVENT_SENT,
    EVENT_BOUNCE,
    EVENT_DNR,
    EVENT_HUMAN_REPLY,
    EVENT_POSITIVE_REPLY,
    EVENT_PAID_SCOPE_ACCEPTED,
    EVENT_PAYMENT_EVIDENCED,
)
OUTCOME_EVENTS = frozenset(EVENTS[1:])
REPLY_PATH = (
    EVENT_HUMAN_REPLY,
    EVENT_POSITIVE_REPLY,
    EVENT_PAID_SCOPE_ACCEPTED,
    EVENT_PAYMENT_EVIDENCED,
)
_TERMINAL_NEGATIVE = frozenset((EVENT_BOUNCE, EVENT_DNR))
_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ObservatoryError(ValueError):
    """Raised when evidence is ambiguous, contradictory, or unsafe to aggregate."""


@dataclass(frozen=True)
class Policy:
    min_matured_exposures: int = 20
    min_positive_reply_ppm: int = 100_000
    max_dnr_ppm: int = 50_000
    min_paid_scope_acceptances: int = 1
    min_payment_evidenced: int = 0

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "Policy":
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise ObservatoryError("policy must be an object or null")
        allowed = set(cls.__dataclass_fields__)
        unknown = set(value) - allowed
        if unknown:
            raise ObservatoryError(f"unknown policy keys: {sorted(unknown)}")
        policy = cls(**{k: value[k] for k in value})
        for name in (
            "min_matured_exposures",
            "min_positive_reply_ppm",
            "max_dnr_ppm",
            "min_paid_scope_acceptances",
            "min_payment_evidenced",
        ):
            v = getattr(policy, name)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ObservatoryError(f"policy.{name} must be a non-negative integer")
        if policy.min_positive_reply_ppm > 1_000_000:
            raise ObservatoryError("policy.min_positive_reply_ppm must be <= 1_000_000")
        if policy.max_dnr_ppm > 1_000_000:
            raise ObservatoryError("policy.max_dnr_ppm must be <= 1_000_000")
        return policy


@dataclass(frozen=True)
class Event:
    prospect_key: str
    experiment_id: str
    segment: str
    offer: str
    route: str
    event: str
    at: datetime
    evidence_ref: str | None


@dataclass(frozen=True)
class Exposure:
    prospect_key: str
    experiment_id: str
    segment: str
    offer: str
    route: str
    sent_at: datetime
    event_times: Mapping[str, datetime]
    evidence_refs: Mapping[str, str]


@dataclass(frozen=True)
class CohortMetrics:
    experiment_id: str
    segment: str
    offer: str
    route: str
    exposures: int
    matured_exposures: int
    immature_exposures: int
    matured_bounces: int
    matured_dnr: int
    matured_human_replies: int
    matured_positive_replies: int
    matured_paid_scope_acceptances: int
    matured_payment_evidenced: int
    bounce_ppm: int
    dnr_ppm: int
    human_reply_ppm: int
    positive_reply_ppm: int
    paid_scope_acceptance_ppm: int
    payment_evidenced_ppm: int
    signal: str
    signal_reason: str
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_iso8601(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ObservatoryError(f"{field} must be a non-empty ISO-8601 timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ObservatoryError(f"{field} is not valid ISO-8601: {value!r}") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ObservatoryError(f"{field} must include a timezone offset")
    return dt.astimezone(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SAFE_KEY.fullmatch(value):
        raise ObservatoryError(
            f"{field} must match {_SAFE_KEY.pattern!r}; use a stable de-identified key"
        )
    if "@" in value:
        raise ObservatoryError(f"{field} must not contain a raw email address")
    return value


def _safe_dimension(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ObservatoryError(f"{field} must be a string")
    text = value.strip()
    if not text or len(text) > 128:
        raise ObservatoryError(f"{field} must be 1..128 characters")
    if "@" in text:
        raise ObservatoryError(f"{field} must not contain raw email-like PII")
    if any(ord(ch) < 32 for ch in text):
        raise ObservatoryError(f"{field} must not contain control characters")
    return text


def _evidence_ref(value: Any, event_name: str) -> str | None:
    required = event_name in OUTCOME_EVENTS
    if value is None:
        if required:
            raise ObservatoryError(f"{event_name} requires a non-empty evidence_ref")
        return None
    if not isinstance(value, str) or not value.strip():
        if required:
            raise ObservatoryError(f"{event_name} requires a non-empty evidence_ref")
        raise ObservatoryError("evidence_ref must be null or a non-empty string <=512 chars")
    text = value.strip()
    if len(text) > 512 or any(ord(ch) < 32 for ch in text):
        raise ObservatoryError("evidence_ref must be 1..512 printable characters")
    if "@" in text:
        raise ObservatoryError(
            "evidence_ref must be an opaque reference, not raw email-like PII"
        )
    return text


def _parse_event(raw: Any, index: int, as_of: datetime) -> Event:
    if not isinstance(raw, Mapping):
        raise ObservatoryError(f"events[{index}] must be an object")
    required = {
        "prospect_key",
        "experiment_id",
        "segment",
        "offer",
        "route",
        "event",
        "at",
    }
    missing = required - set(raw)
    if missing:
        raise ObservatoryError(f"events[{index}] missing keys: {sorted(missing)}")
    unknown = set(raw) - (required | {"evidence_ref"})
    if unknown:
        raise ObservatoryError(f"events[{index}] unknown keys: {sorted(unknown)}")

    event_name = raw["event"]
    if event_name not in EVENTS:
        raise ObservatoryError(f"events[{index}].event must be one of {list(EVENTS)}")

    at = _parse_iso8601(raw["at"], f"events[{index}].at")
    if at > as_of:
        raise ObservatoryError(f"events[{index}].at is later than as_of")

    return Event(
        prospect_key=_safe_identifier(raw["prospect_key"], f"events[{index}].prospect_key"),
        experiment_id=_safe_identifier(raw["experiment_id"], f"events[{index}].experiment_id"),
        segment=_safe_dimension(raw["segment"], f"events[{index}].segment"),
        offer=_safe_dimension(raw["offer"], f"events[{index}].offer"),
        route=_safe_dimension(raw["route"], f"events[{index}].route"),
        event=event_name,
        at=at,
        evidence_ref=_evidence_ref(raw.get("evidence_ref"), event_name),
    )


def _build_exposures(events: Iterable[Event]) -> list[Exposure]:
    grouped: dict[tuple[str, str], list[Event]] = {}
    for event in events:
        grouped.setdefault((event.prospect_key, event.experiment_id), []).append(event)

    exposures: list[Exposure] = []
    for key in sorted(grouped):
        rows = sorted(grouped[key], key=lambda e: (e.at, EVENTS.index(e.event)))
        dimensions = {(r.segment, r.offer, r.route) for r in rows}
        if len(dimensions) != 1:
            raise ObservatoryError(
                f"{key}: segment/offer/route changed inside one prospect experiment"
            )

        by_type: dict[str, Event] = {}
        for row in rows:
            if row.event in by_type:
                if row == by_type[row.event]:
                    continue
                raise ObservatoryError(f"{key}: conflicting duplicate {row.event} event")
            by_type[row.event] = row

        if EVENT_SENT not in by_type:
            raise ObservatoryError(f"{key}: missing SENT event")
        sent = by_type[EVENT_SENT]
        for row in rows:
            if row.at < sent.at:
                raise ObservatoryError(f"{key}: {row.event} predates SENT")

        negative = _TERMINAL_NEGATIVE.intersection(by_type)
        if len(negative) > 1:
            raise ObservatoryError(f"{key}: BOUNCE and DNR are contradictory")
        if negative and set(REPLY_PATH).intersection(by_type):
            raise ObservatoryError(
                f"{key}: terminal negative outcome cannot coexist with reply/accept/payment path"
            )

        prerequisites = {
            EVENT_POSITIVE_REPLY: EVENT_HUMAN_REPLY,
            EVENT_PAID_SCOPE_ACCEPTED: EVENT_POSITIVE_REPLY,
            EVENT_PAYMENT_EVIDENCED: EVENT_PAID_SCOPE_ACCEPTED,
        }
        for event_name, prerequisite in prerequisites.items():
            if event_name in by_type:
                if prerequisite not in by_type:
                    raise ObservatoryError(
                        f"{key}: {event_name} requires explicit {prerequisite} evidence"
                    )
                if by_type[prerequisite].at > by_type[event_name].at:
                    raise ObservatoryError(
                        f"{key}: {event_name} predates prerequisite {prerequisite}"
                    )

        event_times = {name: row.at for name, row in by_type.items()}
        evidence_refs = {
            name: row.evidence_ref
            for name, row in by_type.items()
            if row.evidence_ref is not None
        }
        segment, offer, route = next(iter(dimensions))
        exposures.append(
            Exposure(
                prospect_key=key[0],
                experiment_id=key[1],
                segment=segment,
                offer=offer,
                route=route,
                sent_at=sent.at,
                event_times=event_times,
                evidence_refs=evidence_refs,
            )
        )
    return exposures


def _ppm(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return (numerator * 1_000_000 + denominator // 2) // denominator


def _signal(
    *,
    matured: int,
    positive_ppm: int,
    dnr_ppm: int,
    acceptances: int,
    payments: int,
    policy: Policy,
) -> tuple[str, str]:
    if matured < policy.min_matured_exposures:
        return (
            "LEARN_MORE",
            f"matured support {matured} < policy minimum {policy.min_matured_exposures}",
        )
    if dnr_ppm > policy.max_dnr_ppm:
        return (
            "STOP_DNR_REVIEW",
            f"DNR {dnr_ppm} ppm > policy maximum {policy.max_dnr_ppm} ppm",
        )
    gates = []
    if positive_ppm < policy.min_positive_reply_ppm:
        gates.append(
            f"positive reply {positive_ppm} ppm < {policy.min_positive_reply_ppm} ppm"
        )
    if acceptances < policy.min_paid_scope_acceptances:
        gates.append(
            f"paid-scope acceptances {acceptances} < {policy.min_paid_scope_acceptances}"
        )
    if payments < policy.min_payment_evidenced:
        gates.append(
            f"payment-evidenced count {payments} < {policy.min_payment_evidenced}"
        )
    if gates:
        return "LEARN_MORE", "; ".join(gates)
    return (
        "SCALE_REVIEW",
        "policy evidence gates passed; human review is still required before any action",
    )


def evaluate_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and evaluate a de-identified outreach evidence document."""
    if not isinstance(document, Mapping):
        raise ObservatoryError("document must be an object")

    allowed_top = {
        "schema_version",
        "as_of",
        "maturation_hours",
        "policy",
        "events",
    }
    unknown = set(document) - allowed_top
    if unknown:
        raise ObservatoryError(f"unknown top-level keys: {sorted(unknown)}")

    if type(document.get("schema_version")) is not int or document["schema_version"] != SCHEMA_VERSION:
        raise ObservatoryError(f"schema_version must equal {SCHEMA_VERSION}")

    as_of = _parse_iso8601(document.get("as_of"), "as_of")
    maturation_hours = document.get("maturation_hours")
    if (
        not isinstance(maturation_hours, int)
        or isinstance(maturation_hours, bool)
        or not 1 <= maturation_hours <= 24 * 30
    ):
        raise ObservatoryError("maturation_hours must be an integer in 1..720")

    policy = Policy.from_mapping(document.get("policy"))
    raw_events = document.get("events")
    if not isinstance(raw_events, list):
        raise ObservatoryError("events must be a list")

    parsed = [_parse_event(row, i, as_of) for i, row in enumerate(raw_events)]
    exposures = _build_exposures(parsed)
    cutoff = as_of - timedelta(hours=maturation_hours)

    by_cohort: dict[tuple[str, str, str, str], list[Exposure]] = {}
    for exposure in exposures:
        cohort_key = (
            exposure.experiment_id,
            exposure.segment,
            exposure.offer,
            exposure.route,
        )
        by_cohort.setdefault(cohort_key, []).append(exposure)

    metrics: list[CohortMetrics] = []
    for cohort_key in sorted(by_cohort):
        rows = by_cohort[cohort_key]
        matured_rows = [row for row in rows if row.sent_at <= cutoff]
        matured = len(matured_rows)

        def count_event(name: str) -> int:
            return sum(name in row.event_times for row in matured_rows)

        bounces = count_event(EVENT_BOUNCE)
        dnr = count_event(EVENT_DNR)
        human = count_event(EVENT_HUMAN_REPLY)
        positive = count_event(EVENT_POSITIVE_REPLY)
        accepted = count_event(EVENT_PAID_SCOPE_ACCEPTED)
        payments = count_event(EVENT_PAYMENT_EVIDENCED)

        positive_ppm = _ppm(positive, matured)
        dnr_ppm = _ppm(dnr, matured)
        signal, reason = _signal(
            matured=matured,
            positive_ppm=positive_ppm,
            dnr_ppm=dnr_ppm,
            acceptances=accepted,
            payments=payments,
            policy=policy,
        )

        metrics.append(
            CohortMetrics(
                experiment_id=cohort_key[0],
                segment=cohort_key[1],
                offer=cohort_key[2],
                route=cohort_key[3],
                exposures=len(rows),
                matured_exposures=matured,
                immature_exposures=len(rows) - matured,
                matured_bounces=bounces,
                matured_dnr=dnr,
                matured_human_replies=human,
                matured_positive_replies=positive,
                matured_paid_scope_acceptances=accepted,
                matured_payment_evidenced=payments,
                bounce_ppm=_ppm(bounces, matured),
                dnr_ppm=dnr_ppm,
                human_reply_ppm=_ppm(human, matured),
                positive_reply_ppm=positive_ppm,
                paid_scope_acceptance_ppm=_ppm(accepted, matured),
                payment_evidenced_ppm=_ppm(payments, matured),
                signal=signal,
                signal_reason=reason,
            )
        )

    signal_priority = {
        "SCALE_REVIEW": 0,
        "LEARN_MORE": 1,
        "STOP_DNR_REVIEW": 2,
    }
    metrics.sort(
        key=lambda m: (
            signal_priority[m.signal],
            -m.matured_payment_evidenced,
            -m.matured_paid_scope_acceptances,
            -m.positive_reply_ppm,
            -m.matured_exposures,
            m.dnr_ppm,
            m.experiment_id,
            m.segment,
            m.offer,
            m.route,
        )
    )
    ranked: list[CohortMetrics] = []
    for idx, metric in enumerate(metrics, start=1):
        values = metric.to_dict()
        values["rank"] = idx
        ranked.append(CohortMetrics(**values))

    totals_matured = sum(m.matured_exposures for m in ranked)
    totals = {
        "exposures": sum(m.exposures for m in ranked),
        "matured_exposures": totals_matured,
        "immature_exposures": sum(m.immature_exposures for m in ranked),
        "matured_human_replies": sum(m.matured_human_replies for m in ranked),
        "matured_positive_replies": sum(m.matured_positive_replies for m in ranked),
        "matured_paid_scope_acceptances": sum(
            m.matured_paid_scope_acceptances for m in ranked
        ),
        "matured_payment_evidenced": sum(
            m.matured_payment_evidenced for m in ranked
        ),
        "matured_dnr": sum(m.matured_dnr for m in ranked),
        "matured_bounces": sum(m.matured_bounces for m in ranked),
    }
    totals.update(
        {
            "human_reply_ppm": _ppm(totals["matured_human_replies"], totals_matured),
            "positive_reply_ppm": _ppm(
                totals["matured_positive_replies"], totals_matured
            ),
            "paid_scope_acceptance_ppm": _ppm(
                totals["matured_paid_scope_acceptances"], totals_matured
            ),
            "payment_evidenced_ppm": _ppm(
                totals["matured_payment_evidenced"], totals_matured
            ),
            "dnr_ppm": _ppm(totals["matured_dnr"], totals_matured),
            "bounce_ppm": _ppm(totals["matured_bounces"], totals_matured),
        }
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": _iso_z(as_of),
        "maturation_hours": maturation_hours,
        "maturation_cutoff": _iso_z(cutoff),
        "policy": asdict(policy),
        "authority": {
            "mode": "READ_ONLY_EVIDENCE_ANALYSIS",
            "outbound_action": False,
            "provider_access": False,
            "recipient_selection": False,
            "accounting_recognition": False,
            "payment_evidenced_semantics": (
                "supplied evidence label only; not cash receipt or recognized revenue"
            ),
        },
        "totals": totals,
        "cohorts": [m.to_dict() for m in ranked],
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render a stable human-review report from evaluate_document output."""
    lines = [
        "# Outreach Yield Observatory",
        "",
        f"- As of: `{report['as_of']}`",
        f"- Maturation window: `{report['maturation_hours']}` hours",
        f"- Matured exposures: `{report['totals']['matured_exposures']}`",
        f"- Immature exposures excluded from rates: `{report['totals']['immature_exposures']}`",
        "- Authority: **read-only evidence analysis; no send, provider access, recipient selection, or accounting recognition**",
        "- `PAYMENT_EVIDENCED` means only that the supplied evidence says payment is evidenced; it is not revenue recognition.",
        "",
        "## Cohorts",
        "",
        "| Rank | Experiment | Segment | Offer | Route | Matured | Human reply | Positive | Scope accepted | Payment evidenced | DNR | Signal |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for c in report["cohorts"]:
        def pct(ppm: int) -> str:
            return f"{ppm / 10_000:.2f}%"
        lines.append(
            "| {rank} | {experiment_id} | {segment} | {offer} | {route} | "
            "{matured_exposures} | {human} | {positive} | {accepted} | "
            "{payment} | {dnr} | {signal} |".format(
                **c,
                human=pct(c["human_reply_ppm"]),
                positive=pct(c["positive_reply_ppm"]),
                accepted=pct(c["paid_scope_acceptance_ppm"]),
                payment=pct(c["payment_evidenced_ppm"]),
                dnr=pct(c["dnr_ppm"]),
            )
        )
    lines.extend(["", "## Signal reasons", ""])
    for c in report["cohorts"]:
        lines.append(
            f"- **#{c['rank']} {c['experiment_id']} / {c['segment']} / "
            f"{c['offer']} / {c['route']}** — `{c['signal']}`: {c['signal_reason']}"
        )
    lines.extend(
        [
            "",
            "> Signals are review gates, not instructions to contact anyone. "
            "Re-check live claims/provider state before any external action.",
            "",
        ]
    )
    return "\n".join(lines)


def dumps_report(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
