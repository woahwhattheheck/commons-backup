#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


materialize = load(HERE / 'materialize.py', 'wf1_v5_materialize_tested')
field = load(HERE / 'run_field.py', 'wf1_v5_field_tested')


class Wf1V5ConvergenceTest(unittest.TestCase):
    def test_canonical_source_pins_and_evidence(self):
        source = materialize.SOURCE_ROOT / 'candidates/v4/repairs/gameplay/wf1-wheat-fertilize'
        for name, expected in materialize.PINS.items():
            with self.subTest(name=name):
                self.assertEqual(materialize.git_blob_sha((source / name).read_bytes()), expected)
        receipt = json.loads((source / 'WF1-CURRENT-NATIVE-FIELD-RECEIPT.json').read_text())
        self.assertEqual(receipt['validation']['complete_cells'], 8)
        self.assertEqual(receipt['validation']['game_failures'], 0)
        self.assertEqual(receipt['summary']['positive_margin_cells'], 8)
        self.assertEqual(receipt['summary']['negative_margin_cells'], 0)
        self.assertEqual(receipt['summary']['mean_margin_delta'], 143.25)
        self.assertEqual(receipt['summary']['mean_own_delta'], 132.375)

    def test_materialize_preserves_baseline_and_records_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / 'runtime'
            output = root / 'candidate'
            runtime.mkdir()
            main_bytes = b"VALUE = 'baseline'\n"
            config_bytes = b'{"consumer":"frozen"}\n'
            (runtime / 'main.py').write_bytes(main_bytes)
            (runtime / 'TITAN-CONFIG.json').write_bytes(config_bytes)
            expected_main = materialize.git_blob_sha(main_bytes)
            expected_config = materialize.git_blob_sha(config_bytes)
            receipt = materialize.materialize(
                runtime, output,
                expected_main_blob=expected_main,
                expected_config_blob=expected_config,
            )
            self.assertEqual((output / 'main.py').read_bytes(), main_bytes)
            self.assertEqual((output / 'TITAN-CONFIG.json').read_bytes(), config_bytes)
            self.assertTrue((output / 'r04_wheat_fert.py').is_file())
            self.assertTrue((output / 'wf1_current_adapter.py').is_file())
            self.assertTrue((output / 'wf1_v5_entry.py').is_file())
            self.assertEqual(receipt['baseline']['main_git_blob'], expected_main)
            self.assertEqual(receipt['baseline']['config_git_blob'], expected_config)
            self.assertEqual(receipt['component']['ordering'], 'after_parent_main_agent')
            persisted = json.loads((output / 'WF1-V5-MATERIALIZATION.json').read_text())
            self.assertEqual(persisted, receipt)

    def test_baseline_drift_fails_before_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / 'runtime'
            output = root / 'candidate'
            runtime.mkdir()
            config = b'{}\n'
            (runtime / 'main.py').write_text('x = 1\n')
            (runtime / 'TITAN-CONFIG.json').write_bytes(config)
            with self.assertRaisesRegex(ValueError, 'main.py identity mismatch'):
                materialize.materialize(
                    runtime, output,
                    expected_main_blob='0' * 40,
                    expected_config_blob=materialize.git_blob_sha(config),
                )
            self.assertFalse(output.exists())

    def test_nested_output_fails_without_mutating_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / 'runtime'
            output = runtime / 'candidate'
            runtime.mkdir()
            main_bytes = b"VALUE = 'baseline'\n"
            config_bytes = b'{}\n'
            (runtime / 'main.py').write_bytes(main_bytes)
            (runtime / 'TITAN-CONFIG.json').write_bytes(config_bytes)
            before = sorted(path.name for path in runtime.iterdir())
            with self.assertRaisesRegex(ValueError, 'not be nested under'):
                materialize.materialize(
                    runtime, output,
                    expected_main_blob=materialize.git_blob_sha(main_bytes),
                    expected_config_blob=materialize.git_blob_sha(config_bytes),
                )
            self.assertFalse(output.exists())
            self.assertEqual(sorted(path.name for path in runtime.iterdir()), before)
            self.assertEqual((runtime / 'main.py').read_bytes(), main_bytes)
            self.assertEqual((runtime / 'TITAN-CONFIG.json').read_bytes(), config_bytes)

    def test_entry_calls_parent_before_outer_wf1_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy2(HERE / 'entry.py', root / 'entry.py')
            (root / 'main.py').write_text(
                "def agent(observation, configuration=None):\n"
                "    return {'trace':['parent']}\n",
                encoding='utf-8')
            (root / 'wf1_current_adapter.py').write_text(
                "def apply_wf1_current(observation, action, configuration, enabled=False):\n"
                "    assert enabled is True\n"
                "    return {'trace': action['trace'] + ['wf1']}\n",
                encoding='utf-8')
            entry = load(root / 'entry.py', 'wf1_v5_entry_order_test')
            self.assertEqual(entry.agent({'step': 1}, {}), {'trace': ['parent', 'wf1']})

    def test_field_snapshot_binds_full_package_and_stays_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / 'runtime'
            snapshot = root / 'snapshot'
            (runtime / 'sub').mkdir(parents=True)
            (runtime / '__pycache__').mkdir()
            (runtime / 'main.py').write_text('x = 1\n')
            (runtime / 'TITAN-CONFIG.json').write_text('{}\n')
            (runtime / 'sub' / 'data.txt').write_text('one\n')
            (runtime / '__pycache__' / 'ignored.pyc').write_bytes(b'ignored')
            digest = field.snapshot_runtime(runtime, snapshot)
            self.assertEqual(digest, field.package_digest(runtime))
            self.assertEqual(digest, field.package_digest(snapshot))
            self.assertFalse((snapshot / '__pycache__').exists())
            (runtime / 'sub' / 'data.txt').write_text('two\n')
            self.assertNotEqual(field.package_digest(runtime), digest)
            self.assertEqual(field.package_digest(snapshot), digest)

    def test_field_snapshot_rejects_nested_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / 'runtime'
            runtime.mkdir()
            (runtime / 'main.py').write_text('x = 1\n')
            with self.assertRaisesRegex(ValueError, 'outside runtime'):
                field.snapshot_runtime(runtime, runtime / 'snapshot')
            self.assertFalse((runtime / 'snapshot').exists())

    def test_field_source_snapshot_is_complete_and_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            frozen = Path(tmp) / 'frozen-source'
            hashes = field.snapshot_harness_source(frozen)
            self.assertEqual(set(hashes), {rel.as_posix() for rel in field.SOURCE_FILES})
            for rel in field.SOURCE_FILES:
                source = field.SOURCE_ROOT / rel
                copied = frozen / rel
                self.assertTrue(copied.is_file(), rel)
                self.assertEqual(field._sha256(source), hashes[rel.as_posix()])
                self.assertEqual(field._sha256(copied), hashes[rel.as_posix()])
            field.validate_source_snapshot(frozen, hashes)
            copied_entry = frozen / field.COMPONENT_REL / 'entry.py'
            before = field._sha256(field.HERE / 'entry.py')
            copied_entry.write_text('# frozen copy changed\n')
            self.assertEqual(field._sha256(field.HERE / 'entry.py'), before)
            with self.assertRaisesRegex(RuntimeError, 'changed during field execution'):
                field.validate_source_snapshot(frozen, hashes)

    def test_field_seed_design_is_unique_and_canonical(self):
        self.assertEqual(field.parse_seed_set('9,3,7'), (3, 7, 9))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            field.parse_seed_set('7,3,7')
        with self.assertRaisesRegex(ValueError, 'at least one'):
            field.parse_seed_set(' , ')

    def test_field_cell_custody_binds_both_arms_and_opponents(self):
        base = {
            'seed': 7, 'seat': 1, 'package_sha256': 'control',
            'opponent': {'package_sha256': 'control'},
        }
        candidate = {
            'seed': 7, 'seat': 1, 'package_sha256': 'wf1',
            'opponent': {'package_sha256': 'control'},
        }
        field.validate_cell_custody(
            base, candidate, seed=7, seat=1,
            control_digest='control', candidate_digest='wf1')
        mutations = (
            ('base package', {**base, 'package_sha256': 'other'}, candidate),
            ('candidate package', base, {**candidate, 'package_sha256': 'other'}),
            ('base opponent', {**base, 'opponent': {'package_sha256': 'other'}}, candidate),
            ('candidate opponent', base, {**candidate, 'opponent': {'package_sha256': 'other'}}),
            ('identity', {**base, 'seat': 0}, candidate),
        )
        for label, bad_base, bad_candidate in mutations:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    field.validate_cell_custody(
                        bad_base, bad_candidate, seed=7, seat=1,
                        control_digest='control', candidate_digest='wf1')

    def test_incomplete_field_panel_has_no_economic_summary(self):
        complete = {
            'complete': True,
            'delta': {'own': 5, 'rival': 1, 'margin': 4},
            'first_action_change_step': 647,
            'outcome_transition': 'W->W',
        }
        validation, summary = field.summarize_cells([complete, {'complete': False}])
        self.assertFalse(validation['complete_panel'])
        self.assertFalse(validation['economic_summary_valid'])
        self.assertEqual(summary['requested_cells'], 2)
        self.assertEqual(summary['complete_cells'], 1)
        self.assertEqual(summary['game_failures'], 1)
        for key in ('changed_action_cells', 'positive_margin_cells', 'zero_margin_cells',
                    'negative_margin_cells', 'mean_margin_delta', 'median_margin_delta',
                    'min_margin_delta', 'max_margin_delta', 'mean_own_delta',
                    'mean_rival_delta', 'outcome_transitions'):
            self.assertIsNone(summary[key], key)

    def test_complete_field_panel_reports_transitions_and_economics(self):
        cells = [
            {'complete': True, 'delta': {'own': 10, 'rival': 2, 'margin': 8},
             'first_action_change_step': 647, 'outcome_transition': 'W->W'},
            {'complete': True, 'delta': {'own': -1, 'rival': 0, 'margin': -1},
             'first_action_change_step': None, 'outcome_transition': 'W->L'},
        ]
        validation, summary = field.summarize_cells(cells)
        self.assertTrue(validation['complete_panel'])
        self.assertTrue(validation['economic_summary_valid'])
        self.assertEqual(summary['changed_action_cells'], 1)
        self.assertEqual(summary['positive_margin_cells'], 1)
        self.assertEqual(summary['negative_margin_cells'], 1)
        self.assertEqual(summary['mean_margin_delta'], 3.5)
        self.assertEqual(summary['min_margin_delta'], -1)
        self.assertEqual(summary['max_margin_delta'], 8)
        self.assertEqual(summary['outcome_transitions'], {'W->W': 1, 'W->L': 1})


if __name__ == '__main__':
    unittest.main()
