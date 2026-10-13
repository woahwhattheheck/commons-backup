#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Town-center sale-advance attribution for the canonical V4 sale-window family.

This module is research/admission infrastructure, not a seller.  It recovers the
narrow E7 theorem from historical V3.1 PR #12423 without reviving the V3 router:
on a town-center consumption tick, a candidate timing plan that moves non-FERT
units from a future reference sale into the current pre-consumption market is an
E7 timing exposure.

The official interpreter processes market orders before town consumption.  A
VETO here therefore means "retain the incumbent/reference timing"; it is not a
claim that waiting dominates after rival supply or other adaptive effects.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
HISTORICAL_DONOR_PR = 12423
DEFAULT_TOWN_CENTER_INTERVAL = 24
TOWN_CENTER_EXCLUDED = frozenset(("FERTILIZER",))


def git_blob(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def verify_engine_source(path: str | Path) -> str:
    """Refuse source drift before treating E7 semantics as current-engine truth."""
    data = Path(path).read_bytes()
    actual = git_blob(data)
    if actual != ENGINE_GIT_BLOB:
        raise ValueError(
            f"engine source drift: expected {ENGINE_GIT_BLOB}, got {actual}"
        )
    return actual


def _normalize_timing(
    rows: Sequence[Sequence[int]] | Iterable[Sequence[int]], now: int, label: str
) -> tuple[dict[int, int] | None, str | None]:
    if not isinstance(rows, (list, tuple)):
        return None, f"{label}-not-sequence"
    out: dict[int, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            return None, f"{label}-bad-row-{index}"
        step, quantity = row
        if type(step) is not int or type(quantity) is not int:
            return None, f"{label}-noninteger-row-{index}"
        if step < now:
            return None, f"{label}-past-row-{index}"
        if quantity < 0:
            return None, f"{label}-negative-quantity-{index}"
        if quantity:
            out[step] = out.get(step, 0) + quantity
    return out, None


def classify_candidate(
    *,
    now: int,
    item: str,
    reference: Sequence[Sequence[int]],
    plan: Sequence[Sequence[int]],
    config: Mapping[str, object] | None = None,
) -> dict:
    """Classify one timing proposal as PASS, VETO, or REFUSE.

    REFUSE is fail-closed: the caller must keep its incumbent plan.  VETO is the
    donor-faithful E7 case: at a town-center tick, equal-total non-FERT timing
    moves positive units from future reference dates into `now`.
    """
    base = {
        "schema": "titan.v4.townclock-attribution/v1",
        "engine_git_blob": ENGINE_GIT_BLOB,
        "historical_donor_pr": HISTORICAL_DONOR_PR,
        "decision": "REFUSE",
        "reason": None,
        "now": now,
        "item": item,
        "interval": None,
        "at_town_center_tick": False,
        "reference_now": 0,
        "plan_now": 0,
        "reference_future": 0,
        "plan_future": 0,
        "advanced_units": 0,
    }
    if type(now) is not int or now < 0:
        base["reason"] = "invalid-now"
        return base
    if not isinstance(item, str) or not item:
        base["reason"] = "invalid-item"
        return base
    if config is None:
        cfg: Mapping[str, object] = {}
    elif isinstance(config, Mapping):
        cfg = config
    else:
        base["reason"] = "invalid-config"
        return base
    interval = cfg.get("townCenterSellInterval", DEFAULT_TOWN_CENTER_INTERVAL)
    if type(interval) is not int or interval <= 0:
        base["reason"] = "invalid-town-center-interval"
        return base
    base["interval"] = interval
    base["at_town_center_tick"] = (now % interval == 0)

    reference_map, error = _normalize_timing(reference, now, "reference")
    if error:
        base["reason"] = error
        return base
    plan_map, error = _normalize_timing(plan, now, "plan")
    if error:
        base["reason"] = error
        return base
    assert reference_map is not None and plan_map is not None

    reference_total = sum(reference_map.values())
    plan_total = sum(plan_map.values())
    if plan_total != reference_total:
        base["reason"] = "quantity-drift"
        return base

    reference_now = reference_map.get(now, 0)
    plan_now = plan_map.get(now, 0)
    reference_future = reference_total - reference_now
    plan_future = plan_total - plan_now
    advanced = min(
        max(0, plan_now - reference_now),
        max(0, reference_future - plan_future),
    )
    base.update(
        reference_now=reference_now,
        plan_now=plan_now,
        reference_future=reference_future,
        plan_future=plan_future,
        advanced_units=advanced,
    )

    if item in TOWN_CENTER_EXCLUDED:
        base["decision"] = "PASS"
        base["reason"] = "town-center-excluded-product"
    elif not base["at_town_center_tick"]:
        base["decision"] = "PASS"
        base["reason"] = "not-town-center-tick"
    elif advanced <= 0:
        base["decision"] = "PASS"
        base["reason"] = "no-future-to-current-advance"
    else:
        base["decision"] = "VETO"
        base["reason"] = "pre-consumption-future-sale-advance"
    return base


def candidate_allowed(**kwargs) -> bool:
    """Admission form: only an explicit PASS may replace the incumbent timing."""
    return classify_candidate(**kwargs)["decision"] == "PASS"


def census(records: Sequence[Mapping[str, object]]) -> dict:
    """Deterministically summarize captured optimizer reference/plan records."""
    if not isinstance(records, list):
        raise ValueError("records must be a JSON list")
    decisions = {"PASS": 0, "VETO": 0, "REFUSE": 0}
    veto_units = 0
    by_item: dict[str, dict[str, int]] = {}
    rows = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            result = {
                "decision": "REFUSE",
                "reason": "record-not-mapping",
                "advanced_units": 0,
                "item": "",
                "now": None,
            }
        else:
            result = classify_candidate(
                now=record.get("now"),  # type: ignore[arg-type]
                item=record.get("item"),  # type: ignore[arg-type]
                reference=record.get("reference"),  # type: ignore[arg-type]
                plan=record.get("plan"),  # type: ignore[arg-type]
                config=record.get("config", {}),  # type: ignore[arg-type]
            )
        decision = result["decision"]
        decisions[decision] += 1
        veto_units += int(result.get("advanced_units", 0)) if decision == "VETO" else 0
        item = str(result.get("item") or "")
        item_counts = by_item.setdefault(
            item, {"PASS": 0, "VETO": 0, "REFUSE": 0, "advanced_units": 0}
        )
        item_counts[decision] += 1
        if decision == "VETO":
            item_counts["advanced_units"] += int(result.get("advanced_units", 0))
        rows.append({"index": index, **result})
    return {
        "schema": "titan.v4.townclock-census/v1",
        "records": len(records),
        "decisions": decisions,
        "veto_advanced_units": veto_units,
        "by_item": {key: by_item[key] for key in sorted(by_item)},
        "rows": rows,
        "policy_claim": False,
        "economic_claim": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("records", type=Path, help="JSON list of optimizer reference/plan records")
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verify_engine_source(args.engine)
    payload = json.loads(args.records.read_text())
    report = census(payload)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
