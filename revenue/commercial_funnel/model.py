from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime
from typing import Any, Mapping

from .common import (
    FAMILIES,
    HOLD,
    MAX_EVENTS_PER_OPPORTUNITY,
    READY,
    STAGES,
    STAGE_INDEX,
    FunnelError,
    canonical_json,
    exact_keys,
    parse_time,
    require_id,
    validate_source,
)
from .events import validate_event


def age_bucket(age_seconds: int) -> str:
    if age_seconds <= 86400:
        return "0_1D"
    if age_seconds <= 7 * 86400:
        return "2_7D"
    if age_seconds <= 30 * 86400:
        return "8_30D"
    if age_seconds <= 90 * 86400:
        return "31_90D"
    return "91D_PLUS"


def source_key(source: Mapping[str, str]) -> tuple[str, str, str, str]:
    return source["repository"], source["commit"], source["path"], source["sha256"]


def normalize_opportunity(raw: Any, field: str, as_of: datetime) -> tuple[dict[str, Any], dict[tuple[str, str, str, str], set[str]]]:
    opp = exact_keys(raw, required=("id", "family", "offer", "events"), field=field)
    opp_id = require_id(opp["id"], f"{field}.id")
    family = opp["family"]
    if family not in FAMILIES:
        raise FunnelError(f"{field}.family invalid")
    offer = exact_keys(opp["offer"], required=("id", "version", "source"), field=f"{field}.offer")
    offer_out = {
        "id": require_id(offer["id"], f"{field}.offer.id"),
        "version": require_id(offer["version"], f"{field}.offer.version"),
        "source": validate_source(offer["source"], f"{field}.offer.source"),
    }
    offer_source = source_key(offer_out["source"])
    raw_events = opp["events"]
    if not isinstance(raw_events, list) or len(raw_events) > MAX_EVENTS_PER_OPPORTUNITY:
        raise FunnelError(f"{field}.events must be array <= {MAX_EVENTS_PER_OPPORTUNITY}")

    # Validate every row first, then resolve event IDs from the full multiset.
    # Exact replays collapse. If one ID has more than one distinct normalized
    # meaning, fail closed by emitting *none* of those conflicting variants into
    # positive funnel semantics. This makes packet meaning independent of caller
    # row order while preserving the full evidence-source usage boundary.
    event_groups: dict[str, dict[bytes, tuple[dict[str, Any], set[str]]]] = defaultdict(dict)
    for i, raw_event in enumerate(raw_events):
        normalized, reasons = validate_event(raw_event, f"{field}.events[{i}]", as_of)
        event_id = normalized["id"]
        identity = canonical_json(normalized)
        existing = event_groups[event_id].get(identity)
        if existing is None:
            event_groups[event_id][identity] = (normalized, set(reasons))
        else:
            existing[1].update(reasons)

    event_by_id: dict[str, dict[str, Any]] = {}
    event_reasons: dict[str, list[str]] = defaultdict(list)
    source_event_ids: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    evidence_usage: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)

    for event_id in sorted(event_groups):
        variants = event_groups[event_id]
        variant_records = [variants[key] for key in sorted(variants)]
        if len(variant_records) == 1:
            event_by_id[event_id] = variant_records[0][0]
        else:
            event_reasons[event_id].append("EVENT_ID_CONFLICT")

        for normalized, reasons in variant_records:
            event_reasons[event_id].extend(sorted(reasons))
            key = source_key(normalized["evidence"])
            source_event_ids[key].add(event_id)
            evidence_usage[key].add(opp_id)
            if key == offer_source:
                event_reasons[event_id].append("EVIDENCE_ROLE_CONFLICT")

    for event_ids in source_event_ids.values():
        if len(event_ids) > 1:
            for event_id in sorted(event_ids):
                event_reasons[event_id].append("EVIDENCE_REUSED_WITHIN_OPPORTUNITY")

    events = sorted(event_by_id.values(), key=lambda e: (e["observed_at"], e["stage"], e["id"]))
    reasons = sorted({reason for rs in event_reasons.values() for reason in rs})

    cash_by_id: dict[str, dict[str, Any]] = {}
    reversal_totals: dict[str, int] = defaultdict(int)
    for event in events:
        if event["stage"] == "CASH":
            cash_by_id[event["id"]] = event
        elif event["stage"] == "CASH_REVERSAL":
            target = cash_by_id.get(event["reversal_of"])
            if target is None:
                reasons.append("REVERSAL_TARGET_NOT_PRIOR_CASH")
                continue
            if event["money"]["currency"] != target["money"]["currency"]:
                reasons.append("REVERSAL_CURRENCY_MISMATCH")
                continue
            reversal_totals[target["id"]] += event["money"]["minor_units"]
            if reversal_totals[target["id"]] > target["money"]["minor_units"]:
                reasons.append("REVERSAL_EXCEEDS_CASH")

    evidenced: set[str] = set()
    earliest: dict[str, datetime] = {}
    for event in events:
        if event["stage"] in STAGE_INDEX:
            for stage in [event["stage"], *event["proves"]]:
                evidenced.add(stage)
                when = parse_time(event["observed_at"], "event.observed_at")
                earliest[stage] = min(earliest.get(stage, when), when)

    for stage in STAGES:
        if stage not in evidenced:
            continue
        idx = STAGE_INDEX[stage]
        if any(prior not in evidenced for prior in STAGES[:idx]):
            reasons.append(f"STAGE_GAP_{stage}")
    last_time: datetime | None = None
    for stage in STAGES:
        if stage not in earliest:
            continue
        if last_time is not None and earliest[stage] < last_time:
            reasons.append("STAGE_TIME_ORDER_INVALID")
            break
        last_time = earliest[stage]

    strongest = next((stage for stage in reversed(STAGES) if stage in evidenced), None)
    latest_event_time = max((parse_time(e["observed_at"], "event.observed_at") for e in events), default=None)
    latest_age_bucket = None if latest_event_time is None else age_bucket(int((as_of - latest_event_time).total_seconds()))

    gross: dict[str, int] = defaultdict(int)
    reversals: dict[str, int] = defaultdict(int)
    noncash: dict[str, int] = defaultdict(int)
    for event in events:
        if event["stage"] == "CASH":
            gross[event["money"]["currency"]] += event["money"]["minor_units"]
        elif event["stage"] == "CASH_REVERSAL":
            reversals[event["money"]["currency"]] += event["money"]["minor_units"]
        elif event["stage"] == "NONCASH_AWARD":
            noncash[event["noncash"]["asset"]] += event["noncash"]["quantity"]

    unique_reasons = sorted(set(reasons))
    state = HOLD if unique_reasons else READY
    next_evidence = "REVIEW_HOLD_REASONS" if state == HOLD else ("TRAFFIC" if strongest is None else ("NONE" if strongest == "CASH" else STAGES[STAGE_INDEX[strongest] + 1]))
    result = {
        "id": opp_id,
        "family": family,
        "offer": offer_out,
        "state": state,
        "hold_reasons": unique_reasons,
        "strongest_evidenced_stage": strongest,
        "stage_times": {stage: earliest[stage].strftime("%Y-%m-%dT%H:%M:%SZ") for stage in STAGES if stage in earliest},
        "latest_evidence_age_bucket": latest_age_bucket,
        "next_evidence_needed": next_evidence,
        "gross_cash_by_currency": dict(sorted(gross.items())),
        "cash_reversals_by_currency": dict(sorted(reversals.items())),
        "net_cash_by_currency": {currency: gross[currency] - reversals.get(currency, 0) for currency in sorted(gross)},
        "noncash_awards": dict(sorted(noncash.items())),
        "events": events,
    }
    return result, evidence_usage


def metrics(opportunities: list[dict[str, Any]]) -> dict[str, Any]:
    ready = [opp for opp in opportunities if opp["state"] == READY]
    family_total = {family: 0 for family in FAMILIES}
    family_ready = {family: 0 for family in FAMILIES}
    stage_counts = {stage: 0 for stage in STAGES}
    for opp in opportunities:
        family_total[opp["family"]] += 1
    for opp in ready:
        family_ready[opp["family"]] += 1
        strongest = opp["strongest_evidenced_stage"]
        if strongest is not None:
            for stage in STAGES[: STAGE_INDEX[strongest] + 1]:
                stage_counts[stage] += 1
    dropoff = {f"{stage}_TO_{STAGES[i + 1]}": stage_counts[stage] - stage_counts[STAGES[i + 1]] for i, stage in enumerate(STAGES[:-1])}
    gross: dict[str, int] = defaultdict(int)
    reversals: dict[str, int] = defaultdict(int)
    net: dict[str, int] = defaultdict(int)
    noncash: dict[str, int] = defaultdict(int)
    age: dict[str, int] = defaultdict(int)
    for opp in ready:
        for currency, amount in opp["gross_cash_by_currency"].items():
            gross[currency] += amount
        for currency, amount in opp["cash_reversals_by_currency"].items():
            reversals[currency] += amount
        for currency, amount in opp["net_cash_by_currency"].items():
            net[currency] += amount
        for asset, quantity in opp["noncash_awards"].items():
            noncash[asset] += quantity
        if opp["latest_evidence_age_bucket"] is not None:
            age[opp["latest_evidence_age_bucket"]] += 1
    return {
        "opportunity_count": len(opportunities),
        "eligible_opportunity_count": len(ready),
        "held_opportunity_count": len(opportunities) - len(ready),
        "family_total_counts": family_total,
        "family_eligible_counts": family_ready,
        "stage_counts": stage_counts,
        "stage_dropoff_counts": dropoff,
        "gross_cash_by_currency": dict(sorted(gross.items())),
        "cash_reversals_by_currency": dict(sorted(reversals.items())),
        "net_cash_by_currency": dict(sorted(net.items())),
        "noncash_awards": dict(sorted(noncash.items())),
        "latest_evidence_age_buckets": dict(sorted(age.items())),
    }


def csv_bytes(opportunities: list[dict[str, Any]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["opportunity_id", "family", "offer_id", "offer_version", "state", "strongest_evidenced_stage", "next_evidence_needed", "latest_evidence_age_bucket", "hold_reasons"])
    for opp in opportunities:
        writer.writerow([opp["id"], opp["family"], opp["offer"]["id"], opp["offer"]["version"], opp["state"], opp["strongest_evidenced_stage"] or "", opp["next_evidence_needed"], opp["latest_evidence_age_bucket"] or "", "|".join(opp["hold_reasons"])])
    return out.getvalue().encode("utf-8")


def markdown_bytes(packet_without_outputs: Mapping[str, Any]) -> bytes:
    packet_metrics = packet_without_outputs["metrics"]
    lines = ["# Commercial funnel evidence packet", "", f"- State: **{packet_without_outputs['state']}**", f"- Evaluated at: `{packet_without_outputs['evaluated_at']}`", f"- Opportunities: {packet_metrics['opportunity_count']}", f"- Eligible for analytics: {packet_metrics['eligible_opportunity_count']}", f"- Held: {packet_metrics['held_opportunity_count']}", "", "## Stage counts", "", "| Stage | Eligible opportunities |", "| --- | ---: |"]
    for stage in STAGES:
        lines.append(f"| {stage} | {packet_metrics['stage_counts'][stage]} |")
    lines.extend(["", "## Opportunity evidence state", "", "| Opportunity | Family | State | Strongest stage | Next evidence |", "| --- | --- | --- | --- | --- |"])
    for opp in packet_without_outputs["opportunities"]:
        reasons = ", ".join(opp["hold_reasons"])
        state = opp["state"] if not reasons else f"{opp['state']} ({reasons})"
        lines.append(f"| {opp['id']} | {opp['family']} | {state} | {opp['strongest_evidenced_stage'] or 'NONE'} | {opp['next_evidence_needed']} |")
    lines.extend(["", "This packet is analytical evidence only. It does not authorize outreach, acceptance,", "contracting, fulfillment, transfer, checkout/payment actions, cash-availability claims,", "accounting/tax treatment, or revenue recognition.", ""])
    return "\n".join(lines).encode("utf-8")
