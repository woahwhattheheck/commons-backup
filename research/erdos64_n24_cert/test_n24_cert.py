import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("n24_cert", HERE / "n24_cert.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class N24CertificateTests(unittest.TestCase):
    def test_markstroem_frontier_properties(self):
        result = mod.verify(24, mod.markstroem())
        self.assertEqual(result["edge_count"], 36)
        self.assertEqual(result["degree_histogram"], {"3": 24})
        self.assertEqual(result["power_cycle_counts"]["4"], 0)
        self.assertEqual(result["power_cycle_counts"]["8"], 0)
        self.assertEqual(result["power_cycle_counts"]["16"], 228)
        self.assertFalse(result["all_power_lengths_avoided"])

    def test_encoding_is_edge_order_and_direction_invariant(self):
        edges = mod.markstroem()
        reversed_edges = [(b, a) for a, b in reversed(edges)]
        self.assertEqual(mod.digest(24, edges), mod.digest(24, reversed_edges))

    def test_bad_edges_fail_closed(self):
        good = list(mod.markstroem())
        for bad in (
            good + [good[0]],
            good + [(0, 0)],
            good + [(-1, 2)],
            good + [(0, 24)],
            good + [[0, 1, 2]],
        ):
            with self.assertRaises(mod.GraphError):
                mod.normalize(24, bad)

    def test_minimum_degree_is_enforced(self):
        edges = list(mod.markstroem())
        edges.remove(edges[0])
        with self.assertRaisesRegex(mod.GraphError, "minimum degree"):
            mod.verify(24, edges)

    def test_cycle_canonicalization(self):
        self.assertEqual(
            mod.canonical_cycle([3, 4, 1, 2]),
            mod.canonical_cycle([1, 4, 3, 2]),
        )

    def test_two_switches_preserve_cubic_degree(self):
        for graph in mod.two_switch_neighbors(24, mod.markstroem()):
            self.assertEqual([len(x) for x in mod.adjacency(24, graph)], [3] * 24)

    def test_local_scan_receipt(self):
        result = mod.scan()
        self.assertEqual(result["unique_two_switch_neighbors"], 993)
        self.assertEqual(result["no_c4_no_c8_neighbors"], 30)
        self.assertEqual(result["no_c4_no_c8_no_c16_neighbors"], 0)
        self.assertEqual(
            result["first_short_clean_sha256"],
            "0da825dcd428654baf0d547958bba280f3f2aeafb0bd73cd6938391422eadc1d",
        )

    def test_committed_receipt_regenerates_exactly(self):
        committed = json.loads((HERE / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, mod.receipt())


if __name__ == "__main__":
    unittest.main()
