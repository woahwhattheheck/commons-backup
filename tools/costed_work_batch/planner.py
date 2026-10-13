"""Choose costed batches under one-crew deadlines and permanent family setup.

All economics and availability are caller-supplied WHAT-IF assumptions. A result
is neither evidence that a reward is collectible nor permission to claim/send.
The search is deterministic and returns a certified *model* upper bound when
its node budget is exhausted. See README.md for the precise scheduling model.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cmp_to_key
import hashlib
import json
import re
from typing import Any

SCHEMA = "costed-work-batch/v1"
RESULT_SCHEMA = "costed-work-batch/result/v1"
MAX_JOBS = 256
MAX_MONEY = 10**12
MAX_MINUTES = 525_600
MAX_NODES = 1_000_000
MAX_DOCUMENT_BYTES = 1_048_576
MAX_JSON_DEPTH = 32
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z", re.ASCII)
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:#-]{0,199}\Z", re.ASCII)
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")


class InputError(ValueError):
    """A controlled schema or replay error; never grants execution authority."""


def canonical_json(value: Any) -> str:
    """ASCII JSON with stable keys; a byte identity, not an authenticity seal."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False) + "\n"
    except (TypeError, ValueError, RecursionError) as exc:
        raise InputError("value cannot be represented as bounded JSON") from exc


def parse_json(text: str) -> Any:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            if key in result:
                raise InputError("duplicate JSON object key")
            result[key] = value
        return result

    def integer(token: str) -> int:
        if len(token.lstrip("-")) > 32:
            raise InputError("JSON integer exceeds digit limit")
        return int(token)

    def constant(_: str) -> None:
        raise InputError("nonfinite JSON number")

    try:
        if type(text) is not str or len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise InputError("document exceeds byte limit or is not text")
        # Preflight depth without recursion; brackets inside quoted/escaped text
        # are not structure. json.loads remains the grammar authority.
        depth = 0
        quoted = escaped = False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > MAX_JSON_DEPTH:
                    raise InputError("JSON nesting exceeds depth limit")
            elif char in "]}":
                depth -= 1
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_int=integer)
    except InputError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InputError("invalid UTF-8 JSON document") from exc


def _object(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(k) is not str for k in value):
        raise InputError(f"{where}: expected object with string keys")
    if set(value) != keys:
        raise InputError(f"{where}: unexpected or missing fields")
    return value


def _integer(value: Any, lo: int, hi: int, where: str) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise InputError(f"{where}: integer outside permitted range")
    return value


def _identifier(value: Any, where: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise InputError(f"{where}: expected bounded ASCII identifier")
    return value


def _utc(value: Any, where: str) -> datetime:
    if type(value) is not str or not _UTC.fullmatch(value):
        raise InputError(f"{where}: expected whole-second UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InputError(f"{where}: invalid UTC date") from exc


def _stamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize(scenario: Any) -> dict[str, Any]:
    """Validate before search; do not mutate caller input or infer omitted data."""
    s = _object(scenario, {"schema", "scenario_id", "currency", "start_at",
        "horizon_minutes", "cash_budget_minor", "effort_cost_minor_per_minute",
        "minimum_net_minor", "node_budget", "families", "jobs"}, "scenario")
    if type(s["schema"]) is not str or s["schema"] != SCHEMA:
        raise InputError("unsupported scenario schema")
    _identifier(s["scenario_id"], "scenario_id")
    if type(s["currency"]) is not str or not re.fullmatch(r"[A-Z]{3,12}", s["currency"]):
        raise InputError("currency: expected one uppercase unit label; no FX conversion")
    start = _utc(s["start_at"], "start_at")
    horizon = _integer(s["horizon_minutes"], 1, MAX_MINUTES, "horizon_minutes")
    try:
        start + timedelta(minutes=horizon)
    except OverflowError as exc:
        raise InputError("planning horizon exceeds supported UTC calendar") from exc
    _integer(s["cash_budget_minor"], 0, MAX_MONEY, "cash_budget_minor")
    _integer(s["effort_cost_minor_per_minute"], 0, 10**9, "effort_cost_minor_per_minute")
    _integer(s["minimum_net_minor"], 1, MAX_MONEY, "minimum_net_minor")
    _integer(s["node_budget"], 1, MAX_NODES, "node_budget")
    if type(s["families"]) is not list or len(s["families"]) > MAX_JOBS:
        raise InputError("families: expected bounded array")
    if type(s["jobs"]) is not list or len(s["jobs"]) > MAX_JOBS:
        raise InputError("jobs: expected bounded array")

    families: list[dict[str, Any]] = []
    family_ids: set[str] = set()
    for raw in s["families"]:
        f = _object(raw, {"id", "setup_minutes", "setup_cash_minor"}, "family")
        ident = _identifier(f["id"], "family.id")
        if ident in family_ids:
            raise InputError("duplicate family ID")
        family_ids.add(ident)
        _integer(f["setup_minutes"], 0, MAX_MINUTES, "family.setup_minutes")
        _integer(f["setup_cash_minor"], 0, MAX_MONEY, "family.setup_cash_minor")
        families.append(dict(f))

    jobs: list[dict[str, Any]] = []
    operation_ids: set[str] = set()
    for raw in s["jobs"]:
        j = _object(raw, {"operation_id", "family_id", "availability", "work_units",
            "minutes", "cash_cost_minor", "reward_minor", "collection_probability_bp",
            "valuation_basis", "evidence_ref", "deadline_at"}, "job")
        op = _identifier(j["operation_id"], "job.operation_id")
        if op in operation_ids:
            raise InputError("duplicate operation ID; do not count one job twice")
        operation_ids.add(op)
        if _identifier(j["family_id"], "job.family_id") not in family_ids:
            raise InputError("job references unknown family")
        if type(j["availability"]) is not str or j["availability"] not in ("AVAILABLE", "OWNED_ELSEWHERE", "UNAVAILABLE"):
            raise InputError("job.availability: unsupported value")
        _integer(j["work_units"], 1, 1_000_000, "job.work_units")
        _integer(j["minutes"], 1, MAX_MINUTES, "job.minutes")
        _integer(j["cash_cost_minor"], 0, MAX_MONEY, "job.cash_cost_minor")
        basis = j["valuation_basis"]
        if type(basis) is not str or basis not in ("OWNER_SCENARIO", "ADVERTISED_TERMS", "ACCEPTED_TERMS", "UNVALUED"):
            raise InputError("job.valuation_basis: unsupported value")
        if basis == "UNVALUED":
            if j["reward_minor"] is not None or j["collection_probability_bp"] is not None:
                raise InputError("UNVALUED jobs require null reward and probability")
        else:
            _integer(j["reward_minor"], 0, MAX_MONEY, "job.reward_minor")
            _integer(j["collection_probability_bp"], 0, 10_000, "job.collection_probability_bp")
        ref = j["evidence_ref"]
        if type(ref) is not str or not _REF.fullmatch(ref):
            raise InputError("job.evidence_ref: expected bounded opaque source reference")
        if j["deadline_at"] is not None:
            _utc(j["deadline_at"], "job.deadline_at")
        jobs.append(dict(j))
    return {**s, "families": sorted(families, key=lambda f: f["id"]),
            "jobs": sorted(jobs, key=lambda j: j["operation_id"])}


@dataclass(frozen=True)
class Job:
    operation_id: str
    family_bit: int
    minutes: int
    cash: int
    expected: int
    contribution: int
    deadline: int
    setup_minutes: int
    setup_cash: int


@dataclass(frozen=True)
class State:
    index: int = 0
    families: int = 0
    minutes: int = 0
    cash: int = 0
    expected: int = 0
    chosen: tuple[int, ...] = ()

    def net(self, rate: int) -> int:
        return self.expected - self.cash - self.minutes * rate


def _candidates(s: dict[str, Any]) -> tuple[list[Job], dict[str, list[str]]]:
    families = {f["id"]: (1 << i, f) for i, f in enumerate(s["families"])}
    start = _utc(s["start_at"], "start_at")
    jobs: list[Job] = []
    excluded: dict[str, list[str]] = {}
    for row in s["jobs"]:
        bit, f = families[row["family_id"]]
        reasons: list[str] = []
        if row["availability"] != "AVAILABLE":
            reasons.append(row["availability"])
        if row["valuation_basis"] == "UNVALUED":
            reasons.append("UNVALUED_REWARD")
        deadline = s["horizon_minutes"]
        if row["deadline_at"] is not None:
            delta = _utc(row["deadline_at"], "job.deadline_at") - start
            deadline = min(deadline, (delta.days * 86_400 + delta.seconds) // 60)
        if f["setup_minutes"] + row["minutes"] > deadline:
            reasons.append("DEADLINE_OR_HORIZON_INFEASIBLE")
        if f["setup_cash_minor"] + row["cash_cost_minor"] > s["cash_budget_minor"]:
            reasons.append("CASH_BUDGET_INFEASIBLE")
        expected = 0 if row["reward_minor"] is None else (
            row["reward_minor"] * row["collection_probability_bp"] // 10_000)
        contribution = expected - row["cash_cost_minor"] - row["minutes"] * s["effort_cost_minor_per_minute"]
        if not reasons and contribution <= 0:
            reasons.append("NONPOSITIVE_MARGINAL_NET")
        if reasons:
            excluded[row["operation_id"]] = reasons
        else:
            jobs.append(Job(row["operation_id"], bit, row["minutes"],
                row["cash_cost_minor"], expected, contribution, deadline,
                f["setup_minutes"], f["setup_cash_minor"]))
    # This order is feasibility-complete for the documented permanent-setup model.
    jobs.sort(key=lambda j: (j.deadline, j.operation_id))
    return jobs, excluded


def _append(state: State, i: int, jobs: list[Job], cash_budget: int) -> State | None:
    j = jobs[i]
    first = not (state.families & j.family_bit)
    minutes = state.minutes + j.minutes + (j.setup_minutes if first else 0)
    cash = state.cash + j.cash + (j.setup_cash if first else 0)
    if minutes > j.deadline or cash > cash_budget:
        return None
    return State(i + 1, state.families | j.family_bit, minutes, cash,
                 state.expected + j.expected, state.chosen + (i,))


def _rank(state: State, jobs: list[Job], rate: int) -> tuple[Any, ...]:
    return (-state.net(rate), state.minutes, state.cash,
            tuple(sorted(jobs[i].operation_id for i in state.chosen)))


def _schedule(indices: tuple[int, ...], jobs: list[Job], cash_budget: int) -> State | None:
    state = State()
    for i in sorted(indices):
        after = _append(state, i, jobs, cash_budget)
        if after is None:
            return None
        state = after
    return state


def _density_compare(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    """Descending exact value/weight; free items first, never float division."""
    va, wa, ia = a
    vb, wb, ib = b
    if wa == 0 or wb == 0:
        if wa != wb:
            return -1 if wa == 0 else 1
    else:
        cross = va * wb - vb * wa
        if cross:
            return -1 if cross > 0 else 1
    return (ia > ib) - (ia < ib)


class Bounds:
    """Suffix fractional-knapsack bounds, queried in logarithmic time.

Ignore setup, deadlines and the other resource. Each relaxation is an upper
bound; their minimum remains an upper bound. Precomputation is quadratic in
candidate count, which is capped at 256. Zero-cash jobs remain in the bound.
"""
    def __init__(self, jobs: list[Job]):
        self.tables: list[list[tuple[list[int], list[int], list[tuple[int, int, int]]]]] = []
        for field in ("minutes", "cash"):
            suffixes = []
            for start in range(len(jobs) + 1):
                items = sorted(((j.contribution, getattr(j, field), i)
                    for i, j in enumerate(jobs[start:], start)), key=cmp_to_key(_density_compare))
                weights, values = [0], [0]
                for value, weight, _ in items:
                    weights.append(weights[-1] + weight)
                    values.append(values[-1] + value)
                suffixes.append((weights, values, items))
            self.tables.append(suffixes)

    def remaining(self, index: int, minutes: int, cash: int) -> int:
        upper = []
        for axis, capacity in enumerate((minutes, cash)):
            weights, values, items = self.tables[axis][index]
            k = bisect_right(weights, capacity) - 1
            value = values[k]
            if k < len(items):
                profit, weight, _ = items[k]
                # A fractional optimum can be rounded UP safely, including
                # in the presence of exact integer objective values.
                value += ((capacity - weights[k]) * profit + weight - 1) // weight
            upper.append(value)
        return min(upper)


def _seed(jobs: list[Job], cash_budget: int, rate: int) -> State:
    """Several deterministic feasible heuristics; never an optimality claim."""
    best = State()
    dense = sorted(range(len(jobs)), key=cmp_to_key(lambda a, b: _density_compare(
        (jobs[a].contribution, jobs[a].minutes, a), (jobs[b].contribution, jobs[b].minutes, b))))
    orders = [list(range(len(jobs))), dense,
              sorted(range(len(jobs)), key=lambda i: (-jobs[i].contribution, i))]
    for order in orders:
        selected: tuple[int, ...] = ()
        for i in order:
            candidate = _schedule(selected + (i,), jobs, cash_budget)
            if candidate is not None:
                selected = candidate.chosen
                if _rank(candidate, jobs, rate) < _rank(best, jobs, rate):
                    best = candidate
    # A costly common setup can make every standalone job unattractive while
    # the whole family is profitable. Seed whole families as well as singles.
    groups: dict[int, list[int]] = {}
    for i, j in enumerate(jobs):
        groups.setdefault(j.family_bit, []).append(i)
    group_order = sorted(groups.values(), key=lambda ids: (
        -(sum(jobs[i].contribution for i in ids) - jobs[ids[0]].setup_cash
          - jobs[ids[0]].setup_minutes * rate), tuple(ids)))
    selected = ()
    for ids in group_order:
        individual = _schedule(tuple(ids), jobs, cash_budget)
        if individual is not None and _rank(individual, jobs, rate) < _rank(best, jobs, rate):
            best = individual
        candidate = _schedule(selected + tuple(ids), jobs, cash_budget)
        if candidate is not None and candidate.net(rate) > (
                _schedule(selected, jobs, cash_budget) or State()).net(rate):
            selected = candidate.chosen
            if _rank(candidate, jobs, rate) < _rank(best, jobs, rate):
                best = candidate
    return best


def plan(scenario: Any) -> dict[str, Any]:
    """Return a feasible model batch and a valid bound, even on early cutoff."""
    s = normalize(scenario)
    jobs, excluded = _candidates(s)
    rate, budget = s["effort_cost_minor_per_minute"], s["cash_budget_minor"]
    horizon = s["horizon_minutes"]
    bounds = Bounds(jobs)
    best = _seed(jobs, budget, rate)

    def upper(state: State) -> int:
        return state.net(rate) + bounds.remaining(state.index,
            horizon - state.minutes, budget - state.cash)

    stack: list[tuple[State, int]] = [(State(), upper(State()))]
    expanded = 0
    while stack and expanded < s["node_budget"]:
        state, ceiling = stack.pop()
        if ceiling < best.net(rate):
            continue
        expanded += 1
        if _rank(state, jobs, rate) < _rank(best, jobs, rate):
            best = state
        if state.index == len(jobs):
            continue
        i = state.index
        skipped = State(i + 1, state.families, state.minutes, state.cash,
                        state.expected, state.chosen)
        # LIFO visits include first; every residual subtree retains its bound.
        for child in (skipped, _append(state, i, jobs, budget)):
            if child is not None:
                ceiling = upper(child)
                if ceiling >= best.net(rate):
                    stack.append((child, ceiling))
    # Cheap final pruning matters when the last visited leaf improved the best.
    stack = [(state, ceiling) for state, ceiling in stack if ceiling >= best.net(rate)]
    complete = not stack
    best_net = best.net(rate)
    upper_net = max([best_net] + [ceiling for _, ceiling in stack])
    if best.chosen and best_net >= s["minimum_net_minor"]:
        decision = "QUALIFYING_SCENARIO_BATCH"
    elif upper_net < s["minimum_net_minor"] or complete:
        decision = "NO_QUALIFYING_BATCH"
    else:
        decision = "SEARCH_INCOMPLETE"

    rows = {row["operation_id"]: row for row in s["jobs"]}
    families = {f["id"]: f for f in s["families"]}
    start = _utc(s["start_at"], "start_at")
    timeline: list[dict[str, Any]] = []
    seen: set[str] = set()
    elapsed = 0
    for i in best.chosen:
        j, row = jobs[i], rows[jobs[i].operation_id]
        f = families[row["family_id"]]
        setup = 0 if f["id"] in seen else f["setup_minutes"]
        setup_cash = 0 if f["id"] in seen else f["setup_cash_minor"]
        seen.add(f["id"])
        timeline.append({"operation_id": j.operation_id, "family_id": f["id"],
            "setup_starts_at": _stamp(start + timedelta(minutes=elapsed)),
            "work_starts_at": _stamp(start + timedelta(minutes=elapsed + setup)),
            "finishes_at": _stamp(start + timedelta(minutes=elapsed + setup + j.minutes)),
            "deadline_at": row["deadline_at"], "setup_minutes": setup,
            "work_minutes": j.minutes, "work_units": row["work_units"],
            "setup_cash_minor": setup_cash, "work_cash_minor": j.cash,
            "nominal_reward_minor": row["reward_minor"],
            "collection_probability_bp": row["collection_probability_bp"],
            "scenario_value_minor": j.expected, "valuation_basis": row["valuation_basis"],
            "evidence_ref": row["evidence_ref"]})
        elapsed += setup + j.minutes
    selected = sorted(jobs[i].operation_id for i in best.chosen)
    return {"schema": RESULT_SCHEMA, "scenario_id": s["scenario_id"],
        "currency": s["currency"], "analysis_mode": "WHAT_IF_NOT_AUTHORITY",
        "input_sha256": hashlib.sha256(canonical_json(s).encode("ascii")).hexdigest(),
        "start_at": s["start_at"], "horizon_minutes": horizon,
        "cash_budget_minor": budget, "effort_cost_minor_per_minute": rate,
        "minimum_net_minor": s["minimum_net_minor"], "decision": decision,
        "search": {"status": "OPTIMAL" if complete else "BOUNDED",
            "complete": complete, "net_optimum_proven": upper_net == best_net,
            "lower_bound_minor": best_net, "upper_bound_minor": upper_net,
            "absolute_gap_minor": upper_net - best_net, "nodes_expanded": expanded,
            "node_budget": s["node_budget"], "candidate_count": len(jobs),
            "excluded_count": len(excluded), "algorithm": "edd-setup-bnb-fractional/v1"},
        "batch": {"operation_ids": selected, "family_ids": sorted(seen),
            "job_count": len(selected), "work_units": sum(r["work_units"] for r in timeline),
            "minutes": best.minutes, "cash_cost_minor": best.cash,
            "effort_cost_minor": best.minutes * rate,
            "nominal_reward_minor": sum(r["nominal_reward_minor"] for r in timeline),
            "scenario_value_minor": best.expected, "net_minor": best_net,
            "schedule": timeline},
        "unselected": [{"operation_id": row["operation_id"],
            "reasons": excluded.get(row["operation_id"], ["NOT_SELECTED_BY_SEARCH"])}
            for row in s["jobs"] if row["operation_id"] not in selected],
        "authority": {"source_origin_authenticated": False, "availability_verified": False,
            "task_claimed": False, "external_send_authorized": False,
            "spend_authorized": False, "payment_confirmed": False,
            "revenue_recognized": False}}


def verify(scenario: Any, report: Any) -> dict[str, Any]:
    """Replay supplied scenario; this verifies model integrity, not input truth."""
    expected = plan(scenario)
    if canonical_json(report) != canonical_json(expected):
        raise InputError("report does not match deterministic scenario replay")
    return {"schema": "costed-work-batch/replay/v1", "matches": True,
            "input_sha256": expected["input_sha256"], "analysis_mode": "WHAT_IF_NOT_AUTHORITY"}


def render_text(report: dict[str, Any]) -> str:
    """A readable summary of a report produced by plan(). No implicit FX scale."""
    b, search = report["batch"], report["search"]
    lines = [f"# Costed work batch: {report['scenario_id']}", "",
        "WHAT-IF ONLY. Values, collection probabilities and availability are supplied assumptions.",
        "No task ownership, contact permission, payment, or revenue is established.", "",
        f"Decision: {report['decision']} | Search: {search['status']}",
        f"Unit: {report['currency']} minor units (no currency conversion)",
        f"Scenario value: {b['scenario_value_minor']}; cash cost: {b['cash_cost_minor']}; "
        f"effort cost: {b['effort_cost_minor']}; net: {b['net_minor']}",
        f"Model net interval: [{search['lower_bound_minor']}, {search['upper_bound_minor']}] "
        f"(gap {search['absolute_gap_minor']})",
        f"Minimum net: {report['minimum_net_minor']}; minutes: {b['minutes']}/"
        f"{report['horizon_minutes']}; jobs: {b['job_count']}; work units: {b['work_units']}", "",
        "## Sequential schedule (setup is charged once per family)"]
    for row in b["schedule"]:
        lines.append(f"- {row['operation_id']}: setup {row['setup_starts_at']} "
            f"({row['setup_minutes']}m), work {row['work_starts_at']} -> {row['finishes_at']}; "
            f"deadline {row['deadline_at'] or 'planning horizon'}")
    if not b["schedule"]:
        lines.append("No positive-net model batch selected.")
    lines.extend(["", "## Not selected"])
    for row in report["unselected"]:
        lines.append(f"- {row['operation_id']}: {', '.join(row['reasons'])}")
    lines.extend(["", "Before work: refresh the existing work record and claim ledger; "
        "resolve ownership, actual terms, payout and current deadlines. External "
        "outreach still requires Muse selection and a fresh provider-history check.",
        f"Input digest (integrity only): {report['input_sha256']}"])
    return "\n".join(lines) + "\n"
