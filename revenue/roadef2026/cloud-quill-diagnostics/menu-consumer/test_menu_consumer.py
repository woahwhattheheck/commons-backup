#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import menu_consumer as consumer


class MenuConsumerTests(unittest.TestCase):
    def test_extract_function_ignores_braces_in_comments_and_strings(self):
        source = '''bool dockTemporal(int d) {\n  const char* s = "}"; // { ignored\n  /* } ignored */\n  if (d) { return true; }\n  return false;\n}\nvoid later() {}\n'''
        body = consumer.extract_function(source, "bool dockTemporal(")
        self.assertIn("if (d) { return true; }", body)
        self.assertNotIn("void later", body)

    def test_menu_only_loop_preserves_kernel_body(self):
        source = '''class Solver {\n    bool dockTemporal(int d, const Route& r = {}) { return d || !r.empty(); }\n    void run() {\n''' + consumer.RUN_LOOP + '''\n    }\n};\n'''
        patched = source.replace(consumer.RUN_LOOP, consumer.MENU_ONLY_LOOP, 1)
        original_body = consumer.extract_function(source, "    bool dockTemporal(")
        patched_body = consumer.extract_function(patched, "    bool dockTemporal(")
        self.assertEqual(original_body, patched_body)
        self.assertIn("return d || !r.empty();", original_body)
        self.assertGreater(len(original_body), 70)
        self.assertNotIn("dockTemporal(d,nodes)", patched)
        self.assertIn("dockTemporal(d);", patched)
        self.assertIn("dockExtraMenu", patched)

    def test_route_changes_tracks_implicit_empty_routes(self):
        before = {"srpaths": [{"d": 3, "t": 1, "w": [9]}]}
        after = {"srpaths": [{"d": 3, "t": 0, "w": [7]},
                              {"d": 3, "t": 1, "w": [9]}]}
        self.assertEqual(consumer.route_changes(before, after),
                         [{"d": 3, "t": 0, "before": [], "after": [7]}])

    @staticmethod
    def checker(values, *, valid=True, cost=4, paths=2, segments=3):
        return {"valid": valid, "total_cost": cost, "total_srpaths": paths,
                "total_segments": segments,
                "saturations": [{"sat": value} for value in values]}

    def test_checker_comparison_detects_deep_lexicographic_improvement(self):
        old = self.checker(["0.9", "0.8", "0.7"])
        new = self.checker(["0.9", "0.8", "0.6"], cost=5)
        result = consumer.compare_checker(old, new)
        self.assertEqual(result["relation"], "improved")
        self.assertEqual(result["first_difference_rank_1_based"], 3)
        self.assertEqual(result["cost_delta"], 1)

    def test_checker_comparison_detects_tie_and_worse(self):
        old = self.checker(["0.5", "0.4"])
        self.assertEqual(consumer.compare_checker(old, copy.deepcopy(old))["relation"], "tie")
        worse = self.checker(["0.5", "0.41"])
        self.assertEqual(consumer.compare_checker(old, worse)["relation"], "worse")

    def test_checker_vector_length_must_match(self):
        with self.assertRaisesRegex(ValueError, "differ in length"):
            consumer.compare_checker(self.checker([1]), self.checker([1, 2]))

    def test_binding_verifier_checks_every_named_object(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            menu_root, screen = root / "menus", root / "screen"
            menu_root.mkdir(); (screen / "x").mkdir(parents=True)
            menu = menu_root / "case.json"; menu.write_text('{"routes":[]}\n')
            item = screen / "x" / "input.json"; item.write_text('{}\n')
            bindings = {"instances": [{"menu": menu.name,
                "menu_sha256": consumer.sha256(menu), "inputs": {"input": {
                    "archive_member": "x/input.json", "sha256": consumer.sha256(item)}}}]}
            result = consumer.verify_bindings(bindings, menu_root, screen)
            self.assertEqual(result["objects"], 2)
            item.write_text('{"changed":true}\n')
            with self.assertRaisesRegex(ValueError, "input hash mismatch"):
                consumer.verify_bindings(bindings, menu_root, screen)

    def test_wrong_parent_is_rejected_before_generation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "main.cpp"; parent.write_text("int main(){}\n")
            dock = root / "dock"; dock.mkdir()
            with self.assertRaisesRegex(ValueError, "fleet 2885d176"):
                consumer.build_menu_only_source(parent, dock, root / "out")

    def test_case_order_is_fixed(self):
        self.assertEqual(consumer.CASES,
                         ("setB-02", "setB-05", "setB-07", "setB-10"))


class PublishedResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((Path(__file__).resolve().parent / "RESULTS.json").read_text())

    def test_published_case_partition(self):
        self.assertEqual(self.report["result_summary"]["changed_cases"],
                         ["setB-02", "setB-05", "setB-07"])
        self.assertEqual(self.report["result_summary"]["unchanged_cases"], ["setB-10"])

    def test_every_checker_result_is_valid_and_nonworsening(self):
        for row in self.report["results"]:
            for decimals in ("6", "12"):
                check = row["checks"][decimals]
                self.assertTrue(check["valid"], (row["case"], decimals))
                self.assertIn(check["relation"], ("improved", "tie"))

    def test_route_changes_stay_with_bound_demands(self):
        for row in self.report["results"]:
            targets = set(row["targets"])
            self.assertTrue(all(change["d"] in targets for change in row["route_changes"]))

    def test_b05_single_route_attribution(self):
        controls = self.report["controls"]["b05_single_route"]
        self.assertEqual(controls["d93_only"]["relation_to_incumbent"], "byte_identical")
        self.assertEqual(controls["d654_only"]["relation_to_combined"], "byte_identical")


if __name__ == "__main__":
    unittest.main(verbosity=2)
