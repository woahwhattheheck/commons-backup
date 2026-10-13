"""File-based tests of the actual T03 resume path; no official games are run.

A tiny evaluator fixture records every attempted play() call. The production
runner, manifests, adapter files, JSON outputs and process entrypoint are real.
Set T03_PANEL_PATH to run the same discriminators against a prior source file.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

TARGET = Path(os.environ.get('T03_PANEL_PATH', str(Path(__file__).with_name('evaluate_panel.py'))))
EVALUATOR = '''from pathlib import Path
import hashlib
import json
HERE = Path(__file__).resolve().parent
LOADER = HERE.parent / "20260907-offline-agent/evaluate.py"
class Actor:
    def close(self):
        return "closed"
ORIGINAL_CLOSE = Actor.close

def get_engine(directory):
    return object(), {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(Path(directory).glob("*")) if p.is_file()}

def play(engine, pair, engine_dir, loader, seed, seat, **limits):
    with (HERE / "calls.log").open("a") as stream:
        stream.write(json.dumps([pair, seed, seat, limits]) + "\\n")
    if (HERE / "raise-play").exists():
        raise RuntimeError("fixture play failure")
    incomplete = (HERE / "incomplete").exists()
    own = 120 if "candidate" in Path(pair[seat]).name else 100
    scores = [own, 90] if seat == 0 else [90, own]
    return {"seed": seed, "candidate_seat": seat,
            "status": "action_error" if incomplete else "complete",
            "steps": 3 if incomplete else 719,
            "scores": scores, "failure": "retained fixture error" if incomplete else None,
            "actors": []}
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ResumeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.here = self.root / 'cloud-rolling-scheduler'
        self.here.mkdir()
        self.panel_path = self.here / 'evaluate_panel.py'
        shutil.copyfile(TARGET, self.panel_path)
        self.evaluator = self.root / 'cloud-eval/evaluate.py'
        self.evaluator.parent.mkdir()
        self.evaluator.write_text(EVALUATOR)
        self.loader = self.root / '20260907-offline-agent/evaluate.py'
        self.loader.parent.mkdir()
        self.loader.write_text('# fixture loader\n')
        self.guard = self.root / 'cloud-frontier-policy/next-panel/offline.py'
        self.guard.parent.mkdir(parents=True)
        self.guard.write_text('# fixture offline dependency\n')
        self.engine = self.root / 'engine'
        self.engine.mkdir()
        (self.engine / 'kaggriculture.py').write_text('# fixture engine\n')
        (self.engine / 'kaggriculture.json').write_text('{"duration":719}')
        (self.engine / 'utils.py').write_text('# fixture utility\n')
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        for name in ('scheduler.py', 'policy.py', 'oracle.py', 'arlene.py', 'apex.py',
                     'helper.py', 'candidate-adapter.py', 'arlene-adapter.py', 'apex-adapter.py'):
            (self.runtime / name).write_text('# fixture ' + name + '\n')
        self.manifest = {
            'source_sha256': {name: sha(self.runtime / name)
                             for name in ('scheduler.py', 'policy.py', 'oracle.py', 'arlene.py')},
            'runtime_sha256': {p.name: sha(p) for p in self.runtime.iterdir()},
            'adapters': {name: str(self.runtime / (name + '-adapter.py'))
                         for name in ('candidate', 'arlene', 'apex')},
        }
        self.save_manifest()
        spec = importlib.util.spec_from_file_location('t03_resume_under_test', self.panel_path)
        self.panel = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.panel)
        self.output = self.root / 'results'

    def save_manifest(self):
        (self.runtime / 'runtime-manifest.json').write_text(json.dumps(self.manifest))

    def calls(self):
        path = self.evaluator.parent / 'calls.log'
        return path.read_text().splitlines() if path.exists() else []

    def run_panel(self, **kw):
        args = dict(seeds=[41], opponents=['apex'], seats=[0], arms=['arlene', 'candidate'])
        args.update(kw)
        with contextlib.redirect_stdout(io.StringIO()):
            self.panel.run(self.runtime, self.engine, self.output, **args)
        return json.loads((self.output / 'panel.json').read_text())

    def cell(self, arm='candidate', seed=41, seat=0):
        return self.output / f'{seed}-apex-seat{seat}-{arm}.json'

    def edit_cell(self, edit, **kw):
        path = self.cell(**kw)
        row = json.loads(path.read_text())
        edit(row)
        path.write_text(json.dumps(row))

    def assert_rejected_without_execution(self, **kw):
        before = len(self.calls())
        preserved = {p: p.read_bytes() for p in self.output.glob('*.json')}
        with self.assertRaises(ValueError):
            self.run_panel(**kw)
        self.assertEqual(len(self.calls()), before)
        self.assertEqual({p: p.read_bytes() for p in self.output.glob('*.json')}, preserved)

    def test_duplicate_requested_cells_execute_once(self):
        report = self.run_panel(seeds=[41, 41], arms=['arlene', 'candidate', 'candidate'])
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(len(report['games']), 2)
        self.assertEqual(len(report['pairs']), 1)

    def test_identical_completed_grid_reuses_bytes_without_play(self):
        first = self.run_panel(seats=[0, 1])
        original = {p: p.read_bytes() for p in self.output.glob('*-apex-*.json')}
        second = self.run_panel(seats=[0, 1])
        self.assertEqual(len(self.calls()), 4)
        self.assertEqual(first['pairs'], second['pairs'])
        self.assertEqual(second['resume'], {'executed': 0, 'reused_complete': 4, 'retained_incomplete': 0})
        self.assertEqual(original, {p: p.read_bytes() for p in original})

    def test_candidate_engine_change_cannot_reuse(self):
        self.run_panel(arms=['candidate'])
        (self.engine / 'utils.py').write_text('# changed engine fixture\n')
        self.assert_rejected_without_execution(arms=['candidate'])

    def test_opponent_source_change_cannot_reuse(self):
        self.run_panel()
        path = self.runtime / 'apex.py'
        path.write_text('# different opponent\n')
        self.manifest['runtime_sha256']['apex.py'] = sha(path)
        self.save_manifest()
        self.assert_rejected_without_execution()

    def test_adapter_change_cannot_reuse(self):
        self.run_panel()
        path = self.runtime / 'candidate-adapter.py'
        path.write_text('# revised adapter settings\n')
        self.manifest['runtime_sha256'][path.name] = sha(path)
        self.save_manifest()
        self.assert_rejected_without_execution()

    def test_adapter_mapping_change_cannot_reuse(self):
        self.run_panel()
        self.manifest['adapters']['apex'] = self.manifest['adapters']['arlene']
        self.save_manifest()
        self.assert_rejected_without_execution()

    def test_runtime_dependency_change_cannot_reuse(self):
        self.run_panel()
        path = self.runtime / 'helper.py'
        path.write_text('# changed runtime dependency\n')
        self.manifest['runtime_sha256'][path.name] = sha(path)
        self.save_manifest()
        self.assert_rejected_without_execution()

    def test_evaluator_change_cannot_reuse(self):
        self.run_panel()
        with self.evaluator.open('a') as stream:
            stream.write('\n# changed configuration semantics\n')
        self.assert_rejected_without_execution()

    def test_loader_change_cannot_reuse(self):
        self.run_panel()
        self.loader.write_text('# changed loader\n')
        self.assert_rejected_without_execution()

    def test_offline_dependency_change_cannot_reuse(self):
        self.run_panel()
        self.guard.write_text('# changed external dependency\n')
        self.assert_rejected_without_execution()

    def test_seed_metadata_mismatch_cannot_reuse(self):
        self.run_panel()
        self.edit_cell(lambda r: r.update(seed=999))
        self.assert_rejected_without_execution()

    def test_seat_metadata_mismatch_cannot_reuse(self):
        self.run_panel()
        self.edit_cell(lambda r: r.update(candidate_seat=1))
        self.assert_rejected_without_execution()

    def test_opponent_metadata_mismatch_cannot_reuse(self):
        self.run_panel()
        self.edit_cell(lambda r: r.update(opponent='different'))
        self.assert_rejected_without_execution()

    def test_arm_metadata_mismatch_cannot_reuse(self):
        self.run_panel()
        self.edit_cell(lambda r: r.update(arm='arlene'))
        self.assert_rejected_without_execution()

    def test_candidate_engine_metadata_mismatch_cannot_reuse(self):
        self.run_panel(arms=['candidate'])
        self.edit_cell(lambda r: r['engine_sha256'].update({'utils.py': 'other'}))
        self.assert_rejected_without_execution(arms=['candidate'])

    def test_control_source_metadata_mismatch_cannot_reuse(self):
        self.run_panel(arms=['arlene'])
        self.edit_cell(lambda r: r['source_sha256'].update({'policy.py': 'other'}), arm='arlene')
        self.assert_rejected_without_execution(arms=['arlene'])

    def test_legacy_rows_stay_untouched_not_silently_upgraded(self):
        self.run_panel()
        self.edit_cell(lambda r: r.pop('run_identity', None))
        self.assert_rejected_without_execution()

    def test_grid_preflight_precedes_missing_cell_execution(self):
        self.run_panel(seeds=[41, 43])
        self.cell(arm='arlene', seed=41).unlink()  # temporary fixture, not source data
        self.edit_cell(lambda r: r.update(seed=999), seed=43)
        self.assert_rejected_without_execution(seeds=[41, 43])

    def test_incomplete_attempt_is_visible_not_counted_as_cache_success(self):
        (self.evaluator.parent / 'incomplete').touch()
        self.run_panel()
        report = self.run_panel()
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(report['resume'], {'executed': 0, 'reused_complete': 0, 'retained_incomplete': 2})
        self.assertEqual(report['pairs'], [])
        self.assertTrue(all(r['failure'] == 'retained fixture error' for r in report['games']))

    def test_deadline_change_cannot_reuse(self):
        self.run_panel()
        self.panel.RUN_LIMITS = {**self.panel.RUN_LIMITS, 'action_timeout': 2.0}
        self.assert_rejected_without_execution()

    def test_unrecorded_runtime_change_stops_before_play(self):
        self.run_panel()
        (self.runtime / 'helper.py').write_text('# tampered fixture\n')
        self.assert_rejected_without_execution()

    def test_optimized_python_still_checks_runtime_hashes(self):
        self.run_panel()
        (self.runtime / 'helper.py').write_text('# tampered fixture\n')
        before = len(self.calls())
        result = subprocess.run([sys.executable, '-O', str(self.panel_path),
            '--runtime', str(self.runtime), '--engine-dir', str(self.engine),
            '--output', str(self.output), '--seeds', '41', '--opponents', 'apex'],
            capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Runtime changed', result.stderr)
        self.assertEqual(len(self.calls()), before)

    def test_actor_close_restored_after_success(self):
        self.run_panel()
        ev = sys.modules['t03_panel_evaluator']
        self.assertIs(ev.Actor.close, ev.ORIGINAL_CLOSE)

    def test_actor_close_restored_after_execution_error(self):
        (self.evaluator.parent / 'raise-play').touch()
        with self.assertRaisesRegex(RuntimeError, 'fixture play failure'):
            self.run_panel()
        ev = sys.modules['t03_panel_evaluator']
        self.assertIs(ev.Actor.close, ev.ORIGINAL_CLOSE)
        self.assertFalse(self.cell().exists())

    def test_new_output_directory_executes_changed_inputs(self):
        first = self.run_panel()
        path = self.runtime / 'apex.py'
        path.write_text('# next opponent revision\n')
        self.manifest['runtime_sha256'][path.name] = sha(path)
        self.save_manifest()
        old = self.output
        self.output = self.root / 'second-results'
        second = self.run_panel()
        self.assertEqual(len(self.calls()), 4)
        self.assertEqual(second['resume']['executed'], 2)
        self.assertEqual(json.loads((old / 'panel.json').read_text()), first)

    def test_status_metadata_must_describe_an_attempt(self):
        self.run_panel()
        self.edit_cell(lambda r: r.update(status=None))
        self.assert_rejected_without_execution()

    def test_context_serializes_both_actors_and_execution_limits(self):
        report = self.run_panel()
        context = report['games'][1]['run_identity']['inputs']
        self.assertEqual(context['manifest'], self.manifest)
        self.assertEqual(context['adapter_sha256']['apex'], sha(self.manifest['adapters']['apex']))
        self.assertEqual(context['limits'], {'action_timeout': 1.0, 'startup_timeout': 10, 'game_timeout': 90})
        self.assertEqual(context['harness_sha256']['loader'], sha(self.loader))
        self.assertEqual(context['harness_sha256']['offline'], sha(self.guard))


if __name__ == '__main__':
    unittest.main()
