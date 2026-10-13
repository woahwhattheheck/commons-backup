import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import n24_cert as cert
import published_examples as pub


class PublishedExampleTests(unittest.TestCase):
    def test_all_four_pinned_examples_have_expected_power_cycle_counts(self):
        expected = {
            "markstroem.txt": (228, "ba701ecae49e80975541fa3274c2fa84eb77c3cb4a65614385555e0b984a7575"),
            "24-node-cubic-no-4-8-cycles-p18-free.1.txt": (315, "30cd406b48e4ae6480a5f138d41c8fc4d5f809e2b180e28b5cc718ced44f1c7b"),
            "24-node-cubic-no-4-8-cycles-p18-free.2.txt": (330, "c843c454fe972accf74c312d36b7e8a55b3827b9f4ac90ddc579c5ff0aeb4db5"),
            "24-node-cubic-no-4-8-cycles-p18-free.3.txt": (207, "63c307c75d96e0b1b05ecdba4629034122c512959f6315e4ccf719fda13beb11"),
        }
        for path, _blob, edges in pub.SOURCE_EXAMPLES:
            result = cert.verify(24, edges)
            self.assertEqual(result["edge_count"], 36)
            self.assertEqual(result["degree_histogram"], {"3": 24})
            self.assertEqual(result["power_cycle_counts"]["4"], 0)
            self.assertEqual(result["power_cycle_counts"]["8"], 0)
            self.assertEqual(result["power_cycle_counts"]["16"], expected[path][0])
            self.assertEqual(result["labeled_sha256"], expected[path][1])
            self.assertFalse(result["all_power_lengths_avoided"])

    def test_sagemath_fixture_binds_to_upstream_markstroem(self):
        self.assertTrue(pub.sage_binding_holds())
        self.assertEqual(pub.relabel(cert.markstroem(), pub.SAGE_TO_UPSTREAM_MARKSTROEM), pub.EXAMPLE_0_EDGES)

    def test_c16_counts_prove_the_four_sources_are_pairwise_nonisomorphic(self):
        counts = [cert.verify(24, edges)["power_cycle_counts"]["16"] for _path, _blob, edges in pub.SOURCE_EXAMPLES]
        self.assertEqual(counts, [228, 315, 330, 207])
        self.assertEqual(len(set(counts)), 4)

    def test_committed_receipt_regenerates_exactly(self):
        committed = json.loads((HERE / "published_examples_receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(committed, pub.audit())


if __name__ == "__main__":
    unittest.main()
