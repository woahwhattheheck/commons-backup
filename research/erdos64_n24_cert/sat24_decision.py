#!/usr/bin/env python3
"""Exact lazy-SAT decision spine for order-24 Erdős–Gyárfás candidates.

The base formula is equisatisfiable with existence of a 24-vertex counterexample
up to the still-lazy C8/C16 blockers.  It uses only Python's standard library
and emits ordinary DIMACS CNF plus proof-carrying cycle-cut JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Iterable, Iterator, Sequence

ORDER = 24
MIN_DEGREE = 3
LAZY_LENGTHS = (8, 16)
SCHEMA = "erdos64-n24-lazy-sat-v1"


class DecisionError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise DecisionError(message)


def edge_pairs(order: int = ORDER) -> tuple[tuple[int, int], ...]:
    require(isinstance(order, int) and not isinstance(order, bool) and order >= 4, "bad order")
    return tuple((a, b) for a in range(order) for b in range(a + 1, order))


EDGES = edge_pairs()
EDGE_TO_VAR = {edge: i + 1 for i, edge in enumerate(EDGES)}
EDGE_VAR_COUNT = len(EDGES)
DEG3_VAR_BASE = EDGE_VAR_COUNT + 1
VARIABLE_COUNT = EDGE_VAR_COUNT + ORDER


def edge_var(a: int, b: int) -> int:
    require(isinstance(a, int) and not isinstance(a, bool), "bad endpoint")
    require(isinstance(b, int) and not isinstance(b, bool), "bad endpoint")
    require(0 <= a < ORDER and 0 <= b < ORDER and a != b, "bad edge")
    return EDGE_TO_VAR[(a, b) if a < b else (b, a)]


def deg3_var(v: int) -> int:
    require(isinstance(v, int) and not isinstance(v, bool) and 0 <= v < ORDER, "bad vertex")
    return DEG3_VAR_BASE + v


def incident_vars(v: int) -> tuple[int, ...]:
    return tuple(edge_var(v, w) for w in range(ORDER) if w != v)


def normalize_edges(edges: Iterable[Sequence[int]]) -> tuple[tuple[int, int], ...]:
    out: set[tuple[int, int]] = set()
    rows = 0
    for raw in edges:
        rows += 1
        require(isinstance(raw, (tuple, list)) and len(raw) == 2, "bad edge row")
        a, b = raw
        require(isinstance(a, int) and not isinstance(a, bool), "bad endpoint")
        require(isinstance(b, int) and not isinstance(b, bool), "bad endpoint")
        require(0 <= a < ORDER and 0 <= b < ORDER and a != b, "bad edge")
        edge = (a, b) if a < b else (b, a)
        require(edge not in out, f"duplicate edge {edge}")
        out.add(edge)
    require(len(out) == rows, "edge normalization mismatch")
    return tuple(sorted(out))


def adjacency(edges: Iterable[Sequence[int]]) -> tuple[set[int], ...]:
    graph = tuple(set() for _ in range(ORDER))
    for a, b in normalize_edges(edges):
        graph[a].add(b)
        graph[b].add(a)
    return graph


def canonical_cycle(path: Sequence[int]) -> tuple[int, ...]:
    require(isinstance(path, (tuple, list)), "bad cycle")
    seq = tuple(path)
    require(len(seq) >= 3, "cycle too short")
    require(all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v < ORDER for v in seq), "bad cycle vertex")
    require(len(set(seq)) == len(seq), "cycle is not simple")
    variants: list[tuple[int, ...]] = []
    for orient in (seq, tuple(reversed(seq))):
        variants.extend(orient[i:] + orient[:i] for i in range(len(seq)))
    return min(variants)


def cycles_exact(edges: Iterable[Sequence[int]], length: int) -> tuple[tuple[int, ...], ...]:
    require(length in (4, 8, 16), "unsupported cycle length")
    graph = adjacency(edges)
    found: set[tuple[int, ...]] = set()
    for start in range(ORDER):
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


def cycle_clause(cycle: Sequence[int]) -> tuple[int, ...]:
    cyc = canonical_cycle(cycle)
    require(len(cyc) in (4, 8, 16), "unsupported blocker length")
    return tuple(-edge_var(cyc[i], cyc[(i + 1) % len(cyc)]) for i in range(len(cyc)))


def _minimum_degree_clauses() -> Iterator[tuple[int, ...]]:
    # At least 3 of the 23 incident edges must be true.  Equivalently, no set
    # of 21 incident edge variables may all be false.
    for v in range(ORDER):
        inc = incident_vars(v)
        for subset in itertools.combinations(inc, len(inc) - MIN_DEGREE + 1):
            yield tuple(subset)


def _vertex_zero_symmetry_clauses() -> Iterator[tuple[int, ...]]:
    # Any counterexample has an edge-minimal spanning counterexample.  Such a
    # graph has a degree-3 vertex; relabel it 0 and its neighbors 1,2,3.
    for w in range(1, ORDER):
        yield (edge_var(0, w),) if w <= 3 else (-edge_var(0, w),)
    yield (deg3_var(0),)


def _degree3_certificate_clauses() -> Iterator[tuple[int, ...]]:
    # y_v -> degree(v) <= 3.  Minimum-degree clauses already give degree >= 3,
    # so a true y_v certifies degree exactly 3.
    for v in range(ORDER):
        y = deg3_var(v)
        for four in itertools.combinations(incident_vars(v), 4):
            yield (-y,) + tuple(-x for x in four)


def _edge_minimality_clauses() -> Iterator[tuple[int, ...]]:
    # Every retained edge must touch a certified degree-3 endpoint.  This is
    # exactly the edge-minimal min-degree>=3 reduction needed for no-loss
    # existence search after arbitrary edges are deleted from a counterexample.
    for a, b in EDGES:
        yield (-edge_var(a, b), deg3_var(a), deg3_var(b))


def _c4_blockers() -> Iterator[tuple[int, ...]]:
    # There are exactly three undirected 4-cycles on each 4-set.
    for a, b, c, d in itertools.combinations(range(ORDER), 4):
        for cyc in ((a, b, c, d), (a, b, d, c), (a, c, b, d)):
            yield cycle_clause(cyc)


def base_clause_groups() -> tuple[tuple[str, tuple[tuple[int, ...], ...]], ...]:
    return (
        ("minimum_degree_at_least_3", tuple(_minimum_degree_clauses())),
        ("vertex_zero_symmetry", tuple(_vertex_zero_symmetry_clauses())),
        ("degree3_certificates", tuple(_degree3_certificate_clauses())),
        ("edge_minimality", tuple(_edge_minimality_clauses())),
        ("c4_blockers", tuple(_c4_blockers())),
    )


def base_clauses() -> tuple[tuple[int, ...], ...]:
    return tuple(clause for _, group in base_clause_groups() for clause in group)


def normalize_cut_records(records: Iterable[dict]) -> tuple[dict, ...]:
    by_key: dict[tuple[int, tuple[int, ...]], dict] = {}
    for raw in records:
        require(isinstance(raw, dict), "cut record must be object")
        require(set(raw) == {"length", "cycle", "clause"}, "unexpected cut record fields")
        length = raw["length"]
        require(length in LAZY_LENGTHS, "lazy cut must be C8 or C16")
        cycle = canonical_cycle(raw["cycle"])
        require(len(cycle) == length, "cut length mismatch")
        clause = cycle_clause(cycle)
        require(tuple(raw["clause"]) == clause, "cut clause does not match cycle")
        key = (length, cycle)
        by_key[key] = {"length": length, "cycle": list(cycle), "clause": list(clause)}
    return tuple(by_key[key] for key in sorted(by_key))


def cut_records_for_edges(edges: Iterable[Sequence[int]]) -> tuple[dict, ...]:
    norm = normalize_edges(edges)
    records = []
    for length in LAZY_LENGTHS:
        for cycle in cycles_exact(norm, length):
            clause = cycle_clause(cycle)
            records.append({"length": length, "cycle": list(cycle), "clause": list(clause)})
    return normalize_cut_records(records)


def cut_batch(records: Iterable[dict]) -> dict:
    normalized = normalize_cut_records(records)
    payload = json.dumps(list(normalized), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema": "erdos64-n24-cycle-cuts-v1",
        "order": ORDER,
        "cut_count": len(normalized),
        "counts_by_length": {
            str(length): sum(1 for row in normalized if row["length"] == length)
            for length in LAZY_LENGTHS
        },
        "cuts_sha256": hashlib.sha256(payload).hexdigest(),
        "cuts": list(normalized),
    }


def verify_cut_batch(doc: dict) -> tuple[dict, ...]:
    require(isinstance(doc, dict), "cut batch must be object")
    require(doc.get("schema") == "erdos64-n24-cycle-cuts-v1", "bad cut schema")
    require(doc.get("order") == ORDER, "bad cut order")
    normalized = normalize_cut_records(doc.get("cuts", []))
    require(doc.get("cut_count") == len(normalized), "cut count mismatch")
    expected_counts = {
        str(length): sum(1 for row in normalized if row["length"] == length)
        for length in LAZY_LENGTHS
    }
    require(doc.get("counts_by_length") == expected_counts, "cut length counts mismatch")
    payload = json.dumps(list(normalized), sort_keys=True, separators=(",", ":")).encode("utf-8")
    require(doc.get("cuts_sha256") == hashlib.sha256(payload).hexdigest(), "cut digest mismatch")
    return normalized


def dimacs_text(cut_doc: dict | None = None) -> str:
    base = base_clauses()
    cuts: tuple[dict, ...] = ()
    if cut_doc is not None:
        cuts = verify_cut_batch(cut_doc)
    extra = tuple(tuple(row["clause"]) for row in cuts)
    clauses = base + extra
    lines = [f"c {SCHEMA}", f"c edge_vars 1..{EDGE_VAR_COUNT}", f"c deg3_certificate_vars {DEG3_VAR_BASE}..{VARIABLE_COUNT}", f"p cnf {VARIABLE_COUNT} {len(clauses)}"]
    lines.extend(" ".join(map(str, clause)) + " 0" for clause in clauses)
    return "\n".join(lines) + "\n"


def dimacs_sha256(cut_doc: dict | None = None) -> str:
    return hashlib.sha256(dimacs_text(cut_doc).encode("ascii")).hexdigest()


def base_receipt() -> dict:
    groups = base_clause_groups()
    counts = {name: len(group) for name, group in groups}
    return {
        "schema": SCHEMA,
        "order": ORDER,
        "edge_variables": EDGE_VAR_COUNT,
        "degree3_certificate_variables": ORDER,
        "variables_total": VARIABLE_COUNT,
        "base_clause_counts": counts,
        "base_clauses_total": sum(counts.values()),
        "base_dimacs_sha256": dimacs_sha256(),
        "lazy_cycle_lengths": list(LAZY_LENGTHS),
        "existence_reduction": {
            "minimum_degree": MIN_DEGREE,
            "edge_minimal_subgraph": True,
            "certified_degree3_endpoint_per_edge": True,
            "fixed_degree3_vertex": 0,
            "fixed_neighbors": [1, 2, 3],
            "no_loss_reason": "delete edges to an inclusion-minimal min-degree>=3 spanning subgraph; cycle avoidance is inherited; some vertex then has degree exactly 3; relabel it and its three neighbors",
        },
        "proof_boundary": "C8/C16 are lazy valid cycle blockers; SAT model with zero lazy violations is a counterexample; UNSAT is theorem-grade only with an independently checked SAT proof for the exact emitted CNF",
    }


def parse_solver_output(text: str) -> tuple[str, dict[int, bool] | None]:
    require(isinstance(text, str), "solver output must be text")
    status: str | None = None
    literals: list[int] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("c"):
            continue
        if line in ("SAT", "SATISFIABLE") or line == "s SATISFIABLE":
            require(status in (None, "SAT"), "conflicting solver status")
            status = "SAT"
            continue
        if line in ("UNSAT", "UNSATISFIABLE") or line == "s UNSATISFIABLE":
            require(status in (None, "UNSAT"), "conflicting solver status")
            status = "UNSAT"
            continue
        if line.startswith("v "):
            tokens = line.split()[1:]
            for token in tokens:
                lit = int(token)
                if lit != 0:
                    literals.append(lit)
            continue
        # Common MiniSAT-style bare model line after SAT.
        if status == "SAT" and all(tok.lstrip("-").isdigit() for tok in line.split()):
            for token in line.split():
                lit = int(token)
                if lit != 0:
                    literals.append(lit)
            continue
    require(status is not None, "solver status missing")
    if status == "UNSAT":
        require(not literals, "UNSAT output must not contain model literals")
        return status, None
    model: dict[int, bool] = {}
    for lit in literals:
        var = abs(lit)
        require(1 <= var <= VARIABLE_COUNT, "model variable out of range")
        value = lit > 0
        require(var not in model, f"duplicate model variable {var}")
        model[var] = value
    require(len(model) == VARIABLE_COUNT, f"incomplete SAT model: {len(model)}/{VARIABLE_COUNT}")
    return status, model


def model_edges(model: dict[int, bool]) -> tuple[tuple[int, int], ...]:
    require(isinstance(model, dict), "bad model")
    return tuple(EDGES[var - 1] for var in range(1, EDGE_VAR_COUNT + 1) if model.get(var) is True)


def clause_holds(clause: Sequence[int], model: dict[int, bool]) -> bool:
    for lit in clause:
        value = model.get(abs(lit))
        require(value is not None, f"model missing variable {abs(lit)}")
        if (lit > 0 and value) or (lit < 0 and not value):
            return True
    return False


def validate_base_model(model: dict[int, bool]) -> dict:
    failed = [i for i, clause in enumerate(base_clauses()) if not clause_holds(clause, model)]
    require(not failed, f"model violates base clauses; first index {failed[0] if failed else None}")
    edges = model_edges(model)
    graph = adjacency(edges)
    degrees = [len(ns) for ns in graph]
    require(min(degrees) >= 3, "decoded model violates minimum degree")
    require(graph[0] == {1, 2, 3}, "decoded model violates vertex-0 symmetry")
    require(not cycles_exact(edges, 4), "decoded model contains C4")
    return {
        "edge_count": len(edges),
        "degree_min": min(degrees),
        "degree_max": max(degrees),
        "degree3_certificate_true": sum(1 for v in range(ORDER) if model[deg3_var(v)]),
    }


def model_for_edges(edges: Iterable[Sequence[int]]) -> dict[int, bool]:
    """Construct a satisfying auxiliary assignment for an edge-minimal graph.

    This helper is intentionally strict: each selected edge must touch an actual
    degree-3 endpoint, matching the reduction encoded in the base CNF.
    """
    norm = normalize_edges(edges)
    selected = set(norm)
    graph = adjacency(norm)
    model = {var: EDGES[var - 1] in selected for var in range(1, EDGE_VAR_COUNT + 1)}
    degree3 = {v for v in range(ORDER) if len(graph[v]) == 3}
    for a, b in norm:
        require(a in degree3 or b in degree3, f"graph is not edge-minimal at edge {(a, b)}")
    for v in range(ORDER):
        model[deg3_var(v)] = v in degree3
    return model


def relabel_for_vertex_zero(edges: Iterable[Sequence[int]], root: int) -> tuple[tuple[int, int], ...]:
    norm = normalize_edges(edges)
    graph = adjacency(norm)
    require(len(graph[root]) == 3, "root must have degree 3")
    neighbors = sorted(graph[root])
    mapping = {root: 0}
    for new, old in enumerate(neighbors, start=1):
        mapping[old] = new
    remaining = [v for v in range(ORDER) if v not in mapping]
    for new, old in enumerate(remaining, start=4):
        mapping[old] = new
    return normalize_edges((mapping[a], mapping[b]) for a, b in norm)


def separate_model(model: dict[int, bool]) -> dict:
    base = validate_base_model(model)
    edges = model_edges(model)
    records = cut_records_for_edges(edges)
    batch = cut_batch(records)
    return {
        "schema": "erdos64-n24-separation-v1",
        "base_model": base,
        "lazy_violations": batch["counts_by_length"],
        "counterexample": batch["cut_count"] == 0,
        "cut_batch": batch,
    }


def read_json(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(data, dict), "JSON root must be object")
    return data


def write_exclusive(path: str | Path, text: str) -> None:
    p = Path(path)
    with p.open("x", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("receipt")
    p_cnf = sub.add_parser("write-cnf")
    p_cnf.add_argument("output")
    p_cnf.add_argument("--cuts")
    p_sep = sub.add_parser("separate")
    p_sep.add_argument("solver_output")
    p_sep.add_argument("output")
    p_verify = sub.add_parser("verify-cuts")
    p_verify.add_argument("cuts")
    args = parser.parse_args(argv)

    if args.command == "receipt":
        print(json.dumps(base_receipt(), sort_keys=True, indent=2))
        return 0
    if args.command == "write-cnf":
        cuts = read_json(args.cuts) if args.cuts else None
        write_exclusive(args.output, dimacs_text(cuts))
        print(json.dumps({"path": args.output, "sha256": dimacs_sha256(cuts)}, sort_keys=True))
        return 0
    if args.command == "verify-cuts":
        cuts = verify_cut_batch(read_json(args.cuts))
        print(json.dumps({"ok": True, "cut_count": len(cuts)}, sort_keys=True))
        return 0
    if args.command == "separate":
        status, model = parse_solver_output(Path(args.solver_output).read_text(encoding="utf-8"))
        if status == "UNSAT":
            raise DecisionError("UNSAT requires external proof verification; no cut batch emitted")
        result = separate_model(model or {})
        write_exclusive(args.output, json.dumps(result["cut_batch"], sort_keys=True, indent=2) + "\n")
        print(json.dumps({k: v for k, v in result.items() if k != "cut_batch"}, sort_keys=True))
        return 0
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
