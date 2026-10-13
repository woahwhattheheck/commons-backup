"""Opt-in LARK configuration boundaries; no policies or games are executed."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_league


class LarkConfigurationContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'job.json'
        self.output = self.root / 'output'
        self.cfg = {
            'candidate': str(self.root / 'candidate.py') + '::agent',
            'opponents': {'parent': str(self.root / 'parent.py') + '::agent'},
            'lark_wrappers': {
                'sell_priority': str(self.root / 'sell_priority.py'),
                'pressure_priority': str(self.root / 'pressure_priority.py'),
            },
            'output': str(self.output),
            'cells': [{'id': 'fixture', 'seed': 17, 'seat': 0, 'opponent': 'parent'}],
        }

    def save(self, cfg):
        payload = (json.dumps(cfg, indent=2) + '\n').encode()
        self.path.write_bytes(payload)
        return payload

    def assert_rejected_before_execution(self, cfg):
        self.save(cfg)
        args = argparse.Namespace(config=str(self.path), cell='fixture')
        with patch.object(run_league, 'load_evaluator') as evaluator, \
                patch.object(run_league.subprocess, 'Popen') as process:
            with self.assertRaises(ValueError):
                run_league.cell(args)
            evaluator.assert_not_called()
            process.assert_not_called()
            self.assertFalse(self.output.exists())
            with self.assertRaises(ValueError):
                run_league.launch(args)
            process.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_invalid_markers_fail_before_loading_or_launching(self):
        parent = str(self.root / 'parent.py')
        invalid = [
            parent + '::agent|sell-priority|supply-pressure',
            parent + '::agent|supply-pressure|sell-priority',
            parent + '::agent|sell-priority|sell-priority',
            parent + '::agent|unknown',
            parent + '::agent|supply-pressure-extra',
            parent + '::agent|',
            parent + '::|sell-priority',
            '|supply-pressure',
        ]
        for value in invalid:
            for target in ('candidate', 'opponent'):
                with self.subTest(spec=value, target=target):
                    cfg = copy.deepcopy(self.cfg)
                    if target == 'candidate':
                        cfg['candidate'] = value
                    else:
                        cfg['opponents']['parent'] = value
                    self.assert_rejected_before_execution(cfg)

    def test_invalid_module_configuration_fails_before_execution(self):
        paths = self.cfg['lark_wrappers']
        invalid = [
            None, [], {},
            {'sell_priority': paths['sell_priority']},
            {'pressure_priority': paths['pressure_priority']},
            dict(paths, sell_priority='relative.py'),
            dict(paths, pressure_priority='relative.py'),
            dict(paths, sell_priority=123),
            dict(paths, pressure_priority=None),
        ]
        for value in invalid:
            with self.subTest(paths=value):
                cfg = copy.deepcopy(self.cfg)
                cfg['lark_wrappers'] = value
                self.assert_rejected_before_execution(cfg)

    def test_supported_specs_keep_original_configuration_and_digest(self):
        parent = str(self.root / 'parent.py')
        accepted = [
            parent,
            parent + '::agent',
            parent + '|sell-priority',
            parent + '|supply-pressure',
            parent + '::agent|sell-priority',
            parent + '::agent|supply-pressure',
            str(self.root / 'parent|literal.py') + '::agent|sell-priority',
        ]
        for value in accepted:
            with self.subTest(spec=value):
                cfg = copy.deepcopy(self.cfg)
                cfg['opponents']['parent'] = value
                payload = self.save(cfg)
                loaded, digest = run_league.load_job(self.path)
                self.assertEqual(loaded, cfg)
                self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
                self.assertEqual(self.path.read_bytes(), payload)
                self.assertFalse(self.output.exists())

    def test_absent_optin_keeps_prior_spec_acceptance(self):
        cfg = copy.deepcopy(self.cfg)
        del cfg['lark_wrappers']
        cfg['candidate'] = 'fixture'
        cfg['opponents']['parent'] = 'legacy|opaque'
        payload = self.save(cfg)
        loaded, digest = run_league.load_job(self.path)
        self.assertEqual(loaded, cfg)
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
