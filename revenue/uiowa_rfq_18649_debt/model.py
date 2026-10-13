"""Offline service-level technical-debt scenarios; no external effects.

All solver arithmetic is integer hundredths of an hour. Qualitative service
impact is deliberately not converted into a hidden monetary or maturity score.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SCHEMA = "tjlabs.technical-debt-register/v1"
MAX_ITEMS = 18  # Exhaustive search: at most 2**18 portfolios, never a heuristic.
MAX_BYTES = 2_000_000
FIELDS = {
    "id", "service", "category", "summary", "service_impact", "service_consequence",
    "owner_role", "evidence_refs", "estimate_basis", "effort_hours",
    "weekly_support_hours", "reduction_pct", "benefit_delay_weeks", "benefit_pool",
    "alternative_group", "dependencies", "revisit_trigger",
}


class InputError(ValueError):
    """An actionable, invalid-input diagnosis, not an empty successful result."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _reject(value: str) -> None:
    raise InputError(f"non-integer JSON number is unsupported: {value[:40]}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_register(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise InputError(f"register must be UTF-8 bytes, at most {MAX_BYTES} bytes")
    def integer(token: str) -> int:
        if len(token) > 12:
            raise InputError("integer token exceeds 12 characters")
        return int(token)
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                           parse_float=_reject, parse_constant=_reject, parse_int=integer)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InputError(f"cannot read register: {str(exc)[:180]}") from exc
    return validate(value)


def _object(value: Any, fields: set[str], name: str) -> None:
    if type(value) is not dict or set(value) != fields:
        raise InputError(f"{name}: expected exactly fields {', '.join(sorted(fields))}")


def _text(value: Any, name: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if type(value) is not str or not value.strip() or len(value) > 2000:
        raise InputError(f"{name}: expected nonblank text of at most 2000 characters")
    if any(ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise InputError(f"{name}: control characters and surrogate code points are unsupported")


def _integer(value: Any, name: str, lower: int, upper: int) -> None:
    if type(value) is not int or not lower <= value <= upper:
        raise InputError(f"{name}: expected integer in [{lower}, {upper}]")


def _strings(value: Any, name: str) -> None:
    if type(value) is not list or len(value) > 100:
        raise InputError(f"{name}: expected list of at most 100 strings")
    for element in value:
        _text(element, name)
    if len(set(value)) != len(value):
        raise InputError(f"{name}: duplicate entries")


def _interval(value: Any, name: str, upper: int) -> None:
    if value is None:
        return  # Missing is not zero; such an item cannot enter a numeric portfolio.
    _object(value, {"low", "high"}, name)
    _integer(value["low"], name + ".low", 0, upper)
    _integer(value["high"], name + ".high", value["low"], upper)


def validate(value: Any) -> dict[str, Any]:
    _object(value, {"schema", "evidence_class", "items"}, "register")
    if value["schema"] != SCHEMA:
        raise InputError(f"schema must be {SCHEMA}")
    if value["evidence_class"] not in ("SYNTHETIC", "ASSESSMENT_INPUT"):
        raise InputError("evidence_class must be SYNTHETIC or ASSESSMENT_INPUT")
    items = value["items"]
    if type(items) is not list or not 1 <= len(items) <= MAX_ITEMS:
        raise InputError(f"use 1..{MAX_ITEMS} items per explicit decision cohort; no silent truncation")
    ids: set[str] = set()
    for item in items:
        _object(item, FIELDS, "debt item")
        for field in ("id", "service", "category", "summary", "service_impact",
                      "service_consequence", "owner_role", "estimate_basis", "revisit_trigger"):
            _text(item[field], field)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", item["id"]):
            raise InputError("id must be 1..64 ASCII letters, digits, dot, underscore or hyphen")
        if item["id"] in ids:
            raise InputError(f"duplicate id: {item['id']}")
        ids.add(item["id"])
        if item["category"] not in ("RECURRING_SUPPORT", "OBSOLESCENCE", "ARCHITECTURE", "MAINTAINABILITY"):
            raise InputError(f"{item['id']}: unsupported category")
        if item["service_impact"] not in ("LOW", "MODERATE", "HIGH", "CRITICAL"):
            raise InputError(f"{item['id']}: unsupported service_impact")
        if item["estimate_basis"] not in ("OBSERVED", "ESTIMATED", "UNKNOWN"):
            raise InputError(f"{item['id']}: unsupported estimate_basis")
        _strings(item["evidence_refs"], "evidence_refs")
        _strings(item["dependencies"], "dependencies")
        if item["estimate_basis"] == "OBSERVED" and not item["evidence_refs"]:
            raise InputError(f"{item['id']}: OBSERVED requires evidence references")
        _interval(item["effort_hours"], "effort_hours", 1_000_000)
        _interval(item["weekly_support_hours"], "weekly_support_hours", 1_000_000)
        _interval(item["reduction_pct"], "reduction_pct", 100)
        _integer(item["benefit_delay_weeks"], "benefit_delay_weeks", 0, 520)
        _text(item["benefit_pool"], "benefit_pool", nullable=True)
        _text(item["alternative_group"], "alternative_group", nullable=True)
        support, reduction = item["weekly_support_hours"], item["reduction_pct"]
        if support and reduction and support["high"] * reduction["high"] and not item["benefit_pool"]:
            raise InputError(f"{item['id']}: nonzero benefit requires a benefit_pool")
        if item["estimate_basis"] == "UNKNOWN" and all(item[k] is not None for k in
                ("effort_hours", "weekly_support_hours", "reduction_pct")):
            raise InputError(f"{item['id']}: UNKNOWN must retain at least one null estimate")
    by_id = {item["id"]: item for item in items}
    for item in items:
        for dep in item["dependencies"]:
            if dep not in by_id:
                raise InputError(f"{item['id']}: missing dependency {dep}")
    done: set[str] = set()
    active: set[str] = set()
    def visit(key: str) -> None:
        if key in active:
            raise InputError(f"dependency cycle includes {key}")
        if key not in done:
            active.add(key)
            for dep in by_id[key]["dependencies"]:
                visit(dep)
            active.remove(key)
            done.add(key)
    for key in by_id:
        visit(key)
    # Detach caller containers and put rows in canonical identity order.
    result = json.loads(canonical(value))
    result["items"].sort(key=lambda item: item["id"])
    for item in result["items"]:
        item["dependencies"].sort()
        item["evidence_refs"].sort()
    return result


def _hours(hundredths: int) -> str:
    sign = "-" if hundredths < 0 else ""
    whole, fraction = divmod(abs(hundredths), 100)
    return f"{sign}{whole}.{fraction:02d}"


def _known(item: dict[str, Any]) -> bool:
    return all(item[key] is not None for key in ("effort_hours", "weekly_support_hours", "reduction_pct"))


def analyze(register: dict[str, Any], budget_hours: int, horizon_weeks: int,
            required_ids: tuple[str, ...] = ()) -> dict[str, Any]:
    data = validate(register)
    _integer(budget_hours, "budget_hours", 0, 10_000_000)
    _integer(horizon_weeks, "horizon_weeks", 1, 520)
    if type(required_ids) not in (list, tuple):
        raise InputError("required_ids must be a list or tuple of item IDs")
    required = list(required_ids)
    _strings(required, "required_ids")
    items = data["items"]
    ids = [item["id"] for item in items]
    index = {key: i for i, key in enumerate(ids)}
    if any(key not in index for key in required):
        raise InputError("required_ids contains an unknown item")
    n = len(items)
    needs: list[int] = [0] * n
    conflicts: list[int] = [0] * n
    costs: list[int] = [0] * n
    low: list[int] = [0] * n
    high: list[int] = [0] * n
    unknown_mask = 0
    rows: list[dict[str, Any]] = []
    def closure(i: int) -> int:
        mask = 1 << i
        for dep in items[i]["dependencies"]:
            mask |= closure(index[dep])
        return mask
    for i, item in enumerate(items):
        needs[i] = closure(i)
        for j, other in enumerate(items):
            if i != j and any(item[k] is not None and item[k] == other[k]
                              for k in ("benefit_pool", "alternative_group")):
                conflicts[i] |= 1 << j
        row = dict(item)
        row["dependency_closure"] = [ids[j] for j in range(n) if needs[i] & (1 << j)]
        if not _known(item):
            unknown_mask |= 1 << i
            row["modeled"] = None
        else:
            effort, weekly, pct = (item[k] for k in ("effort_hours", "weekly_support_hours", "reduction_pct"))
            weeks = max(0, horizon_weeks - item["benefit_delay_weeks"])
            saved_low = weekly["low"] * pct["low"] * weeks
            saved_high = weekly["high"] * pct["high"] * weeks
            costs[i] = effort["high"]
            low[i] = saved_low - 100 * effort["high"]
            high[i] = saved_high - 100 * effort["low"]
            row["modeled"] = {
                "benefit_weeks": weeks, "saved_hours_low": _hours(saved_low),
                "saved_hours_high": _hours(saved_high), "net_hours_low": _hours(low[i]),
                "net_hours_high": _hours(high[i]),
            }
        rows.append(row)
    required_mask = sum(1 << index[key] for key in required)
    winners: list[tuple[Any, ...] | None] = [None, None]
    selected: list[dict[str, Any] | None] = [None, None]
    feasible = 0
    visited = 0
    def walk(i: int, mask: int, cost: int, lo: int, hi: int, needed: int) -> None:
        nonlocal feasible, visited
        if i == n:
            visited += 1
            if mask & required_mask != required_mask or mask & needed != needed:
                return
            feasible += 1
            chosen = [ids[j] for j in range(n) if mask & (1 << j)]
            for objective, key in enumerate(((-lo, -hi, cost, tuple(chosen)),
                                              (-hi, -lo, cost, tuple(chosen)))):
                if winners[objective] is None or key < winners[objective]:
                    winners[objective] = key
                    selected[objective] = {"ids": chosen, "effort_hours_high": cost,
                        "net_hours_low": _hours(lo), "net_hours_high": _hours(hi),
                        "unused_capacity_hours": budget_hours - cost}
            return
        walk(i + 1, mask, cost, lo, hi, needed)
        bit = 1 << i
        if not unknown_mask & bit and not conflicts[i] & mask and cost + costs[i] <= budget_hours:
            walk(i + 1, mask | bit, cost + costs[i], lo + low[i], hi + high[i], needed | needs[i])
    walk(0, 0, 0, 0, 0, 0)
    conservative = set(selected[0]["ids"]) if selected[0] else set()
    optimistic = set(selected[1]["ids"]) if selected[1] else set()
    investigations: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        group = [j for j in range(n) if needs[i] & (1 << j)]
        if row["id"] in conservative:
            disposition = "SELECTED_IN_CONSERVATIVE_SCENARIO"
        elif needs[i] & unknown_mask:
            disposition = "NEEDS_ESTIMATE"
        elif any(conflicts[j] & needs[i] for j in group):
            disposition = "INCOMPATIBLE_DEPENDENCY_CLOSURE"
        elif sum(costs[j] for j in group) > budget_hours:
            disposition = "DEPENDENCY_CLOSURE_EXCEEDS_CAPACITY"
        elif row["id"] in optimistic:
            disposition = "UNCERTAINTY_SENSITIVE"
        elif sum(high[j] for j in group) <= 0:
            disposition = "NO_POSITIVE_MODELED_PAYBACK"
        else:
            disposition = "DEFER_IN_THIS_PORTFOLIO"
        row["disposition"] = disposition
        if needs[i] & unknown_mask:
            question = "Obtain missing effort, weekly burden or reduction bounds for this dependency closure."
            priority = 1
        elif row["service_impact"] in ("HIGH", "CRITICAL") and row["id"] not in conservative:
            question = "Review service consequence before deferral; avoided risk is not valued by support-hour payback."
            priority = 2
        elif row["id"] in optimistic - conservative:
            question = "Validate the benefit and effort bounds that change the selected portfolio."
            priority = 3
        elif row["estimate_basis"] != "OBSERVED":
            question = "Corroborate assumptions with a representative backlog/support sample and its observation period."
            priority = 4
        else:
            question = "Check workload overlap, benefit timing and the recorded revisit trigger with the service owner."
            priority = 5
        investigations.append({"priority": priority, "id": row["id"], "question": question,
                               "revisit_trigger": row["revisit_trigger"]})
    report: dict[str, Any] = {
        "schema": "tjlabs.technical-debt-analysis/v1", "evidence_class": data["evidence_class"],
        "decision_status": "SCENARIOS_AVAILABLE" if feasible else "NO_FEASIBLE_PORTFOLIO",
        "truth_boundary": "ANALYST_SCENARIO_NOT_APPROVAL_OR_UNIVERSITY_FINDING",
        "register_sha256": hashlib.sha256(canonical(data)).hexdigest(),
        "parameters": {"budget_hours": budget_hours, "horizon_weeks": horizon_weeks,
                       "required_ids": sorted(required)},
        "method": {"objective": "net support hours saved; qualitative impact remains separate",
                   "capacity_basis": "sum of selected upper effort bounds, shared dependencies counted once",
                   "uncertainty": "endpoint scenarios, not probabilities or confidence intervals",
                   "benefit_timing": "each item's explicit delay includes implementation and dependency lead time",
                   "overlap": "at most one item per non-null benefit pool and alternative group",
                   "tie_break": "other endpoint, lower upper effort, lexicographically sorted IDs"},
        "search": {"cohort_items": n, "visited_leaf_portfolios": visited,
                   "feasible_portfolios": feasible, "exhaustive_with_capacity_and_exclusion_pruning": True},
        "portfolios": {"conservative": selected[0], "optimistic": selected[1]},
        "uncertainty_sensitive_ids": sorted(conservative ^ optimistic),
        "items": rows,
        "investigations": sorted(investigations, key=lambda q: (q["priority"], q["id"])),
    }
    report["report_sha256"] = hashlib.sha256(canonical(report)).hexdigest()
    return report
