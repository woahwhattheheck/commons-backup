"""Regression coverage for actual export, extraction and lazy candidate loading."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import official
import pack


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kag-pack-test-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "candidate.py").write_text('def agent(obs, cfg=None):\n    return {"farmer": ["PASS"]}\n')
        (self.source / "weights.bin").write_bytes(bytes(range(256)))
        self.spec = self.root / "spec.json"
        self.write_spec()

    def tearDown(self):
        self.temp.cleanup()

    def write_spec(self):
        self.spec.write_text(json.dumps({"schema_version": 1, "label": "fixture",
            "source_callable": "agent", "provenance": {"license": "MIT", "source_ref": "fixture"},
            "files": {name: {"source": str(path.relative_to(self.root)), "sha256": pack.digest(path)}
                      for name, path in {"main.py": self.source / "candidate.py",
                                         "models/weights.bin": self.source / "weights.bin"}.items()}}))

    def test_reproducible_archive_and_exact_binary_assets(self):
        first = pack.build(self.spec, self.root / "one")
        second = pack.build(self.spec, self.root / "two")
        self.assertEqual(first["archive_sha256"], second["archive_sha256"])
        self.assertEqual((self.root / "one/submission.tar.gz").read_bytes(),
                         (self.root / "two/submission.tar.gz").read_bytes())
        destination = self.root / "unpacked"
        pack.verify(self.root / "one", destination)
        self.assertEqual((destination / "main.py").read_bytes(), (self.source / "candidate.py").read_bytes())
        self.assertEqual((destination / "models/weights.bin").read_bytes(), bytes(range(256)))

    def test_changed_source_does_not_build_old_profile(self):
        (self.source / "weights.bin").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Source bytes"):
            pack.build(self.spec, self.root / "bundle")
        self.assertFalse((self.root / "bundle").exists())

    def test_corrupted_archive_is_not_extracted(self):
        pack.build(self.spec, self.root / "bundle")
        archive = self.root / "bundle/submission.tar.gz"
        archive.write_bytes(archive.read_bytes() + b"unexpected")
        with self.assertRaisesRegex(ValueError, "Archive differs"):
            pack.verify(self.root / "bundle", self.root / "unpacked")
        self.assertFalse((self.root / "unpacked").exists())

    def test_changed_candidate_receipt_is_rejected(self):
        pack.build(self.spec, self.root / "bundle")
        path = self.root / "bundle/receipt.json"
        receipt = json.loads(path.read_text())
        receipt["candidate_sha256"] = "0" * 64
        path.write_bytes(pack.canonical(receipt))
        with self.assertRaisesRegex(ValueError, "Candidate differs"):
            pack.verify(self.root / "bundle")

    def test_archive_names_stay_relative_and_existing_outputs_survive(self):
        for name in ("../main.py", "/main.py", "a/../main.py", "a//main.py"):
            with self.assertRaises(ValueError):
                pack.member_name(name)
        pack.build(self.spec, self.root / "bundle")
        original = (self.root / "bundle/submission.tar.gz").read_bytes()
        with self.assertRaises(FileExistsError):
            pack.build(self.spec, self.root / "bundle")
        self.assertEqual(original, (self.root / "bundle/submission.tar.gz").read_bytes())


class OfficialLoadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kag-loader-test-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        sys.modules.pop("kag_pack_fixture_helper", None)
        self.temp.cleanup()

    def write_agent(self, text):
        path = self.root / "main.py"
        path.write_text(text)
        return path

    def test_last_callable_is_selected_instead_of_named_agent(self):
        path = self.write_agent('def agent(o, c):\n    return {"selected": "agent"}\n'
                                'def helper():\n    return {"selected": "last"}\n')
        self.assertEqual(official.make_agent(path)({}, {}), {"selected": "last"})

    def test_one_argument_agent_preserves_state_between_calls(self):
        path = self.write_agent('count = 0\ndef agent(o):\n    global count\n'
                                '    count += 1\n    return {"count": count, "step": o.step}\n')
        function = official.make_agent(path)
        self.assertEqual(function({"step": 0}, {}), {"count": 1, "step": 0})
        self.assertEqual(function({"step": 1}, {}), {"count": 2, "step": 1})

    def test_sidecar_import_and_official_raw_path(self):
        (self.root / "kag_pack_fixture_helper.py").write_text("VALUE = 37\n")
        path = self.write_agent('from kag_pack_fixture_helper import VALUE\n'
            'def agent(o, c):\n    return {"value": VALUE, "path": c["__raw_path__"]}\n')
        configuration = {"seed": None}
        self.assertEqual(official.make_agent(path)({}, configuration),
                         {"value": 37, "path": str(path)})
        self.assertEqual(configuration, {"seed": None})

    def test_initialization_is_inside_first_action_deadline(self):
        path = self.write_agent('import time\ntime.sleep(0.25)\n'
                                'def agent(o, c):\n    return {"farmer": ["PASS"]}\n')
        adapter = self.root / "adapter.py"
        pack.write_adapter(adapter, path)
        ev = pack.load_evaluator()
        original = ev.Actor(str(path), self.root, ev.LOADER, 20260907)
        try:
            self.assertEqual(original.ready["kind"], "ready")
            self.assertEqual(original.act({}, {}, 1)["kind"], "action")
        finally:
            original.close()
        exported = ev.Actor(str(adapter), self.root, ev.LOADER, 20260907)
        try:
            self.assertEqual(exported.ready["kind"], "ready")
            self.assertEqual(exported.act({}, {}, 0.05)["kind"], "timeout")
        finally:
            exported.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
