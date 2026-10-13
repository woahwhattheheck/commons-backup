# SPDX-License-Identifier: Apache-2.0
"""Focused regression suite. Optional actual-archive tests use TITAN_ARCHIVE."""
from __future__ import annotations
import ast
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import tarfile
import tempfile
import unittest

import check_mechanics_contract as check


class ConsumerTests(unittest.TestCase):
    def scan(self, source, aliases=()):
        return check.consumer_requirements(source, 'consumer.py', aliases)

    def test_direct_import_alias(self):
        row = self.scan('import mechanics as m\nm.market_price(1)\n')
        self.assertEqual(row['required'], {'market_price': [2]})

    def test_from_import(self):
        row = self.scan('from mechanics import _parse_order as parse\n')
        self.assertEqual(row['required'], {'_parse_order': [1]})

    def test_dependency_injected_alias(self):
        row = self.scan('def apply(mechanics):\n    return mechanics.CROPS\n', ('mechanics',))
        self.assertEqual(row['required'], {'CROPS': [2]})

    def test_self_attribute_alias(self):
        row = self.scan('self.m._parse_order([])', ('self.m',))
        self.assertIn('_parse_order', row['required'])

    def test_constant_getattr(self):
        row = self.scan("import mechanics as m\nx = getattr(m, '_parse_order')")
        self.assertIn('_parse_order', row['required'])

    def test_dynamic_getattr_not_certified(self):
        row = self.scan('import mechanics as m\nx = getattr(m, name)')
        self.assertEqual(check.check_contract('', [row])['status'], 'REVIEW')

    def test_optional_attribute_not_mandatory(self):
        row = self.scan("import mechanics as m\nx = getattr(m, 'optional', None)")
        self.assertFalse(row['required'])
        self.assertTrue(row['unresolved_dynamic_lines'])

    def test_star_import_requires_review(self):
        row = self.scan('from mechanics import *')
        self.assertEqual(check.check_contract('', [row])['status'], 'REVIEW')

    def test_write_is_not_read_dependency(self):
        row = self.scan('import mechanics as m\nm.new_value = 1')
        self.assertFalse(row['required'])

    def test_unrelated_module_ignored(self):
        row = self.scan('import other as m\nm.unknown()')
        self.assertFalse(row['required'])

    def test_missing_callback_helpers(self):
        row = self.scan('mechanics._parse_order([])\nmechanics._refresh_prices({})', ('mechanics',))
        result = check.check_contract('CROPS = {}', [row])
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual({item['name'] for item in result['missing_api']}, {'_parse_order', '_refresh_prices'})

    def test_missing_transitive_provider_global(self):
        result = check.check_contract('def _refresh_prices(m):\n    return missing_helper(m)\n', [])
        self.assertEqual(result['undefined_provider_globals'], {'mechanics._refresh_prices': ['missing_helper']})

    def test_nested_provider_global(self):
        result = check.check_contract('def factory():\n    def nested():\n        return absent()\n    return nested\n', [])
        self.assertEqual(result['undefined_provider_globals'], {'mechanics.factory.nested': ['absent']})

    def test_builtin_provider_globals(self):
        result = check.check_contract('def parse(v):\n    return isinstance(v, list) and max(v)\n', [])
        self.assertEqual(result['status'], 'PASS')


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.tar.gz'
        self.runtime = {'mechanics.py': b'X = 1\n', 'main.py': b'import mechanics\n'}
        self.source = {'runtime': {name: {'bytes': len(data), 'sha256': check.sha256(data)}
                                  for name, data in self.runtime.items()}}

    def write(self, rows=None, source=None, extras=()):
        rows = list((self.runtime if rows is None else rows).items())
        rows += [('SOURCE.json', json.dumps(self.source if source is None else source).encode())]
        rows += list(extras)
        with tarfile.open(self.path, 'w:gz') as archive:
            for name, data in rows:
                if isinstance(data, tarfile.TarInfo):
                    archive.addfile(data)
                else:
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))

    def test_report_cannot_overwrite_input(self):
        self.write()
        before = self.path.read_bytes()
        result = subprocess.run([sys.executable, '-B', str(Path(check.__file__)), '--archive', str(self.path), '--report', str(self.path)], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_valid_manifest(self):
        self.write()
        members, info = check.read_archive(self.path)
        self.assertEqual(info['runtime_files_verified'], 2)
        self.assertEqual(members['mechanics.py'], self.runtime['mechanics.py'])

    def test_expected_sha_mismatch(self):
        self.write()
        with self.assertRaisesRegex(check.InvalidArchive, 'SHA256'):
            check.read_archive(self.path, '0' * 64)

    def test_digest_mismatch(self):
        rows = dict(self.runtime, **{'mechanics.py': b'X = 2\n'})
        self.write(rows=rows)
        with self.assertRaisesRegex(check.InvalidArchive, 'digest/size'):
            check.read_archive(self.path)

    def test_missing_manifest_member(self):
        self.write(rows={'mechanics.py': self.runtime['mechanics.py']})
        with self.assertRaisesRegex(check.InvalidArchive, 'membership'):
            check.read_archive(self.path)

    def test_extra_member(self):
        self.write(extras=[('unexpected.py', b'')])
        with self.assertRaisesRegex(check.InvalidArchive, 'membership'):
            check.read_archive(self.path)

    def test_duplicate_member(self):
        self.write(extras=[('main.py', b'')])
        with self.assertRaisesRegex(check.InvalidArchive, 'duplicate'):
            check.read_archive(self.path)

    def test_normalized_duplicate_member(self):
        self.write(extras=[('./main.py', b'')])
        with self.assertRaisesRegex(check.InvalidArchive, 'duplicate'):
            check.read_archive(self.path)

    def test_parent_path(self):
        self.write(extras=[('../outside.py', b'')])
        with self.assertRaisesRegex(check.InvalidArchive, 'unsafe'):
            check.read_archive(self.path)

    def test_absolute_path(self):
        self.write(extras=[('/outside.py', b'')])
        with self.assertRaisesRegex(check.InvalidArchive, 'unsafe'):
            check.read_archive(self.path)

    def test_symlink_member(self):
        symlink = tarfile.TarInfo('link.py')
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = 'mechanics.py'
        self.write(extras=[('link.py', symlink)])
        with self.assertRaisesRegex(check.InvalidArchive, 'non-regular'):
            check.read_archive(self.path)

    def test_nonobject_source(self):
        self.write(source=[])
        with self.assertRaisesRegex(check.InvalidArchive, 'must be an object'):
            check.read_archive(self.path)

    def test_runtime_schema(self):
        self.write(source={'runtime': []})
        with self.assertRaisesRegex(check.InvalidArchive, 'mapping'):
            check.read_archive(self.path)


@unittest.skipUnless(os.environ.get('TITAN_ARCHIVE'), 'Set TITAN_ARCHIVE for the real pinned package')
class ActualPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.members, cls.info = check.read_archive(Path(os.environ['TITAN_ARCHIVE']),
            '820ed99e09ea22b09ab4e412742c654ad7330e266ab25d92fb1997cda91a18be')
        cls.provider = cls.members['mechanics.py'].decode()
        cls.probe = check.consumer_requirements(
            (Path(__file__).parent / 'funded_payback_api_probe.py').read_text(), 'funded_payback_api_probe.py', ('mechanics',))
        source = cls.members['checks/reference/engine/kaggriculture.py'].decode()
        tree = ast.parse(source)
        cls.helper_text = '\n\n'.join(ast.get_source_segment(source, node) for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in {'_parse_order', '_refresh_prices'})

    def test_all_80_runtime_members_match(self):
        self.assertEqual(self.info['runtime_files_verified'], 80)
        self.assertEqual(self.info['archive_bytes'], 302328)

    def test_actual_package_has_the_two_missing_symbols(self):
        result = check.check_contract(self.provider, [self.probe])
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual({item['name'] for item in result['missing_api']}, {'_parse_order', '_refresh_prices'})

    def test_same_official_helpers_in_memory_close_contract(self):
        result = check.check_contract(self.provider + '\n' + self.helper_text, [self.probe])
        self.assertEqual(result['status'], 'PASS')

    def test_helper_only_copy_without_transitive_dependency_fails(self):
        truncated = self.provider.replace('def _shape(func, x, T=None):', 'def removed_shape(func, x, T=None):')
        result = check.check_contract(truncated + '\n' + self.helper_text, [self.probe])
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('_shape', {x for v in result['undefined_provider_globals'].values() for x in v})

    def test_existing_archived_wrapper_closes_actual_probe(self):
        provider, identity = check.selected_provider(self.members, 'reference/titan-history/terminal_mechanics.py')
        result = check.check_contract(provider, [self.probe])
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(identity['base']['sha256'], check.sha256(self.members['mechanics.py']))

    def test_wrapper_without_actual_base_copy_is_rejected(self):
        broken = dict(self.members)
        path = 'reference/titan-history/terminal_mechanics.py'
        broken[path] = broken[path].replace(b'globals().update', b'other().update')
        with self.assertRaisesRegex(check.InvalidArchive, 'recognized'):
            check.selected_provider(broken, path)

    def test_wrapper_override_is_not_silently_resolved(self):
        broken = dict(self.members)
        path = 'reference/titan-history/terminal_mechanics.py'
        broken[path] += b'\ndef market_price(*args):\n    return 0\n'
        with self.assertRaisesRegex(check.InvalidArchive, 'overrides'):
            check.selected_provider(broken, path)

    def test_official_parser_positive_and_rejection_cases(self):
        namespace = {}
        exec(compile(self.provider + '\n' + self.helper_text, '<in-memory-reference-only>', 'exec'), namespace)
        parse = namespace['_parse_order']
        self.assertEqual(parse(['HIRE']), {'type': 'HIRE'})
        self.assertEqual(parse(['BUY_LAND']), {'type': 'BUY_LAND'})
        self.assertEqual(parse(['SELL', 'WHEAT', 3]), {'type': 'SELL', 'item': 'WHEAT', 'remaining': 3})
        for order in (None, [], ['PASS'], ['SELL'], ['SELL', 'WHEAT', 0], ['SELL', 'WHEAT', -2], ['SELL', 'WHEAT', 'bad']):
            with self.subTest(order=order):
                self.assertIsNone(parse(order))
        market = {'inventory': {product: 10000 for product in namespace['PRODUCTS']}, 'prices': {}}
        namespace['_refresh_prices'](market)
        self.assertEqual(set(market['prices']), set(namespace['PRODUCTS']))
        for product in namespace['PRODUCTS']:
            self.assertEqual(market['prices'][product], namespace['market_price'](product, 10000))


if __name__ == '__main__':
    unittest.main(verbosity=2)
