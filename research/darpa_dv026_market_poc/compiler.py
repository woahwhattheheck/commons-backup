from __future__ import annotations

from typing import Any

try:
    from .contract import MECHANISMS, RECEIPT_SCHEMA, RESULT_SCHEMA, SCHEMA, STATUS_HOLD, STATUS_READY, sha256_value, validate_scenario
    from .evaluator import evaluate_mechanism
    from .market import _trader, efficient_surplus
except ImportError:
    from contract import MECHANISMS, RECEIPT_SCHEMA, RESULT_SCHEMA, SCHEMA, STATUS_HOLD, STATUS_READY, sha256_value, validate_scenario
    from evaluator import evaluate_mechanism
    from market import _trader, efficient_surplus


def compile_result(raw_scenario: Any) -> dict[str, Any]:
    scenario = validate_scenario(raw_scenario)
    trader_objs = [_trader(row) for row in scenario["traders"]]
    trader_map = {t.trader_id: t for t in trader_objs}
    efficient = efficient_surplus(trader_objs)
    mechanism_results = [
        evaluate_mechanism(scenario, trader_objs, trader_map, mechanism, efficient)
        for mechanism in MECHANISMS
    ]

    blockers: list[str] = []
    if efficient <= 0:
        blockers.append("NO_POSITIVE_FEASIBLE_SURPLUS")
    for result in mechanism_results:
        if not result["strictly_above_90_percent"]:
            blockers.append(f"EFFICIENCY_GATE:{result['mechanism']}")
    if len(scenario["panel"]["slots"]) != 10:
        blockers.append("TEN_MODEL_PLAN_MISSING")
    if scenario["panel"]["external_execution"]:
        blockers.append("EXTERNAL_EXECUTION_TRUTH_CONFLICT")

    core = {
        "schema": RESULT_SCHEMA,
        "scenario_schema": SCHEMA,
        "scenario_id": scenario["scenario_id"],
        "scenario_sha256": sha256_value(scenario),
        "mechanisms": mechanism_results,
        "panel": {
            "logical_slots": 10,
            "external_llm_panel_executed": False,
            "panel_sha256": sha256_value(scenario["panel"]),
        },
        "benchmark": {
            "kind": scenario["benchmark"]["kind"],
            "benchmark_id": scenario["benchmark"]["benchmark_id"],
            "source_sha256": scenario["benchmark"]["source_sha256"],
            "new_human_subject_collection": False,
            "benchmark_authority_claim": "SYNTHETIC_TEST_VECTOR" if scenario["benchmark"]["kind"] == "SYNTHETIC" else "PUBLIC_PREEXISTING_SOURCE_COMMITMENT_ONLY",
        },
        "status": STATUS_READY if not blockers else STATUS_HOLD,
        "blockers": sorted(blockers),
        "authority": {
            "sbir_eligibility_proven": False,
            "darpa_submission_authorized": False,
            "external_model_execution_proven": False,
            "human_market_calibration_proven": False,
            "award_or_payment_proven": False,
        },
    }
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "result_sha256": sha256_value(core),
        "scenario_sha256": core["scenario_sha256"],
        "implementation_contract_sha256": sha256_value({
            "schema": SCHEMA,
            "result_schema": RESULT_SCHEMA,
            "mechanisms": list(MECHANISMS),
            "efficiency_gate": "strictly_gt_9000_bps",
        }),
    }
    return {**core, "receipt": receipt}
