# SPDX-License-Identifier: Apache-2.0
"""Regression checks for the canonical evaluator's self-contained default layout."""
from contextlib import contextmanager
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

import build_integrated as build


@contextmanager
def rendered_tree():
    """Materialize the deterministic in-memory release without publishing it."""
    data, _, _ = build.render()
    with tempfile.TemporaryDirectory(prefix="titan-evaluator-defaults-") as temp:
        root = Path(temp)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                target = root / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
        yield root


def import_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot import %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class EvaluatorDefaultPackagingTests(unittest.TestCase):
    def test_default_evaluator_dependencies_are_packaged(self):
        mapping = build.source_files()
        expected = {
            "checks/reference/evaluator/evaluate.py": "reference/evaluator/evaluate.py",
            "checks/reference/evaluator/loader.py": "reference/evaluator/loader.py",
            "checks/reference/evaluator/official_agent.py": "reference/evaluator/official_agent.py",
            "checks/reference/evaluator/opponents.py": "reference/evaluator/opponents.py",
            "checks/reference/20260907-offline-agent/evaluate.py": "reference/evaluator/loader.py",
            "checks/reference/20260907-offline-agent/main.py": "../20260907-offline-agent/main.py",
        }
        for packaged, source in expected.items():
            with self.subTest(packaged=packaged):
                self.assertEqual(mapping.get(packaged), source)
                self.assertTrue((build.ROOT / source).is_file())

    def test_historical_loader_alias_is_exact(self):
        mapping = build.source_files()
        loader = build.ROOT / mapping["checks/reference/evaluator/loader.py"]
        loader_alias = build.ROOT / mapping["checks/reference/20260907-offline-agent/evaluate.py"]
        historical_loader = build.ROOT / "../20260907-offline-agent/evaluate.py"
        self.assertEqual(loader.read_bytes(), historical_loader.read_bytes())
        self.assertEqual(loader_alias.read_bytes(), historical_loader.read_bytes())

    def test_historical_candidate_contract_is_packaged_and_executable(self):
        with rendered_tree() as root:
            candidate = import_path(
                root / "checks/reference/20260907-offline-agent/main.py",
                "packaged_historical_candidate",
            )
            self.assertIsInstance(candidate.POLICY, dict)
            self.assertTrue(callable(candidate.agent))
            self.assertEqual(candidate.POLICY["animal_cap"], 28)
            self.assertTrue(candidate.POLICY["expansion"])

            evaluator = import_path(
                root / "checks/reference/evaluator/evaluate.py",
                "packaged_official_evaluator",
            )
            self.assertTrue(evaluator.LOADER.is_file())
            self.assertTrue(evaluator.LOADER.with_name("main.py").is_file())

    def test_compact_default_executes_through_packaged_relative_candidate(self):
        with rendered_tree() as root:
            opponents = import_path(
                root / "checks/reference/evaluator/opponents.py",
                "packaged_default_opponents",
            )
            action = opponents.compact_no_expansion({"farms": []})
            self.assertEqual(action, {"farmer": ["PASS"], "hands": [], "market": []})
            self.assertEqual(opponents._COMPACT.POLICY["animal_cap"], 22)
            self.assertEqual(opponents._COMPACT.POLICY["max_hands"], 9)
            self.assertFalse(opponents._COMPACT.POLICY["expansion"])

    def test_packaged_paths_satisfy_existing_evaluator_defaults(self):
        source = (build.ROOT / "reference/evaluator/evaluate.py").read_text(encoding="utf-8")
        opponents = (build.ROOT / "reference/evaluator/opponents.py").read_text(encoding="utf-8")
        self.assertIn('HERE.parent / "20260907-offline-agent" / "evaluate.py"', source)
        self.assertIn("HERE / 'opponents.py'", source)
        self.assertIn('parent.parent / "20260907-offline-agent" / "main.py"', opponents)
        mapping = build.source_files()
        self.assertIn("checks/reference/evaluator/opponents.py", mapping)
        self.assertIn("checks/reference/20260907-offline-agent/evaluate.py", mapping)
        self.assertIn("checks/reference/20260907-offline-agent/main.py", mapping)


if __name__ == "__main__":
    unittest.main()
