"""Deterministic synthetic acceptance fixture for the Choice/SkyTouch release evidence core."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    from .gate import canonical_json, evaluate, plan_effect_replay, snapshot_sha256, verify_receipt
except ImportError:
    from gate import canonical_json, evaluate, plan_effect_replay, snapshot_sha256, verify_receipt


def _baseline(property_index: int) -> dict[str, Any]:
    return {
        "property_id": f"SYNTH-PROPERTY-{property_index:03d}",
        "revision": 100 + property_index,
        "config": {
            "inventory.overbooking_limit": 2,
            "integration.crm.endpoint_label": f"CRM-SYNTH-{property_index:03d}",
            "integration.crm.retry_limit": 3,
            "rates.default.currency": "USD",
            "rooms.housekeeping.mode": "MANUAL",
        },
    }


def make_bundle(property_index: int) -> dict[str, Any]:
    baseline = _baseline(property_index)
    candidate = deepcopy(baseline)
    candidate["revision"] += 1
    candidate["config"]["integration.crm.retry_limit"] = 5
    candidate["config"]["rooms.housekeeping.mode"] = "SYNCED"
    bundle = {
        "schema": "choice-skytouch-release-evidence/v1",
        "release_id": f"SYNTH-RELEASE-{property_index:03d}",
        "base_snapshot_sha256": snapshot_sha256(baseline),
        "baseline": baseline,
        "candidate": candidate,
        "changes": [
            {
                "path": "integration.crm.retry_limit",
                "before": 3,
                "after": 5,
                "effect_kind": "integration-reload",
            },
            {
                "path": "rooms.housekeeping.mode",
                "before": "MANUAL",
                "after": "SYNCED",
                "effect_kind": "property-config-refresh",
            },
        ],
        "invariants": [
            {"name": "currency-stays-usd", "path": "rates.default.currency", "expected": "USD"},
            {"name": "overbooking-limit-stays-two", "path": "inventory.overbooking_limit", "expected": 2},
        ],
    }
    return bundle


def run_acceptance() -> dict[str, Any]:
    receipts = []
    aggregate_effect_state = None
    total_new_first_pass = 0
    total_collapsed_second_pass = 0

    for index in range(1, 21):
        bundle = make_bundle(index)
        first = evaluate(bundle)
        reversed_bundle = deepcopy(bundle)
        reversed_bundle["changes"] = list(reversed(reversed_bundle["changes"]))
        reversed_bundle["invariants"] = list(reversed(reversed_bundle["invariants"]))
        second = evaluate(reversed_bundle)
        if first.receipt_sha256 != second.receipt_sha256:
            raise RuntimeError("order-invariant receipt mismatch")
        if first.receipt["status"] != "PASS" or not verify_receipt(first.receipt):
            raise RuntimeError("acceptance receipt did not pass")

        plan1 = plan_effect_replay(first.receipt, aggregate_effect_state)
        total_new_first_pass += len(plan1["new_effect_intents"])
        aggregate_effect_state = plan1["effect_state"]
        plan2 = plan_effect_replay(first.receipt, aggregate_effect_state)
        if plan2["new_effect_intents"]:
            raise RuntimeError("second replay emitted a duplicate logical effect")
        total_collapsed_second_pass += len(plan2["collapsed_effect_ids"])
        receipts.append(first.receipt)

    # Hostiles are independent bundles so a single failure cannot mask another class.
    hostiles: dict[str, str] = {}

    stale = make_bundle(1)
    stale["base_snapshot_sha256"] = "0" * 64
    hostiles["stale_base"] = evaluate(stale).receipt["failures"][0]["code"]

    undeclared = make_bundle(2)
    undeclared["candidate"]["config"]["rates.default.currency"] = "EUR"
    hostiles["undeclared_mutation"] = next(
        row["code"] for row in evaluate(undeclared).receipt["failures"] if row["code"] == "UNDECLARED_MUTATION"
    )

    failed_invariant = make_bundle(3)
    failed_invariant["candidate"]["config"]["inventory.overbooking_limit"] = 9
    failed_invariant["changes"].append(
        {"path": "inventory.overbooking_limit", "before": 2, "after": 9, "effect_kind": "property-config-refresh"}
    )
    hostiles["failed_invariant"] = next(
        row["code"] for row in evaluate(failed_invariant).receipt["failures"] if row["code"] == "INVARIANT_FAILED"
    )

    property_drift = make_bundle(4)
    property_drift["candidate"]["property_id"] = "SYNTH-PROPERTY-OTHER"
    hostiles["property_drift"] = next(
        row["code"] for row in evaluate(property_drift).receipt["failures"] if row["code"] == "PROPERTY_ID_DRIFT"
    )

    no_advance = make_bundle(5)
    no_advance["candidate"]["revision"] = no_advance["baseline"]["revision"]
    hostiles["nonadvancing_revision"] = next(
        row["code"] for row in evaluate(no_advance).receipt["failures"] if row["code"] == "NONADVANCING_REVISION"
    )

    summary = {
        "schema": "choice-skytouch-acceptance/v1",
        "synthetic_properties": 20,
        "passing_releases": len(receipts),
        "declared_changes": sum(row["declared_change_count"] for row in receipts),
        "first_pass_new_effect_intents": total_new_first_pass,
        "second_pass_collapsed_effect_intents": total_collapsed_second_pass,
        "second_pass_new_effect_intents": 0,
        "hostile_classes": dict(sorted(hostiles.items())),
        "all_receipts_verified": all(verify_receipt(row) for row in receipts),
        "external_effects_performed": False,
        "buyer_acceptance_claimed": False,
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path)
    args = parser.parse_args(argv)
    summary = run_acceptance()
    payload = canonical_json(summary) + b"\n"
    if args.write:
        args.write.write_bytes(payload)
    print(payload.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
