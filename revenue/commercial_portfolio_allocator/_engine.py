from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

VERSION = "commercial-portfolio-allocator/v1"
PPM = 1_000_000
MAX_OPPORTUNITIES = 256
MAX_CAPACITY_UNITS = 10_000
MAX_MONEY_MINOR = 10**15
MAX_EVIDENCE_AGE_SECONDS = 366 * 24 * 60 * 60

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
KIND_VALUES = {"deal", "competition", "procurement"}
STATE_VALUES = {"ACTIVE", "DNR", "CLOSED", "BLOCKED"}


class ContractError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_exact_keys(obj: Mapping[str, Any], required: set[str], optional: set[str] = set()) -> None:
    keys = set(obj)
    missing = required - keys
    extra = keys - required - optional
    if missing:
        raise ContractError(f"missing keys: {sorted(missing)}")
    if extra:
        raise ContractError(f"unexpected keys: {sorted(extra)}")


def _require_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ContractError(f"invalid {name}")
    return value


def _require_sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ContractError(f"invalid {name}")
    return value


def _require_nonempty_text(value: Any, name: str, limit: int = 512) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ContractError(f"invalid {name}")
    return value


def _require_int(value: Any, name: str, *, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low or value > high:
        raise ContractError(f"invalid {name}")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{name} must be boolean")
    return value


def _parse_ts(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{name} must be UTC Z timestamp")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"invalid {name}") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise ContractError(f"{name} must be UTC")
    return dt


def _ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ContractError("evaluation time must be timezone-aware")
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_ids(values: Any, name: str) -> List[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ContractError(f"{name} must be array")
    out: List[str] = []
    seen = set()
    for raw in values:
        value = _require_id(raw, name)
        if value in seen:
            raise ContractError(f"duplicate {name}: {value}")
        seen.add(value)
        out.append(value)
    return sorted(out)


def derive_collision_key(buyer_id: str, opportunity_key: str) -> str:
    buyer = _require_id(buyer_id, "buyer_id")
    opportunity = _require_id(opportunity_key, "opportunity_key")
    return sha256_hex(canonical_json({"buyer_id": buyer, "opportunity_key": opportunity}))


def _normalize_opportunity(raw: Any, portfolio_currency: str) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ContractError("opportunity must be object")
    _require_exact_keys(
        raw,
        {
            "opportunity_id",
            "buyer_id",
            "opportunity_key",
            "collision_key",
            "kind",
            "state",
            "stage",
            "currency",
            "gross_value_minor",
            "conversion_ppm",
            "conversion_basis_ref",
            "conversion_basis_sha256",
            "risk_ppm",
            "strategic_weight_ppm",
            "effort_units",
            "deadline_at",
            "evidence_observed_at",
            "evidence_source_ref",
            "evidence_source_sha256",
            "requires_dependency_keys",
            "prerequisites_ready",
            "owner_review_ready",
        },
    )
    currency = raw["currency"]
    if not isinstance(currency, str) or not CURRENCY_RE.fullmatch(currency):
        raise ContractError("invalid opportunity.currency")
    if currency != portfolio_currency:
        raise ContractError("opportunity currency does not match portfolio currency")
    kind = raw["kind"]
    if kind not in KIND_VALUES:
        raise ContractError("invalid opportunity.kind")
    state = raw["state"]
    if state not in STATE_VALUES:
        raise ContractError("invalid opportunity.state")
    stage = _require_nonempty_text(raw["stage"], "opportunity.stage", 128)
    opportunity_id = _require_id(raw["opportunity_id"], "opportunity.opportunity_id")
    buyer_id = _require_id(raw["buyer_id"], "opportunity.buyer_id")
    opportunity_key = _require_id(raw["opportunity_key"], "opportunity.opportunity_key")
    collision_key = _require_id(raw["collision_key"], "opportunity.collision_key")
    expected_collision_key = derive_collision_key(buyer_id, opportunity_key)
    if collision_key != expected_collision_key:
        raise ContractError("opportunity.collision_key does not match canonical buyer/opportunity identity")
    return {
        "opportunity_id": opportunity_id,
        "buyer_id": buyer_id,
        "opportunity_key": opportunity_key,
        "collision_key": collision_key,
        "kind": kind,
        "state": state,
        "stage": stage,
        "currency": currency,
        "gross_value_minor": _require_int(raw["gross_value_minor"], "opportunity.gross_value_minor", low=1, high=MAX_MONEY_MINOR),
        "conversion_ppm": _require_int(raw["conversion_ppm"], "opportunity.conversion_ppm", low=0, high=PPM),
        "conversion_basis_ref": _require_nonempty_text(raw["conversion_basis_ref"], "opportunity.conversion_basis_ref"),
        "conversion_basis_sha256": _require_sha(raw["conversion_basis_sha256"], "opportunity.conversion_basis_sha256"),
        "risk_ppm": _require_int(raw["risk_ppm"], "opportunity.risk_ppm", low=0, high=PPM),
        "strategic_weight_ppm": _require_int(raw["strategic_weight_ppm"], "opportunity.strategic_weight_ppm", low=0, high=2 * PPM),
        "effort_units": _require_int(raw["effort_units"], "opportunity.effort_units", low=1, high=MAX_CAPACITY_UNITS),
        "deadline_at": _ts(_parse_ts(raw["deadline_at"], "opportunity.deadline_at")),
        "evidence_observed_at": _ts(_parse_ts(raw["evidence_observed_at"], "opportunity.evidence_observed_at")),
        "evidence_source_ref": _require_nonempty_text(raw["evidence_source_ref"], "opportunity.evidence_source_ref"),
        "evidence_source_sha256": _require_sha(raw["evidence_source_sha256"], "opportunity.evidence_source_sha256"),
        "requires_dependency_keys": _normalize_ids(raw["requires_dependency_keys"], "opportunity.requires_dependency_keys"),
        "prerequisites_ready": _require_bool(raw["prerequisites_ready"], "opportunity.prerequisites_ready"),
        "owner_review_ready": _require_bool(raw["owner_review_ready"], "opportunity.owner_review_ready"),
    }


def normalize_packet(packet: Any) -> Dict[str, Any]:
    if not isinstance(packet, Mapping):
        raise ContractError("packet must be object")
    _require_exact_keys(
        packet,
        {
            "version",
            "portfolio_id",
            "portfolio_currency",
            "capacity_units",
            "horizon_end",
            "evidence_max_age_seconds",
            "satisfied_dependency_keys",
            "opportunities",
        },
    )
    if packet["version"] != VERSION:
        raise ContractError("unsupported version")
    portfolio_id = _require_id(packet["portfolio_id"], "portfolio_id")
    currency = packet["portfolio_currency"]
    if not isinstance(currency, str) or not CURRENCY_RE.fullmatch(currency):
        raise ContractError("invalid portfolio_currency")
    capacity = _require_int(packet["capacity_units"], "capacity_units", low=1, high=MAX_CAPACITY_UNITS)
    horizon = _ts(_parse_ts(packet["horizon_end"], "horizon_end"))
    evidence_age = _require_int(
        packet["evidence_max_age_seconds"],
        "evidence_max_age_seconds",
        low=0,
        high=MAX_EVIDENCE_AGE_SECONDS,
    )
    satisfied = _normalize_ids(packet["satisfied_dependency_keys"], "satisfied_dependency_keys")
    raw_opps = packet["opportunities"]
    if not isinstance(raw_opps, Sequence) or isinstance(raw_opps, (str, bytes, bytearray)):
        raise ContractError("opportunities must be array")
    if len(raw_opps) > MAX_OPPORTUNITIES:
        raise ContractError("too many opportunities")
    opportunities = [_normalize_opportunity(item, currency) for item in raw_opps]
    return {
        "version": VERSION,
        "portfolio_id": portfolio_id,
        "portfolio_currency": currency,
        "capacity_units": capacity,
        "horizon_end": horizon,
        "evidence_max_age_seconds": evidence_age,
        "satisfied_dependency_keys": satisfied,
        "opportunities": opportunities,
    }


def _collapse_opportunities(opps: Sequence[Mapping[str, Any]], reasons: List[str]) -> Tuple[List[Dict[str, Any]], int]:
    by_id: Dict[str, Dict[str, Any]] = {}
    replays = 0
    for raw in opps:
        opp = dict(raw)
        oid = opp["opportunity_id"]
        prior = by_id.get(oid)
        if prior is None:
            by_id[oid] = opp
        elif canonical_json(prior) == canonical_json(opp):
            replays += 1
        else:
            if "OPPORTUNITY_ID_CONFLICT" not in reasons:
                reasons.append("OPPORTUNITY_ID_CONFLICT")
    return sorted(by_id.values(), key=lambda o: o["opportunity_id"]), replays


def _urgency_ppm(now: datetime, deadline: datetime, horizon: datetime) -> int:
    span = max(1, int((horizon - now).total_seconds()))
    remaining = max(0, min(span, int((deadline - now).total_seconds())))
    elapsed_fraction_ppm = ((span - remaining) * PPM) // span
    return PPM + elapsed_fraction_ppm


def _metrics(opp: Mapping[str, Any], *, now: datetime, horizon: datetime) -> Dict[str, int]:
    expected = (opp["gross_value_minor"] * opp["conversion_ppm"]) // PPM
    risk_adjusted = (expected * (PPM - opp["risk_ppm"])) // PPM
    urgency = _urgency_ppm(now, _parse_ts(opp["deadline_at"], "deadline_at"), horizon)
    weighted = (risk_adjusted * urgency) // PPM
    objective = (weighted * opp["strategic_weight_ppm"]) // PPM
    efficiency = (objective * PPM) // opp["effort_units"] if opp["effort_units"] else 0
    return {
        "expected_cash_pipeline_minor": expected,
        "risk_adjusted_pipeline_minor": risk_adjusted,
        "urgency_ppm": urgency,
        "objective_points": objective,
        "efficiency_ppm": efficiency,
    }


def _better_state(candidate: Tuple[int, int, Tuple[str, ...]], incumbent: Optional[Tuple[int, int, Tuple[str, ...]]]) -> bool:
    if incumbent is None:
        return True
    if candidate[0] != incumbent[0]:
        return candidate[0] > incumbent[0]
    if candidate[1] != incumbent[1]:
        return candidate[1] > incumbent[1]
    return candidate[2] < incumbent[2]


def _select_knapsack(eligible: Sequence[Dict[str, Any]], capacity: int) -> Tuple[Tuple[str, ...], int, int, int]:
    # capacity_used -> (total objective, total expected cash, sorted ids)
    dp: Dict[int, Tuple[int, int, Tuple[str, ...]]] = {0: (0, 0, tuple())}
    by_id = {item["opportunity_id"]: item for item in eligible}
    for item in sorted(eligible, key=lambda x: x["opportunity_id"]):
        effort = item["effort_units"]
        objective = item["metrics"]["objective_points"]
        expected = item["metrics"]["expected_cash_pipeline_minor"]
        next_dp = dict(dp)
        for used, state in list(dp.items()):
            new_used = used + effort
            if new_used > capacity:
                continue
            ids = tuple(sorted(state[2] + (item["opportunity_id"],)))
            candidate = (state[0] + objective, state[1] + expected, ids)
            if _better_state(candidate, next_dp.get(new_used)):
                next_dp[new_used] = candidate
        dp = next_dp

    best_used = 0
    best_state = dp[0]
    for used, state in dp.items():
        if _better_state(state, best_state):
            best_used, best_state = used, state
        elif state[0] == best_state[0] and state[1] == best_state[1] and state[2] == best_state[2] and used < best_used:
            best_used = used
    # Defensive invariant: every selected id came from eligible.
    if any(oid not in by_id for oid in best_state[2]):
        raise AssertionError("knapsack returned unknown opportunity")
    return best_state[2], best_used, best_state[0], best_state[1]


def compile_plan(packet: Any, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    normalized = normalize_packet(packet)
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ContractError("now must be timezone-aware")
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    horizon = _parse_ts(normalized["horizon_end"], "horizon_end")

    portfolio_reasons: List[str] = []
    opportunities, replay_collapses = _collapse_opportunities(normalized["opportunities"], portfolio_reasons)

    collision_owner: Dict[str, str] = {}
    for opp in opportunities:
        prior = collision_owner.get(opp["collision_key"])
        if prior is None:
            collision_owner[opp["collision_key"]] = opp["opportunity_id"]
        elif prior != opp["opportunity_id"]:
            if "COLLISION_KEY_CONFLICT" not in portfolio_reasons:
                portfolio_reasons.append("COLLISION_KEY_CONFLICT")

    for opp in opportunities:
        if _parse_ts(opp["evidence_observed_at"], "evidence_observed_at") > now:
            if "FUTURE_EVIDENCE" not in portfolio_reasons:
                portfolio_reasons.append("FUTURE_EVIDENCE")

    suppressed: List[Dict[str, Any]] = []
    eligible: List[Dict[str, Any]] = []
    satisfied = set(normalized["satisfied_dependency_keys"])
    horizon_elapsed = horizon <= now

    for opp in opportunities:
        reasons: List[str] = []
        if horizon_elapsed:
            reasons.append("HORIZON_ELAPSED")
        if opp["state"] == "DNR":
            reasons.append("DNR")
        elif opp["state"] == "CLOSED":
            reasons.append("CLOSED")
        elif opp["state"] == "BLOCKED":
            reasons.append("BLOCKED")

        deadline = _parse_ts(opp["deadline_at"], "deadline_at")
        observed = _parse_ts(opp["evidence_observed_at"], "evidence_observed_at")
        if deadline <= now:
            reasons.append("DEADLINE_PASSED")
        elif deadline > horizon:
            reasons.append("OUTSIDE_HORIZON")
        age = int((now - observed).total_seconds())
        if age > normalized["evidence_max_age_seconds"]:
            reasons.append("STALE_EVIDENCE")
        if not opp["prerequisites_ready"]:
            reasons.append("PREREQUISITES_NOT_READY")
        missing_dependencies = sorted(set(opp["requires_dependency_keys"]) - satisfied)
        if missing_dependencies:
            reasons.append("DEPENDENCY_UNSATISFIED")
        if not opp["owner_review_ready"]:
            reasons.append("OWNER_REVIEW_NOT_READY")
        if opp["effort_units"] > normalized["capacity_units"]:
            reasons.append("EFFORT_EXCEEDS_CAPACITY")

        metrics = _metrics(opp, now=now, horizon=horizon if horizon > now else now)
        if metrics["expected_cash_pipeline_minor"] <= 0 or metrics["objective_points"] <= 0:
            reasons.append("ZERO_ALLOCATABLE_VALUE")

        record = {
            "opportunity_id": opp["opportunity_id"],
            "buyer_id": opp["buyer_id"],
            "collision_key": opp["collision_key"],
            "kind": opp["kind"],
            "stage": opp["stage"],
            "effort_units": opp["effort_units"],
            "deadline_at": opp["deadline_at"],
            "metrics": metrics,
            "conversion_basis_ref": opp["conversion_basis_ref"],
            "evidence_source_ref": opp["evidence_source_ref"],
        }
        if reasons:
            suppressed.append({**record, "reasons": sorted(set(reasons))})
        else:
            eligible.append(record)

    hard_hold = bool(portfolio_reasons)
    selected_ids: Tuple[str, ...] = tuple()
    used_capacity = 0
    total_objective = 0
    total_expected = 0
    if not hard_hold:
        selected_ids, used_capacity, total_objective, total_expected = _select_knapsack(eligible, normalized["capacity_units"])

    selected_set = set(selected_ids)
    selected: List[Dict[str, Any]] = []
    eligible_not_selected: List[Dict[str, Any]] = []
    for record in eligible:
        if record["opportunity_id"] in selected_set:
            selected.append(record)
        else:
            reason = "PORTFOLIO_HOLD" if hard_hold else "CAPACITY_OR_OBJECTIVE_NOT_SELECTED"
            eligible_not_selected.append({**record, "reasons": [reason]})
    suppressed.extend(eligible_not_selected)
    selected.sort(key=lambda r: r["opportunity_id"])
    suppressed.sort(key=lambda r: r["opportunity_id"])

    risk_adjusted_total = sum(r["metrics"]["risk_adjusted_pipeline_minor"] for r in selected)
    gross_total = sum(
        next(o["gross_value_minor"] for o in opportunities if o["opportunity_id"] == r["opportunity_id"])
        for r in selected
    )

    if hard_hold:
        stage = "HOLD"
        next_action = "INVESTIGATE_PORTFOLIO_EVIDENCE"
    elif selected:
        stage = "ALLOCATED"
        next_action = "OWNER_REVIEW_SELECTED"
    else:
        stage = "NO_ELIGIBLE"
        next_action = "REFRESH_OR_SOURCE_OPPORTUNITIES"

    commitment = dict(normalized)
    commitment["opportunities"] = sorted(
        normalized["opportunities"],
        key=lambda o: (o["opportunity_id"], canonical_json(o)),
    )
    input_sha = sha256_hex(canonical_json(commitment))
    core: Dict[str, Any] = {
        "version": VERSION,
        "portfolio_id": normalized["portfolio_id"],
        "evaluated_at": _ts(now),
        "horizon_end": normalized["horizon_end"],
        "stage": stage,
        "next_action": next_action,
        "portfolio_reasons": sorted(portfolio_reasons),
        "currency": normalized["portfolio_currency"],
        "capacity_units": normalized["capacity_units"],
        "used_capacity_units": used_capacity if not hard_hold else 0,
        "unused_capacity_units": normalized["capacity_units"] - (used_capacity if not hard_hold else 0),
        "selected": selected if not hard_hold else [],
        "suppressed": suppressed,
        "selected_gross_pipeline_minor": gross_total if not hard_hold else 0,
        "selected_expected_cash_pipeline_minor": total_expected if not hard_hold else 0,
        "selected_risk_adjusted_pipeline_minor": risk_adjusted_total if not hard_hold else 0,
        "selected_objective_points": total_objective if not hard_hold else 0,
        "booked_revenue_minor": 0,
        "recognized_revenue_minor": 0,
        "replay_collapses": replay_collapses,
        "authority_ceiling": {
            "external_action_authorized": False,
            "buyer_contact_authorized": False,
            "bid_submission_authorized": False,
            "provider_mutation_authorized": False,
            "payment_mutation_authorized": False,
            "buyer_acceptance_inferred": False,
            "booked_revenue_authorized": False,
            "recognized_revenue_authorized": False,
        },
        "truth_notes": {
            "pipeline_value_is_booked_revenue": False,
            "conversion_probability_is_model_inferred": False,
            "source_hash_authenticates_external_truth": False,
        },
        "input_sha256": input_sha,
    }
    core["receipt_sha256"] = sha256_hex(canonical_json(core))
    return core


def verify_plan(packet: Any, plan: Any, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    if not isinstance(plan, Mapping):
        raise ContractError("plan must be object")
    if "evaluated_at" not in plan:
        raise ContractError("plan missing evaluated_at")
    historical_at = _parse_ts(plan["evaluated_at"], "plan.evaluated_at")
    expected = compile_plan(packet, now=historical_at)
    historical_valid = canonical_json(expected) == canonical_json(dict(plan))
    current = compile_plan(packet, now=now)
    return {
        "historical_valid": historical_valid,
        "historical_receipt_sha256": expected["receipt_sha256"],
        "current_stage": current["stage"],
        "current_next_action": current["next_action"],
        "current_receipt_sha256": current["receipt_sha256"],
    }


def render_markdown(plan: Mapping[str, Any]) -> str:
    lines = [
        "# Commercial Portfolio Allocation",
        "",
        f"- Portfolio: `{plan['portfolio_id']}`",
        f"- Stage: **{plan['stage']}**",
        f"- Next owner-review action: **{plan['next_action']}**",
        f"- Evaluated: `{plan['evaluated_at']}`",
        f"- Capacity: `{plan['used_capacity_units']} / {plan['capacity_units']}` units",
        f"- Selected expected-cash pipeline: `{plan['selected_expected_cash_pipeline_minor']} {plan['currency']} minor units`",
        "- Booked revenue by allocator: `0`",
        "",
    ]
    if plan["portfolio_reasons"]:
        lines.extend(["## Portfolio holds", ""])
        lines.extend(f"- `{reason}`" for reason in plan["portfolio_reasons"])
        lines.append("")
    lines.extend(["## Selected", ""])
    if plan["selected"]:
        for item in plan["selected"]:
            metrics = item["metrics"]
            lines.append(
                f"- `{item['opportunity_id']}` — effort {item['effort_units']}; expected pipeline "
                f"{metrics['expected_cash_pipeline_minor']}; objective {metrics['objective_points']}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Truth ceiling", ""])
    lines.append(
        "Selection is an owner-review queue only. It does not authorize contact, submission, provider/payment mutation, "
        "buyer acceptance, booking, or accounting revenue recognition. Declared conversion inputs are not inferred probabilities."
    )
    lines.extend(["", f"Receipt: `{plan['receipt_sha256']}`", ""])
    return "\n".join(lines)
