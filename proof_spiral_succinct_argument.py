#!/usr/bin/env python3
"""Proof-spiral succinct argument — working runner, not a mock SKU.

YouTube: https://youtu.be/jVHeHmufZhk (Purplemind: succinct arguments / Merkle + PCP)

A verifier is convinced a computation is correct without (a) redoing the
whole work or (b) blind trust. The prover runs an agreed pi / modular
program, commits the execution trace with a Merkle tree, and answers
random adjacent-step openings. Naive sampling of a million-step trace
with one error misses the needle (the spiral). A PCP-style 3-coloring
rewrite spreads any false claim to a constant fraction of bad edges so
~1000 random checks catch it.

HOLD / BUILD-AND-VERIFY. cash_usd=0. No outreach. Open door. No login.

    python3 proof_spiral_succinct_argument.py
    python3 test_proof_spiral_succinct_argument.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from typing import Iterable

LEFTOVER_ID = "proof-spiral-succinct-argument-20260901-01"
YOUTUBE = "https://youtu.be/jVHeHmufZhk"
HOLD = "HOLD / BUILD-AND-VERIFY"

# Leibniz π in fixed-point integers: acc/SCALE → π. Real digits, not commentary.
SCALE = 10**12
MOD = 1_000_000_007
MUL = 1103515245
ADD = 12345

MILLION = 1_000_000
NEEDLE_INDEX = 424_242
NAIVE_K = 64
NAIVE_TRIALS = 200
NAIVE_SEED = 20260901
MERKLE_N = 512
MERKLE_QUERIES = 32
MERKLE_SEED = 7
PCP_PART = 36
PCP_FIELD = 1_000_000_007
PCP_CHECKS = 1000
PCP_SEED = 11
PI_DIGITS = 6
PI_PREFIX_EXPECTED = 314159
MIN_FALSE_BAD_FRACTION = 0.05

# Cached million-step honest trace for this process (tests + CLI).
_HONEST_MILLION: list[tuple[int, int, int]] | None = None


def row_bytes(row: tuple[int, int, int]) -> bytes:
    step, acc, mod = row
    return ("%d:%d:%d" % (step, acc, mod)).encode("ascii")


def next_row(row: tuple[int, int, int]) -> tuple[int, int, int]:
    step, acc, mod = row
    sign = 1 if (step & 1) == 0 else -1
    acc = acc + sign * ((4 * SCALE) // (2 * step + 1))
    digit = abs(acc) % 10
    mod = (MUL * mod + ADD + digit) % MOD
    return (step + 1, acc, mod)


def valid_adjacent(left: tuple[int, int, int], right: tuple[int, int, int]) -> bool:
    return right == next_row(left)


def execute_program(n: int, start: tuple[int, int, int] | None = None) -> list[tuple[int, int, int]]:
    if n < 2:
        raise ValueError("program needs at least two steps")
    step, acc, mod = start if start is not None else (0, 0, 1)
    rows: list[tuple[int, int, int]] = [None] * n  # type: ignore[list-item]
    for i in range(n):
        rows[i] = (step, acc, mod)
        sign = 1 if (step & 1) == 0 else -1
        acc = acc + sign * ((4 * SCALE) // (2 * step + 1))
        digit = abs(acc) % 10
        mod = (MUL * mod + ADD + digit) % MOD
        step += 1
    return rows


def pi_prefix(acc: int, digits: int = PI_DIGITS) -> int:
    if digits < 1:
        raise ValueError("digits")
    return abs(acc) * (10 ** (digits - 1)) // SCALE


def honest_million() -> list[tuple[int, int, int]]:
    global _HONEST_MILLION
    if _HONEST_MILLION is None:
        _HONEST_MILLION = execute_program(MILLION)
    return _HONEST_MILLION


def inject_single_error(
    rows: list[tuple[int, int, int]], index: int = NEEDLE_INDEX
) -> list[tuple[int, int, int]]:
    if not 1 <= index < len(rows) - 1:
        raise ValueError("needle index out of range")
    out = list(rows)
    step, acc, mod = out[index]
    out[index] = (step, acc + 1, mod)
    return out


def transition_errors(rows: list[tuple[int, int, int]]) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for i in range(len(rows) - 1):
        expected = next_row(rows[i])
        got = rows[i + 1]
        if expected != got:
            delta = got[1] - expected[1]
            found.append((i, delta if delta != 0 else 1))
    return found


# --- Merkle commitment over step rows ---------------------------------------


def _digest(tag: bytes, *parts: bytes) -> bytes:
    h = hashlib.sha256()
    h.update(tag)
    for part in parts:
        h.update(part)
    return h.digest()


def leaf_digest(payload: bytes) -> bytes:
    return _digest(b"L", payload)


def node_digest(left: bytes, right: bytes) -> bytes:
    return _digest(b"N", left, right)


class MerkleTree:
    """Binary Merkle tree. Odd levels duplicate the last node."""

    def __init__(self, payloads: Iterable[bytes]):
        payloads = list(payloads)
        if not payloads:
            raise ValueError("Merkle tree needs at least one leaf")
        self.payloads = payloads
        self.n = len(payloads)
        level = [leaf_digest(p) for p in payloads]
        self.levels = [level]
        while len(level) > 1:
            nxt = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else left
                nxt.append(node_digest(left, right))
            self.levels.append(nxt)
            level = nxt

    @property
    def root(self) -> bytes:
        return self.levels[-1][0]

    def path(self, index: int) -> list[tuple[str, str]]:
        if not 0 <= index < self.n:
            raise IndexError(index)
        out: list[tuple[str, str]] = []
        idx = index
        for level in self.levels[:-1]:
            if idx % 2 == 0:
                sib_idx = idx + 1
                side = "R"
            else:
                sib_idx = idx - 1
                side = "L"
            if sib_idx >= len(level):
                sib = level[idx]
                side = "R"
            else:
                sib = level[sib_idx]
            out.append((side, sib.hex()))
            idx //= 2
        return out


def verify_merkle_path(payload: bytes, path: list[tuple[str, str]], root_hex: str) -> bool:
    current = leaf_digest(payload)
    for side, sib_hex in path:
        try:
            sib = bytes.fromhex(sib_hex)
        except ValueError:
            return False
        if len(sib) != 32:
            return False
        if side == "L":
            current = node_digest(sib, current)
        elif side == "R":
            current = node_digest(current, sib)
        else:
            return False
    return current.hex() == root_hex


def commit_trace(rows: list[tuple[int, int, int]]) -> MerkleTree:
    return MerkleTree(row_bytes(r) for r in rows)


def open_adjacent(
    tree: MerkleTree, rows: list[tuple[int, int, int]], index: int
) -> dict:
    if not 0 <= index < len(rows) - 1:
        raise IndexError(index)
    return {
        "index": index,
        "left": list(rows[index]),
        "right": list(rows[index + 1]),
        "left_path": tree.path(index),
        "right_path": tree.path(index + 1),
    }


def verify_adjacent_opening(root_hex: str, opening: dict) -> tuple[bool, str]:
    try:
        index = int(opening["index"])
        left = tuple(opening["left"])
        right = tuple(opening["right"])
        left_path = [(str(s), str(h)) for s, h in opening["left_path"]]
        right_path = [(str(s), str(h)) for s, h in opening["right_path"]]
    except (KeyError, TypeError, ValueError):
        return False, "malformed"
    if len(left) != 3 or len(right) != 3:
        return False, "row-shape"
    if not verify_merkle_path(row_bytes(left), left_path, root_hex):  # type: ignore[arg-type]
        return False, "left-commitment"
    if not verify_merkle_path(row_bytes(right), right_path, root_hex):  # type: ignore[arg-type]
        return False, "right-commitment"
    if not valid_adjacent(left, right):  # type: ignore[arg-type]
        return False, "transition"
    _ = index
    return True, "ok"


def honest_prove_verify(n: int = MERKLE_N, queries: int = MERKLE_QUERIES, seed: int = MERKLE_SEED) -> dict:
    rows = execute_program(n)
    tree = commit_trace(rows)
    root_hex = tree.root.hex()
    rng = random.Random(seed)
    accepted = 0
    reasons: list[str] = []
    for _ in range(queries):
        i = rng.randrange(n - 1)
        ok, reason = verify_adjacent_opening(root_hex, open_adjacent(tree, rows, i))
        if ok:
            accepted += 1
        else:
            reasons.append(reason)
    return {
        "n": n,
        "queries": queries,
        "accepted": accepted,
        "root": root_hex,
        "ok": accepted == queries and not reasons,
        "reasons": reasons,
        "verifier_hashes": queries * 2,
        "prover_steps": n,
    }


def adaptive_cheat_opening(tree: MerkleTree, rows: list[tuple[int, int, int]], index: int) -> dict:
    """Valid-looking adjacent pair that is not the committed leaf at `index`."""
    step, acc, mod = rows[index]
    fake_left = (step, acc + 99, mod)
    fake_right = next_row(fake_left)
    return {
        "index": index,
        "left": list(fake_left),
        "right": list(fake_right),
        "left_path": tree.path(index),
        "right_path": tree.path(index + 1),
    }


def cheating_prover_rejected(n: int = MERKLE_N, seed: int = MERKLE_SEED) -> dict:
    rows = execute_program(n)
    tree = commit_trace(rows)
    root_hex = tree.root.hex()
    rng = random.Random(seed + 1)
    index = rng.randrange(n - 1)
    opening = adaptive_cheat_opening(tree, rows, index)
    # The fake pair transitions correctly. Commitment must still fail.
    trans_ok = valid_adjacent(tuple(opening["left"]), tuple(opening["right"]))  # type: ignore[arg-type]
    ok, reason = verify_adjacent_opening(root_hex, opening)
    return {
        "index": index,
        "fake_transition_internally_valid": trans_ok,
        "accepted": ok,
        "reason": reason,
        "rejected": (not ok) and reason in ("left-commitment", "right-commitment"),
    }


# --- Naive sampling (the spiral) --------------------------------------------


def naive_sample_hits(rows: list[tuple[int, int, int]], k: int, seed: int) -> int:
    rng = random.Random(seed)
    hits = 0
    limit = len(rows) - 1
    for _ in range(k):
        i = rng.randrange(limit)
        if not valid_adjacent(rows[i], rows[i + 1]):
            hits += 1
    return hits


def naive_spiral_demo(
    rows: list[tuple[int, int, int]] | None = None,
    k: int = NAIVE_K,
    trials: int = NAIVE_TRIALS,
    seed: int = NAIVE_SEED,
) -> dict:
    if rows is None:
        rows = inject_single_error(honest_million(), NEEDLE_INDEX)
    n = len(rows)
    errors = transition_errors(rows)
    bad_pairs = len(errors)
    trial_hits = [naive_sample_hits(rows, k, seed + t) for t in range(trials)]
    trials_that_hit = sum(1 for h in trial_hits if h > 0)
    first_hits = trial_hits[0]
    # One corrupted row breaks the two adjacent pairs that touch it.
    miss_prob = (1.0 - (bad_pairs / (n - 1))) ** k if n > 1 else 1.0
    return {
        "n": n,
        "needle_index": NEEDLE_INDEX,
        "bad_adjacent_pairs": bad_pairs,
        "k": k,
        "trials": trials,
        "first_trial_hits": first_hits,
        "first_trial_missed": first_hits == 0,
        "trials_that_hit": trials_that_hit,
        "trials_that_missed": trials - trials_that_hit,
        "theoretical_miss_probability": miss_prob,
        "high_miss": miss_prob >= 0.99,
    }


# --- PCP-style rewrite: 3-coloring / bad-edge sampler -----------------------


def tripartite_edges(part: int) -> list[tuple[int, int]]:
    edges: list[tuple[int, int]] = []
    a0, b0, c0 = 0, part, 2 * part
    for a in range(part):
        for b in range(part):
            edges.append((a0 + a, b0 + b))
        for c in range(part):
            edges.append((a0 + a, c0 + c))
    for b in range(part):
        for c in range(part):
            edges.append((b0 + b, c0 + c))
    return edges


def honest_coloring(part: int) -> list[int]:
    return [0] * part + [1] * part + [2] * part


def fingerprint_sparse(x: int, errors: list[tuple[int, int]], n: int, field: int = PCP_FIELD) -> int:
    acc = 0
    for index, delta in errors:
        acc = (acc + (delta % field) * pow(x, n - 1 - index, field)) % field
    return acc


def amplified_coloring(
    part: int, errors: list[tuple[int, int]], n: int, field: int = PCP_FIELD
) -> list[int]:
    """Proper 3-coloring iff errors is empty; else shift part A where F(x) ≠ 0."""
    colors = honest_coloring(part)
    if not errors:
        return colors
    for v in range(part):
        x = v + 2
        if fingerprint_sparse(x, errors, n, field) != 0:
            colors[v] = (colors[v] + 1) % 3
    return colors


def bad_edge_stats(edges: list[tuple[int, int]], colors: list[int]) -> dict:
    bad = 0
    for u, v in edges:
        if colors[u] == colors[v]:
            bad += 1
    total = len(edges)
    return {
        "bad_edges": bad,
        "total_edges": total,
        "fraction": (bad / total) if total else 0.0,
    }


def sample_bad_edges(
    edges: list[tuple[int, int]], colors: list[int], k: int, seed: int
) -> int:
    rng = random.Random(seed)
    hits = 0
    n_edges = len(edges)
    for _ in range(k):
        u, v = edges[rng.randrange(n_edges)]
        if colors[u] == colors[v]:
            hits += 1
    return hits


def pcp_amplify_demo(
    rows: list[tuple[int, int, int]] | None = None,
    part: int = PCP_PART,
    checks: int = PCP_CHECKS,
    seed: int = PCP_SEED,
) -> dict:
    if rows is None:
        rows = inject_single_error(honest_million(), NEEDLE_INDEX)
    n = len(rows)
    errors = transition_errors(rows)
    edges = tripartite_edges(part)
    true_colors = amplified_coloring(part, [], n)
    false_colors = amplified_coloring(part, errors, n)
    true_stats = bad_edge_stats(edges, true_colors)
    false_stats = bad_edge_stats(edges, false_colors)
    sampled_hits = sample_bad_edges(edges, false_colors, checks, seed)
    return {
        "part": part,
        "vertices": 3 * part,
        "true_bad_edges": true_stats["bad_edges"],
        "true_total_edges": true_stats["total_edges"],
        "true_fraction": true_stats["fraction"],
        "false_bad_edges": false_stats["bad_edges"],
        "false_total_edges": false_stats["total_edges"],
        "false_fraction": false_stats["fraction"],
        "error_count": len(errors),
        "checks": checks,
        "sampled_bad_hits": sampled_hits,
        "caught_after_amplification": sampled_hits > 0,
        "constant_fraction": false_stats["fraction"] >= MIN_FALSE_BAD_FRACTION,
    }


def run_acceptance() -> dict:
    honest = honest_prove_verify()
    cheat = cheating_prover_rejected()
    million = honest_million()
    prefix = pi_prefix(million[-1][1], PI_DIGITS)
    corrupted = inject_single_error(million, NEEDLE_INDEX)
    spiral = naive_spiral_demo(corrupted)
    pcp = pcp_amplify_demo(corrupted)
    pass_bits = {
        "honest_prove_verify_accepts": bool(honest["ok"]),
        "cheating_prover_rejected": bool(cheat["rejected"]),
        "cheat_fake_transition_was_valid": bool(cheat["fake_transition_internally_valid"]),
        "pi_prefix_real": prefix == PI_PREFIX_EXPECTED,
        "naive_first_trial_missed": bool(spiral["first_trial_missed"]),
        "naive_high_miss_probability": bool(spiral["high_miss"]),
        "pcp_true_zero_bad": pcp["true_bad_edges"] == 0,
        "pcp_false_constant_fraction": bool(pcp["constant_fraction"]),
        "needle_caught_after_amplification": bool(pcp["caught_after_amplification"]),
        "cash_usd_zero": True,
        "outreach_zero": True,
    }
    ok = all(pass_bits.values())
    return {
        "id": LEFTOVER_ID,
        "youtube": YOUTUBE,
        "hold": HOLD,
        "cash_usd": 0,
        "outreach": 0,
        "status": "PASS" if ok else "FAIL",
        "pass_bits": pass_bits,
        "honest": honest,
        "cheat": cheat,
        "pi_prefix": prefix,
        "pi_prefix_expected": PI_PREFIX_EXPECTED,
        "spiral": spiral,
        "pcp": pcp,
        "named_counts": {
            "prover_steps_merkle": honest["prover_steps"],
            "verifier_adjacent_openings": honest["queries"],
            "verifier_rows_opened": honest["queries"] * 2,
            "honest_accepted": honest["accepted"],
            "cheat_rejected": 1 if cheat["rejected"] else 0,
            "million_steps": spiral["n"],
            "needle_index": spiral["needle_index"],
            "bad_adjacent_pairs": spiral["bad_adjacent_pairs"],
            "naive_k": spiral["k"],
            "naive_trials": spiral["trials"],
            "naive_first_trial_hits": spiral["first_trial_hits"],
            "naive_trials_that_missed": spiral["trials_that_missed"],
            "naive_trials_that_hit": spiral["trials_that_hit"],
            "pcp_vertices": pcp["vertices"],
            "pcp_true_bad_edges": pcp["true_bad_edges"],
            "pcp_false_bad_edges": pcp["false_bad_edges"],
            "pcp_false_total_edges": pcp["false_total_edges"],
            "pcp_checks": pcp["checks"],
            "pcp_sampled_bad_hits": pcp["sampled_bad_hits"],
            "pi_prefix": prefix,
            "cash_usd": 0,
        },
    }


def format_report(result: dict) -> str:
    counts = result["named_counts"]
    bits = result["pass_bits"]
    lines = [
        "id=%s" % result["id"],
        "status=%s" % result["status"],
        "hold=%s" % result["hold"],
        "cash_usd=%s" % result["cash_usd"],
        "youtube=%s" % result["youtube"],
        "PLAIN: succinct argument — Merkle commit + PCP amplification. No redo. No blind trust.",
        "honest_accept=%s accepted=%s/%s" % (
            bits["honest_prove_verify_accepts"],
            counts["honest_accepted"],
            counts["verifier_adjacent_openings"],
        ),
        "cheat_rejected=%s reason=%s" % (bits["cheating_prover_rejected"], result["cheat"]["reason"]),
        "pi_prefix=%s expected=%s" % (counts["pi_prefix"], result["pi_prefix_expected"]),
        "naive n=%s needle=%s bad_pairs=%s k=%s first_hits=%s missed=%s" % (
            counts["million_steps"],
            counts["needle_index"],
            counts["bad_adjacent_pairs"],
            counts["naive_k"],
            counts["naive_first_trial_hits"],
            bits["naive_first_trial_missed"],
        ),
        "naive trials_missed=%s/%s theoretical_miss=%.6f" % (
            counts["naive_trials_that_missed"],
            counts["naive_trials"],
            result["spiral"]["theoretical_miss_probability"],
        ),
        "pcp true_bad=%s false_bad=%s/%s fraction=%.4f checks=%s hits=%s caught=%s" % (
            counts["pcp_true_bad_edges"],
            counts["pcp_false_bad_edges"],
            counts["pcp_false_total_edges"],
            result["pcp"]["false_fraction"],
            counts["pcp_checks"],
            counts["pcp_sampled_bad_hits"],
            bits["needle_caught_after_amplification"],
        ),
        "open_door=yes login=no outreach=0",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Proof-spiral succinct argument runner")
    parser.add_argument("--json", action="store_true", help="print machine receipt")
    args = parser.parse_args(argv)
    result = run_acceptance()
    if args.json:
        sys.stdout.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    else:
        sys.stdout.write(format_report(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
