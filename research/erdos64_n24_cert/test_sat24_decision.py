#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sat24_decision as sat

MARKSTROEM_EDGES = (
    (0, 1), (0, 8), (0, 9), (1, 2), (1, 11), (2, 3), (2, 11),
    (3, 4), (3, 12), (4, 5), (4, 14), (5, 6), (5, 14), (6, 7),
    (6, 15), (7, 8), (7, 17), (8, 17), (9, 10), (9, 18), (10, 11),
    (10, 18), (12, 13), (12, 19), (13, 14), (13, 19), (15, 16),
    (15, 20), (16, 17), (16, 20), (18, 21), (19, 22), (20, 23),
    (21, 22), (21, 23), (22, 23),
)


class Sat24DecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = sat.relabel_for_vertex_zero(MARKSTROEM_EDGES, 0)
        cls.model = sat.model_for_edges(cls.fixture)

    def test_base_counts_and_digest_are_stable(self):
        receipt = sat.base_receipt()
        self.assertEqual(receipt["edge_variables"], 276)
        self.assertEqual(receipt["degree3_certificate_variables"], 24)
        self.assertEqual(receipt["variables_total"], 300)
        self.assertEqual(receipt["base_clause_counts"], {
            "minimum_degree_at_least_3": 6072,
            "vertex_zero_symmetry": 24,
            "degree3_certificates": 212520,
            "edge_minimality": 276,
            "c4_blockers": 31878,
        })
        self.assertEqual(receipt["base_clauses_total"], 250770)
        self.assertEqual(len(sat.dimacs_sha256()), 64)

    def test_relabelled_markstroem_satisfies_exact_base(self):
        summary = sat.validate_base_model(self.model)
        self.assertEqual(summary["edge_count"], 36)
        self.assertEqual(summary["degree_min"], 3)
        self.assertEqual(summary["degree_max"], 3)
        self.assertEqual(summary["degree3_certificate_true"], 24)
        self.assertEqual(sat.adjacency(self.fixture)[0], {1, 2, 3})
        self.assertEqual(len(sat.cycles_exact(self.fixture, 4)), 0)

    def test_known_frontier_model_separates_to_228_c16_cuts(self):
        result = sat.separate_model(self.model)
        self.assertFalse(result["counterexample"])
        self.assertEqual(result["lazy_violations"], {"8": 0, "16": 228})
        batch = result["cut_batch"]
        self.assertEqual(batch["cut_count"], 228)
        sat.verify_cut_batch(batch)
        for row in batch["cuts"]:
            self.assertEqual(row["length"], 16)
            self.assertFalse(sat.clause_holds(row["clause"], self.model))

    def test_cut_batch_tamper_is_rejected(self):
        batch = sat.separate_model(self.model)["cut_batch"]
        bad = copy.deepcopy(batch)
        bad["cuts"][0]["clause"][0] *= -1
        with self.assertRaises(sat.DecisionError):
            sat.verify_cut_batch(bad)
        bad2 = copy.deepcopy(batch)
        bad2["cuts_sha256"] = "0" * 64
        with self.assertRaises(sat.DecisionError):
            sat.verify_cut_batch(bad2)

    def test_sat_competition_model_parser_is_strict(self):
        literals = [str(v if self.model[v] else -v) for v in range(1, sat.VARIABLE_COUNT + 1)]
        text = "s SATISFIABLE\n" + "\n".join(
            "v " + " ".join(literals[i:i + 40]) + " 0" for i in range(0, len(literals), 40)
        ) + "\n"
        status, parsed = sat.parse_solver_output(text)
        self.assertEqual(status, "SAT")
        self.assertEqual(parsed, self.model)
        with self.assertRaises(sat.DecisionError):
            sat.parse_solver_output("s SATISFIABLE\nv 1 -2 0\n")
        with self.assertRaises(sat.DecisionError):
            sat.parse_solver_output("s SATISFIABLE\nv 1 -1 0\n")
        self.assertEqual(sat.parse_solver_output("s UNSATISFIABLE\n"), ("UNSAT", None))

    def test_edge_minimal_certificate_rejects_nonminimal_graph(self):
        # K_24 has min degree >=3 but no endpoint of an edge has degree 3.
        complete = sat.EDGES
        with self.assertRaises(sat.DecisionError):
            sat.model_for_edges(complete)

    def test_cut_serialization_is_canonical(self):
        batch = sat.separate_model(self.model)["cut_batch"]
        reversed_batch = sat.cut_batch(reversed(batch["cuts"]))
        self.assertEqual(reversed_batch, batch)
        dumped = json.dumps(batch, sort_keys=True, separators=(",", ":"))
        self.assertIn('"cut_count":228', dumped)


if __name__ == "__main__":
    unittest.main()
