# SPDX-License-Identifier: Apache-2.0
"""Execute the authenticated current Features/TitanAgent code with test doubles.

Only dependencies (clock, deadline timer, producer and selected consumer) are
stubbed. The classes, act, checkpoint and exception paths are actual source.
This is a source/ABI/cancellation suite, not a full engine or economics gate.
"""
import argparse
import ast
import base64
import builtins
import copy
from dataclasses import dataclass, fields
import json
import lzma
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

import port_current_runtime as port
import r04_fast_tape_clone as clone

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / 'fixtures' / 'titan_runtime.b952.py'
TAPES = HERE / 'fixtures' / 'r01_tapes.py'


def corpus():
    data = TAPES.read_bytes()
    if port.git_blob(data) != 'a43289b9cc5e34a2481fddf652762a7d92f427ef':
        raise ValueError('frozen corpus identity mismatch')
    values = [n.value for n in ast.parse(data).body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == '_B85' for t in n.targets)]
    if len(values) != 1:
        raise ValueError('unique literal corpus required')
    tapes = json.loads(lzma.decompress(base64.b85decode(ast.literal_eval(values[0]))))
    if len(tapes) != 13 or any(len(t) != 719 for t in tapes):
        raise ValueError('13 x 719 corpus required')
    return [action for tape in tapes for action in tape]


def runtime(source):
    tree = ast.parse(source)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name in ('Features', 'TitanAgent')]
    if len(classes) != 2:
        raise ValueError('actual runtime classes missing')
    state = types.SimpleNamespace(active=False, enters=0, producer_calls=0)

    class DeadlineExceeded(Exception):
        pass

    class Timer:
        def __init__(self, seconds):
            self.expired = DeadlineExceeded('test timer expiration')
            state.timer = self
        def __enter__(self):
            state.active = True
            state.enters += 1
            return self
        def __exit__(self, *args):
            state.active = False
            return False

    fallback = {'farmer': ['PASS'], 'hands': [], 'market': []}
    deadline = types.SimpleNamespace(
        DeadlineExceeded=DeadlineExceeded, _DeadlineTimer=Timer,
        legal_pass=lambda *args: copy.deepcopy(fallback),
        terminal_liquidation_fallback=lambda *args: copy.deepcopy(fallback))
    name = '_test_current_' + port.git_blob(source)
    module = types.ModuleType(name)
    module.__dict__.update(dataclass=dataclass, deepcopy=copy.deepcopy,
                          deadline=deadline, time=types.SimpleNamespace(
                              perf_counter=lambda: 0.0, process_time=lambda: 0.0))
    sys.modules[name] = module
    exec(compile(ast.Module(body=classes, type_ignores=[]), '<actual runtime classes>', 'exec'),
         module.__dict__)
    module.state = state
    return module


def agent(module, enabled=None):
    options = dict(consumer='parent', seed=False, funding=False)
    if enabled is not None:
        options[port.KEY] = enabled
    value = module.TitanAgent(module.Features(**options))
    value.ready = True
    value.controller = types.SimpleNamespace(cur=0)
    value.consumer = types.SimpleNamespace(selected_post_units=None)
    value.input = {'farmer': ['PASS'], 'hands': [], 'market': []}

    def produce(obs):
        if not module.state.active:
            raise AssertionError('producer escaped the deadline')
        module.state.producer_calls += 1
        return value.input

    value.production = types.SimpleNamespace(act=produce)
    return value


class PortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = RUNTIME.read_bytes()
        if port.git_blob(cls.source) != port.REFERENCE_RUNTIME:
            raise ValueError('reference runtime identity mismatch')
        cls.output = port.transform(cls.source, port.REFERENCE_RUNTIME)
        cls.actions = corpus()

    def test_only_two_source_edits(self):
        reverted = self.output.decode().replace(port.NEW_FIELD, port.OLD_FIELD, 1)
        reverted = reverted.replace(port.NEW_CHECKPOINT, port.OLD_CHECKPOINT, 1)
        self.assertEqual(reverted.encode(), self.source)
        self.assertEqual(port.git_blob(self.output), '2b2bd80e3fa76c61139bdbfeaa58dc8a8987339a')

    def test_requires_exact_current_input(self):
        with self.assertRaises(ValueError):
            port.transform(self.source, '0' * 40)
        with self.assertRaises(ValueError):
            port.transform(self.source + b'\n', port.REFERENCE_RUNTIME)
        with self.assertRaises(ValueError):
            port.transform(self.source.decode(), port.REFERENCE_RUNTIME)

    def test_repeated_application_rejected(self):
        with self.assertRaises(ValueError):
            port.transform(self.output, port.git_blob(self.output))

    def test_missing_and_duplicate_anchors_rejected(self):
        mutations = [
            self.source.replace(b'self.selected = deepcopy(selected)', b'self.selected = selected'),
            self.source + b'\nclass Features:\n    pass\n',
            self.source.replace(port.OLD_FIELD.encode(),
                                (port.OLD_FIELD + '    another: bool = False\n').encode()),
            self.source + b"\nTEXT = '''\n" + port.OLD_CHECKPOINT.encode() + b"'''\n",
            self.source.replace(b'with timer:', b'with another_timer:'),
            self.source.replace(b'selected = self.production.act(obs)', b'selected = another(obs)'),
            self.source.replace(b'(self.selected, self.controller.cur)', b'(selected, self.controller.cur)'),
            self.source.replace(b'\n', b'\r\n'),
        ]
        for source in mutations:
            with self.subTest(blob=port.git_blob(source)), self.assertRaises(ValueError):
                port.transform(source, port.git_blob(source))

    def test_nonexecuting_transform(self):
        source = b"raise RuntimeError('never execute source')\n" + self.source
        result = port.transform(source, port.git_blob(source))
        self.assertTrue(result.startswith(b'raise RuntimeError'))

    def test_existing_dataclass_abi_and_default_off(self):
        old, new = runtime(self.source), runtime(self.output)
        before, after = fields(old.Features), fields(new.Features)
        self.assertEqual([(f.name, f.default) for f in after[:-1]],
                         [(f.name, f.default) for f in before])
        self.assertEqual(after[-1].name, port.KEY)
        self.assertIs(after[-1].default, False)
        defaults = [f.default for f in before]
        instance = new.Features(*defaults)
        self.assertFalse(getattr(instance, port.KEY))
        self.assertEqual(instance.__dict__, {**old.Features(*defaults).__dict__, port.KEY: False})

    def test_off_does_not_import_helper(self):
        module = runtime(self.output)
        value = agent(module, False)
        real_import = builtins.__import__
        def check(name, *args, **kwargs):
            if name == 'r04_fast_tape_clone':
                raise AssertionError('disabled path imported helper')
            return real_import(name, *args, **kwargs)
        with mock.patch('builtins.__import__', side_effect=check):
            result = value.act({'step': 1})
        self.assertEqual(result, value.input)
        self.assertEqual(value.diagnostics['status'], 'completed')

    def test_on_clone_is_inside_existing_timer(self):
        module = runtime(self.output)
        value = agent(module, True)
        original = clone.apply_fast_tape_clone
        def wrapped(selected):
            self.assertTrue(module.state.active)
            self.assertEqual(module.state.producer_calls, 1)
            return original(selected)
        with mock.patch.object(clone, 'apply_fast_tape_clone', side_effect=wrapped) as call:
            value.act({'step': 1})
        self.assertEqual(call.call_count, 1)
        self.assertEqual(module.state.enters, 1)
        self.assertFalse(module.state.active)

    def test_all_9347_actual_runtime_off_on_checkpoints(self):
        baseline, patched = runtime(self.source), runtime(self.output)
        old, off, on = agent(baseline), agent(patched, False), agent(patched, True)
        for index, action in enumerate(self.actions):
            snapshots = []
            outputs = []
            for value in (old, off, on):
                value.input = action
                outputs.append(value.act({'step': index % 719}))
                snapshots.append(value.selected)
                self.assertEqual(value.diagnostics['status'], 'completed')
                self.assertEqual(value.diagnostics['parent_calls'], 1)
                self.assertIsNot(value.selected, action)
                for key in action:
                    self.assertIsNot(value.selected[key], action[key])
                for key in ('hands', 'market'):
                    for source_row, copied_row in zip(action[key], value.selected[key]):
                        self.assertIsNot(source_row, copied_row)
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0], outputs[2])
            self.assertEqual(snapshots[0], snapshots[1])
            self.assertEqual(snapshots[0], snapshots[2])
        self.assertEqual(len(self.actions), 9347)

    def test_checkpoint_preserves_alias_graph(self):
        module = runtime(self.output)
        value = agent(module, True)
        row = ['PASS']
        value.input = {'farmer': row, 'hands': [row, row], 'market': []}
        value.act({'step': 1})
        self.assertIs(value.selected['farmer'], value.selected['hands'][0])
        self.assertIs(value.selected['hands'][0], value.selected['hands'][1])
        value.selected['farmer'].append('only output')
        self.assertEqual(row, ['PASS'])

    def test_deadline_during_clone_cannot_publish_checkpoint(self):
        module = runtime(self.output)
        value = agent(module, True)
        value.input = {'farmer': ['NORTH'], 'hands': [], 'market': []}
        def expired(selected):
            raise module.state.timer.expired
        with mock.patch.object(clone, 'apply_fast_tape_clone', side_effect=expired) as call:
            result = value.act({'step': 1})
        self.assertEqual(result['farmer'], ['PASS'])
        self.assertIsNone(value.selected)
        self.assertIsNone(value._completed_route)
        self.assertFalse(value.ready)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(value.diagnostics['status'], 'deadline_fallback')
        self.assertEqual(value.diagnostics['fallback_stage'], 'production')

    def test_unrelated_deadline_exception_is_not_swallowed(self):
        module = runtime(self.output)
        value = agent(module, True)
        error = module.deadline.DeadlineExceeded('different timer')
        with mock.patch.object(clone, 'apply_fast_tape_clone', side_effect=error):
            with self.assertRaises(module.deadline.DeadlineExceeded) as caught:
                value.act({'step': 1})
        self.assertIs(caught.exception, error)

    def test_later_deadline_uses_completed_checkpoint(self):
        module = runtime(self.output)
        value = agent(module, True)
        value.input = {'farmer': ['NORTH'], 'hands': [['WEST']], 'market': []}
        def expired(*args):
            raise module.state.timer.expired
        value.transform_selected = expired
        result = value.act({'step': 1})
        self.assertEqual(result, value.input)
        self.assertIsNot(result, value.selected)
        self.assertIsNot(result['farmer'], value.selected['farmer'])
        self.assertEqual(value._completed_route, 0)
        self.assertEqual(value.diagnostics['fallback_stage'], 'selected_transform')

    def test_expired_entry_prelude_never_calls_clone(self):
        module = runtime(self.output)
        value = agent(module, True)
        with mock.patch.object(clone, 'apply_fast_tape_clone', side_effect=AssertionError('unused')) as call:
            result = value.act({'step': 1}, entry_started=-2.0)
        self.assertEqual(result['farmer'], ['PASS'])
        self.assertIsNone(value.selected)
        self.assertEqual(module.state.enters, 0)
        self.assertEqual(call.call_count, 0)
        self.assertEqual(value.diagnostics['fallback_stage'], 'entrypoint_prelude')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=RUNTIME)
    parser.add_argument('--tapes', type=Path, default=TAPES)
    args, remaining = parser.parse_known_args()
    RUNTIME, TAPES = args.runtime, args.tapes
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
