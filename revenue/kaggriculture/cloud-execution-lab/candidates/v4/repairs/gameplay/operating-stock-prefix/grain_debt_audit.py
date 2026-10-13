# SPDX-License-Identifier: Apache-2.0
"""Diagnose WHEAT-sale/feed-stock interactions in canonical TITAN V4 traces.

This is evidence tooling only.  It does not rewrite an action, controller,
runtime, configuration, archive, or submission.
"""
from __future__ import annotations

from collections import Counter
import argparse
import json
from pathlib import Path
from typing import Any, Iterable

CAP_REASON = "feed_reservation_exceeds_two_units"
BINDING_GAP_REASONS = {
    "no_matching_completed_unit_snapshot",
    "crop_input_repair_owns_current_queue",
}


def _nonnegative_int(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("expected nonnegative integer")
    return value


def wheat_sale_quantity(action: Any, *, executable_cap: int = 10) -> int:
    """Count returned executable-prefix WHEAT SELL quantity, fail-closed."""
    if not isinstance(action, dict):
        raise ValueError("returned action must be an object")
    market = action.get("market")
    if not isinstance(market, list):
        raise ValueError("returned action market must be a list")
    if type(executable_cap) is not int or executable_cap < 1:
        raise ValueError("invalid executable cap")
    total = 0
    for row in market[:executable_cap]:
        if not row:
            continue
        if not isinstance(row, list):
            raise ValueError("malformed market row")
        if len(row) >= 2 and row[:2] == ["SELL", "WHEAT"]:
            if len(row) != 3:
                raise ValueError("malformed WHEAT sale")
            total += _nonnegative_int(row[2])
    return total


def cap_witness(*, stock: int, offered: int, required: int, returned_wheat: int = 0) -> dict:
    """Mirror the current protect_feed_stock reservation algebra.

    The production helper computes permitted/withheld exactly this way, then
    declines the repair when withheld > 2.  This helper makes that boundary
    explicit without pretending to execute the rest of the feed certificate.
    """
    stock = _nonnegative_int(stock)
    offered = _nonnegative_int(offered)
    required = _nonnegative_int(required)
    returned_wheat = _nonnegative_int(returned_wheat)
    if required > stock + returned_wheat:
        return {
            "coverable": False,
            "permitted_sale": None,
            "withheld_units": None,
            "cap_bypass": False,
        }
    permitted = min(stock, max(0, stock + returned_wheat - required))
    withheld = max(0, min(stock, offered) - permitted)
    return {
        "coverable": True,
        "permitted_sale": permitted,
        "withheld_units": withheld,
        "cap_bypass": withheld > 2,
    }


def classify_event(event: Any) -> dict:
    """Classify one returned callback plus TitanAgent diagnostics.

    Expected fields:
      step: optional nonnegative integer
      returned_action (or action): exact returned action object
      diagnostics: TitanAgent diagnostics object containing feed_stock
      delta_margin: optional number copied from the surrounding gate cell
    """
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    action = event.get("returned_action", event.get("action"))
    sale = wheat_sale_quantity(action)
    step = event.get("step")
    if step is not None:
        step = _nonnegative_int(step)
    diagnostics = event.get("diagnostics")
    if diagnostics is None:
        diagnostics = {}
    if not isinstance(diagnostics, dict):
        raise ValueError("diagnostics must be an object")
    feed = diagnostics.get("feed_stock")

    result = {
        "step": step,
        "returned_wheat_sale": sale,
        "classification": None,
        "reason": None,
        "certified": False,
        "changed": False,
    }
    if sale == 0:
        result["classification"] = "NO_RETURNED_WHEAT_SALE"
        return result
    if not isinstance(feed, dict):
        result["classification"] = "MISSING_FEED_STOCK_DIAGNOSTIC"
        return result

    reason = feed.get("reason")
    changed = feed.get("changed") is True
    certified = feed.get("certified") is True
    result.update(reason=reason, changed=changed, certified=certified)
    for key in ("required_wheat", "withheld_units", "observed_shed_wheat"):
        if key in feed and type(feed[key]) is int and feed[key] >= 0:
            result[key] = feed[key]

    if reason == CAP_REASON:
        result["classification"] = "CAP_BYPASS_RETURNED_SALE"
    elif reason == "reserve_reachable_feed" and changed and certified:
        result["classification"] = "GUARD_RESERVED_FEED"
    elif reason == "feed_prefix_already_covered" and certified and not changed:
        result["classification"] = "FEED_ALREADY_COVERED"
    elif reason in BINDING_GAP_REASONS and not certified:
        result["classification"] = "BINDING_GAP_RETURNED_SALE"
    elif not certified:
        result["classification"] = "OTHER_UNCERTIFIED_RETURNED_SALE"
    else:
        result["classification"] = "OTHER_CERTIFIED_RETURNED_SALE"
    return result


def summarize(events: Iterable[Any]) -> dict:
    """Aggregate callback classifications; never infer starvation from sale alone."""
    counts = Counter()
    reasons = Counter()
    cap_steps = []
    cap_sale_quantity = 0
    total_sale_quantity = 0
    rows = []
    for event in events:
        row = classify_event(event)
        rows.append(row)
        counts[row["classification"]] += 1
        if row.get("reason") is not None:
            reasons[str(row["reason"])] += 1
        total_sale_quantity += row["returned_wheat_sale"]
        if row["classification"] == "CAP_BYPASS_RETURNED_SALE":
            cap_steps.append(row["step"])
            cap_sale_quantity += row["returned_wheat_sale"]
    return {
        "schema": "titan-v4-graindebt-audit/v1",
        "events": len(rows),
        "returned_wheat_sale_quantity": total_sale_quantity,
        "classification_counts": dict(sorted(counts.items())),
        "reason_counts": dict(sorted(reasons.items())),
        "cap_bypass": {
            "events": counts.get("CAP_BYPASS_RETURNED_SALE", 0),
            "returned_wheat_sale_quantity": cap_sale_quantity,
            "steps": cap_steps,
            "causal_status": "REQUIRES_DOWNSTREAM_FEED_OUTCOME_CORRELATION"
            if cap_steps else "NOT_OBSERVED",
        },
        "policy_mutation": False,
    }


def _load_records(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return payload["events"]
    raise ValueError("input must be a JSON list, {events:[...]}, or JSONL")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = summarize(_load_records(args.input))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
