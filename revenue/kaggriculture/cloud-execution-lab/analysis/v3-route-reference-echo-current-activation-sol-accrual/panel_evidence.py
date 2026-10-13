# SPDX-License-Identifier: Apache-2.0
"""Strict parsers for route-reference-echo action and activation evidence."""
from __future__ import annotations

import math
import statistics

OPERATION = "titan-v3-route-reference-echo-current-activation-20260910-01"
SOURCE_OPERATION = "titan-v3-route-reference-echo-20260909-sol-accrual-01"


class EvidenceError(ValueError):
    pass


def integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceError(f"{label}: expected integer")
    return value


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{label}: expected number")
    value = float(value)
    if not math.isfinite(value):
        raise EvidenceError(f"{label}: expected finite number")
    return value


def mean(values):
    values = list(values)
    return statistics.mean(values) if values else 0.0


def outcome(margin):
    return "win" if margin > 0 else "loss" if margin < 0 else "tie"


def index(report, arm):
    rows = report.get("games")
    if not isinstance(rows, list) or not rows:
        raise EvidenceError(f"{arm}: no games")
    result = {}
    for game in rows:
        if not isinstance(game, dict):
            raise EvidenceError(f"{arm}: malformed game")
        opponent = game.get("opponent")
        seed = integer(game.get("seed"), "seed")
        seat = integer(game.get("candidate_seat"), "candidate_seat")
        if not isinstance(opponent, str) or not opponent or seat not in (0, 1):
            raise EvidenceError("invalid opponent/seat")
        key = opponent, seed, seat
        if key in result:
            raise EvidenceError(f"{arm}: duplicate cell {key}")
        result[key] = game
    return result


def action_steps(game, arm, key):
    if game.get("status") != "complete":
        raise EvidenceError(f"{arm}: incomplete cell {key}")
    steps = game.get("candidate_action_step_sha256")
    if (not isinstance(steps, list) or not steps or
            any(not isinstance(value, str) or len(value) != 64 for value in steps)):
        raise EvidenceError(f"{arm}: bad action hashes {key}")
    count = integer(game.get("candidate_action_count"), "action count")
    interpreted = integer(game.get("steps"), "interpreted steps")
    if count != len(steps) or count != interpreted:
        raise EvidenceError(f"{arm}: action/interpreter count mismatch {key}")
    return steps


def scores(game, arm, key):
    raw = game.get("scores")
    if not isinstance(raw, list) or len(raw) != 2:
        raise EvidenceError(f"{arm}: bad scores {key}")
    values = [number(value, "score") for value in raw]
    seat = key[2]
    own, rival = values[seat], values[1 - seat]
    return own, rival, own - rival


def activation_events(game, key):
    raw = game.get("candidate_agent_evidence")
    if not isinstance(raw, list):
        raise EvidenceError(f"candidate: no evidence list {key}")
    result, tokens, last = [], set(), -1
    for row in raw:
        if not isinstance(row, dict):
            raise EvidenceError(f"candidate: malformed evidence row {key}")
        step = integer(row.get("step"), "evidence step")
        evidence = row.get("evidence")
        if step < last or not isinstance(evidence, dict):
            raise EvidenceError(f"candidate: unordered/malformed evidence {key}")
        last = step
        if (evidence.get("operation") != OPERATION or
                evidence.get("source_operation") != SOURCE_OPERATION):
            raise EvidenceError(f"candidate: evidence identity mismatch {key}")
        token, report = evidence.get("receipt_sha256"), evidence.get("report")
        if (not isinstance(token, str) or len(token) != 64 or token in tokens or
                not isinstance(report, dict)):
            raise EvidenceError(f"candidate: bad receipt {key}")
        tokens.add(token)
        removed = integer(report.get("removed_quantity"), "removed_quantity")
        now = integer(report.get("now"), "normalization step")
        if (report.get("changed") is not True or report.get("status") != "NORMALIZED" or
                removed <= 0 or now != step):
            raise EvidenceError(f"candidate: false activation {key}")
        result.append({
            "step": step, "item": report.get("item"),
            "removed_quantity": removed,
            "canonical_quantity": report.get("canonical_quantity"),
            "scheduler_owned_quantity": report.get("scheduler_owned_quantity"),
            "controller_route": evidence.get("controller_route"),
            "receipt_sha256": token,
        })
    return result


def sign_tail(positive, negative):
    n = positive + negative
    if not n:
        return None
    k = max(positive, negative)
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2**n
