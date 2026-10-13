from __future__ import annotations
import importlib.util
import tempfile
import unittest
import sys
from pathlib import Path
MODULE_PATH = Path(__file__).with_name('actions_queue_storm_fix.py')
SPEC = importlib.util.spec_from_file_location('queue_fix', MODULE_PATH)
queue_fix = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = queue_fix
SPEC.loader.exec_module(queue_fix)

class TransformTests(unittest.TestCase):

    def transform(self, source: str, **kwargs):
        return queue_fix.transform_text(source, **kwargs)

    def test_sale_ready_shape_is_scoped(self):
        source = "name: SaleReady\n\non:\n  push:\n    paths:\n      - 'packmarket/sale_readiness.py'\n  pull_request:\n    paths:\n      - 'packmarket/sale_readiness.py'\n"
        result = self.transform(source)
        self.assertTrue(result.changed)
        self.assertIn('  push:\n    branches: [main]\n    paths:', result.text)

    def test_pr_before_push_is_scoped(self):
        source = 'name: IncidentDesk CI\non:\n  pull_request:\n    paths:\n      - "incidentdesk/**"\n  push:\n    paths:\n      - "incidentdesk/**"\npermissions:\n  contents: read\n'
        result = self.transform(source)
        self.assertTrue(result.changed)
        self.assertIn('  push:\n    branches: [main]\n    paths:', result.text)

    def test_already_scoped_is_idempotent(self):
        source = 'on:\n  push:\n    branches: [main]\n    paths:\n      - app/**\n  pull_request:\n    paths:\n      - app/**\n'
        first = self.transform(source)
        self.assertFalse(first.changed)
        self.assertEqual(first.status, 'already_scoped')
        second = self.transform(first.text)
        self.assertEqual(first, second)

    def test_reviewpulse_pr_only_is_unchanged(self):
        source = 'on:\n  pull_request:\n    paths:\n      - reviewpulse/**\njobs:\n  test:\n    runs-on: ubuntu-latest\n'
        result = self.transform(source)
        self.assertFalse(result.changed)
        self.assertEqual(result.status, 'no_push')

    def test_push_only_requires_opt_in(self):
        source = 'on:\n  push:\n    paths:\n      - app/**\n'
        result = self.transform(source)
        self.assertFalse(result.changed)
        self.assertEqual(result.status, 'push_only_skipped')
        opted_in = self.transform(source, include_push_only=True)
        self.assertTrue(opted_in.changed)

    def test_branches_ignore_requires_manual_review(self):
        source = 'on:\n  push:\n    branches-ignore:\n      - release/**\n    paths:\n      - app/**\n  pull_request:\n    paths:\n      - app/**\n'
        result = self.transform(source)
        self.assertFalse(result.changed)
        self.assertEqual(result.status, 'branches_ignore_skipped')

    def test_inline_on_is_skipped(self):
        source = 'on: [push, pull_request]\n'
        result = self.transform(source)
        self.assertFalse(result.changed)
        self.assertEqual(result.status, 'inline_on_skipped')

    def test_empty_inline_push_map_is_normalized(self):
        source = 'on:\n  push: {}\n  pull_request:\n'
        result = self.transform(source)
        self.assertTrue(result.changed)
        self.assertEqual(result.text, 'on:\n  push:\n    branches: [main]\n  pull_request:\n')

    def test_crlf_is_preserved(self):
        source = 'on:\r\n  push:\r\n    paths:\r\n      - app/**\r\n  pull_request:\r\n'
        result = self.transform(source)
        self.assertTrue(result.changed)
        self.assertNotIn('\n', result.text.replace('\r\n', ''))

    def test_quoted_on_is_supported(self):
        source = "'on':\n  push:\n    paths:\n      - app/**\n  pull_request:\n"
        result = self.transform(source)
        self.assertTrue(result.changed)

    def test_nested_push_key_outside_on_is_not_touched(self):
        source = 'name: x\njobs:\n  test:\n    env:\n      push: yes\n'
        result = self.transform(source)
        self.assertFalse(result.changed)
        self.assertEqual(result.text, source)

    def test_custom_default_branch(self):
        source = 'on:\n  push:\n    paths:\n      - app/**\n  pull_request:\n'
        result = self.transform(source, default_branch='trunk')
        self.assertIn('branches: [trunk]', result.text)

class FilesystemTests(unittest.TestCase):

    def test_atomic_write_and_check_cycle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workflow = root / '.github' / 'workflows' / 'ci.yml'
            workflow.parent.mkdir(parents=True)
            workflow.write_text('on:\n  push:\n    paths:\n      - app/**\n  pull_request:\n', encoding='utf-8')
            exit_code = queue_fix.main([str(root), '--write'])
            self.assertEqual(exit_code, 0)
            self.assertIn('branches: [main]', workflow.read_text(encoding='utf-8'))
            exit_code = queue_fix.main([str(root), '--check'])
            self.assertEqual(exit_code, 0)
if __name__ == '__main__':
    unittest.main(verbosity=2)
