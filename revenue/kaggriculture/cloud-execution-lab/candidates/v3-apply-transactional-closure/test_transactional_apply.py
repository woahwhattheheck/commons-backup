# SPDX-License-Identifier: Apache-2.0
"""Predecessor-killing contracts for the V3 apply transaction.

Run from this directory:

    python -m unittest -v test_transactional_apply.py
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import warnings

import apply_v3 as repaired
import upstream_apply_v3 as upstream

UPSTREAM_SHA256 = "8e1093429a1bb463e2b82490963b43d9c9a4fcbd16f9d1b8d02fd75434f84436"


RUNTIME = """from dataclasses import dataclass
import time

@dataclass
class Features:
    enabled: bool = False

    def __post_init__(self):
        pass

class TitanAgent:
    def _initialize(self):
        self._restore_seller_state()
        self.ready = True

    def act(self, observation, configuration=None):
        cfg = dict(configuration or {})
        obs = dict(observation)
        seller_checkpoint = None
        started = cpu_started = 0
        output = {}
        self._commit_seller_state(seller_checkpoint)
        self.diagnostics.update(status='completed', elapsed_seconds=time.perf_counter()-started,
                                act_cpu_seconds=time.process_time()-cpu_started)
        output = self._finish_production(obs, output, cfg)
        return output

    __call__ = act
"""

SCHEDULER = """class SellScheduler:
    def act(self, obs, config=None):
        now = 0
        out = {}
        market = []
        targets = {}
        out['market']=market
        for item,q in targets.items():
            pass
        return out
"""

FROZEN = """class FrozenSelected:
    def transform(self, obs, config=None):
        now = 0
        out = {}
        targets = {}
        funding = None
        if funding is not None:self.diagnostics['same_turn_funding']=funding
        for item,q in targets.items():
            pass
        return out
"""

BROKEN_FROZEN = FROZEN.replace("        for item,q in targets.items():\n", "        for product,quantity in targets.items():\n")


class Fixture:
    def __init__(self, root: Path, *, frozen: str = FROZEN, config=None):
        self.root = root
        root.mkdir(parents=True)
        values = {
            "titan_runtime.py": RUNTIME,
            "scheduler.py": SCHEDULER,
            "frozen_selected.py": frozen,
            "TITAN-CONFIG.json": json.dumps(config if config is not None else {"consumer": "frozen"}) + "\n",
            "TITAN-RELEASE.md": "# Canonical release\n",
        }
        for offset, (name, value) in enumerate(values.items()):
            path = root / name
            path.write_text(value, encoding="utf-8", newline="")
            path.chmod(0o640 + (offset % 2) * 0o004)

    def snapshot(self):
        return {
            name: ((self.root / name).read_bytes(), stat.S_IMODE((self.root / name).stat().st_mode))
            for name in repaired.TARGET_FILES
        }

    def residues(self):
        return sorted(path.name for path in self.root.iterdir() if ".v3-stage-" in path.name or ".v3-backup-" in path.name)


class SourceBindingTests(unittest.TestCase):
    def test_authenticated_upstream_copy_is_exact(self):
        path = Path(upstream.__file__)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), UPSTREAM_SHA256)

    def test_repair_keeps_the_same_policy_constants(self):
        self.assertEqual(repaired.PARAMS, upstream.PARAMS)
        self.assertEqual(repaired.FIELDS, upstream.FIELDS)
        self.assertEqual(repaired.RUNTIME_METHODS, upstream.RUNTIME_METHODS)
        self.assertEqual(repaired.SELLER_METHOD, upstream.SELLER_METHOD)
        self.assertEqual(repaired.RELEASE_NOTE, upstream.RELEASE_NOTE)

    def test_source_manifest_closes(self):
        root = Path(__file__).resolve().parent
        manifest = json.loads((root / "SOURCE.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_packet_sha256"],
                         "f68792bf7f0fb269864ef4ab25967292e2d4cd03439dbc5c52b98dfcebd1b728")
        for name, expected in manifest["files"].items():
            payload = (root / name).read_bytes()
            self.assertEqual(len(payload), expected["bytes"], name)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), expected["sha256"], name)


class PredecessorTests(unittest.TestCase):
    def test_legacy_late_anchor_failure_leaves_half_integrated_tree(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(Path(td) / "package", frozen=BROKEN_FROZEN)
            before = fixture.snapshot()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                with self.assertRaisesRegex(AssertionError, "frozen pre-pending seam"):
                    upstream.apply(str(fixture.root))
            after = fixture.snapshot()
            self.assertNotEqual(after["titan_runtime.py"], before["titan_runtime.py"])
            self.assertNotEqual(after["scheduler.py"], before["scheduler.py"])
            for name in ("frozen_selected.py", "TITAN-CONFIG.json", "TITAN-RELEASE.md"):
                self.assertEqual(after[name], before[name])

    def test_repair_late_anchor_failure_is_exact_identity(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(Path(td) / "package", frozen=BROKEN_FROZEN)
            before = fixture.snapshot()
            with self.assertRaisesRegex(AssertionError, "frozen pre-pending seam"):
                repaired.apply(str(fixture.root))
            self.assertEqual(fixture.snapshot(), before)
            self.assertEqual(fixture.residues(), [])

    def test_repair_late_config_collision_is_exact_identity(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(Path(td) / "package", config={"consumer": "frozen", "e11_rival_sell": False})
            before = fixture.snapshot()
            with self.assertRaisesRegex(AssertionError, "e11_rival_sell"):
                repaired.apply(str(fixture.root))
            self.assertEqual(fixture.snapshot(), before)
            self.assertEqual(fixture.residues(), [])


class CommitTests(unittest.TestCase):
    def test_success_closes_all_five_files_and_preserves_modes(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(Path(td) / "package")
            before = fixture.snapshot()
            self.assertEqual(repaired.apply(str(fixture.root)), str(fixture.root))
            after = fixture.snapshot()
            self.assertTrue(all(after[name][0] != before[name][0] for name in repaired.TARGET_FILES))
            self.assertEqual({name: pair[1] for name, pair in after.items()},
                             {name: pair[1] for name, pair in before.items()})
            ast.parse((fixture.root / "titan_runtime.py").read_text(encoding="utf-8"))
            ast.parse((fixture.root / "scheduler.py").read_text(encoding="utf-8"))
            ast.parse((fixture.root / "frozen_selected.py").read_text(encoding="utf-8"))
            cfg = json.loads((fixture.root / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
            for key in ("e11_rival_sell", "rival_model", "e20_hire_guard") + repaired.L01_KEYS:
                self.assertIs(cfg[key], False)
            for key, value in repaired.PARAMS.items():
                self.assertEqual(cfg[key], value)
            release = (fixture.root / "TITAN-RELEASE.md").read_text(encoding="utf-8")
            self.assertEqual(release.count("## V3 integration lanes (candidates/v3)"), 1)
            self.assertEqual(fixture.residues(), [])

    def test_one_shot_baseexception_mid_commit_rolls_back_exact_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(Path(td) / "package")
            before = fixture.snapshot()
            real_replace = os.replace
            calls = []

            def fail_third(source, target):
                calls.append((source, target))
                if len(calls) == 3:
                    raise KeyboardInterrupt("injected replacement interruption")
                return real_replace(source, target)

            with mock.patch.object(repaired.os, "replace", side_effect=fail_third):
                with self.assertRaisesRegex(KeyboardInterrupt, "injected replacement interruption"):
                    repaired.apply(str(fixture.root))
            self.assertGreaterEqual(len(calls), 5)  # three commit attempts plus two restores
            self.assertEqual(fixture.snapshot(), before)
            self.assertEqual(fixture.residues(), [])

    def test_stage_failure_before_first_replace_leaves_exact_identity(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(Path(td) / "package")
            before = fixture.snapshot()
            real_fsync = os.fsync
            calls = []

            def fail_third(fd):
                calls.append(fd)
                if len(calls) == 3:
                    raise OSError("injected staging failure")
                return real_fsync(fd)

            with mock.patch.object(repaired.os, "fsync", side_effect=fail_third):
                with self.assertRaisesRegex(OSError, "injected staging failure"):
                    repaired.apply(str(fixture.root))
            self.assertEqual(fixture.snapshot(), before)
            self.assertEqual(fixture.residues(), [])

    def test_second_application_fails_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(Path(td) / "package")
            repaired.apply(str(fixture.root))
            once = fixture.snapshot()
            with self.assertRaises(AssertionError):
                repaired.apply(str(fixture.root))
            self.assertEqual(fixture.snapshot(), once)
            self.assertEqual(fixture.residues(), [])

    def test_missing_target_fails_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(Path(td) / "package")
            (fixture.root / "TITAN-RELEASE.md").unlink()
            before = {p.name: p.read_bytes() for p in fixture.root.iterdir()}
            with self.assertRaises(FileNotFoundError):
                repaired.apply(str(fixture.root))
            after = {p.name: p.read_bytes() for p in fixture.root.iterdir()}
            self.assertEqual(after, before)
            self.assertEqual(fixture.residues(), [])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_target_is_rejected_without_touching_referent(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(Path(td) / "package")
            release = fixture.root / "TITAN-RELEASE.md"
            external = Path(td) / "external.md"
            external.write_bytes(release.read_bytes())
            release.unlink()
            release.symlink_to(external)
            before = {name: (fixture.root / name).read_bytes() for name in repaired.TARGET_FILES}
            external_before = external.read_bytes()
            with self.assertRaisesRegex(ValueError, "TITAN-RELEASE.md: expected a regular file"):
                repaired.apply(str(fixture.root))
            self.assertEqual({name: (fixture.root / name).read_bytes() for name in repaired.TARGET_FILES}, before)
            self.assertEqual(external.read_bytes(), external_before)
            self.assertEqual(fixture.residues(), [])

    def test_invalid_utf8_fails_before_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            fixture = Fixture(Path(td) / "package")
            path = fixture.root / "TITAN-RELEASE.md"
            path.write_bytes(b"\xff\xfe")
            before = fixture.snapshot()
            with self.assertRaisesRegex(ValueError, "TITAN-RELEASE.md: expected UTF-8 source"):
                repaired.apply(str(fixture.root))
            self.assertEqual(fixture.snapshot(), before)
            self.assertEqual(fixture.residues(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
