#!/usr/bin/env python3

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("path_manifest", ROOT / "host" / "path_manifest.py")
path_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(path_manifest)


class PathManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = path_manifest.load_manifest(ROOT / "architecture" / "path-manifest.json")
        cls.classifier = path_manifest.PathClassifier(cls.manifest)

    def test_manifest_is_descriptive(self):
        self.assertEqual(self.manifest["participation_effect"], "NONE")
        self.assertEqual(self.manifest["fallback"]["classification"], "UNMAPPED")

    def test_known_paths_share_one_classifier(self):
        expected = {
            "p/example-record.md": "CANONICAL_SOURCE",
            "p/example-record.html": "DERIVED_PROJECTION",
            "by/~ZXhhbXBsZQ.html": "DERIVED_PROJECTION",
            "projection/converged/v1/digest.json": "DERIVED_PROJECTION",
            "revenue/outcome_commerce/catalog.json": "SCHEMA_AND_CATALOG",
            "orchestration/jeffersonville/topology.json": "SCHEMA_AND_CATALOG",
            "host/titan_hands_windows/server.py": "EXECUTABLE_SOURCE",
            "muhl/containers/example.mno": "CORPUS_PAYLOAD",
            "commerce.html": "PUBLIC_SURFACE",
            "orchestration.html": "PUBLIC_SURFACE",
            "architecture/path-manifest.json": "SCHEMA_AND_CATALOG",
            "architecture/path-manifest.schema.json": "SCHEMA_AND_CATALOG",
            "architecture/PATHS.md": "PROCEDURE_SOURCE",
        }
        for path, classification in expected.items():
            with self.subTest(path=path):
                self.assertEqual(self.classifier.classify(path)["classification"], classification)

    def test_typed_files_precede_broad_subsystem_prefixes(self):
        expected = {
            "revenue/dio/substrate_receipt.py": ("EXECUTABLE_SOURCE", "code"),
            "revenue/dio/test_receipt.py": ("EXECUTABLE_SOURCE", "tests"),
            "revenue/dio/status.html": ("PUBLIC_SURFACE", "web"),
            "orchestration/jeffersonville/probe.py": ("EXECUTABLE_SOURCE", "code"),
            "orchestration/jeffersonville/test_probe.py": ("EXECUTABLE_SOURCE", "tests"),
            "orchestration/jeffersonville/status.html": ("PUBLIC_SURFACE", "web"),
            "muhl/tools/inspect.py": ("EXECUTABLE_SOURCE", "code"),
            "muhl/tools/test_inspect.py": ("EXECUTABLE_SOURCE", "tests"),
            "muhl/public/index.html": ("PUBLIC_SURFACE", "web"),
            "host/titan_hands/register_codex.ps1": ("EXECUTABLE_SOURCE", "code"),
        }
        for path, (classification, subsystem) in expected.items():
            with self.subTest(path=path):
                row = self.classifier.classify(path)
                self.assertEqual(row["classification"], classification)
                self.assertEqual(row["subsystem"], subsystem)

    def test_unknown_path_is_visible_not_silent(self):
        row = self.classifier.classify("novel-format.payload")
        self.assertEqual(row["classification"], "UNMAPPED")
        self.assertIn("VISIBLE_DIAGNOSTIC", row["flags"])

    def test_glob_double_star_observes_root_and_nested(self):
        self.assertEqual(self.classifier.classify("sample.py")["classification"], "EXECUTABLE_SOURCE")
        self.assertEqual(self.classifier.classify("new/area/sample.py")["classification"], "EXECUTABLE_SOURCE")
        self.assertEqual(
            self.classifier.classify(".github/workflows/tests.yml")["subsystem"],
            "ci",
        )

    def test_report_is_deterministic_and_counts_tests(self):
        paths = ["test_alpha.py", "nested/test_beta.js", "p/one.md", "new.payload"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "board_ingest.py").write_text("ASSET_PATHS = ['p', 'recent.json']\n", encoding="utf-8")
            first = path_manifest.build_report(root, self.manifest, paths=paths)
            second = path_manifest.build_report(root, self.manifest, paths=reversed(paths))
        self.assertEqual(first, second)
        self.assertEqual(first["tests"]["root_count"], 1)
        self.assertEqual(first["tests"]["nested_count"], 1)
        self.assertEqual(first["unmapped_paths"], ["new.payload"])
        self.assertEqual(first["generator_contracts"][0]["declared_count"], 2)
        self.assertEqual(first["generator_unmapped_count"], 0)

    def test_mixed_staging_contract_classifies_directories_and_missing_literals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "board_ingest.py").write_text(
                "ASSET_PATHS = ['p', 'builds', 'panel.json', 'recent.json']\n",
                encoding="utf-8",
            )
            report = path_manifest.build_report(
                root,
                self.manifest,
                paths=["p/one.md", "builds/records/receipt.json", "recent.json"],
            )
        contract = report["generator_contracts"][0]
        targets = {row["path"]: row for row in contract["targets"]}
        self.assertEqual(contract["path_semantics"], "MIXED_STAGING_AND_GENERATED")
        self.assertEqual(targets["p"]["target_kind"], "TRACKED_DIRECTORY")
        self.assertEqual(targets["p"]["classification_path"], "p/one.md")
        self.assertEqual(targets["p"]["classification"], "CANONICAL_SOURCE")
        self.assertEqual(targets["builds"]["target_kind"], "TRACKED_DIRECTORY")
        self.assertEqual(targets["builds"]["classification"], "IMMUTABLE_EVIDENCE")
        self.assertEqual(targets["panel.json"]["target_kind"], "MISSING_PATH")
        self.assertEqual(targets["panel.json"]["classification_path"], "panel.json")
        self.assertEqual(targets["panel.json"]["classification"], "SCHEMA_AND_CATALOG")
        self.assertEqual(contract["missing_tracked_targets"], ["panel.json"])
        self.assertEqual(report["generator_unmapped_count"], 0)
        self.assertEqual(report["generator_unmapped_targets"], [])

    def test_mixed_staging_contract_reports_unmapped_declarations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "board_ingest.py").write_text("ASSET_PATHS = ['novel.payload']\n", encoding="utf-8")
            report = path_manifest.build_report(root, self.manifest, paths=[])
        self.assertEqual(report["generator_unmapped_count"], 1)
        self.assertEqual(
            report["generator_unmapped_targets"],
            [{"contract_id": "board-staging-and-projection-assets", "path": "novel.payload"}],
        )
        self.assertEqual(report["generator_contracts"][0]["unmapped_targets"], ["novel.payload"])
        summary = path_manifest.markdown_summary(report)
        self.assertIn("Mixed staging/generator targets unmapped: **1**", summary)
        self.assertIn("Unmapped declarations: `novel.payload`", summary)

    def test_schema_and_manifest_are_valid_json(self):
        schema = json.loads((ROOT / "architecture" / "path-manifest.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["participation_effect"]["const"], "NONE")
        self.assertIn("$schema", schema["properties"])
        self.assertTrue(set(self.manifest).issubset(schema["properties"]))
        self.assertTrue(set(schema["required"]).issubset(self.manifest))
        self.assertEqual(path_manifest.manifest_digest(self.manifest), path_manifest.manifest_digest(dict(self.manifest)))


if __name__ == "__main__":
    unittest.main()
