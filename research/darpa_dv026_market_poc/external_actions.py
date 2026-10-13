from __future__ import annotations

from typing import Any

try:
    from .contract import (
        ContractError,
        MECHANISMS,
        _expect_keys,
        _ratio,
        canonical_bytes,
        sha256_value,
        validate_blackbox_action,
        validate_scenario,
    )
    from .market import (
        _behavioral_metrics,
        _market_receipt,
        _public_value,
        _trader,
        blackbox_observation,
        efficient_surplus,
        run_call,
        run_continuous,
    )
except ImportError:
    from contract import (
        ContractError,
        MECHANISMS,
        _expect_keys,
        _ratio,
        canonical_bytes,
        sha256_value,
        validate_blackbox_action,
        validate_scenario,
    )
    from market import (
        _behavioral_metrics,
        _market_receipt,
        _public_value,
        _trader,
        blackbox_observation,
        efficient_surplus,
        run_call,
        run_continuous,
    )

ACTION_BUNDLE_SCHEMA = "darpa-dv026-external-action-bundle/v1"
EXTERNAL_RESULT_SCHEMA = "darpa-dv026-external-action-evaluation/v1"
EXTERNAL_RECEIPT_SCHEMA = "darpa-dv026-external-action-evaluation-receipt/v1"
EXTERNAL_READY = "EXTERNAL_ACTION_EVALUATION_READY_FOR_OWNER_REVIEW"
EXTERNAL_HOLD = "HOLD_EXTERNAL_ACTION_EVALUATION"


def _normalize_bundle(raw: Any, scenario: dict[str, Any]) -> dict[str, Any]:
    bundle = _expect_keys(raw, {"schema", "scenario_sha256", "actions"}, where="external action bundle")
    if bundle["schema"] != ACTION_BUNDLE_SCHEMA:
        raise ContractError("unsupported external action bundle schema")
    scenario_sha = sha256_value(scenario)
    if bundle["scenario_sha256"] != scenario_sha:
        raise ContractError("external action bundle scenario digest mismatch")
    rows = bundle["actions"]
    if not isinstance(rows, list):
        raise ContractError("external action bundle actions must be a list")
    expected_count = len(MECHANISMS) * len(scenario["traders"])
    if len(rows) != expected_count:
        raise ContractError(f"external action bundle must contain exactly {expected_count} mechanism/trader actions")

    seen: set[tuple[str, str]] = set()
    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        item = _expect_keys(row, {"mechanism", "action"}, where=f"external action bundle.actions[{index}]")
        mechanism = item["mechanism"]
        if mechanism not in MECHANISMS:
            raise ContractError("external action bundle contains unsupported mechanism")
        action = item["action"]
        if not isinstance(action, dict):
            raise ContractError("external action bundle action must be an object")
        trader_id = action.get("trader_id")
        if not isinstance(trader_id, str):
            raise ContractError("external action bundle action trader_id required")
        key = (mechanism, trader_id)
        if key in seen:
            raise ContractError("duplicate external mechanism/trader action")
        seen.add(key)
        normalized_rows.append({"mechanism": mechanism, "action": action})

    expected = {(mechanism, trader["trader_id"]) for mechanism in MECHANISMS for trader in scenario["traders"]}
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise ContractError(f"external action bundle mechanism/trader coverage mismatch missing={missing} extra={extra}")
    return {
        "schema": ACTION_BUNDLE_SCHEMA,
        "scenario_sha256": scenario_sha,
        "actions": sorted(normalized_rows, key=lambda row: (row["mechanism"], row["action"]["trader_id"])),
    }


def _evaluate_mechanism_external(
    scenario: dict[str, Any],
    trader_objs: list[Any],
    trader_map: dict[str, Any],
    mechanism: str,
    efficient: int,
    action_map: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    orders: list[Any] = []
    for trader in sorted(trader_objs, key=lambda item: (item.action_step, item.trader_id)):
        observation = blackbox_observation(scenario, trader, mechanism)
        observation_sha = sha256_value(observation)
        action = action_map[(mechanism, trader.trader_id)]
        order = validate_blackbox_action(action, trader, observation_sha, mechanism)
        observations.append(observation)
        orders.append(order)
    if len({order.order_id for order in orders}) != len(orders):
        raise ContractError("duplicate action/order identity")

    if mechanism == "CONTINUOUS_DOUBLE_AUCTION":
        fills = run_continuous(orders, trader_map)
    else:
        final_reference, _ = _public_value(scenario["reference_price"], scenario["news"], 10**9)
        fills = run_call(orders, trader_map, final_reference)
    realized = sum(fill.surplus for fill in fills)
    return {
        "mechanism": mechanism,
        "efficient_surplus": efficient,
        "realized_surplus": realized,
        "allocative_efficiency": _ratio(realized, efficient),
        "strictly_above_90_percent": efficient > 0 and realized * 10000 > efficient * 9000,
        "behavioral_metrics": _behavioral_metrics(orders, fills, scenario["news"], scenario["reference_price"]),
        "provenance": _market_receipt(mechanism, scenario, observations, orders, fills),
    }


def evaluate_external_actions(raw_scenario: Any, raw_bundle: Any) -> dict[str, Any]:
    scenario = validate_scenario(raw_scenario)
    bundle = _normalize_bundle(raw_bundle, scenario)
    trader_objs = [_trader(row) for row in scenario["traders"]]
    trader_map = {trader.trader_id: trader for trader in trader_objs}
    efficient = efficient_surplus(trader_objs)
    action_map = {(row["mechanism"], row["action"]["trader_id"]): row["action"] for row in bundle["actions"]}
    mechanism_results = [
        _evaluate_mechanism_external(scenario, trader_objs, trader_map, mechanism, efficient, action_map)
        for mechanism in MECHANISMS
    ]

    blockers: list[str] = []
    if efficient <= 0:
        blockers.append("NO_POSITIVE_FEASIBLE_SURPLUS")
    for result in mechanism_results:
        if not result["strictly_above_90_percent"]:
            blockers.append(f"EFFICIENCY_GATE:{result['mechanism']}")

    core = {
        "schema": EXTERNAL_RESULT_SCHEMA,
        "scenario_id": scenario["scenario_id"],
        "scenario_sha256": sha256_value(scenario),
        "action_bundle_sha256": sha256_value(bundle),
        "mechanisms": mechanism_results,
        "status": EXTERNAL_READY if not blockers else EXTERNAL_HOLD,
        "blockers": sorted(blockers),
        "authority": {
            "external_action_file_evaluated": True,
            "external_llm_execution_proven": False,
            "model_provider_identity_proven": False,
            "darpa_phase_i_milestone_proven": False,
            "sbir_eligibility_proven": False,
            "darpa_submission_authorized": False,
            "award_or_payment_proven": False,
        },
    }
    receipt = {
        "schema": EXTERNAL_RECEIPT_SCHEMA,
        "result_sha256": sha256_value(core),
        "scenario_sha256": core["scenario_sha256"],
        "action_bundle_sha256": core["action_bundle_sha256"],
        "evaluation_contract_sha256": sha256_value({
            "bundle_schema": ACTION_BUNDLE_SCHEMA,
            "result_schema": EXTERNAL_RESULT_SCHEMA,
            "mechanisms": list(MECHANISMS),
            "efficiency_gate": "strictly_gt_9000_bps",
            "external_identity_authority": "UNPROVEN",
        }),
    }
    return {**core, "receipt": receipt}


def _validate_external_result_shape(candidate: Any) -> dict[str, Any]:
    result = _expect_keys(
        candidate,
        {"schema", "scenario_id", "scenario_sha256", "action_bundle_sha256", "mechanisms", "status", "blockers", "authority", "receipt"},
        where="external action evaluation result",
    )
    if result["schema"] != EXTERNAL_RESULT_SCHEMA:
        raise ContractError("unsupported external action evaluation result schema")
    if not isinstance(result["mechanisms"], list) or len(result["mechanisms"]) != len(MECHANISMS):
        raise ContractError("external action evaluation result must contain every mechanism exactly once")
    receipt = _expect_keys(
        result["receipt"],
        {"schema", "result_sha256", "scenario_sha256", "action_bundle_sha256", "evaluation_contract_sha256"},
        where="external action evaluation receipt",
    )
    if receipt["schema"] != EXTERNAL_RECEIPT_SCHEMA:
        raise ContractError("unsupported external action evaluation receipt schema")
    return result


def verify_external_result(raw_scenario: Any, raw_bundle: Any, candidate: Any) -> bool:
    try:
        checked = _validate_external_result_shape(candidate)
        expected = evaluate_external_actions(raw_scenario, raw_bundle)
        return canonical_bytes(expected) == canonical_bytes(checked)
    except (UnicodeError, TypeError, ValueError, OverflowError, RecursionError):
        return False


def render_external_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# DARPA DV026 external black-box action evaluation",
        "",
        f"- status: `{result['status']}`",
        f"- scenario: `{result['scenario_id']}`",
        f"- scenario SHA-256: `{result['scenario_sha256']}`",
        f"- action bundle SHA-256: `{result['action_bundle_sha256']}`",
        "- external LLM execution proven: `false`",
        "- model/provider identity proven: `false`",
        "- DARPA Phase-I milestone proven: `false`",
        "- SBIR eligibility proven: `false`",
        "- DARPA submission authorized: `false`",
        "- award/payment proven: `false`",
        "",
        "## Mechanisms",
    ]
    for mechanism in result["mechanisms"]:
        ratio = mechanism["allocative_efficiency"]
        lines.append(
            f"- `{mechanism['mechanism']}`: realized `{mechanism['realized_surplus']}` / efficient "
            f"`{mechanism['efficient_surplus']}`; basis points `{ratio['basis_points']}`; "
            f">90% `{str(mechanism['strictly_above_90_percent']).lower()}`"
        )
    if result["blockers"]:
        lines.extend(["", "## Blockers", *[f"- `{item}`" for item in result["blockers"]]])
    lines.extend([
        "",
        "This evaluates a supplied action file only. It does not prove the actions came from any named model/provider or satisfy a DARPA milestone.",
        "",
        f"Receipt: `{result['receipt']['result_sha256']}`",
        "",
    ])
    return "\n".join(lines)
