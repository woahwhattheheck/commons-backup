# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
from pathlib import Path
import tarfile
import tempfile
import unittest

import build_candidate


SCHEDULER = """class SellScheduler:\n    def act(self, obs, configuration=None):\n        config = configuration or {}\n        now = int(obs.get('step', 0))\n        targets = {'WHEAT': 1}\n        self.pending = {}\n        self.diagnostics = {}\n        out = {'market': [['SELL', 'WHEAT', 1]]}\n        market = list(out['market'])\n        out['market']=market\n        for item,q in targets.items():\n            sold=sum(o[2] for o in out['market'] if o and o[0]=='SELL' and o[1]==item)\n            self.pending[item]=max(0,q-sold)\n        return out\n\ndef absorption(item, step, shops, config):\n    return 0\n"""

FROZEN = """from scheduler import *\nclass FrozenSelected:\n    def transform(self, obs, config, base):\n        now = int(obs.get('step', 0))\n        targets = {'WHEAT': 1}\n        self.pending = {}\n        self.diagnostics = {}\n        out = {'market': [['SELL', 'WHEAT', 1]]}\n        funding = None\n        if funding is not None:self.diagnostics['same_turn_funding']=funding\n        for item,q in targets.items():\n            sold=sum(o[2] for o in out['market'] if o and o[0]=='SELL' and o[1]==item)\n            self.pending[item]=max(0,q-sold)\n        return out\n"""


class BuilderTests(unittest.TestCase):
    def _archive(self, root: Path, *, unsafe: bool = False) -> Path:
        archive_path = root / "candidate.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            files = {
                "payload/scheduler.py": SCHEDULER,
                "payload/frozen_selected.py": FROZEN,
            }
            if unsafe:
                files["../escape.txt"] = "no"
            for name, content in files.items():
                data = content.encode()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        return archive_path

    def test_builder_inserts_hook_before_pending_accounting(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = self._archive(root)
            output = root / "out"
            manifest = build_candidate.build(
                archive, output, expected_sha256=None, module_dir=Path(__file__).resolve().parent
            )
            for filename in ("scheduler.py", "frozen_selected.py"):
                text = (output / "payload" / filename).read_text()
                self.assertEqual(text.count(build_candidate.MARKER), 1)
                self.assertLess(text.index(build_candidate.MARKER), text.index("for item,q in targets.items():"))
                self.assertEqual(text.count("def _argus_e11_before_pending"), 1)
            self.assertEqual(len(manifest["patched_files"]), 2)
            self.assertTrue((output / "payload" / "ARGUS-G01-BUILD.json").is_file())

    def test_default_hash_gate_rejects_noncanonical_archive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = self._archive(root)
            with self.assertRaisesRegex(ValueError, "archive SHA256 mismatch"):
                build_candidate.build(archive, root / "out", module_dir=Path(__file__).resolve().parent)
            self.assertFalse((root / "out").exists())

    def test_path_traversal_archive_is_rejected_and_output_removed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = self._archive(root, unsafe=True)
            with self.assertRaisesRegex(ValueError, "unsafe archive member"):
                build_candidate.build(
                    archive, root / "out", expected_sha256=None, module_dir=Path(__file__).resolve().parent
                )
            self.assertFalse((root / "out").exists())
            self.assertFalse((root.parent / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
