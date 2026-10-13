# SPDX-License-Identifier: Apache-2.0
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest

HERE = Path(__file__).resolve()
V3 = HERE.parents[2]
if str(V3) not in sys.path:
    sys.path.insert(0, str(V3))

import p07_materialize as p07


RUNTIME = '''from copy import deepcopy
from dataclasses import dataclass

@dataclass(frozen=True)
class Features:
    consumer: str = 'frozen'
    terminal_route: bool = False
    early_capital: bool = False

    def __post_init__(self):
        if not 0 <= self.reserve_seconds < self.budget_seconds <= 1:
            raise ValueError('invalid action deadline')

class TitanAgent:
    def __init__(self):
        self.committed_seed_retry_module = None

    def _initialize(self):
        f = self.features
        self._restore_seller_state()
        self.ready = True

    def _selected_snapshot(self, obs, returned=None):
        return None

    def act(self, obs, cfg):
        try:
            if True:
                selected = self.production.act(obs)
                self.selected = deepcopy(selected)
        except Exception:
            self.ready = False
            # Retain only the route paired with a complete selected fallback.
            raise
'''


def archive_bytes(extra=None):
    files = {
        "main.py": b"def agent(*args): return None\n",
        "titan_runtime.py": RUNTIME.encode(),
        "TITAN-CONFIG.json": b'{"consumer": "frozen"}\n',
        "TITAN-RELEASE.md": b"# release\n",
        "SOURCE.json": json.dumps({"runtime": {}, "default": {}}).encode(),
    }
    files.update(extra or {})
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", filename="", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tf:
            for name, data in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o644
                info.mtime = 0
                tf.addfile(info, io.BytesIO(data))
    return out.getvalue()


class P07MaterializeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p07-materialize-"))
        self.base = self.tmp / "base.tar.gz"
        self.base.write_bytes(archive_bytes())
        self.expected = hashlib.sha256(self.base.read_bytes()).hexdigest()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_disabled_mode_is_byte_exact(self):
        out = self.tmp / "off.tar.gz"
        receipt = p07.materialize(self.base, out, enabled=False, expected_sha256=self.expected)
        self.assertEqual(out.read_bytes(), self.base.read_bytes())
        self.assertTrue(receipt["default_off_byte_identity"])

    def test_enabled_mode_wires_preconsumer_seam_and_metadata(self):
        out = self.tmp / "on.tar.gz"
        tree = self.tmp / "tree"
        receipt = p07.materialize(
            self.base, out, enabled=True, expected_sha256=self.expected, tree=tree
        )
        runtime = (tree / "titan_runtime.py").read_text()
        self.assertIn("joint_actor_assignment: bool = False", runtime)
        self.assertIn("selected = self._joint_actor_selected(obs, cfg, selected)", runtime)
        self.assertLess(
            runtime.index("selected = self._joint_actor_selected"),
            runtime.index("self.selected = deepcopy(selected)"),
        )
        # One reset is in ready=False reconstruction and one in deadline fallback.
        self.assertGreaterEqual(runtime.count("self.joint_actor_assignment.reset()"), 2)
        config = json.loads((tree / "TITAN-CONFIG.json").read_text())
        self.assertIs(config["joint_actor_assignment"], True)
        self.assertTrue((tree / "p07_joint_actor_assignment.py").is_file())
        self.assertTrue((tree / "checks/test_p07_joint_actor_assignment.py").is_file())
        source = json.loads((tree / "SOURCE.json").read_text())
        self.assertTrue(source["p07_candidate"]["enabled"])
        self.assertEqual(receipt["base_archive_sha256"], self.expected)
        self.assertFalse(receipt["default_off_byte_identity"])

    def test_enabled_build_is_deterministic(self):
        one = self.tmp / "one.tar.gz"
        two = self.tmp / "two.tar.gz"
        p07.materialize(self.base, one, enabled=True, expected_sha256=self.expected)
        p07.materialize(self.base, two, enabled=True, expected_sha256=self.expected)
        self.assertEqual(one.read_bytes(), two.read_bytes())

    def test_wrong_base_hash_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            p07.materialize(self.base, self.tmp / "out.tar.gz", enabled=True, expected_sha256="0" * 64)

    def test_anchor_drift_is_rejected(self):
        bad = self.tmp / "bad.tar.gz"
        bad.write_bytes(archive_bytes({"titan_runtime.py": RUNTIME.replace("early_capital", "moved").encode()}))
        expected = hashlib.sha256(bad.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "Features field"):
            p07.materialize(bad, self.tmp / "out.tar.gz", enabled=True, expected_sha256=expected)

    def test_unsafe_tar_member_is_rejected(self):
        unsafe = self.tmp / "unsafe.tar.gz"
        out = io.BytesIO()
        with gzip.GzipFile(fileobj=out, mode="wb", filename="", mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tf:
                for name, data in {
                    "main.py": b"x",
                    "titan_runtime.py": b"x",
                    "TITAN-CONFIG.json": b"{}",
                    "../escape": b"bad",
                }.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tf.addfile(info, io.BytesIO(data))
        unsafe.write_bytes(out.getvalue())
        expected = hashlib.sha256(unsafe.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "unsafe"):
            p07.materialize(unsafe, self.tmp / "out.tar.gz", enabled=True, expected_sha256=expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
