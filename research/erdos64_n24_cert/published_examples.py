#!/usr/bin/env python3
"""Bind and verify all four published 24-vertex Markström examples for Erdős #64."""
from __future__ import annotations
import argparse
import json
from typing import Sequence
import n24_cert as cert

UPSTREAM_REPOSITORY = "rbsandeep/Erdos-Gyarfas"
UPSTREAM_BRANCH = "special-graphs"
UPSTREAM_COMMIT = "f7bea75afecb07dab552047ece2d551722f32272"
UPSTREAM_TREE = "06c2d84a617ce9852be9bcaa4025235ab81af6c1"
UPSTREAM_README_BLOB = "a3be3d50b5aa5377f9ba20f7c187c039cc7d4a0f"

def parse_edges(text: str):
    return cert.normalize(24, (tuple(map(int, token.split("-"))) for token in text.split()))

SOURCE_EXAMPLES = (
    ("markstroem.txt", "e661c40ad9560d74a543f956ce47e07dbb5fd6db", parse_edges("0-1 0-17 0-22 1-2 1-17 2-3 2-23 3-4 3-23 4-5 4-20 5-6 5-20 6-7 6-23 7-8 7-21 8-9 8-21 9-10 9-22 10-11 10-22 11-12 11-21 12-13 12-19 13-14 13-19 14-15 14-20 15-16 15-18 16-17 16-18 18-19")),
    ("24-node-cubic-no-4-8-cycles-p18-free.1.txt", "851b3aa030e2233839f61095f13d6889829db69f", parse_edges("0-1 0-6 0-9 1-2 1-6 2-3 2-7 3-4 3-7 4-5 4-8 5-8 5-14 6-20 7-21 8-15 9-10 9-17 10-11 10-19 11-12 11-20 12-13 12-23 13-14 13-18 14-17 15-16 15-18 16-17 16-20 18-19 19-22 21-22 21-23 22-23")),
    ("24-node-cubic-no-4-8-cycles-p18-free.2.txt", "79fff11f0cea351f468fe89131320666b9495732", parse_edges("0-1 0-11 0-12 1-2 1-12 2-3 2-13 3-4 3-16 4-5 4-14 5-6 5-14 6-7 6-17 7-8 7-19 8-9 8-23 9-10 9-23 10-11 10-20 11-22 12-21 13-15 13-22 14-15 15-16 16-17 17-18 18-19 18-23 19-20 20-21 21-22")),
    ("24-node-cubic-no-4-8-cycles-p18-free.3.txt", "2c8c4664964097da3e39efe3efc272834d85ebc6", parse_edges("0-1 0-10 0-13 1-2 1-10 2-3 2-7 3-4 3-8 4-5 4-8 5-6 5-15 6-14 6-15 7-9 7-12 8-9 9-22 10-11 11-12 11-16 12-19 13-14 13-23 14-23 15-18 16-17 16-18 17-18 17-19 19-20 20-21 20-22 21-22 21-23")),
)

EXAMPLE_0_EDGES = SOURCE_EXAMPLES[0][2]
SAGE_TO_UPSTREAM_MARKSTROEM = (11, 21, 7, 6, 5, 20, 14, 13, 12, 10, 9, 8, 23, 3, 4, 15, 18, 19, 22, 2, 16, 0, 1, 17)

def relabel(edges, mapping):
    cert.require(len(mapping) == 24 and set(mapping) == set(range(24)), "bad relabel permutation")
    return cert.normalize(24, ((mapping[a], mapping[b]) for a, b in edges))

def sage_binding_holds() -> bool:
    return relabel(cert.markstroem(), SAGE_TO_UPSTREAM_MARKSTROEM) == EXAMPLE_0_EDGES

def audit() -> dict:
    examples = []
    c16_counts = []
    for path, blob, edges in SOURCE_EXAMPLES:
        result = cert.verify(24, edges)
        cert.require(result["edge_count"] == 36 and result["degree_histogram"] == {"3": 24}, f"{path}: not cubic")
        cert.require(result["power_cycle_counts"]["4"] == 0, f"{path}: contains C4")
        cert.require(result["power_cycle_counts"]["8"] == 0, f"{path}: contains C8")
        cert.require(result["power_cycle_counts"]["16"] > 0, f"{path}: expected C16")
        cert.require(not result["all_power_lengths_avoided"], f"{path}: unexpected counterexample")
        c16_counts.append(result["power_cycle_counts"]["16"])
        examples.append({
            "path": path, "git_blob": blob, "order": 24, "edges": 36,
            "degree_histogram": {"3": 24},
            "labeled_sha256": result["labeled_sha256"],
            "power_cycle_counts": result["power_cycle_counts"],
        })
    cert.require(c16_counts == [228, 315, 330, 207], "unexpected C16 counts")
    cert.require(len(set(c16_counts)) == 4, "fixtures are not distinguished by C16 count")
    cert.require(sage_binding_holds(), "Sage fixture failed explicit relabel binding")
    return {
        "schema": "erdos64-n24-four-examples-v1",
        "source": {
            "repository": UPSTREAM_REPOSITORY, "branch": UPSTREAM_BRANCH,
            "commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE,
            "readme_blob": UPSTREAM_README_BLOB,
        },
        "examples": examples,
        "cross_source_binding": {
            "sagemath_fixture_isomorphic_to_upstream_markstroem": True,
            "sage_to_upstream_markstroem_permutation": list(SAGE_TO_UPSTREAM_MARKSTROEM),
        },
        "pairwise_distinct_witness": {
            "invariant": "exact number of simple 16-cycles",
            "counts_in_source_order": c16_counts, "all_distinct": True,
        },
        "evidence_ceiling": "published finite examples only; no proof/counterexample/prize/payment/revenue claim",
    }

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("audit",))
    parser.parse_args(argv)
    print(json.dumps(audit(), sort_keys=True, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
