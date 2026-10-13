from __future__ import annotations

import csv
import io
from collections import defaultdict
from itertools import combinations
from statistics import median_low
from typing import Any, Mapping

from .common import STAGES, STAGE_INDEX, UPSTREAM_READY, LabError, parse_time

def _basis_points(numerator: int, denominator: int) -> int | None:
    if denominator == 0:
        return None
    return (numerator * 10_000) // denominator

def _add_money(target: dict[str, int], values: Any, field: str) -> None:
    if not isinstance(values, dict):
        raise LabError(f"{field} invalid")
    for currency, amount in values.items():
        if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha() or currency != currency.upper():
            raise LabError(f"{field} currency invalid")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise LabError(f"{field} amount invalid")
        target[currency] += amount

def _arm_metrics(arm: Mapping[str, Any], assigned: list[dict[str, Any]], opportunities: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    ready: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    for assignment in assigned:
        opp = opportunities[assignment["opportunity_id"]]
        (ready if opp.get("state") == UPSTREAM_READY else held).append(opp)

    stage_counts = {stage: 0 for stage in STAGES}
    time_to_stage: dict[str, list[int]] = {"REPLY": [], "ACCEPTANCE": [], "CASH": []}
    gross: dict[str, int] = defaultdict(int)
    reversals: dict[str, int] = defaultdict(int)
    net: dict[str, int] = defaultdict(int)
    for opp in ready:
        strongest = opp.get("strongest_evidenced_stage")
        if strongest is not None:
            if strongest not in STAGE_INDEX:
                raise LabError(f"upstream strongest stage invalid: {opp.get('id')}")
            for stage in STAGES[: STAGE_INDEX[strongest] + 1]:
                stage_counts[stage] += 1
        stage_times = opp.get("stage_times")
        if not isinstance(stage_times, dict):
            raise LabError(f"upstream stage_times invalid: {opp.get('id')}")
        if "TRAFFIC" in stage_times:
            start = parse_time(stage_times["TRAFFIC"], f"upstream.{opp.get('id')}.stage_times.TRAFFIC")
            for stage in time_to_stage:
                if stage in stage_times:
                    finish = parse_time(stage_times[stage], f"upstream.{opp.get('id')}.stage_times.{stage}")
                    seconds = int((finish - start).total_seconds())
                    if seconds < 0:
                        raise LabError(f"upstream negative time-to-stage: {opp.get('id')}")
                    time_to_stage[stage].append(seconds)
        _add_money(gross, opp.get("gross_cash_by_currency", {}), f"upstream.{opp.get('id')}.gross_cash_by_currency")
        _add_money(reversals, opp.get("cash_reversals_by_currency", {}), f"upstream.{opp.get('id')}.cash_reversals_by_currency")
        _add_money(net, opp.get("net_cash_by_currency", {}), f"upstream.{opp.get('id')}.net_cash_by_currency")

    eligible_count = len(ready)
    reach_bps = {stage: _basis_points(stage_counts[stage], eligible_count) for stage in STAGES}
    transition_bps: dict[str, int | None] = {}
    for i, stage in enumerate(STAGES[:-1]):
        next_stage = STAGES[i + 1]
        transition_bps[f"{stage}_TO_{next_stage}"] = _basis_points(stage_counts[next_stage], stage_counts[stage])
    medians = {stage: (median_low(values) if values else None) for stage, values in time_to_stage.items()}

    return {
        "arm": dict(arm),
        "assigned_count": len(assigned),
        "eligible_count": eligible_count,
        "held_count": len(held),
        "held_opportunity_ids": sorted(str(opp.get("id")) for opp in held),
        "stage_counts": stage_counts,
        "stage_reach_bps": reach_bps,
        "transition_bps": transition_bps,
        "median_seconds_from_traffic": medians,
        "gross_cash_by_currency": dict(sorted(gross.items())),
        "cash_reversals_by_currency": dict(sorted(reversals.items())),
        "net_cash_by_currency": dict(sorted(net.items())),
    }

def _strategy_status(metrics: Mapping[str, Any], *, minimum_sample: int) -> dict[str, Any]:
    """Describe evidence quality without claiming authenticated experiment chronology.

    Plan/assignment timestamps and immutable-reference metadata are caller-supplied in v1.
    They can enforce internal ordering consistency, but cannot prove when the experiment
    actually existed. Therefore v1 never emits expand/pause/keep-testing strategy advice.
    """
    reasons = ["SELF_ASSERTED_CHRONOLOGY_UNVERIFIED"]
    if metrics["held_count"]:
        reasons.append("UPSTREAM_HOLD_PRESENT")
    if metrics["eligible_count"] < minimum_sample:
        reasons.append("SELF_ASSERTED_MINIMUM_SAMPLE_NOT_MET")
    return {"state": "DESCRIPTIVE_ONLY", "reasons": sorted(reasons)}

def _money_delta(left: Mapping[str, int], right: Mapping[str, int]) -> dict[str, int]:
    return {currency: left.get(currency, 0) - right.get(currency, 0) for currency in sorted(set(left) | set(right))}

def _comparisons(arms: list[dict[str, Any]], minimum_sample: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for left, right in combinations(arms, 2):
        left_rates = left["stage_reach_bps"]
        right_rates = right["stage_reach_bps"]
        rate_delta: dict[str, int | None] = {}
        for stage in ("REPLY", "ACCEPTANCE", "CASH"):
            lval, rval = left_rates[stage], right_rates[stage]
            rate_delta[stage] = None if lval is None or rval is None else lval - rval
        sufficient = (
            left["eligible_count"] >= minimum_sample
            and right["eligible_count"] >= minimum_sample
            and left["held_count"] == 0
            and right["held_count"] == 0
        )
        out.append(
            {
                "left_arm_id": left["arm"]["id"],
                "right_arm_id": right["arm"]["id"],
                "comparison_state": "DESCRIPTIVE_SAMPLE_READY" if sufficient else "DESCRIPTIVE_SAMPLE_INCOMPLETE",
                "stage_reach_bps_delta_left_minus_right": rate_delta,
                "net_cash_delta_left_minus_right_by_currency": _money_delta(left["net_cash_by_currency"], right["net_cash_by_currency"]),
                "interpretation": "OBSERVATIONAL_NOT_CAUSAL",
            }
        )
    return out

def _csv_bytes(arms: list[dict[str, Any]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(
        [
            "arm_id",
            "segment",
            "offer_id",
            "offer_version",
            "proof_package",
            "route_class",
            "assigned_count",
            "eligible_count",
            "held_count",
            "reply_reach_bps",
            "acceptance_reach_bps",
            "cash_reach_bps",
            "strategy_status",
            "strategy_status_reasons",
        ]
    )
    for item in arms:
        arm = item["arm"]
        writer.writerow(
            [
                arm["id"],
                arm["segment"],
                arm["offer_id"],
                arm["offer_version"],
                arm["proof_package"],
                arm["route_class"],
                item["assigned_count"],
                item["eligible_count"],
                item["held_count"],
                "" if item["stage_reach_bps"]["REPLY"] is None else item["stage_reach_bps"]["REPLY"],
                "" if item["stage_reach_bps"]["ACCEPTANCE"] is None else item["stage_reach_bps"]["ACCEPTANCE"],
                "" if item["stage_reach_bps"]["CASH"] is None else item["stage_reach_bps"]["CASH"],
                item["strategy_status"]["state"],
                "|".join(item["strategy_status"]["reasons"]),
            ]
        )
    return out.getvalue().encode("utf-8")

def _markdown_bytes(packet: Mapping[str, Any]) -> bytes:
    lines = [
        "# Commercial experiment evidence packet",
        "",
        f"- State: **{packet['state']}**",
        f"- Evaluated at: `{packet['evaluated_at']}`",
        f"- Experiment: `{packet['experiment']['id']}` revision `{packet['experiment']['revision']}`",
        f"- Family: `{packet['experiment']['family']}`",
        f"- Upstream funnel state: `{packet['upstream_funnel']['state']}`",
        "",
        "## Arm outcomes",
        "",
        "| Arm | Segment | Offer | Route | Eligible / Assigned | Reply bps | Acceptance bps | Cash bps | Strategy status |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in packet["arms"]:
        arm = item["arm"]
        rates = item["stage_reach_bps"]
        def show(value: int | None) -> str:
            return "NA" if value is None else str(value)
        lines.append(
            f"| {arm['id']} | {arm['segment']} | {arm['offer_id']}@{arm['offer_version']} | {arm['route_class']} | "
            f"{item['eligible_count']} / {item['assigned_count']} | {show(rates['REPLY'])} | {show(rates['ACCEPTANCE'])} | "
            f"{show(rates['CASH'])} | {item['strategy_status']['state']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Arm comparisons are descriptive observations over a caller-asserted cohort. They are not causal proof.",
            "Plan declaration time, assignment time and declared thresholds are self-asserted in v1 and are not",
            "authenticated predeclaration evidence. This packet cannot emit expand/pause strategy recommendations.",
            "This packet does not authorize buyer contact, send/resend, proposal submission, contracting, pricing",
            "commitments, provider/payment actions, fulfillment, cash-availability claims, accounting/tax treatment,",
            "or revenue recognition. Existing DNR, suppression, consent and collision controls remain authoritative.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")
