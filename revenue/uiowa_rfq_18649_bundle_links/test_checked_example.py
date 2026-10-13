"""Check published deliverable bytes without regenerating expectations in place."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from build_example import HERE, build
from verify_bundle import check

EXAMPLE = HERE / 'checked_example'
GENERATED = {
    'review.html', 'citations.json', 'sources/report.html',
    'sources/évidence.html', 'sources/final-report.md', 'sources/evidence.csv',
}


def contents(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob('*') if p.is_file()}


def report(root: Path) -> dict:
    return check(root, json.loads((root / 'citations.json').read_text(encoding='utf-8')))


class PublishedExampleTests(unittest.TestCase):
    def test_complete_portable_file_set(self):
        self.assertEqual(set(contents(EXAMPLE)), GENERATED | {'verification.json'})

    def test_builder_reproduces_published_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            fresh = Path(temporary) / 'new'
            build(fresh)
            actual = contents(fresh)
            self.assertEqual(set(actual), GENERATED)
            for name, data in actual.items():
                self.assertEqual(data, (EXAMPLE / name).read_bytes(), name)

    def test_saved_report_is_actual_recomputed_result(self):
        actual = report(EXAMPLE)
        saved = json.loads((EXAMPLE / 'verification.json').read_text(encoding='utf-8'))
        self.assertEqual(actual, saved)
        self.assertEqual((actual['total'], actual['verified'], actual['unresolved']), (19, 19, 0))
        self.assertEqual(actual['verdict'], 'VERIFIED')

    def test_verification_leaves_every_input_byte_unchanged(self):
        before = contents(EXAMPLE)
        report(EXAMPLE)
        self.assertEqual(contents(EXAMPLE), before)

    def test_fresh_report_does_not_accept_stale_saved_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / 'changed'
            shutil.copytree(EXAMPLE, changed)
            (changed / 'sources/report.html').unlink()
            self.assertEqual(json.loads((changed / 'verification.json').read_text())['verdict'], 'VERIFIED')
            actual = report(changed)
            self.assertEqual(actual['verdict'], 'UNRESOLVED')
            self.assertGreater(actual['unresolved'], 0)

    def test_tampered_record_content_is_detected_without_rewriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            changed = Path(temporary) / 'changed'
            shutil.copytree(EXAMPLE, changed)
            csv_path = changed / 'sources/evidence.csv'
            csv_path.write_bytes(csv_path.read_bytes().replace(b'E-006', b'E-999'))
            before = contents(changed)
            actual = report(changed)
            self.assertEqual(actual['counts']['CONTENT_CHANGED'], 8)
            self.assertEqual(contents(changed), before)

    def test_saved_result_has_recorded_core_receipt_identity(self):
        receipt = json.loads((HERE / 'validation_receipt.json').read_text(encoding='utf-8'))
        data = (EXAMPLE / 'verification.json').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), receipt['integration']['example_report_sha256'])
        self.assertEqual(receipt['browser_navigation']['status'], 'NOT_VERIFIED')


if __name__ == '__main__':
    unittest.main()
