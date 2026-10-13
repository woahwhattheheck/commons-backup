"""Pinned full-interpreter, open-loop sale-time counterfactuals; NOT a policy.

Only recorded actions are replayed. Opponents do not adapt after intervention.
Raw market positions are preserved, including invalid rows and the live cap.
The observer records successful SELL units, not inventory-admission estimates.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

PINS = {
    "engine/kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "engine/kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "engine/utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
    "evaluator/loader.py": "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def load_engine(reference):
    """Authenticate all inputs before using the existing offline loader."""
    root = Path(reference)
    for name, expected in PINS.items():
        data = (root / name).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != expected:
            raise ValueError("source mismatch: " + name)
    spec = importlib.util.spec_from_file_location("harvestclock_loader", root / "evaluator/loader.py")
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    engine, _ = loader.get_engine(root / "engine")
    return engine, loader.Struct


def initialize(engine, Struct, seed=17, configuration=None):
    cfg = Struct({k: v.get("default") if isinstance(v, dict) else v
                  for k, v in engine.specification["configuration"].items()})
    cfg.update(configuration or {})
    cfg.seed = seed
    env = Struct(configuration=cfg, done=False, info={})
    state = [Struct(observation=Struct(), action={}, status="ACTIVE", reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    return state, env


def shift_sale(tape, seat, source_turn, source_row, target_turn, target_row):
    """Move one literal SELL, retaining all other raw slots and unit actions.

    Turns are zero-based tape indices. Destination must be a literal market PASS
    or the next appended slot. No compaction, quantity coercion or cap assumption.
    """
    if seat not in (0, 1) or type(seat) is not int:
        raise ValueError("seat must be 0 or 1")
    for index in (source_turn, source_row, target_turn, target_row):
        if type(index) is not int or index < 0:
            raise ValueError("nonnegative integer indices required")
    if source_turn == target_turn:
        raise ValueError("a timing intervention requires different turns")
    if max(source_turn, target_turn) >= len(tape):
        raise ValueError("turn outside tape")
    out = [[copy.deepcopy(action) for action in pair] for pair in tape]
    source = out[source_turn][seat].get("market", [])
    target = out[target_turn][seat].setdefault("market", [])
    if not isinstance(source, list) or not isinstance(target, list):
        raise ValueError("market must be a list")
    if source_row >= len(source):
        raise ValueError("source row absent")
    row = source[source_row]
    if not (isinstance(row, list) and len(row) == 3 and row[0] == "SELL"
            and isinstance(row[1], str) and type(row[2]) is int and row[2] > 0):
        raise ValueError("source must be a positive literal SELL")
    if target_row > len(target) or (target_row < len(target) and target[target_row] != ["PASS"]):
        raise ValueError("destination must be PASS or next appended slot")
    source[source_row] = ["PASS"]
    if target_row == len(target):
        target.append(copy.deepcopy(row))
    else:
        target[target_row] = copy.deepcopy(row)
    return out


def observed_step(engine, state, env, actions, step):
    """Execute one complete engine turn; temporary observers restore on failure.

    This is a sequential offline API, not thread-safe. The engine remains the
    only transition implementation. Successful $1 sales still count as fills.
    """
    if len(state) != 2 or len(actions) != 2:
        raise ValueError("two-player state/action pair required")
    if type(step) is not int or step < 0 or env.done or any(s.status == "DONE" for s in state):
        raise ValueError("cannot execute outside a live episode")
    for seat in (0, 1):
        state[seat].observation.step = step
        state[seat].action = copy.deepcopy(actions[seat])
    cap = max(1, int(env.configuration.get("maxMarketOrdersPerTurn", 10)))
    queues = []
    for action in actions:
        market = action.get("market", []) if isinstance(action, dict) else []
        queues.append(market[:cap] if isinstance(market, list) else [])
    slots = iter((seat, row) for row in range(max(map(len, queues), default=0))
                 for seat in (0, 1) if row < len(queues[seat]))
    current = {}
    report = {"step": step, "rows": [], "market_entry_shed": None}
    original_parse, original_commit, original_market = engine._parse_order, engine._commit_unit, engine._process_market
    farm_seat = {id(farm): seat for seat, farm in enumerate(state[0].observation.farms)}

    def parse(order):
        seat, row = next(slots)
        parsed = original_parse(order)
        record = {"seat": seat, "row": row, "raw": copy.deepcopy(order),
                  "parsed": copy.deepcopy(parsed), "sold": 0, "sale_cash": 0}
        report["rows"].append(record)
        current[seat] = record
        return parsed

    def commit(op, item, price, farm, private, market, shed_capacity=100):
        ok = original_commit(op, item, price, farm, private, market, shed_capacity)
        if ok and op == "SELL":
            record = current[farm_seat[id(farm)]]
            record["sold"] += 1
            record["sale_cash"] += price
        return ok

    def market(s, e):
        report["market_entry_shed"] = [copy.deepcopy(x.observation.private["shed"]) for x in s]
        return original_market(s, e)

    engine._parse_order, engine._commit_unit, engine._process_market = parse, commit, market
    try:
        engine.interpreter(state, env)
    finally:
        engine._parse_order, engine._commit_unit, engine._process_market = original_parse, original_commit, original_market
    report["money"] = [farm["money"] for farm in state[0].observation.farms]
    return report


def replay(engine, initial_state, initial_env, tape, start_step):
    """Replay a contiguous fixed-action tape from an independent shared snapshot."""
    if not tape or type(start_step) is not int or start_step < 0:
        raise ValueError("nonempty tape and nonnegative start step required")
    if initial_state[0].observation.get("step", 0) != start_step:
        raise ValueError("snapshot/tape step mismatch")
    state, env = copy.deepcopy((initial_state, initial_env))
    reports = [observed_step(engine, state, env, actions, start_step + offset)
               for offset, actions in enumerate(tape)]
    terminal = all(s.status == "DONE" for s in state)
    money = [farm["money"] for farm in state[0].observation.farms]
    return {"steps": len(tape), "reports": reports, "money": money,
            "terminal": terminal, "rewards": [s.reward for s in state] if terminal else None,
            "state_sha256": digest(state), "env_sha256": digest(env),
            "outcome_sha256": digest([{k: s[k] for k in ("observation", "status", "reward")}
                                      for s in state]),
            "tape_sha256": digest(tape)}


def _fill_timeline(result, seat):
    timeline = []
    for turn in result["reports"]:
        by_item = {}
        for row in turn["rows"]:
            if row["seat"] == seat and row["sold"]:
                item = row["parsed"]["item"]
                value = by_item.setdefault(item, [0, 0])
                value[0] += row["sold"]
                value[1] += row["sale_cash"]
        timeline.append([turn["step"], sorted(by_item.items())])
    return timeline


def compare(engine, state, env, baseline_tape, candidate_tape, start_step, seat):
    """Return measured engagement, window cash and (only at DONE) final margin.

    A changed action or positive open-loop residual is not a policy promotion.
    This API intentionally has no SHIP/KILL field or field-strength estimate.
    """
    if type(seat) is not int or seat not in (0, 1) or len(baseline_tape) != len(candidate_tape):
        raise ValueError("same-length tapes and valid seat required")
    for before, after in zip(baseline_tape, candidate_tape):
        if len(before) != 2 or len(after) != 2 or before[1-seat] != after[1-seat]:
            raise ValueError("opponent action tape must remain fixed")
        a, b = copy.deepcopy(before[seat]), copy.deepcopy(after[seat])
        if isinstance(a, dict) and isinstance(b, dict):
            a.pop("market", None)
            b.pop("market", None)
        if a != b:
            raise ValueError("non-market action changed")
    baseline = replay(engine, state, env, baseline_tape, start_step)
    candidate = replay(engine, state, env, candidate_tape, start_step)
    changed = [start_step+i for i, (a, b) in enumerate(zip(baseline_tape, candidate_tape)) if a != b]
    filled = _fill_timeline(baseline, seat) != _fill_timeline(candidate, seat)
    delta = [candidate["money"][i]-baseline["money"][i] for i in (0, 1)]
    terminal = baseline["terminal"] and candidate["terminal"]
    return {"schema": "titan.sale-window-engagement.v1", "seat": seat,
            "method": "full pinned interpreter; fixed open-loop action tapes, not adaptive agents",
            "changed_turns": changed, "sale_fill_timeline_changed": filled,
            "engagement": ("UNCHANGED_RETURN" if not changed else
                           "SALE_FILL_CHANGED" if filled else "CHANGED_WITHOUT_SALE_FILL_DELTA"),
            "window_cash_delta": delta,
            "window_margin_delta": delta[seat]-delta[1-seat],
            "terminal_margin_delta": (delta[seat]-delta[1-seat]) if terminal else None,
            "baseline": baseline, "candidate": candidate}
