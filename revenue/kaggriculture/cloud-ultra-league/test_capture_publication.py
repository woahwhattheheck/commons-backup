"""Capture publication with real gzip files and synthetic evaluators, never games."""
import argparse
import contextlib
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import run_league as driver


class CapturePublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def paths(self, name):
        folder = self.root / name
        folder.mkdir()
        return folder / 'trajectory.jsonl.gz.partial', folder / 'trajectory.jsonl.gz'

    def compressed(self, path, payload):
        with path.open('xb') as raw:
            with gzip.GzipFile(filename='trajectory.jsonl.gz', mode='wb',
                               fileobj=raw, compresslevel=1) as stream:
                stream.write(payload)

    def frames(self, count):
        return b''.join(json.dumps({'transition': i, 'state': []}).encode() + b'\n'
                        for i in range(count))

    def configuration(self, name, evaluator='synthetic'):
        folder = self.root / name
        folder.mkdir()
        config = folder / 'config.json'
        output = folder / 'output'
        config.write_text(json.dumps({
            'evaluator': str(evaluator), 'engine': 'synthetic', 'loader': 'synthetic',
            'candidate': 'synthetic', 'opponents': {'synthetic': 'synthetic'},
            'rng_seed': 0, 'action_timeout': 1, 'startup_timeout': 1,
            'game_timeout': 1, 'jobs': 1, 'output': str(output),
            'cells': [{'id': 'cell-1', 'seed': 11, 'seat': 0, 'opponent': 'synthetic'}],
        }), encoding='utf-8')
        return argparse.Namespace(config=str(config), cell='cell-1'), output / 'cell-1'

    def evaluator(self, frames=3, failed=False, interrupt=False):
        class Engine:
            specification = {}

            def interpreter(self, state, env):
                return state

        failure = {'kind': 'synthetic_timeout', 'seat': 0, 'step': frames} if failed else None

        def play(engine, specs, cache, loader, seed, seat, *args):
            for _ in range(frames):
                engine.interpreter([], None)
            if interrupt:
                raise KeyboardInterrupt('synthetic capture interruption')
            return {'seed': seed, 'candidate_seat': seat,
                    'status': 'failed' if failed else 'complete',
                    'scores': None if failed else [1, 0], 'failure': failure,
                    'wall_seconds': 0.125, 'steps': frames}

        return SimpleNamespace(Actor=type('Actor', (), {}),
                               get_engine=lambda *args: (Engine(), {}), play=play)

    def invoke(self, args, evaluator):
        with mock.patch.object(driver, 'load_evaluator', return_value=evaluator):
            with contextlib.redirect_stdout(io.StringIO()):
                return driver.cell(args)

    def test_real_gzip_publish_roundtrip_including_empty_capture(self):
        for count in (0, 3):
            with self.subTest(count=count):
                partial, final = self.paths('roundtrip-' + str(count))
                payload = self.frames(count)
                self.compressed(partial, payload)
                before = partial.read_bytes()
                digest = driver.publish_trajectory(partial, final, count)
                self.assertFalse(partial.exists())
                self.assertEqual(final.read_bytes(), before)
                self.assertEqual(gzip.decompress(final.read_bytes()), payload)
                self.assertEqual(digest, hashlib.sha256(before).hexdigest())

    def test_bad_gzip_and_frame_contract_preserve_partial(self):
        cases = [
            ('truncated-footer', self.frames(3), 3),
            ('bad-crc', self.frames(3), 3),
            ('missing-index', b'{"state":[]}\n', 1),
            ('bool-index', b'{"transition":false}\n', 1),
            ('float-index', b'{"transition":0.0}\n', 1),
            ('string-index', b'{"transition":"0"}\n', 1),
            ('duplicate-index', b'{"transition":0}\n{"transition":0}\n', 2),
            ('gap-index', b'{"transition":0}\n{"transition":2}\n', 2),
            ('nonobject', b'[]\n', 1),
            ('invalid-json', b'{\n', 1),
            ('invalid-utf8', b'\xff\n', 1),
            ('count-mismatch', self.frames(2), 3),
            ('unexpected-frame', self.frames(1), 0),
        ]
        for name, payload, count in cases:
            with self.subTest(case=name):
                partial, final = self.paths(name)
                self.compressed(partial, payload)
                raw = bytearray(partial.read_bytes())
                if name == 'truncated-footer':
                    partial.write_bytes(raw[:-4])
                elif name == 'bad-crc':
                    raw[-8] ^= 1
                    partial.write_bytes(raw)
                before = partial.read_bytes()
                with self.assertRaises((ValueError, OSError, EOFError)):
                    driver.publish_trajectory(partial, final, count)
                self.assertFalse(final.exists())
                self.assertEqual(partial.read_bytes(), before)

    def test_sync_and_rename_faults_retain_the_available_evidence(self):
        for stage in ('file-sync', 'rename', 'directory-sync'):
            with self.subTest(stage=stage):
                partial, final = self.paths(stage)
                self.compressed(partial, self.frames(2))
                before = partial.read_bytes()
                real_fsync = driver.os.fsync
                sync_calls = []

                def sync(fd):
                    sync_calls.append(fd)
                    target = 1 if stage == 'file-sync' else 2
                    if stage != 'rename' and len(sync_calls) == target:
                        raise OSError('synthetic ' + stage)
                    return real_fsync(fd)

                with contextlib.ExitStack() as stack:
                    stack.enter_context(mock.patch.object(driver.os, 'fsync', side_effect=sync))
                    if stage == 'rename':
                        stack.enter_context(mock.patch.object(Path, 'replace',
                            side_effect=OSError('synthetic rename')))
                    with self.assertRaisesRegex(OSError, 'synthetic ' + stage):
                        driver.publish_trajectory(partial, final, 2)
                promoted = stage == 'directory-sync'
                self.assertEqual(final.exists(), promoted)
                self.assertEqual(partial.exists(), not promoted)
                self.assertEqual((final if promoted else partial).read_bytes(), before)

    def test_cell_preserves_header_hash_empty_and_failed_prefix(self):
        for count, failed in ((0, False), (3, False), (2, True)):
            with self.subTest(count=count, failed=failed):
                args, folder = self.configuration('cell-%s-%s' % (count, failed))
                self.assertEqual(self.invoke(args, self.evaluator(count, failed)), int(failed))
                result = json.loads((folder / 'result.json').read_text())
                final = folder / 'trajectory.jsonl.gz'
                raw = final.read_bytes()
                rows = [json.loads(line) for line in gzip.decompress(raw).splitlines()]
                self.assertEqual([row['transition'] for row in rows], list(range(count)))
                self.assertEqual(result['recorded_transitions'], count)
                self.assertEqual(result['trajectory_sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(result['wall_seconds'], 0.125)
                self.assertEqual(result['status'], 'failed' if failed else 'complete')
                self.assertEqual(result['failure'],
                    {'kind': 'synthetic_timeout', 'seat': 0, 'step': count} if failed else None)
                self.assertFalse((folder / 'trajectory.jsonl.gz.partial').exists())
                self.assertFalse((folder / 'CAPTURE-ERROR.json').exists())
                legacy_dir = folder / 'legacy'
                legacy_dir.mkdir()
                legacy = legacy_dir / final.name
                with gzip.open(legacy, 'wt', encoding='utf-8', compresslevel=1) as stream:
                    stream.write('')
                previous = legacy.read_bytes()
                self.assertTrue(raw[3] & 8)
                self.assertTrue(previous[3] & 8)
                self.assertEqual(raw[10:].split(b'\0', 1)[0], previous[10:].split(b'\0', 1)[0])

    def test_cell_io_faults_write_diagnostics_without_success_result(self):
        for stage in ('recording', 'publishing', 'result'):
            with self.subTest(stage=stage):
                args, folder = self.configuration('fault-' + stage)
                real_write = driver.write_json

                def write(path, value):
                    if path.name == 'result.json':
                        self.assertTrue((folder / 'trajectory.jsonl.gz').exists())
                        raise OSError('synthetic result write')
                    return real_write(path, value)

                with contextlib.ExitStack() as stack:
                    if stage == 'recording':
                        stack.enter_context(mock.patch.object(driver.gzip.GzipFile, 'write',
                            side_effect=OSError('synthetic compressed write')))
                    elif stage == 'publishing':
                        stack.enter_context(mock.patch.object(driver, 'publish_trajectory',
                            side_effect=OSError('synthetic publication')))
                    else:
                        stack.enter_context(mock.patch.object(driver, 'write_json', side_effect=write))
                    with self.assertRaisesRegex(OSError, 'synthetic'):
                        self.invoke(args, self.evaluator(failed=True))
                error = json.loads((folder / 'CAPTURE-ERROR.json').read_text())
                self.assertEqual(error['error_type'], 'OSError')
                self.assertEqual(error['stage'], stage)
                self.assertFalse((folder / 'result.json').exists())
                self.assertEqual((folder / 'trajectory.jsonl.gz').exists(), stage == 'result')
                self.assertEqual((folder / 'trajectory.jsonl.gz.partial').exists(), stage != 'result')
                if error['evaluator_result'] is not None:
                    self.assertEqual(error['evaluator_result']['failure'],
                                     {'kind': 'synthetic_timeout', 'seat': 0, 'step': 3})

    def test_existing_partial_is_never_truncated(self):
        args, folder = self.configuration('exclusive')
        evaluator = self.evaluator()
        original_get = evaluator.get_engine
        partial = folder / 'trajectory.jsonl.gz.partial'
        sentinel = b'previous partial evidence\x00'

        def get_engine(*args):
            partial.write_bytes(sentinel)
            return original_get(*args)

        evaluator.get_engine = get_engine
        with self.assertRaises(FileExistsError):
            self.invoke(args, evaluator)
        self.assertEqual(partial.read_bytes(), sentinel)
        self.assertFalse((folder / 'trajectory.jsonl.gz').exists())
        self.assertFalse((folder / 'result.json').exists())
        error = json.loads((folder / 'CAPTURE-ERROR.json').read_text())
        self.assertEqual(error['stage'], 'recording')
        self.assertEqual(error['error_type'], 'FileExistsError')

    def test_keyboard_interrupt_retains_partial_and_propagates(self):
        args, folder = self.configuration('interrupt')
        with self.assertRaisesRegex(KeyboardInterrupt, 'synthetic capture interruption'):
            self.invoke(args, self.evaluator(frames=1, interrupt=True))
        partial = folder / 'trajectory.jsonl.gz.partial'
        self.assertEqual(len(gzip.decompress(partial.read_bytes()).splitlines()), 1)
        self.assertFalse((folder / 'trajectory.jsonl.gz').exists())
        self.assertFalse((folder / 'result.json').exists())
        error = json.loads((folder / 'CAPTURE-ERROR.json').read_text())
        self.assertEqual(error['error_type'], 'KeyboardInterrupt')
        self.assertEqual(error['recorded_transitions'], 1)
        self.assertIsNone(error['evaluator_result'])

    def test_real_child_hides_final_until_close_and_kill_retains_partial(self):
        # This cell-level regression also runs against the original driver: it
        # fails on premature final-path visibility, without calling a new helper.
        evaluator = self.root / 'paused_evaluator.py'
        evaluator.write_text('''import sys
class Actor:
    pass
class Engine:
    specification = {}
    def interpreter(self, state, env):
        return state
def get_engine(engine, loader):
    return Engine(), {}
def play(engine, specs, cache, loader, seed, seat, *args):
    engine.interpreter([], None)
    engine.stream.flush()
    print("CAPTURE_PAUSED", flush=True)
    sys.stdin.buffer.read(1)
    raise RuntimeError("synthetic pause unexpectedly released")
''', encoding='utf-8')
        args, folder = self.configuration('paused-child', evaluator)
        process = subprocess.Popen([sys.executable, '-B', str(Path(driver.__file__).resolve()),
                                    '--config', args.config, '--cell', args.cell],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        partial = folder / 'trajectory.jsonl.gz.partial'
        final = folder / 'trajectory.jsonl.gz'
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(5), 'synthetic child did not reach recording pause')
                self.assertEqual(process.stdout.readline(), b'CAPTURE_PAUSED\n')
            self.assertFalse(final.exists(), 'final trajectory was visible while its gzip was still open')
            self.assertTrue(partial.exists())
            self.assertGreater(partial.stat().st_size, 0)
            self.assertFalse((folder / 'result.json').exists())
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
        self.assertNotEqual(process.returncode, 0)
        self.assertTrue(partial.exists())
        self.assertFalse(final.exists())
        self.assertFalse((folder / 'result.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
