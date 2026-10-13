"""Focused adapter regressions using the preserved official file-loader contract."""
import builtins
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import bank
import intake

PACK = Path(os.environ.get('T07_PACK', str(Path(__file__).resolve().parents[3] / 'cloud-pack')))


class BankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(PACK, self.root / 'contract', ignore=shutil.ignore_patterns('__pycache__'))

    def policy(self, source, mode='not_applicable'):
        p = self.root / 'policy.py'
        p.write_text(source)
        entry = {'source': 'policy.py', 'source_sha256': bank.sha256(p),
                 'assignment': mode, 'dependencies': {}}
        (self.root / 'BANK.json').write_text(json.dumps({'entries': {'sample': entry}}))
        return bank.make_agent(self.root, 'sample')

    def test_state_is_persistent_but_not_shared_between_instances(self):
        source = 'count = 0\ndef agent(obs):\n global count\n count += 1\n return {"count": count}\n'
        first = self.policy(source)
        second = bank.make_agent(self.root, 'sample')
        self.assertEqual(first({}), {'count': 1})
        self.assertEqual(first({}), {'count': 2})
        self.assertEqual(second({}), {'count': 1})

    def test_official_one_argument_slicing_and_last_callable(self):
        run = self.policy('def helper():\n return None\ndef agent(obs):\n return {"answer": obs["value"]}\n')
        self.assertEqual(run({'value': 8}, {'extra': True}), {'answer': 8})

    def test_greedy_mode_really_uses_upstream_import_fallback(self):
        run = self.policy('try:\n import numpy\n _HUNGARIAN = True\nexcept ImportError:\n _HUNGARIAN = False\ndef agent(obs):\n return {"hungarian": _HUNGARIAN}\n', 'greedy')
        previous = builtins.__import__
        self.assertEqual(run({}), {'hungarian': False})
        self.assertIs(builtins.__import__, previous)

    def test_branch_mismatch_is_not_silently_accepted(self):
        run = self.policy('_HUNGARIAN = True\ndef agent(obs):\n return {}\n', 'greedy')
        previous = builtins.__import__
        with self.assertRaisesRegex(RuntimeError, 'assignment branch'):
            run({})
        self.assertIs(builtins.__import__, previous)

    def test_import_state_restored_after_policy_exception(self):
        run = self.policy('def agent(obs):\n raise ValueError("example failure")\n')
        previous = builtins.__import__
        with self.assertRaisesRegex(ValueError, 'example failure'):
            run({})
        self.assertIs(builtins.__import__, previous)

    def test_changed_source_detected_before_import(self):
        self.policy('def agent(obs):\n return {}\n')
        (self.root / 'policy.py').write_text('raise AssertionError("must not execute")\n')
        with self.assertRaisesRegex(ValueError, 'source differs'):
            bank.make_agent(self.root, 'sample')

    def test_git_blob_empty_reference(self):
        self.assertEqual(intake.git_blob(b''), 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')

    def test_sha256_exact_bytes(self):
        self.assertEqual(intake.digest(b'a\r\n'), hashlib.sha256(b'a\r\n').hexdigest())
        self.assertNotEqual(intake.digest(b'a\r\n'), intake.digest(b'a\n'))


if __name__ == '__main__':
    unittest.main()
