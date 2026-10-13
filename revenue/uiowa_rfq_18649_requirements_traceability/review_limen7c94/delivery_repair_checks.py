#!/usr/bin/env python3
"""Synthetic delivery-contract tests. Execute only explicitly pinned local source."""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from review_limen7c94 import packet, blob

NEW = OLD = None
SOURCE: Path
ORIGINAL: Path


def run_cli(args):
    return subprocess.run([sys.executable, *(['-O'] if sys.flags.optimize else []),
                           str(SOURCE), *map(str, args)], text=True, capture_output=True, timeout=15)


class DeliveryContract(unittest.TestCase):
    def test_semantic_definitions_are_unchanged(self):
        def defs(path):
            return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text()).body
                    if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
        old, new = defs(ORIGINAL), defs(SOURCE)
        for name in ('TraceError', '_index', '_known_text', '_revision', '_validate',
                     'Example', 'render_markdown', '_object', '_constant', 'load'):
            with self.subTest(name=name):
                self.assertEqual(new[name], old[name])

    def test_csv_legacy_prefix_preserved_and_orphan_roundtrips(self):
        p = packet(2)
        p['criteria'][0]['text'] = 'Fictional, "quoted" criterion\nwith unicode: café'
        p['acceptances'].append(dict(p['acceptances'][0], acceptance_id='ORPHAN,"\nΩ',
                                     criterion_id='MISSING,"\nΩ'))
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / name for name in ('old.csv', 'new.csv')]
            OLD.write_sheet([OLD.Example(p)], paths[0])
            NEW.write_sheet([NEW.Example(p)], paths[1])
            tables = []
            for path in paths:
                with path.open(newline='', encoding='utf-8') as f:
                    tables.append(list(csv.reader(f)))
            self.assertEqual([row[:10] for row in tables[1]], tables[0])
            with paths[1].open(newline='', encoding='utf-8') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2, 'orphans must not become invented criteria')
            for row in rows:
                self.assertEqual(row['packet_verdict'], 'NOT_ESTABLISHED')
                self.assertEqual(row['packet_open_criteria'], '0')
                self.assertEqual(row['packet_dangling_link_count'], '1')
                self.assertEqual(json.loads(row['packet_dangling_links']), NEW.Example(p).dangling_links())
                self.assertIn('Resolve', row['packet_follow_up'])

    def test_csv_packet_metadata_stays_with_its_example(self):
        complete, incomplete = packet(), packet()
        complete['example_id'] = 'SYN-COMPLETE'
        incomplete['example_id'] = 'SYN-OPEN'
        incomplete['acceptances'] = []
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'both.csv'
            NEW.write_sheet([NEW.Example(complete), NEW.Example(incomplete)], dest)
            with dest.open(newline='', encoding='utf-8') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r['packet_verdict'] for r in rows], ['EVIDENCED', 'NOT_ESTABLISHED'])
            self.assertEqual([r['packet_open_criteria'] for r in rows], ['0', '1'])
            self.assertEqual([r['packet_dangling_links'] for r in rows], ['[]', '[]'])

    def test_every_collision_is_checked_before_other_outputs_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'traceability_sheet.csv').write_bytes(b'PRIOR-SHEET')
            (root/'traceability.json').write_bytes(b'PRIOR-JSON')
            source = root/'traceability_report.md'
            source.write_text(json.dumps(packet()))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            run = run_cli(['--input', source, '--outdir', root])
            self.assertEqual(run.returncode, 2)
            self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()}, before)
            self.assertNotIn('wrote 3 files', run.stdout)
            self.assertNotIn('Traceback', run.stderr)

    def test_alias_of_second_input_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root/'one.json'
            second = root/'two.json'
            for p in (first, second):
                p.write_text(json.dumps(packet()))
            out = root/'out'
            out.mkdir()
            os.link(second, out/'traceability.json')
            expected = second.read_bytes()
            run = run_cli(['--input', first, second, '--outdir', out])
            self.assertEqual(run.returncode, 2)
            self.assertEqual(second.read_bytes(), expected)
            self.assertFalse((out/'traceability_sheet.csv').exists())

    def test_parent_directory_symlink_alias_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root/'real'
            real.mkdir()
            alias = root/'alias'
            alias.symlink_to(real, target_is_directory=True)
            source = real/'traceability.json'
            source.write_text(json.dumps(packet()))
            before = source.read_bytes()
            run = run_cli(['--input', source, '--outdir', alias])
            self.assertEqual(run.returncode, 2)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(len(list(real.iterdir())), 1)

    def test_output_product_aliases_are_refused(self):
        for kind in ('symlink', 'hardlink'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root/'source.json'
                source.write_text(json.dumps(packet()))
                out = root/'out'
                out.mkdir()
                first = out/'traceability_sheet.csv'
                second = out/'traceability_report.md'
                first.write_bytes(b'PRIOR-REPORT')
                if kind == 'symlink':
                    second.symlink_to(first)
                else:
                    os.link(first, second)
                run = run_cli(['--input', source, '--outdir', out])
                self.assertEqual(run.returncode, 2)
                self.assertEqual(first.read_bytes(), b'PRIOR-REPORT')
                self.assertEqual(second.read_bytes(), b'PRIOR-REPORT')
                self.assertFalse((out/'traceability.json').exists())

    def test_ordinary_regeneration_remains_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'source.json'
            source.write_text(json.dumps(packet()))
            out = root/'out'
            args = ['--input', source, '--outdir', out]
            self.assertEqual(run_cli(args).returncode, 0)
            before = {p.name:p.read_bytes() for p in out.iterdir()}
            self.assertEqual(run_cli(args).returncode, 0)
            self.assertEqual({p.name:p.read_bytes() for p in out.iterdir()}, before)
            self.assertEqual(len(before), 3)

    def test_output_path_error_is_diagnosed_without_source_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'source.json'
            source.write_text(json.dumps(packet()))
            out = root/'not-a-directory'
            out.write_bytes(b'PRIOR')
            before = source.read_bytes()
            run = run_cli(['--input', source, '--outdir', out])
            self.assertEqual(run.returncode, 2)
            self.assertNotIn('Traceback', run.stderr)
            self.assertEqual(out.read_bytes(), b'PRIOR')
            self.assertEqual(source.read_bytes(), before)


def main():
    global NEW, OLD, SOURCE, ORIGINAL
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--expect-blob', default='481b5325cb1f28192b385a57f4cb447da0c3652e')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    SOURCE, ORIGINAL = args.source.resolve(strict=True), args.original.resolve(strict=True)
    for path, expected in ((SOURCE,args.expect_blob),(ORIGINAL,'d625dbbe73729638e1dfbe887a3c2c7a607b0524')):
        if blob(path.read_bytes()) != expected:
            parser.error('source identity mismatch; no tested module executed')
    if args.out.exists() or args.out.is_symlink():
        parser.error('receipt exists; choose a new path')
    def load(path, name):
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    OLD,NEW=load(ORIGINAL,'limen_original042'),load(SOURCE,'limen_repaired042')
    log=io.StringIO()
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DeliveryContract))
    receipt={'schema':'uiowa042-delivery-repair-review/v1','synthetic':True,'source_git_blob':blob(SOURCE.read_bytes()),
             'original_git_blob':blob(ORIGINAL.read_bytes()),'test_git_blob':blob(Path(__file__).read_bytes()),
             'fixture_helper_git_blob':blob((Path(__file__).parent/'review_limen7c94.py').read_bytes()),
             'optimization':sys.flags.optimize,'tests_run':result.testsRun,'failures':len(result.failures),
             'errors':len(result.errors),'skips':len(result.skipped),'passed':result.wasSuccessful(),'log':log.getvalue(),
             'limits':['Stable filesystem preflight; no race-proof or atomic-publication claim.',
                       'Sparse exact-source synthetic tests, not original-author, hosted or full-repository tests.']}
    with args.out.open('x',encoding='utf-8') as f:
        json.dump(receipt,f,indent=2,sort_keys=True)
        f.write('\n')
    print(log.getvalue(),end='')
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':
    raise SystemExit(main())
