"""Bind the composition to the independently reviewed statistical function spans."""
import ast
import hashlib
from pathlib import Path
import unittest
import soundness

EXPECTED = {'_positive_trials': '23851772e6091162509225d534df689a92705fb38f9d1660f0e68b720ac53e19', 'rule_of_three_upper_bound': 'fb69069a4d48325c8831a615ccc5d02a2046cc978029bcb843e1dda116e913ad', 'zero_event_upper_bound': 'b1c0099de03cb67300005df1ff15fcec86065af5e1d2c43bda4498aca706ccc7', '_validate_proportion': 'd3737928756bb2147a25a1917c1a8f8e246d3c1c0fb247ef89a2017f2ab613bf', '_check_zero_claim': '6fd7c5e49532c680a12a115e7d8c7df38741d151bff7ea0a2fc50aa1e506ec44', '_check_median': '4fabf476c70d7e7587a4dd0410f86fbae240b140a1ab18fc48ce0a2aeb07cdba', '_check_components': 'ea0e161d3e84b922d588726a5b05daaaa68c088997cb524962fc40d898b6371d', 'render_text': '19937ceacea558e976ce991dc49a325efaf5398c9eadffa9dfed8945115cad0d'}


class ReviewedMethodParity(unittest.TestCase):
    def test_reviewed_function_spans_are_unchanged(self):
        source = Path(soundness.__file__).read_text(encoding="utf-8")
        functions = {node.name: ast.get_source_segment(source, node).encode("utf-8")
                     for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}
        for name, digest in EXPECTED.items():
            with self.subTest(function=name):
                self.assertEqual(hashlib.sha256(functions[name]).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
