#!/usr/bin/env python3
"""Exact-source M1 recovery verification; no game engine or package-green claim.

Use: python -B verify_m1_recovery.py --predecessor m1_hugeint_only.py \
       --candidate r04_m1_wheat_trade.py --out recovery-receipt.json
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
from pathlib import Path
import types

PARENT = "429e32b3eb0ac9fa7bb440dce8fdf3c882210a6a"
CANDIDATE = "d4d068d62ffc8fcd25842193bc7031f764630262"
CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "boardSize": 10,
          "shedCapacity": 100, "maxMarketOrdersPerTurn": 10}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load_bound(path, expected, name):
    data = path.read_bytes()
    require(git_blob(data) == expected, "source identity mismatch: " + name)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module


def action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def observation(step, *, player=0, seats=2, money=5000.0, shed=0, public=100):
    farm = {"money": money, "farmer": [4, 4], "hands": []}
    return {"step": step, "player": player,
            "market": {"inventory": {"WHEAT": public}, "prices": {"WHEAT": 20}},
            "private": {"shed": {"WHEAT": shed}},
            "farms": [copy.deepcopy(farm) for _ in range(seats)]}


def tape(due, demand):
    result = [action() for _ in range(719)]
    result[due]["farmer"] = ["PICKUP", "WHEAT", demand]
    return result


def verify(predecessor_path, candidate_path):
    parent = load_bound(predecessor_path, PARENT, "m1_bound_parent")
    candidate = load_bound(candidate_path, CANDIDATE, "m1_bound_candidate")
    cases = 0
    calls_per_arm = 0
    buy_callbacks = 0
    trace = hashlib.sha256()
    # Both real seats, four days including the final eligible full day, two
    # funding boundaries, four demand levels, and three private stock levels.
    for player, start, money, demand, stock in itertools.product(
            (0, 1), (100, 148, 580, 688), (1000.0, 1090.0, 5000.0),
            (0, 1, 3, 7), (0, 2, 98)):
        cases += 1
        parent.reset_for_tests()
        candidate.reset_for_tests()
        for offset in range(4):
            calls_per_arm += 1
            step = start + offset
            obs = observation(step, player=player, money=money,
                              shed=stock, public=100 - 2 * offset)
            plan = tape(start + 4, demand)
            row = action()
            obs_snapshot, plan_snapshot = copy.deepcopy(obs), copy.deepcopy(plan)
            left = parent.apply_m1_wheat_trade(
                obs, row, plan, configuration=CONFIG, enabled=True)
            require(obs == obs_snapshot and plan == plan_snapshot and row == action(),
                    "predecessor mutated an input")
            right = candidate.apply_m1_wheat_trade(
                obs, row, plan, configuration=CONFIG, enabled=True)
            require(obs == obs_snapshot and plan == plan_snapshot and row == action(),
                    "candidate mutated an input")
            require(left == right, "valid-state action drift")
            require((left is row) == (right is row), "valid-state identity drift")
            require(parent._STATE == candidate._STATE, "valid-state tracker drift")
            require(parent.REPORT == candidate.REPORT, "valid-state report drift")
            if right is not row:
                buy_callbacks += 1
                require(right["market"] and right["market"][-1][:2] == ["BUY_PRODUCT", "WHEAT"],
                        "activation did not buy WHEAT")
            trace.update(json.dumps([player, start, money, demand, stock, step,
                                     right, candidate._STATE, candidate.REPORT],
                                    sort_keys=True, separators=(",", ":")).encode())
            trace.update(b"\n")
    require(buy_callbacks > 0, "positive cases never activated")

    # The real helper entrypoint, rather than only its scalar validator.
    huge_int_cases = 0
    for player in (0, 1):
        candidate.reset_for_tests()
        plan = tape(104, 3)
        candidate.apply_m1_wheat_trade(observation(100, player=player), action(), plan,
                                       configuration=CONFIG, enabled=True)
        obs = observation(101, player=player, money=10**1000, public=98)
        row = action()
        before = copy.deepcopy(obs)
        result = candidate.apply_m1_wheat_trade(obs, row, plan, configuration=CONFIG, enabled=True)
        require(result is row and obs == before and candidate.REPORT["buy_orders"] == 0,
                "huge integer did not fail closed at full API")
        huge_int_cases += 1

    shape_cases = 0
    for player, seats in ((0, 0), (0, 1), (0, 3), (1, 3), (2, 3), (-1, 2),
                          (True, 2), (False, 2), ("0", 2), (0.0, 2), (None, 2)):
        candidate.reset_for_tests()
        row = action()
        obs = observation(101, player=player, seats=seats, public=98)
        before = copy.deepcopy(obs)
        result = candidate.apply_m1_wheat_trade(obs, row, tape(104, 3),
                                               configuration=CONFIG, enabled=True)
        require(result is row and candidate._STATE == {} and obs == before,
                "invalid seat surface reached mutation")
        shape_cases += 1

    off_cases = 0
    for obs in (None, {}, observation(101, player=2, seats=3, money=10**1000)):
        candidate.reset_for_tests()
        before_state, before_report = copy.deepcopy(candidate._STATE), copy.deepcopy(candidate.REPORT)
        row = action()
        require(candidate.apply_m1_wheat_trade(obs, row, None, enabled=False) is row,
                "OFF path changed identity")
        require(candidate._STATE == before_state and candidate.REPORT == before_report,
                "OFF path mutated module state")
        off_cases += 1
    return {"status": "PASS", "scope": "exact_helper_full_api_not_materialized_router_or_games",
            "predecessor_git_blob": PARENT, "candidate_git_blob": CANDIDATE,
            "valid_state_sequences": cases, "callbacks_per_arm": calls_per_arm,
            "positive_buy_callbacks": buy_callbacks,
            "action_identity_state_report_parity": True,
            "input_nonmutation": True, "both_seats": True,
            "full_api_huge_integer_cases": huge_int_cases,
            "invalid_seat_cases": shape_cases, "disabled_identity_state_cases": off_cases,
            "trace_sha256": trace.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predecessor", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    inputs = {args.predecessor.resolve(), args.candidate.resolve(), Path(__file__).resolve()}
    require(args.out.resolve() not in inputs, "output aliases a source")
    result = verify(args.predecessor, args.candidate)
    result["verifier_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["receipt_sha256"] = hashlib.sha256(payload.encode()).hexdigest()
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
