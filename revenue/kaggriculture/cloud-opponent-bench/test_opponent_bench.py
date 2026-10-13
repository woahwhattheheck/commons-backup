"""Focused integrity tests; full official-engine games run in the workflow."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load("prepare")
benchmark = load("benchmark")


class PrepareTests(unittest.TestCase):
    def fixture(self, key, assignment, agent=b"def agent(obs, cfg=None): return {}\n"):
        import base64, zlib
        packed = base64.b85encode(zlib.compress(agent)).decode()
        cell = f"{assignment} = {packed!r}\n"
        notebook = json.dumps({"cells": [{"cell_type": "code", "source": cell}]})
        expected = dict(prepare.SOURCES[key])
        expected.update(notebook_sha256=hashlib.sha256(notebook.encode()).hexdigest(),
                        agent_sha256=hashlib.sha256(agent).hexdigest(), agent_bytes=len(agent))
        return {"metadata": {"ref": expected["ref"], "currentVersionNumber": expected["version_number"]},
                "blob": {"sourceNullable": notebook}}, expected

    def test_extracts_without_executing_notebook(self):
        with tempfile.TemporaryDirectory() as root:
            pull, expected = self.fixture("kaito_v43", "payload")
            path = Path(root) / "pull.json"
            path.write_text(json.dumps(pull))
            original = prepare.SOURCES["kaito_v43"]
            prepare.SOURCES["kaito_v43"] = expected
            try:
                agent, receipt = prepare.extract(path, "kaito_v43")
            finally:
                prepare.SOURCES["kaito_v43"] = original
            self.assertIn(b"def agent", agent)
            self.assertEqual(receipt["agent_sha256"], expected["agent_sha256"])

    def test_rejects_changed_notebook(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "pull.json"
            path.write_text(json.dumps({"metadata": {"ref": prepare.SOURCES["kaito_v43"]["ref"],
                                                       "currentVersionNumber": 13},
                                        "blob": {"sourceNullable": "{}"}}))
            with self.assertRaisesRegex(ValueError, "notebook bytes changed"):
                prepare.extract(path, "kaito_v43")

    def test_literal_only(self):
        with self.assertRaises((ValueError, TypeError)):
            prepare.literal_assignment("payload = dangerous()", "payload")


class BenchmarkTests(unittest.TestCase):
    def test_phases_are_disjoint_and_unique(self):
        self.assertFalse(set(benchmark.SEEDS["development"]) & set(benchmark.SEEDS["validation"]))
        for values in benchmark.SEEDS.values():
            self.assertEqual(len(values), len(set(values)))

    def test_command_rotates_public_panel_via_existing_evaluator(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            agents = {}
            for key, source in (("kaito_v43", b"a"), ("igor_multiroute", b"b")):
                (root / f"{key}.py").write_bytes(source)
                agents[key] = {"agent_sha256": hashlib.sha256(source).hexdigest()}
            (root / "manifest.json").write_text(json.dumps({"agents": agents}))
            cmd = benchmark.command(Path("engine"), root, Path("candidate.py"), "development", Path("out.json"))
            self.assertEqual(Path(cmd[2]).resolve(), benchmark.EVALUATOR)
            self.assertEqual(cmd.count("--opponent"), 2)
            self.assertIn("9000011,9000049,9000061", cmd)


if __name__ == "__main__":
    unittest.main(verbosity=2)
