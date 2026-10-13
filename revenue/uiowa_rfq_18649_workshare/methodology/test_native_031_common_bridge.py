#!/usr/bin/env python3
"""Exact-source integration for GRANITE's canonical packet; no document recheck."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('uiowa031_bridge_subject', HERE / 'native_031_common_bridge.py')
if spec is None or spec.loader is None:
    raise ImportError('missing bridge')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
FIXTURE = HERE / 'native-031-fixture'


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.manifest = b.read_native_csv((FIXTURE / 'manifest.csv').read_bytes().decode(), b.MANIFEST_REQUIRED)
        self.register = b.read_native_csv((FIXTURE / 'register.csv').read_bytes().decode(), b.NATIVE_REQUIRED)

    def bridge(self):
        return b.native_to_common(self.manifest, self.register)

    def test_actual_source_blob_bindings(self):
        for name, expected in [('manifest.csv', '5a64f102860d92d5f3261282daf067f1444c83c6'),
                               ('register.csv', '0becca45433eceaacb91882aa66533ab998289e0')]:
            data = (FIXTURE / name).read_bytes()
            actual = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            self.assertEqual(actual, expected)

    def test_original_custody_gap_reproduces(self):
        errors = b.m._validator.validate(FIXTURE / 'register.csv')
        self.assertEqual(errors, ["missing required columns: ['content_digest', 'custodian_or_owner']"])

    def test_actual_register_passes_current_common_after_mapping(self):
        common = self.bridge()['common_register']
        self.assertEqual(b.m._validator.validate_records(common['columns'], common['rows']), [])
        self.assertEqual(len(common['rows']), 8)
        self.assertEqual(len({(r['group'], r['area']) for r in common['rows']}), 5)

    def test_actual_native_tables_round_trip_exact(self):
        result = b.loads(b.dumps(self.bridge()))
        manifest, register = b.common_to_native(result)
        self.assertEqual(manifest, self.manifest)
        self.assertEqual(register, self.register)
        # This specific original packet uses the same deterministic CSV dialect.
        self.assertEqual(b.render_table(manifest).encode(), (FIXTURE / 'manifest.csv').read_bytes())
        self.assertEqual(b.render_table(register).encode(), (FIXTURE / 'register.csv').read_bytes())

    def test_multicell_documents_remain_one_manifest_row(self):
        result = self.bridge()
        self.assertEqual(len(result['manifest']['rows']), 6)
        cells = {}
        for row in result['common_register']['rows']:
            cells.setdefault(row['source_id'], set()).add((row['group'], row['area']))
        self.assertEqual(sorted(s for s,c in cells.items() if len(c) > 1), ['SRC-SYN-005', 'SRC-SYN-006'])

    def test_exact_scope_claims_confidence_missingness_retained(self):
        result = self.bridge()['common_register']['rows']
        for original, mapped in zip(self.register['rows'], result):
            for column in self.register['columns']:
                self.assertEqual(mapped[column], original[column])
        self.assertEqual(result[-1]['confidence'], 'NOT_EVIDENCED')
        self.assertEqual(result[-1]['evidence_state'], 'NO_EVIDENCE_OBSERVED')

    def test_declared_owner_and_digest_not_fetched_or_promoted(self):
        result = self.bridge()
        for field in b.LIMITS:
            self.assertIs(result[field], False)
        first = result['common_register']['rows'][0]
        self.assertEqual(first['custodian_or_owner'], self.manifest['rows'][0]['owner'])
        self.assertEqual(first['content_digest'], 'sha256:' + self.manifest['rows'][0]['sha256'])
        self.assertEqual(first['source_ref'], 'ESS Branch Protection Standard v3')

    def test_same_source_id_cannot_choose_arbitrary_manifest_row(self):
        self.manifest['rows'].append(copy.deepcopy(self.manifest['rows'][0]))
        with self.assertRaisesRegex(b.m.RegisterError, 'unambiguous'):
            self.bridge()

    def test_missing_source_has_no_guessed_join(self):
        self.register['rows'][0]['source_id'] = 'not-in-manifest'
        with self.assertRaisesRegex(b.m.RegisterError, 'unresolved exact'):
            self.bridge()

    def test_whitespace_not_normalized_into_other_identity(self):
        self.register['rows'][0]['source_id'] += ' '
        with self.assertRaises(b.m.RegisterError):
            self.bridge()

    def test_native_custody_if_supplied_must_agree(self):
        self.register['columns'].extend(b.DERIVED)
        docs = {d['source_id']: d for d in self.manifest['rows']}
        for row in self.register['rows']:
            doc = docs[row['source_id']]
            row.update(custodian_or_owner=doc['owner'], content_digest='sha256:' + doc['sha256'])
        self.assertEqual(self.bridge()['derived_columns'], [])
        self.register['rows'][0]['custodian_or_owner'] = 'conflicting owner'
        with self.assertRaisesRegex(b.m.RegisterError, 'conflicts'):
            self.bridge()

    def test_empty_digest_or_owner_not_filled_in(self):
        for field in ('sha256', 'owner'):
            old = self.manifest['rows'][0][field]
            self.manifest['rows'][0][field] = ''
            with self.subTest(field=field), self.assertRaises(b.m.RegisterError):
                self.bridge()
            self.manifest['rows'][0][field] = old

    def test_unknown_manifest_and_register_fields_preserved(self):
        self.manifest['columns'].insert(0, 'local_annotation')
        for doc in self.manifest['rows']:
            doc['local_annotation'] = 'literal\r\n"quoted",値'
        self.register['columns'].append('local_extension')
        for row in self.register['rows']:
            row['local_extension'] = '0007.0'
        self.assertEqual(b.common_to_native(b.loads(b.dumps(self.bridge()))), (self.manifest, self.register))

    def test_unused_document_retained(self):
        extra = copy.deepcopy(self.manifest['rows'][0])
        extra['source_id'] = 'UNREFERENCED-SYNTHETIC-DOC'
        self.manifest['rows'].append(extra)
        self.assertEqual(len(self.bridge()['manifest']['rows']), 7)

    def test_derived_digest_tamper_is_rejected(self):
        result = self.bridge()
        result['common_register']['rows'][0]['content_digest'] = 'sha256:' + 'f'*64
        with self.assertRaisesRegex(b.m.RegisterError, 'recomputation'):
            b.common_to_native(result)

    def test_false_authority_cannot_be_relabelled(self):
        for value in (True, 0, 'false', None):
            result = self.bridge()
            result['assessment_authority'] = value
            with self.subTest(value=value), self.assertRaises(b.m.RegisterError):
                b.common_to_native(result)

    def test_extra_bundle_field_is_not_dropped(self):
        result = self.bridge()
        result['ignored_data'] = 'not lost'
        with self.assertRaises(b.m.RegisterError):
            b.common_to_native(result)

    def test_duplicate_native_header_is_rejected(self):
        text = (FIXTURE/'register.csv').read_bytes().decode()
        text = text.replace('practice_supported', 'source_id', 1)
        with self.assertRaises(b.m.RegisterError):
            b.read_native_csv(text, b.NATIVE_REQUIRED)

    def test_extra_missing_native_cells_rejected(self):
        text = (FIXTURE/'register.csv').read_bytes().decode()
        for first_line in (text.splitlines()[1] + ',surplus', ','.join(text.splitlines()[1].split(',')[:-1])):
            with self.assertRaises(b.m.RegisterError):
                b.read_native_csv(text.splitlines()[0] + '\r\n' + first_line + '\r\n', b.NATIVE_REQUIRED)

    def test_duplicate_json_keys_rejected(self):
        text = b.dumps(self.bridge()).replace('"schema":', '"schema":"wrong","schema":', 1)
        with self.assertRaisesRegex(b.m.RegisterError, 'duplicate'):
            b.loads(text)

    def test_array_envelope_rejected(self):
        with self.assertRaises(b.m.RegisterError):
            b.loads('[]')

    def test_cli_full_native_round_trip_both_interpreters(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for optimized in (False, True):
                command = [sys.executable] + (['-O'] if optimized else []) + [str(HERE/'native_031_common_bridge.py')]
                bundle = out/f'bundle-{optimized}.json'
                proc = subprocess.run(command + ['import', str(FIXTURE), str(bundle)], capture_output=True, text=True, timeout=15)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                for op, name in [('export-manifest', 'manifest.csv'), ('export-register', 'register.csv'), ('export-common', 'common.csv')]:
                    target = out/f'{optimized}-{name}'
                    proc = subprocess.run(command + [op, str(bundle), str(target)], capture_output=True, text=True, timeout=15)
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    if name == 'common.csv':
                        self.assertEqual(b.m._validator.validate(target), [])
                    else:
                        self.assertEqual(target.read_bytes(), (FIXTURE/name).read_bytes())
            self.assertEqual((out/'bundle-False.json').read_bytes(), (out/'bundle-True.json').read_bytes())

    def test_cli_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'keep.json'
            out.write_text('keep')
            proc = subprocess.run([sys.executable, str(HERE/'native_031_common_bridge.py'), 'import', str(FIXTURE), str(out)],
                                  capture_output=True, text=True, timeout=15)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(out.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
