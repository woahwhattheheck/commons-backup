from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("composition_intake", HERE / "composition_intake.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class IntakeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_json(self, name: str, value: object) -> None:
        (self.root / name).write_text(json.dumps(value, sort_keys=True), encoding="utf-8")

    def package(self, rel: str, files: list[str]) -> None:
        base = self.root / rel
        base.mkdir(parents=True, exist_ok=True)
        for name in files:
            path = base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# fixture\n", encoding="utf-8")

    def ledgers(self, rows: list[dict], components: list[dict]) -> None:
        self.write_json("INTEGRATION.json", {"schema": MOD.INTEGRATION_SCHEMA, "landed": rows})
        self.write_json("COMPOSITION.json", {"schema": MOD.COMPOSITION_SCHEMA, "components": components})

    def test_classifies_covered_blocked_unregistered_and_source_only(self) -> None:
        self.package("repairs/a", ["compose_a.py"])
        self.package("repairs/b", ["build_native_b.py"])
        self.package("repairs/c", ["materialize_c.py"])
        self.package("repairs/d", ["helper.py"])
        self.ledgers(
            [
                {"lane": "A", "repair_path": "repairs/a"},
                {"lane": "B", "repair_path": "repairs/b"},
                {"lane": "C", "repair_path": "repairs/c"},
                {"lane": "D", "repair_path": "repairs/d"},
            ],
            [
                {"id": "a", "state": "compose", "package": "repairs/a", "entrypoints": ["repairs/a/compose_a.py"]},
                {"id": "b", "state": "blocked", "package": "repairs/b", "entrypoints": ["repairs/b/build_native_b.py"]},
            ],
        )
        result = MOD.run(self.root)
        self.assertTrue(result["ok"])
        classes = {item["repair_path"]: item["classification"] for item in result["packages"]}
        self.assertEqual(classes["repairs/a"], "graph_covered")
        self.assertEqual(classes["repairs/b"], "explicitly_blocked")
        self.assertEqual(classes["repairs/c"], "unregistered_transform_candidate")
        self.assertEqual(classes["repairs/d"], "source_only_no_transform")
        self.assertEqual([item["repair_path"] for item in result["queue"]], ["repairs/c"])

    def test_evidence_only_is_not_promoted_to_queue(self) -> None:
        self.package("research/x", ["compose_x.py"])
        self.ledgers(
            [{"lane": "X", "repair_path": "research/x"}],
            [{"id": "x", "state": "evidence_only", "package": "research/x", "entrypoints": ["research/x/compose_x.py"]}],
        )
        result = MOD.run(self.root)
        self.assertEqual(result["packages"][0]["classification"], "evidence_only")
        self.assertEqual(result["queue"], [])

    def test_broad_graph_package_does_not_swallow_nested_repair_without_entrypoint(self) -> None:
        self.package("repairs/performance/alpha", ["materialize_alpha.py"])
        self.package("repairs/performance", ["compose_other.py"])
        self.ledgers(
            [{"lane": "alpha", "repair_path": "repairs/performance/alpha"}],
            [{"id": "broad", "state": "compose", "package": "repairs/performance", "entrypoints": ["repairs/performance/compose_other.py"]}],
        )
        result = MOD.run(self.root)
        self.assertEqual(result["packages"][0]["classification"], "unregistered_transform_candidate")

    def test_broad_graph_package_covers_when_declared_entrypoint_is_inside_exact_repair(self) -> None:
        self.package("repairs/performance/alpha", ["compose_alpha.py"])
        (self.root / "repairs/performance").mkdir(parents=True, exist_ok=True)
        self.ledgers(
            [{"lane": "alpha", "repair_path": "repairs/performance/alpha"}],
            [{"id": "broad", "state": "compose", "package": "repairs/performance", "entrypoints": ["repairs/performance/alpha/compose_alpha.py"]}],
        )
        result = MOD.run(self.root)
        self.assertEqual(result["packages"][0]["classification"], "graph_covered")

    def test_shared_package_is_grouped_with_warning_not_double_counted(self) -> None:
        self.package("repairs/shared", ["compose_shared.py"])
        self.ledgers(
            [
                {"lane": "one", "repair_path": "repairs/shared"},
                {"lane": "two", "repair_path": "repairs/shared"},
            ],
            [],
        )
        result = MOD.run(self.root)
        self.assertTrue(result["ok"])
        self.assertEqual(result["counts"]["repair_packages"], 1)
        self.assertEqual(result["packages"][0]["lanes"], ["one", "two"])
        self.assertEqual(result["warnings"][0]["code"], "shared_repair_package")

    def test_missing_repair_path_is_unroutable_not_guessed(self) -> None:
        self.ledgers([{"lane": "legacy", "source_blob": "abc"}], [])
        result = MOD.run(self.root)
        self.assertTrue(result["ok"])
        self.assertEqual(result["unroutable_rows"], [{"index": 0, "lane": "legacy", "reason": "repair_path_missing"}])

    def test_missing_package_fails_closed(self) -> None:
        self.ledgers([{"lane": "gone", "repair_path": "repairs/gone"}], [])
        result = MOD.run(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["code"], "repair_package_unusable")

    def test_unsafe_repair_path_fails_closed(self) -> None:
        self.ledgers([{"lane": "escape", "repair_path": "../escape"}], [])
        result = MOD.run(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(item["code"] == "unsafe_repair_path" for item in result["errors"]))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_package_fails_closed(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "compose_bad.py").write_text("# bad\n", encoding="utf-8")
        (self.root / "repairs").mkdir()
        os.symlink(outside, self.root / "repairs/link")
        self.ledgers([{"lane": "link", "repair_path": "repairs/link"}], [])
        result = MOD.run(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["reason"], "symlink")

    def test_duplicate_lane_fails_closed(self) -> None:
        self.package("repairs/a", ["helper.py"])
        self.package("repairs/b", ["helper.py"])
        self.ledgers(
            [{"lane": "same", "repair_path": "repairs/a"}, {"lane": "same", "repair_path": "repairs/b"}],
            [],
        )
        result = MOD.run(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(item["code"] == "duplicate_lane" for item in result["errors"]))

    def test_duplicate_component_id_fails_closed(self) -> None:
        self.ledgers([], [
            {"id": "dup", "state": "compose", "package": "repairs/a", "entrypoints": []},
            {"id": "dup", "state": "blocked", "package": "repairs/b", "entrypoints": []},
        ])
        result = MOD.run(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any(item["code"] == "duplicate_component_id" for item in result["errors"]))

    def test_strict_loader_rejects_duplicate_keys(self) -> None:
        (self.root / "INTEGRATION.json").write_text('{"schema":"titan-v4-integration-ledger/v1","landed":[],"landed":[]}', encoding="utf-8")
        self.write_json("COMPOSITION.json", {"schema": MOD.COMPOSITION_SCHEMA, "components": []})
        result = MOD.run(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["code"], "ledger_load_error")
        self.assertIn("duplicate JSON key", result["errors"][0]["error"])

    def test_strict_loader_rejects_nonfinite_json(self) -> None:
        (self.root / "INTEGRATION.json").write_text('{"schema":"titan-v4-integration-ledger/v1","landed":[],"x":NaN}', encoding="utf-8")
        self.write_json("COMPOSITION.json", {"schema": MOD.COMPOSITION_SCHEMA, "components": []})
        result = MOD.run(self.root)
        self.assertFalse(result["ok"])
        self.assertIn("non-finite JSON constant", result["errors"][0]["error"])

    def test_deterministic_output_independent_of_row_order(self) -> None:
        self.package("repairs/a", ["compose_a.py"])
        self.package("repairs/z", ["materialize_z.py"])
        components: list[dict] = []
        rows = [{"lane": "z", "repair_path": "repairs/z"}, {"lane": "a", "repair_path": "repairs/a"}]
        self.ledgers(rows, components)
        first = MOD.run(self.root)
        self.ledgers(list(reversed(rows)), components)
        second = MOD.run(self.root)
        self.assertEqual(first["packages"], second["packages"])
        self.assertEqual(first["queue"], second["queue"])

    def test_transform_pattern_is_conservative(self) -> None:
        self.package("repairs/a", ["apply_policy.py", "run_native.py", "test_policy.py", "composer_notes.py", "compose_real.py"])
        self.ledgers([{"lane": "a", "repair_path": "repairs/a"}], [])
        result = MOD.run(self.root)
        self.assertEqual(result["packages"][0]["candidate_entrypoints"], ["repairs/a/compose_real.py"])

    def test_bad_schemas_fail_closed(self) -> None:
        self.write_json("INTEGRATION.json", {"schema": "wrong", "landed": []})
        self.write_json("COMPOSITION.json", {"schema": "wrong", "components": []})
        result = MOD.run(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual({item["code"] for item in result["errors"]}, {"bad_integration_schema", "bad_composition_schema"})


if __name__ == "__main__":
    unittest.main()
