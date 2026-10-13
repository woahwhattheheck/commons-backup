#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Self-contained report provenance and publication regressions.

All suite files generated here are synthetic parser fixtures, not game results.
Set ATLAS_REPORTER_SOURCE to exercise the same tests against an original source.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import select
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(os.environ.get('ATLAS_REPORTER_SOURCE',
                             str(Path(__file__).with_name('build_combined_report.py'))))
spec = importlib.util.spec_from_file_location('publication_reporter_under_test', SOURCE)
REPORTER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(REPORTER)


def make_inputs(directory: Path) -> None:
    directory.mkdir()
    paths = {suite[2] for suite in REPORTER.SUITES}
    paths.update(REPORTER.LAB + name for name in
                 ('selected_action_sell.py', 'selected_sell_core.py', 'mechanics.py',
                  'reference/decision/decision.py', 'ordered_selected_sell.py',
                  'reference/evaluator/evaluate.py', 'reference/evaluator/loader.py',
                  'reference/engine/kaggriculture.py', 'reference/engine/kaggriculture.json',
                  'reference/engine/utils.py'))
    paths.add(REPORTER.PROJECTION + 'projection.py')
    import hashlib
    digests = {name: hashlib.sha256(name.encode()).hexdigest() for name in paths}
    snapshot = dict(checkout='1' * 40, run_id='17', attempt='1', python='fixture',
                    files={name: dict(sha256=sha) for name, sha in digests.items()})
    (directory / 'SOURCE-SNAPSHOT.json').write_text(json.dumps(snapshot))
    engine = {name: digests[REPORTER.LAB + 'reference/engine/' + name]
              for name in ('kaggriculture.py', 'kaggriculture.json', 'utils.py')}
    for _, log, _, _, _ in REPORTER.SUITES:
        (directory / log).write_text('Ran 1 test in 0.001s\n\nOK\n')
    common = dict(failures=0, errors=0, successful=True)
    projection = dict(common, tests_run=1,
                      seller_sha256=digests[REPORTER.LAB + 'selected_action_sell.py'],
                      projection_sha256=digests[REPORTER.PROJECTION + 'projection.py'],
                      engine_sha256=engine, differential_cases=0, interpreter_transitions=0)
    market = dict(common, test_methods=1, engine_sha256=engine, official_market_cases=0,
                  sources={name: digests[REPORTER.LAB + name] for name in
                           ('selected_action_sell.py', 'selected_sell_core.py', 'mechanics.py',
                            'reference/decision/decision.py')})
    loader = dict(common, test_methods=1, official_market_cases=0,
                  source_sha256={'checker': digests[REPORTER.MARKET + 'check_market_contracts.py'],
                                 'evaluator': digests[REPORTER.LAB + 'reference/evaluator/evaluate.py'],
                                 'loader': digests[REPORTER.LAB + 'reference/evaluator/loader.py']})
    for name, value in (('projection', projection), ('market', market), ('loader', loader)):
        (directory / (name + '-results.json')).write_text(json.dumps(value))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / 'inputs'
        make_inputs(self.inputs)
        self.output = self.root / 'report.json'
        self.old = b'{"previous":"complete"}\n'
        self.output.write_bytes(self.old)
        self.assertTrue(REPORTER.build_report(self.inputs)['successful'])

    def context(self, **changes):
        value = dict(event='pull_request', event_sha='1' * 40,
                     pull_request_head='2' * 40, pull_request_base='3' * 40,
                     checkout_semantics='pull_request_merge')
        value.update(changes)
        return value

    def set_context(self, value):
        path = self.inputs / 'SOURCE-SNAPSHOT.json'
        snapshot = json.loads(path.read_text())
        snapshot['source_context'] = value
        path.write_text(json.dumps(snapshot))

    def run_cli(self):
        return REPORTER.main(['--directory', str(self.inputs), '--output', str(self.output)])

    def test_legacy_snapshot_keeps_optional_context_absent(self):
        report = REPORTER.build_report(self.inputs)
        self.assertTrue(report['successful'])
        self.assertNotIn('source_context', report)
        self.assertEqual(report['total_tests'], 6)

    def test_merge_context_preserves_distinct_head_base_and_extensions(self):
        context = self.context(extra={'note': 'retained provenance'})
        self.set_context(context)
        report = REPORTER.build_report(self.inputs)
        self.assertTrue(report['successful'], report['problems'])
        self.assertEqual(report.get('source_context'), context)
        self.assertNotEqual(report['checkout'], context['pull_request_head'])

    def test_event_commit_context_round_trips(self):
        context = self.context(event='workflow_dispatch', checkout_semantics='event_commit',
                               pull_request_head=None, pull_request_base=None)
        self.set_context(context)
        report = REPORTER.build_report(self.inputs)
        self.assertTrue(report['successful'])
        self.assertEqual(report.get('source_context'), context)

    def test_conflicting_event_commit_is_not_complete(self):
        self.set_context(self.context(event_sha='f' * 40))
        report = REPORTER.build_report(self.inputs)
        self.assertFalse(report['complete'])
        self.assertFalse(report['successful'])
        self.assertTrue(any('event_sha' in p for p in report['problems']))
        self.assertEqual(report['observed_tests'], 6)

    def test_invalid_event_hashes_are_not_complete(self):
        for value in (None, 17, '', 'z' * 40, '1' * 39, '1' * 41):
            with self.subTest(value=value):
                self.set_context(self.context(event_sha=value))
                self.assertFalse(REPORTER.build_report(self.inputs)['successful'])

    def test_missing_or_invalid_pr_refs_are_not_complete(self):
        for key in ('pull_request_head', 'pull_request_base'):
            for value in (None, 'short', 123, ['2' * 40]):
                with self.subTest(key=key, value=value):
                    self.set_context(self.context(**{key: value}))
                    self.assertFalse(REPORTER.build_report(self.inputs)['successful'])

    def test_nonobject_context_is_preserved_as_failure_evidence(self):
        for value in (None, [], 'bad', 0):
            with self.subTest(value=value):
                self.set_context(value)
                report = REPORTER.build_report(self.inputs)
                self.assertFalse(report['successful'])
                self.assertIn('source_context', report)
                self.assertEqual(report['source_context'], value)

    def test_invalid_event_names_are_not_complete(self):
        for event in ('', '  ', None, 17):
            with self.subTest(event=event):
                self.set_context(self.context(event=event))
                self.assertFalse(REPORTER.build_report(self.inputs)['successful'])

    def test_unsupported_context_semantics_are_not_complete(self):
        for semantics in ('unknown', None, 7, []):
            with self.subTest(semantics=semantics):
                self.set_context(self.context(checkout_semantics=semantics))
                self.assertFalse(REPORTER.build_report(self.inputs)['successful'])

    def test_event_commit_does_not_claim_merge_refs(self):
        self.set_context(self.context(checkout_semantics='event_commit'))
        self.assertFalse(REPORTER.build_report(self.inputs)['successful'])

    def test_report_does_not_change_input_files(self):
        self.set_context(self.context())
        before = {p.name: p.read_bytes() for p in self.inputs.iterdir()}
        REPORTER.build_report(self.inputs)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.inputs.iterdir()})

    def test_cli_preserves_context_and_status(self):
        context = self.context()
        self.set_context(context)
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(json.loads(self.output.read_text()).get('source_context'), context)
        self.set_context(self.context(event_sha='4' * 40))
        self.assertEqual(self.run_cli(), 1)
        self.assertFalse(json.loads(self.output.read_text())['successful'])

    def test_success_replaces_complete_file_and_existing_mode(self):
        self.output.chmod(0o640)
        self.assertEqual(self.run_cli(), 0)
        self.assertTrue(json.loads(self.output.read_text())['successful'])
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o640)
        self.assertEqual(list(self.root.glob('.report.json.*.tmp')), [])

    def test_new_target_is_created(self):
        self.output.unlink()
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(json.loads(self.output.read_text())['total_tests'], 6)

    @unittest.skipUnless(os.name == 'posix', 'POSIX umask fixture')
    def test_new_output_preserves_caller_umask(self):
        self.output.unlink()
        previous = os.umask(0o027)
        try:
            self.assertEqual(self.run_cli(), 0)
        finally:
            os.umask(previous)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o640)

    def test_replace_failure_preserves_original_exception_and_bytes(self):
        failure = OSError('replace witness')
        with patch('os.replace', side_effect=failure):
            with self.assertRaises(OSError) as caught:
                self.run_cli()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.output.read_bytes(), self.old)
        self.assertEqual(list(self.root.glob('.report.json.*.tmp')), [])

    def test_fsync_failure_preserves_original_exception_and_bytes(self):
        failure = OSError('fsync witness')
        with patch('os.fsync', side_effect=failure):
            with self.assertRaises(OSError) as caught:
                self.run_cli()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.output.read_bytes(), self.old)
        self.assertEqual(list(self.root.glob('.report.json.*.tmp')), [])

    def test_fdopen_failure_closes_staging_descriptor(self):
        failure = OSError('fdopen witness')
        captured = []
        def fail(fd, *args, **kwargs):
            captured.append(fd)
            raise failure
        with patch('os.fdopen', side_effect=fail):
            with self.assertRaises(OSError) as caught:
                self.run_cli()
        self.assertIs(caught.exception, failure)
        with self.assertRaises(OSError): os.fstat(captured[0])
        self.assertEqual(self.output.read_bytes(), self.old)
        self.assertEqual(list(self.root.glob('.report.json.*.tmp')), [])

    def test_flush_failure_preserves_previous_report(self):
        real_fdopen = os.fdopen
        failure = OSError('flush witness')
        class FlushWriter:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): return self.stream.__exit__(*args)
            def flush(self): raise failure
            def __getattr__(self, name): return getattr(self.stream, name)
        def fdopen(*args, **kwargs): return FlushWriter(real_fdopen(*args, **kwargs))
        with patch('os.fdopen', side_effect=fdopen):
            with self.assertRaises(OSError) as caught:
                self.run_cli()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.output.read_bytes(), self.old)
        self.assertEqual(list(self.root.glob('.report.json.*.tmp')), [])

    def test_short_write_never_replaces_target(self):
        real_fdopen = os.fdopen
        class ShortWriter:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): return self.stream.__exit__(*args)
            def write(self, value): return self.stream.write(value[:17])
            def __getattr__(self, name): return getattr(self.stream, name)
        def fdopen(*args, **kwargs): return ShortWriter(real_fdopen(*args, **kwargs))
        with patch('os.fdopen', side_effect=fdopen):
            with self.assertRaisesRegex(OSError, 'short report write'):
                self.run_cli()
        self.assertEqual(self.output.read_bytes(), self.old)
        self.assertEqual(list(self.root.glob('.report.json.*.tmp')), [])

    def test_interrupt_during_replace_preserves_target(self):
        failure = KeyboardInterrupt('interrupt witness')
        with patch('os.replace', side_effect=failure):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.run_cli()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.output.read_bytes(), self.old)

    def test_cleanup_failure_does_not_mask_write_error(self):
        failure = OSError('first failure')
        with patch('os.replace', side_effect=failure), patch.object(Path, 'unlink', side_effect=OSError('cleanup')):
            with self.assertRaises(OSError) as caught:
                self.run_cli()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.output.read_bytes(), self.old)

    def test_serialization_error_leaves_target_untouched(self):
        failure = ValueError('encode witness')
        # Input decoding is not patched; the only dumps call is final encoding.
        with patch.object(REPORTER.json, 'dumps', side_effect=failure):
            with self.assertRaises(ValueError) as caught:
                self.run_cli()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.output.read_bytes(), self.old)

    @unittest.skipUnless(os.name == 'posix', 'POSIX symlink fixture')
    def test_existing_symlink_keeps_link_and_replaces_target(self):
        actual = self.root / 'target.json'
        actual.write_bytes(self.old)
        self.output.unlink()
        self.output.symlink_to(actual.name)
        self.assertEqual(self.run_cli(), 0)
        self.assertTrue(self.output.is_symlink())
        self.assertTrue(json.loads(actual.read_text())['successful'])

    def test_missing_parent_is_not_created(self):
        self.output = self.root / 'absent' / 'report.json'
        with self.assertRaises(FileNotFoundError): self.run_cli()
        self.assertFalse(self.output.parent.exists())

    def test_directory_target_and_contents_survive(self):
        self.output.unlink()
        self.output.mkdir()
        retained = self.output / 'keep'
        retained.write_bytes(self.old)
        with self.assertRaises(OSError): self.run_cli()
        self.assertEqual(retained.read_bytes(), self.old)
        self.assertEqual(list(self.root.glob('.report.json.*.tmp')), [])

    def test_stdout_mode_preserves_output_shape(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = REPORTER.main(['--directory', str(self.inputs)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['total_tests'], 6)
        self.assertEqual(self.output.read_bytes(), self.old)

    def test_incomplete_report_is_published_with_failure_exit(self):
        (self.inputs / 'market-tests.log').unlink()
        self.assertEqual(self.run_cli(), 1)
        report = json.loads(self.output.read_text())
        self.assertFalse(report['complete'])
        self.assertTrue(report['problems'])

    def killed_writer(self):
        code = r'''
import importlib.util, os, sys, time
from pathlib import Path
spec=importlib.util.spec_from_file_location('killed_reporter',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
output=Path(sys.argv[3])
def stop():
    print('READY',flush=True)
    while True: time.sleep(1)
real_write=Path.write_text
def old_write(path,text,**kwargs):
    if path==output:
        with path.open('wb') as f:
            f.write(text.encode()[:17]);f.flush();os.fsync(f.fileno())
        stop()
    return real_write(path,text,**kwargs)
Path.write_text=old_write
os.replace=lambda *args:stop()
m.main(['--directory',sys.argv[2],'--output',str(output)])
'''
        process = subprocess.Popen([sys.executable, '-c', code, str(SOURCE),
                                    str(self.inputs), str(self.output)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ready, _, _ = select.select([process.stdout], [], [], 5)
            self.assertTrue(ready, 'writer did not reach publication boundary')
            self.assertEqual(process.stdout.readline().strip(), 'READY')
            process.kill()
            process.communicate(timeout=5)
        finally:
            if process.poll() is None: process.kill()
            process.communicate(timeout=5)

    @unittest.skipUnless(os.name == 'posix', 'POSIX controlled SIGKILL')
    def test_sigkill_before_commit_preserves_existing_complete_file(self):
        self.killed_writer()
        self.assertEqual(self.output.read_bytes(), self.old)

    @unittest.skipUnless(os.name == 'posix', 'POSIX controlled SIGKILL')
    def test_sigkill_before_commit_does_not_publish_new_partial_file(self):
        self.output.unlink()
        self.killed_writer()
        self.assertFalse(self.output.exists())

    def test_unicode_context_is_preserved(self):
        context = self.context(note='café 日本語')
        self.set_context(context)
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(json.loads(self.output.read_text()).get('source_context'), context)


if __name__ == '__main__':
    unittest.main(verbosity=2)
