"""T03 optional telemetry cannot prevent its supplied actor cleanup.

The actual panel runner wraps a process-backed evaluator fixture. Each test
starts only its own disposable Python children; there are no official games.
T03_PANEL_PATH selects a predecessor for the same run-path discriminators.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import test_panel_resume as resume


PROCESS_EVALUATOR = r'''
import subprocess
import sys
import tempfile
ACTORS = []
CLOSED = []
class Actor:
    def __init__(self):
        self.directory = tempfile.TemporaryDirectory()
        self.stats = {}
        self.closed = False
        self.proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        ACTORS.append(self)
        payload = HERE / 'event_input.bin'
        if payload.exists():
            (Path(self.directory.name) / 't03-events.json').write_bytes(payload.read_bytes())
        if (HERE / 'event_is_directory').exists():
            (Path(self.directory.name) / 't03-events.json').mkdir()
    def close(self):
        if self.closed:
            return 'already closed'
        self.closed = True
        CLOSED.append(self.proc.pid)
        self.proc.terminate()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill(); self.proc.wait(timeout=2)
        self.directory.cleanup()
        return 'closed'
ORIGINAL_CLOSE = Actor.close
_original_play = play
def play(*args, **kwargs):
    row = _original_play(*args, **kwargs)
    actors = [Actor(), Actor()]
    try:
        return row
    finally:
        for actor in actors:
            actor.close()
        row['actors'] = [dict(actor.stats) for actor in actors]
'''


class TelemetryCases(unittest.TestCase):
    save_manifest = resume.ResumeCases.save_manifest
    calls = resume.ResumeCases.calls
    run_panel = resume.ResumeCases.run_panel
    cell = resume.ResumeCases.cell

    def setUp(self):
        resume.ResumeCases.setUp(self)
        self.evaluator.write_text(resume.EVALUATOR + PROCESS_EVALUATOR)
        self.addCleanup(self.cleanup_children)

    def cleanup_children(self):
        module = sys.modules.get('t03_panel_evaluator')
        if module is None or Path(module.__file__) != self.evaluator:
            return
        for actor in module.ACTORS:
            if actor.proc.poll() is None:
                actor.proc.kill(); actor.proc.wait(timeout=2)
            actor.directory.cleanup()

    def event(self, payload):
        (self.evaluator.parent / 'event_input.bin').write_bytes(payload)

    def run_once(self):
        return self.run_panel(arms=['candidate'])

    def closed_actors(self):
        module = sys.modules['t03_panel_evaluator']
        self.assertEqual(len(module.ACTORS), 2)
        self.assertEqual(len(module.CLOSED), 2)
        self.assertIs(module.Actor.close, module.ORIGINAL_CLOSE)
        for actor in module.ACTORS:
            self.assertTrue(actor.closed)
            self.assertIsNotNone(actor.proc.returncode)
            self.assertFalse(Path(actor.directory.name).exists())
        return module.ACTORS

    def errors(self, report, raw=None):
        rows = report['games'][0]['actors']
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertNotIn('t03_events', row)
            problem = row['t03_events_error']
            if raw is not None:
                self.assertEqual(problem['bytes'], len(raw))
                self.assertEqual(problem['sha256'], hashlib.sha256(raw).hexdigest())
                self.assertEqual(base64.b64decode(problem['raw_base64']), raw)
        return [row['t03_events_error'] for row in rows]

    def test_valid_events_are_unchanged(self):
        events = [{'step': 458, 'label': 'route-界', 'gain': 12.5}]
        self.event(json.dumps(events, ensure_ascii=False).encode('utf-8'))
        result = self.run_once(); self.closed_actors()
        for actor in result['games'][0]['actors']:
            self.assertEqual(actor['t03_events'], events)
            self.assertNotIn('t03_events_error', actor)

    def test_missing_events_are_optional(self):
        result = self.run_once(); self.closed_actors()
        self.assertEqual(result['games'][0]['actors'], [{}, {}])

    def test_malformed_json_preserves_attempt_and_closes_both_children(self):
        raw = b'{"step": 458,'
        self.event(raw)
        result = self.run_once(); self.closed_actors()
        problems = self.errors(result, raw)
        self.assertTrue(all(p['kind'] == 'decode_error' for p in problems))
        self.assertEqual(result['games'][0]['status'], 'complete')
        self.assertEqual(result['games'][0]['scores'], [120, 90])
        self.assertIsNone(result['games'][0]['failure'])
        self.assertEqual(len(self.calls()), 1)

    def test_invalid_utf8_preserves_exact_bytes(self):
        raw = b'[{"note":"\xff\xfe"}]'
        self.event(raw)
        result = self.run_once(); self.closed_actors()
        problems = self.errors(result, raw)
        self.assertTrue(all(p['type'] == 'UnicodeDecodeError' for p in problems))

    def test_empty_telemetry_is_retained_as_empty_not_missing(self):
        self.event(b'')
        result = self.run_once(); self.closed_actors()
        self.errors(result, b'')

    def test_directory_read_error_still_closes_children(self):
        (self.evaluator.parent / 'event_is_directory').touch()
        result = self.run_once(); self.closed_actors()
        for problem in self.errors(result):
            self.assertEqual(problem['kind'], 'read_error')
            self.assertEqual(problem['type'], 'IsADirectoryError')
            self.assertIsNone(problem['raw_base64'])
            self.assertIsNone(problem['bytes'])
            self.assertIsNone(problem['sha256'])

    def test_read_io_error_does_not_invent_bytes(self):
        self.event(b'[]'); original = Path.open
        def opened(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get('mode', 'r')
            if path.name == 't03-events.json' and 'r' in mode:
                raise OSError('injected read failure')
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'open', new=opened):
            result = self.run_once()
        self.closed_actors()
        for problem in self.errors(result):
            self.assertEqual(problem['kind'], 'read_error')
            self.assertIsNone(problem['raw_base64'])
            self.assertIsNone(problem['bytes'])

    def test_existing_failed_attempt_is_not_upgraded_by_telemetry_handling(self):
        self.event(b'{'); (self.evaluator.parent / 'incomplete').touch()
        result = self.run_once(); self.closed_actors()
        self.assertEqual(result['games'][0]['status'], 'action_error')
        self.assertEqual(result['games'][0]['failure'], 'retained fixture error')
        self.assertEqual(result['pairs'], [])
        self.errors(result, b'{')

    def test_valid_nonlist_json_keeps_existing_contract(self):
        self.event(b'{"metadata":true}')
        result = self.run_once(); self.closed_actors()
        for row in result['games'][0]['actors']:
            self.assertEqual(row['t03_events'], {'metadata': True})

    def test_keyboard_interrupt_cleans_current_actor_then_propagates(self):
        self.event(b'[]'); original = Path.open
        stop = KeyboardInterrupt('stop while reading optional telemetry')
        def opened(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get('mode', 'r')
            if path.name == 't03-events.json' and 'r' in mode:
                raise stop
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'open', new=opened):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.run_once()
        self.assertIs(caught.exception, stop)
        ev = sys.modules['t03_panel_evaluator']
        self.assertTrue(ev.ACTORS[0].closed)
        self.assertIsNotNone(ev.ACTORS[0].proc.returncode)
        self.assertFalse(Path(ev.ACTORS[0].directory.name).exists())
        self.assertIs(ev.Actor.close, ev.ORIGINAL_CLOSE)
        self.assertFalse(self.cell().exists())

    def test_original_cleanup_error_is_not_suppressed(self):
        self.event(b'{')
        with self.evaluator.open('a') as stream:
            stream.write("\nCLEANUP_ERROR=RuntimeError('original cleanup error')\n"
                         "_cleanup=Actor.close\n"
                         "def bad_cleanup(actor):\n"
                         "    _cleanup(actor)\n"
                         "    raise CLEANUP_ERROR\n"
                         "Actor.close=ORIGINAL_CLOSE=bad_cleanup\n")
        with self.assertRaisesRegex(RuntimeError, 'original cleanup error') as caught:
            self.run_once()
        ev = sys.modules['t03_panel_evaluator']
        self.assertIs(caught.exception, ev.CLEANUP_ERROR)
        self.assertTrue(ev.ACTORS[0].closed)
        self.assertIs(ev.Actor.close, ev.ORIGINAL_CLOSE)
        self.assertFalse(self.cell().exists())

    def test_resume_retains_telemetry_error_without_new_processes(self):
        self.event(b'{')
        first = self.run_once(); self.closed_actors()
        original = self.cell().read_bytes()
        second = self.run_once()
        self.assertEqual(first['games'], second['games'])
        self.assertEqual(second['resume']['reused_complete'], 1)
        self.assertEqual(second['resume']['executed'], 0)
        self.assertEqual(sys.modules['t03_panel_evaluator'].ACTORS, [])
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.cell().read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
