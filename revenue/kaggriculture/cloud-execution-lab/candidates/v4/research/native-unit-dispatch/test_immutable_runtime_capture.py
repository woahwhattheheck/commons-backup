# SPDX-License-Identifier: Apache-2.0
"""Regression tests for KINETIC immutable validated/executed runtime custody."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_kinetic_games as k


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class ImmutableRuntimeCapture(unittest.TestCase):
    def fixture(self, root: Path):
        files = {
            'mechanics.py': b'BASE = 1\n',
            'main.py': b'VALUE = "main"\n',
            'checks/reference/evaluator/loader.py': b'VALUE = "loader"\n',
            'checks/reference/engine/kaggriculture.py': b'VALUE = "engine"\n',
            'checks/reference/engine/kaggriculture.json': b'{"name":"engine"}\n',
            'checks/reference/engine/utils.py': b'VALUE = "utils"\n',
        }
        for name, raw in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        manifest = {'runtime': {name: {'sha256': _sha(raw)} for name, raw in files.items()}}
        manifest_raw = (json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n').encode()
        (root / 'SOURCE.json').write_bytes(manifest_raw)
        engine_pins = {name: k.git_blob(files[name]) for name in k.ENGINE_GIT_BLOBS}
        return manifest_raw, files, engine_pins

    def control_fixture(self, root: Path):
        source_root = Path(k.__file__).resolve().parent
        files = {name: (source_root / name).read_bytes() for name in k.CONTROL_FILES}
        for name, raw in files.items():
            (root / name).write_bytes(raw)
        return files

    def patches(self, manifest_raw, files, engine_pins):
        return patch.multiple(
            k,
            SOURCE_SHA256=_sha(manifest_raw),
            ENGINE_GIT_BLOBS=engine_pins,
        ), patch.object(k, 'BASE_MECHANICS_BLOB', k.git_blob(files['mechanics.py']))

    def probe_args(self, root: Path, output: Path, expected_runner: str, digest: str):
        return [
            '--native-root', str(root / 'unused-native-root'),
            '--output', str(output),
            '--expected-runner-git-blob', expected_runner,
            '--control-probe',
            '--expected-control-bundle-sha256', digest,
        ]

    def test_path_replacement_after_capture_cannot_change_materialized_transport_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'root'; root.mkdir()
            manifest_raw, files, engine_pins = self.fixture(root)
            outer, base = self.patches(manifest_raw, files, engine_pins)
            with outer, base:
                captured_manifest, captured = k.capture_runtime(root)
                (root / 'main.py').write_bytes(b'VALUE = "reopened"\n')
                (root / 'mechanics.py').write_bytes(b'MUTATED = True\n')
                frozen = Path(d) / 'frozen'
                k.materialize_runtime(frozen, captured_manifest, captured)
            self.assertEqual(files['main.py'], (frozen / 'main.py').read_bytes())
            self.assertEqual(files['mechanics.py'], (frozen / 'mechanics.py').read_bytes())
            self.assertEqual(manifest_raw, (frozen / 'SOURCE.json').read_bytes())

    def test_post_capture_runtime_path_mutation_cannot_change_executed_code_or_data(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            marker = root / 'attacker-executed'
            captured = {
                'entry.py': (
                    'from pathlib import Path\n'
                    'import helper\n'
                    'VALUE = helper.VALUE + "|" + '
                    'Path(__file__).with_name("payload.txt").read_text()\n'
                ).encode(),
                'helper.py': b'VALUE = "captured-helper"\n',
                'payload.txt': b'captured-data',
            }
            for name, raw in captured.items():
                (root / name).write_bytes(raw)

            # Source-real predecessor: after a valid capture, mutate every path
            # that the old child would later reopen. Memory authority must make
            # all three attacker replacements irrelevant to execution.
            (root / 'entry.py').write_text(
                'from pathlib import Path\n'
                f'Path({str(marker)!r}).write_text("ENTRY")\n'
                'raise RuntimeError("mutated entry executed")\n'
            )
            (root / 'helper.py').write_text(
                'from pathlib import Path\n'
                f'Path({str(marker)!r}).write_text("HELPER")\n'
                'VALUE = "mutated-helper"\n'
            )
            (root / 'payload.txt').write_text('mutated-data')

            sys.modules.pop('helper', None)
            sys.modules.pop('kinetic_runtime_fixture', None)
            try:
                with k._captured_runtime_authority(captured):
                    module = k._load_captured_module(
                        'kinetic_runtime_fixture', 'entry.py', captured
                    )
                self.assertEqual(module.VALUE, 'captured-helper|captured-data')
                self.assertFalse(marker.exists())
            finally:
                sys.modules.pop('helper', None)
                sys.modules.pop('kinetic_runtime_fixture', None)

    def test_candidate_mechanics_override_is_exact_and_only_for_mechanics(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); manifest_raw, files, engine_pins = self.fixture(root)
            candidate = b'CANDIDATE = 1\n'
            (root / 'mechanics.py').write_bytes(candidate)
            outer, base = self.patches(manifest_raw, files, engine_pins)
            with outer, base:
                captured_manifest, captured = k.capture_runtime(root, _sha(candidate))
                self.assertEqual(candidate, captured['mechanics.py'])
                self.assertEqual(manifest_raw, captured_manifest)
                with self.assertRaisesRegex(ValueError, 'mechanics.py'):
                    k.capture_runtime(root, _sha(b'wrong'))
                (root / 'main.py').write_bytes(b'DRIFT = 1\n')
                with self.assertRaisesRegex(ValueError, 'main.py'):
                    k.capture_runtime(root, _sha(candidate))

    def test_manifest_drift_fails_before_runtime_authority(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); manifest_raw, files, engine_pins = self.fixture(root)
            outer, base = self.patches(manifest_raw, files, engine_pins)
            with outer, base:
                (root / 'SOURCE.json').write_text('{}\n')
                with self.assertRaisesRegex(ValueError, 'SOURCE manifest'):
                    k.capture_runtime(root)

    def test_unsafe_runtime_member_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manifest = {'runtime': {'../escape.py': {'sha256': _sha(b'x')}}}
            raw = (json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n').encode()
            (root / 'SOURCE.json').write_bytes(raw)
            with patch.object(k, 'SOURCE_SHA256', _sha(raw)):
                with self.assertRaisesRegex(ValueError, 'Unsafe runtime member'):
                    k.capture_runtime(root)

    def test_symlinked_runtime_member_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'root'; root.mkdir()
            manifest_raw, files, engine_pins = self.fixture(root)
            outside = Path(d) / 'outside.py'; outside.write_bytes(files['main.py'])
            (root / 'main.py').unlink(); (root / 'main.py').symlink_to(outside)
            outer, base = self.patches(manifest_raw, files, engine_pins)
            with outer, base:
                with self.assertRaisesRegex(ValueError, 'Unsafe runtime input: main.py'):
                    k.capture_runtime(root)

    def test_captured_runner_survives_repo_and_decoy_scratch_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            mutable = base / 'mutable-control'; mutable.mkdir()
            original = self.control_fixture(mutable)
            expected_runner = k.git_blob(original['run_kinetic_games.py'])
            captured, digest = k.capture_control_bundle(mutable, expected_runner)
            self.assertEqual(original, captured)

            (mutable / 'run_kinetic_games.py').write_text(
                'raise SystemExit("MUTATED REPO RUNNER EXECUTED")\n'
            )
            marker = base / 'scratch-runner-executed'
            decoy = base / 'scratch-control' / 'run_kinetic_games.py'
            decoy.parent.mkdir()
            decoy.write_text(
                'from pathlib import Path\n'
                f'Path({str(marker)!r}).write_text("EXECUTED")\n'
                'raise SystemExit("MUTATED SCRATCH RUNNER EXECUTED")\n'
            )
            output = base / 'probe.json'
            proc = k.run_captured_runner(
                captured['run_kinetic_games.py'],
                expected_runner,
                self.probe_args(base, output, expected_runner, digest),
                timeout=20,
            )
            stderr = proc.stderr.decode('utf-8', errors='replace')
            self.assertEqual(proc.returncode, 0, stderr)
            receipt = json.loads(output.read_text())
            self.assertEqual(receipt['executed_control_bundle_sha256'], digest)
            self.assertEqual(receipt['executed_control_runner_blob'], expected_runner)
            self.assertIs(receipt['runner_executed_from_captured_bytes'], True)
            self.assertFalse(marker.exists(), stderr)
            with self.assertRaisesRegex(ValueError, 'Captured runner bytes do not match external identity'):
                k.run_captured_runner(
                    (mutable / 'run_kinetic_games.py').read_bytes(),
                    expected_runner,
                    self.probe_args(base, output, expected_runner, digest),
                    timeout=20,
                )

    def test_external_runner_pin_rejects_pre_capture_repo_runner_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            original = self.control_fixture(root)
            expected_runner = k.git_blob(original['run_kinetic_games.py'])
            (root / 'run_kinetic_games.py').write_text(
                '# valid but poisoned replacement\nraise SystemExit("POISONED")\n'
            )
            with self.assertRaisesRegex(ValueError, 'Unverified control runner'):
                k.capture_control_bundle(root, expected_runner)
            with self.assertRaisesRegex(ValueError, 'Invalid expected runner Git blob'):
                k.capture_control_bundle(root, 'not-an-external-pin')

    def test_control_helper_drift_fails_closed_before_parent_use(self):
        for name in ('compose_kinetic.py', 'check_kinetic.py'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                original = self.control_fixture(root)
                expected_runner = k.git_blob(original['run_kinetic_games.py'])
                (root / name).write_bytes(b'DRIFT = True\n')
                with self.assertRaisesRegex(ValueError, f'Unverified control input: {name}'):
                    k.capture_control_bundle(root, expected_runner)

    def test_unverified_composer_cannot_execute_before_authentication(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            original = self.control_fixture(root)
            expected_runner = k.git_blob(original['run_kinetic_games.py'])
            marker = root / 'composer-executed'
            (root / 'compose_kinetic.py').write_text(
                'from pathlib import Path\n'
                f'Path({str(marker)!r}).write_text("EXECUTED")\n'
                f'BASE_BLOB = {k.BASE_MECHANICS_BLOB!r}\n'
                'def git_blob(raw): return "d34362e98277c930b7b28519f2892bea758b3878"\n'
                'def compose(source): return source\n'
            )
            with self.assertRaisesRegex(ValueError, 'Unverified control input: compose_kinetic.py'):
                k.capture_control_bundle(root, expected_runner)
            self.assertFalse(marker.exists())

    def test_unverified_checker_cannot_execute_before_authentication(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            original = self.control_fixture(root)
            expected_runner = k.git_blob(original['run_kinetic_games.py'])
            marker = root / 'checker-executed'
            (root / 'check_kinetic.py').write_text(
                'from pathlib import Path\n'
                f'Path({str(marker)!r}).write_text("EXECUTED")\n'
                'def imported(*args): raise RuntimeError("attacker checker executed")\n'
            )
            with self.assertRaisesRegex(ValueError, 'Unverified control input: check_kinetic.py'):
                k.capture_control_bundle(root, expected_runner)
            self.assertFalse(marker.exists())

    def test_captured_composer_is_executed_from_authenticated_bytes_not_reopened_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            original = self.control_fixture(root)
            expected_runner = k.git_blob(original['run_kinetic_games.py'])
            captured, _ = k.capture_control_bundle(root, expected_runner)
            marker = root / 'reopened-composer-executed'
            (root / 'compose_kinetic.py').write_text(
                'from pathlib import Path\n'
                f'Path({str(marker)!r}).write_text("EXECUTED")\n'
                'raise RuntimeError("reopened composer executed")\n'
            )
            module = k.load_captured_composer(captured['compose_kinetic.py'])
            self.assertEqual(module.BASE_BLOB, k.BASE_MECHANICS_BLOB)
            self.assertTrue(callable(module.compose))
            self.assertFalse(marker.exists())

    def test_child_modes_fail_closed_when_runner_is_started_from_path_not_captured_bootstrap(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            original = self.control_fixture(root)
            expected_runner = k.git_blob(original['run_kinetic_games.py'])
            output = root / 'probe.json'
            proc = subprocess.run(
                [
                    sys.executable,
                    '-I', '-S', '-B',
                    str(root / 'run_kinetic_games.py'),
                    '--native-root', str(root / 'unused-native-root'),
                    '--output', str(output),
                    '--expected-runner-git-blob', expected_runner,
                    '--control-probe',
                    '--expected-control-bundle-sha256', '0' * 64,
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('not launched from authenticated captured bytes', proc.stderr)
            self.assertFalse(output.exists())

    def test_hostile_pythonpath_sitecustomize_cannot_run_before_child_bootstrap(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            control = base / 'control'; control.mkdir()
            original = self.control_fixture(control)
            expected_runner = k.git_blob(original['run_kinetic_games.py'])
            captured, digest = k.capture_control_bundle(control, expected_runner)
            hostile = base / 'hostile'; hostile.mkdir()
            marker = base / 'sitecustomize-executed'
            (hostile / 'sitecustomize.py').write_text(
                'from pathlib import Path\n'
                f'Path({str(marker)!r}).write_text("EXECUTED")\n'
                'raise RuntimeError("hostile sitecustomize executed")\n'
            )
            output = base / 'probe.json'
            with patch.dict(k.os.environ, {
                'PYTHONPATH': str(hostile),
                'PYTHONSTARTUP': str(hostile / 'sitecustomize.py'),
                'PYTHONINSPECT': '1',
            }, clear=False):
                proc = k.run_captured_runner(
                    captured['run_kinetic_games.py'],
                    expected_runner,
                    self.probe_args(base, output, expected_runner, digest),
                    optimized=True,
                    timeout=20,
                )
            stderr = proc.stderr.decode('utf-8', errors='replace')
            self.assertEqual(proc.returncode, 0, stderr)
            self.assertFalse(marker.exists(), stderr)
            receipt = json.loads(output.read_text())
            self.assertIs(receipt['runner_executed_from_captured_bytes'], True)
            self.assertEqual(receipt['executed_control_runner_blob'], expected_runner)


if __name__ == '__main__':
    unittest.main()
