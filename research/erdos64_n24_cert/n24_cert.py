#!/usr/bin/env python3
"""Exact 24-vertex certificate utilities for Erdős–Gyárfás problem #64."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from typing import Iterable, Sequence


class GraphError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise GraphError(message)


def normalize(order: int, edges: Iterable[Sequence[int]]) -> tuple[tuple[int, int], ...]:
    require(isinstance(order, int) and not isinstance(order, bool) and order > 0, "bad order")
    out: set[tuple[int, int]] = set()
    rows = 0
    for raw in edges:
        rows += 1
        require(isinstance(raw, (list, tuple)) and len(raw) == 2, "bad edge row")
        a, b = raw
        require(
            isinstance(a, int) and not isinstance(a, bool)
            and isinstance(b, int) and not isinstance(b, bool),
            "non-integer endpoint",
        )
        require(0 <= a < order and 0 <= b < order, "endpoint out of range")
        require(a != b, "loop")
        edge = (a, b) if a < b else (b, a)
        require(edge not in out, f"duplicate edge {edge}")
        out.add(edge)
    require(len(out) == rows, "edge normalization mismatch")
    return tuple(sorted(out))


def adjacency(order: int, edges: Iterable[Sequence[int]]) -> tuple[set[int], ...]:
    graph = tuple(set() for _ in range(order))
    for a, b in normalize(order, edges):
        graph[a].add(b)
        graph[b].add(a)
    return graph


def encoding(order: int, edges: Iterable[Sequence[int]]) -> bytes:
    norm = normalize(order, edges)
    return (
        f"order {order}\nedges {len(norm)}\n"
        + "".join(f"{a} {b}\n" for a, b in norm)
    ).encode("ascii")


def digest(order: int, edges: Iterable[Sequence[int]]) -> str:
    return hashlib.sha256(encoding(order, edges)).hexdigest()


def canonical_cycle(path: Sequence[int]) -> tuple[int, ...]:
    seq = tuple(path)
    require(len(seq) >= 3, "cycle too short")
    n = len(seq)
    variants = []
    for orient in (seq, tuple(reversed(seq))):
        variants.extend(orient[i:] + orient[:i] for i in range(n))
    return min(variants)


def cycles_exact(order: int, edges: Iterable[Sequence[int]], length: int) -> tuple[tuple[int, ...], ...]:
    require(3 <= length <= order, "bad cycle length")
    graph = adjacency(order, edges)
    found: set[tuple[int, ...]] = set()
    for start in range(order):
        stack = [(start, (start,), frozenset((start,)))]
        while stack:
            v, path, used = stack.pop()
            if len(path) == length:
                if start in graph[v]:
                    found.add(canonical_cycle(path))
                continue
            for w in graph[v]:
                if w == start or w in used or w < start:
                    continue
                stack.append((w, path + (w,), used | {w}))
    return tuple(sorted(found))


def has_cycle(order: int, edges: Iterable[Sequence[int]], length: int) -> bool:
    require(3 <= length <= order, "bad cycle length")
    graph = adjacency(order, edges)
    for start in range(order):
        stack = [(start, (start,), frozenset((start,)))]
        while stack:
            v, path, used = stack.pop()
            if len(path) == length:
                if start in graph[v]:
                    return True
                continue
            for w in graph[v]:
                if w == start or w in used or w < start:
                    continue
                stack.append((w, path + (w,), used | {w}))
    return False


def power_lengths(order: int) -> tuple[int, ...]:
    values = []
    value = 4
    while value <= order:
        values.append(value)
        value *= 2
    return tuple(values)


MARKSTROEM_EDGES = (
    (0, 1), (0, 8), (0, 9), (1, 2), (1, 11), (2, 3), (2, 11),
    (3, 4), (3, 12), (4, 5), (4, 14), (5, 6), (5, 14), (6, 7),
    (6, 15), (7, 8), (7, 17), (8, 17), (9, 10), (9, 18), (10, 11),
    (10, 18), (12, 13), (12, 19), (13, 14), (13, 19), (15, 16),
    (15, 20), (16, 17), (16, 20), (18, 21), (19, 22), (20, 23),
    (21, 22), (21, 23), (22, 23),
)


def markstroem() -> tuple[tuple[int, int], ...]:
    return normalize(24, MARKSTROEM_EDGES)


def verify(order: int, edges: Iterable[Sequence[int]]) -> dict:
    norm = normalize(order, edges)
    graph = adjacency(order, norm)
    degrees = tuple(len(ns) for ns in graph)
    require(min(degrees) >= 3, f"minimum degree {min(degrees)} < 3")
    counts = {}
    first = {}
    for length in power_lengths(order):
        found = cycles_exact(order, norm, length)
        counts[str(length)] = len(found)
        first[str(length)] = list(found[0]) if found else None
    return {
        "order": order,
        "edge_count": len(norm),
        "degree_histogram": {str(k): v for k, v in sorted(Counter(degrees).items())},
        "labeled_sha256": digest(order, norm),
        "power_cycle_counts": counts,
        "first_power_cycles": first,
        "all_power_lengths_avoided": all(value == 0 for value in counts.values()),
    }


def lex_row_symmetry_holds(order: int, edges: Iterable[Sequence[int]]) -> bool:
    """Garcia's adjacent-row lex condition after omitting columns i,i+1."""
    graph = adjacency(order, edges)
    for i in range(order - 1):
        cols = [k for k in range(order) if k not in (i, i + 1)]
        left = tuple(int(k in graph[i]) for k in cols)
        right = tuple(int(k in graph[i + 1]) for k in cols)
        if left < right:
            return False
    return True


def two_switch_neighbors(order: int, edges: Iterable[Sequence[int]]) -> tuple[tuple[tuple[int, int], ...], ...]:
    norm = normalize(order, edges)
    base = set(norm)
    seen: dict[str, tuple[tuple[int, int], ...]] = {}
    for i, (a, b) in enumerate(norm):
        for c, d in norm[i + 1:]:
            if len({a, b, c, d}) != 4:
                continue
            for new1, new2 in (((a, c), (b, d)), ((a, d), (b, c))):
                x, y = tuple(sorted(new1)), tuple(sorted(new2))
                if x in base or y in base or x == y:
                    continue
                candidate = set(base)
                candidate.remove((a, b))
                candidate.remove((c, d))
                candidate.update((x, y))
                ordered = tuple(sorted(candidate))
                seen[digest(order, ordered)] = ordered
    return tuple(seen[key] for key in sorted(seen))


def scan() -> dict:
    base = markstroem()
    neighbors = two_switch_neighbors(24, base)
    short_clean: list[tuple[str, tuple[tuple[int, int], ...]]] = []
    full_clean: list[str] = []
    for candidate in neighbors:
        if has_cycle(24, candidate, 4) or has_cycle(24, candidate, 8):
            continue
        item = (digest(24, candidate), candidate)
        short_clean.append(item)
        if not has_cycle(24, candidate, 16):
            full_clean.append(item[0])
    short_clean.sort()
    material = {
        "base_labeled_sha256": digest(24, base),
        "unique_two_switch_neighbors": len(neighbors),
        "no_c4_no_c8_neighbors": len(short_clean),
        "no_c4_no_c8_no_c16_neighbors": len(full_clean),
        "first_short_clean_sha256": short_clean[0][0] if short_clean else None,
        "full_clean_labeled_sha256": sorted(full_clean),
    }
    packed = (json.dumps(material, sort_keys=True, separators=(",", ":")) + "\n").encode()
    material["scan_sha256"] = hashlib.sha256(packed).hexdigest()
    return material


def receipt() -> dict:
    base = verify(24, markstroem())
    local = scan()
    return {
        "schema": "erdos64-n24-cert-v1",
        "sources": {
            "garcia_arxiv": "arXiv:2609.04686v1",
            "sagemath_commit": "671dfa344f4cc4a6d54f343cbfd1272ee81698c9",
            "sagemath_smallgraphs_blob": "f747bce25536d6eb8a59b7d2e06aad83239d112a",
            "commons_prior_audit_verifier_blob": "79f749138e8186f8cfd27abb2f741fdf3c6c2098",
        },
        "scope": {
            "order": 24,
            "minimum_degree": 3,
            "forbid_cycles": [4, 8],
            "decisive_remaining_cycle": 16,
            "evidence_ceiling": "bounded local search; no proof/counterexample/prize claim",
        },
        "sat_bridge": {
            "edge_variables": 276,
            "c4_blocking_clauses": 31878,
            "c8_policy": "lazy exact blockers for concrete simple 8-cycles",
            "symmetry": "adjacent row i lex >= row i+1 after omitting columns i,i+1",
        },
        "markstroem": base,
        "markstroem_label_satisfies_adjacent_lex": lex_row_symmetry_holds(24, markstroem()),
        "one_two_switch_neighborhood": local,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify-markstroem", "scan", "receipt"))
    args = parser.parse_args(argv)
    if args.command == "verify-markstroem":
        payload = verify(24, markstroem())
    elif args.command == "scan":
        payload = scan()
    else:
        payload = receipt()
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
