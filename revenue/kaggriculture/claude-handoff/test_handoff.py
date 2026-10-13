"""Integrity and phase-separation regressions for the real handoff runner."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import handoff


class HandoffTests(unittest.TestCase):
    def test_source_corruption_is_detected(self):
        manifest = handoff.read_manifest()
        entry = next(f for f in manifest['files'] if f['path'].endswith('cloud-market/main.py'))
        path = Path(__file__).resolve().parents[3] / entry['path']
        data = path.read_bytes()
        self.assertEqual(handoff.verify_bytes(data, entry), data)
        with self.assertRaisesRegex(ValueError, 'Source bytes differ'):
            handoff.verify_bytes(data + b'\n', entry)

    def test_new_seed_sets_exclude_published_seeds(self):
        previous = {1,17,101,37,211,997,23,83,449,2027,65537,6607,104729,
                    733,2801,8191,1237,4421,10007,32771,65539,131071,262147,524287}
        seeds = handoff.read_manifest()['seeds']
        self.assertEqual(seeds['calibration'], [4421])
        new = seeds['smoke'] + seeds['development'] + seeds['validation']
        self.assertEqual(len(new), len(set(new)))
        self.assertFalse(set(new) & previous)

    def test_changed_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'main.py'
            handoff.write_once(path, b'first')
            handoff.write_once(path, b'first')
            with self.assertRaises(ValueError):
                handoff.write_once(path, b'second')
            self.assertEqual(path.read_bytes(), b'first')

    def development_fixture(self):
        return {'contract': {'phase':'development', 'candidate_sha256':'candidate',
                             'manifest_sha256':'manifest',
                             'opponents':{'lean20':'lean20', 'euler28':'euler28', 'compact22':'compact22'},
                             'seeds':handoff.read_manifest()['seeds']['development']},
                'complete':True, 'expected_games':36,
                'games':[{'status':'complete'} for _ in range(36)],
                'replay_by_opponent':{'lean20':True,'euler28':True,'compact22':True}}

    def test_validation_uses_exact_complete_development_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'development.json'
            path.write_text(json.dumps(self.development_fixture()))
            self.assertEqual(handoff.ensure_development(path,'candidate','manifest'),
                             hashlib.sha256(path.read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                handoff.ensure_development(path,'changed','manifest')
            with self.assertRaises(ValueError):
                handoff.ensure_development(path,'candidate','other-manifest')
            with self.assertRaises(ValueError):
                handoff.ensure_development(path,'candidate','manifest',{'lean20':'different'})

    def test_extra_opponent_is_frozen_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'rival.py'
            source.write_bytes(b'def agent(obs): return {}\n')
            expected = handoff.digest(source.read_bytes())
            paths = handoff.extra_opponents(['rival='+str(source)], ['rival='+expected], root/'out')
            source.write_bytes(b'changed')
            self.assertEqual(handoff.digest(paths['rival'].read_bytes()), expected)
            with self.assertRaises(ValueError):
                handoff.extra_opponents(['rival='+str(source)], ['rival='+expected], root/'other')
            with self.assertRaises(ValueError):
                handoff.extra_opponents([], ['rival='+expected], root/'other')

    def test_incomplete_failed_or_uncalibrated_development_cannot_validate(self):
        base = self.development_fixture()
        cases = []
        for key, value in [('complete',False), ('games',[]), ('replay_by_opponent',{})]:
            report = copy.deepcopy(base)
            report[key] = value
            cases.append(report)
        failed = copy.deepcopy(base)
        failed['games'][0]['status'] = 'failed'
        cases.append(failed)
        wrong_seeds = copy.deepcopy(base)
        wrong_seeds['contract']['seeds'] = [4421]
        cases.append(wrong_seeds)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'development.json'
            for report in cases:
                path.write_text(json.dumps(report))
                with self.subTest(report=report), self.assertRaises(ValueError):
                    handoff.ensure_development(path,'candidate','manifest')


if __name__ == '__main__':
    unittest.main(verbosity=2)
