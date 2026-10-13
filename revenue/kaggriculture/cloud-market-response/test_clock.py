# SPDX-License-Identifier: MIT
"""T12 public-clock regressions and optional exact retained-input correspondence.

Run directly for boundary units. --archive adds real ResponsePolicy execution;
no game is simulated and retained frames are not an on-policy strength panel.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import types
import unittest
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
SOURCE = HERE
ARCHIVE_SHA = 'aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9'
MEMBER = 'evaluation/pilot/9965001-p0-control.frames.jsonl.gz'


def load(path, name=None):
    name = name or ('t12_clock_' + uuid.uuid4().hex)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Boundary:
    """Recording dependencies under the actual published public boundary code."""
    def __init__(self, kind):
        self.kind = kind
        self.created = []
        owner = self

        class Recorder:
            def __init__(self):
                self.calls = 0
                self.inputs = []
                owner.created.append(self)

            def act(self, obs, cfg=None):
                self.calls += 1
                self.inputs.append((obs, cfg))
                return {'step': int(obs['step']), 'calls': self.calls}

        if kind == 'actor':
            module = load(SOURCE / 'policy.py')
            actor = module.ResponsePolicy.__new__(module.ResponsePolicy)
            actor.calls = actor.interventions = 0
            actor.scheduler = Recorder()
            actor.scheduler.diagnostics = {}
            actor.source = types.SimpleNamespace(PRODUCTS=(), post_units=lambda *a: ({}, {'shed': {}}))
            actor.observe = lambda obs, cfg: int(obs['step'])
            self.call = actor.act
        elif kind == 'policy':
            self.module = load(SOURCE / 'policy.py')
            self.module.ResponsePolicy = Recorder
            self.call = self.module.agent
        else:
            self.module = types.ModuleType('clock_entry_' + uuid.uuid4().hex)
            if kind == 'main':
                self.module.__file__ = str(SOURCE / 'main.py')
            exec(compile((SOURCE / 'main.py').read_text(), str(SOURCE / 'main.py'), 'exec'), self.module.__dict__)

            class Loader:
                def exec_module(self, module):
                    module.ResponsePolicy = Recorder

            self.module._util = types.SimpleNamespace(
                spec_from_file_location=lambda name, path: types.SimpleNamespace(name=name, loader=Loader()),
                module_from_spec=lambda spec: types.ModuleType(spec.name))
            self.call = self.module.agent

    def config(self, value=None):
        if self.kind == 'raw':
            return dict(value or {}, __raw_path__=str(SOURCE / 'main.py'))
        return value


class ClockCases(unittest.TestCase):
    kinds = ('actor', 'policy', 'main', 'raw')

    def test_sparse_persistence_both_players_and_day_boundaries(self):
        for kind in self.kinds:
            for player in (0, 1):
                with self.subTest(kind=kind, player=player):
                    b = Boundary(kind)
                    for index, step in enumerate((0, 1, 23, 24, 25, 47, 48), 1):
                        result = b.call({'player': player, 'day': step // 24, 'hour': step % 24}, b.config())
                        self.assertEqual(result, {'step': step, 'calls': index})
                    self.assertEqual(len(b.created), 1)

    def test_mixed_explicit_sparse_and_none_steps(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                b = Boundary(kind)
                for i, obs in enumerate(({'step': 0}, {'day': 0, 'hour': 1}, {'step': None, 'day': 0, 'hour': 2}, {'step': 3}), 1):
                    self.assertEqual(b.call(obs, b.config()), {'step': i - 1, 'calls': i})
                self.assertEqual(len(b.created), 1)

    def test_explicit_step_wins_over_day_and_hour(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                b = Boundary(kind)
                obs = {'step': 7, 'day': 'unused', 'hour': None}
                self.assertEqual(b.call(obs, b.config())['step'], 7)
                self.assertIs(b.created[0].inputs[-1][0], obs)

    def test_explicit_zero_and_derived_zero_restart_singletons(self):
        for kind in self.kinds[1:]:
            with self.subTest(kind=kind):
                b = Boundary(kind)
                for obs in ({'step': 0}, {'step': 1}, {'step': 0, 'day': 9, 'hour': 9}, {'day': 0, 'hour': 1}, {'day': 0, 'hour': 0}):
                    b.call(obs, b.config())
                self.assertEqual([a.calls for a in b.created], [2, 2, 1])

    def test_direct_actor_is_not_reset_by_clock_normalization(self):
        b = Boundary('actor')
        for obs in ({'step': 0}, {'day': 0, 'hour': 1}, {'day': 0, 'hour': 0}):
            b.call(obs)
        self.assertEqual(len(b.created), 1)
        self.assertEqual(b.created[0].calls, 3)

    def test_none_and_empty_configuration_use_default_day(self):
        for kind in self.kinds:
            for cfg in (None, {}):
                with self.subTest(kind=kind, cfg=cfg):
                    b = Boundary(kind)
                    self.assertEqual(b.call({'day': 2, 'hour': 3}, b.config(cfg))['step'], 51)

    def test_custom_day_and_integer_text(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                b = Boundary(kind)
                self.assertEqual(b.call({'day': '2', 'hour': '3'}, b.config({'turnsPerDay': '10'}))['step'], 23)

    def test_inputs_and_nested_identity_are_preserved(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                b = Boundary(kind)
                nested = {'a': [1, 2]}
                obs = {'day': 3, 'hour': 4, 'private': nested}
                cfg = b.config({'turnsPerDay': 12, 'nested': nested})
                before = copy.deepcopy((obs, cfg))
                b.call(obs, cfg)
                self.assertEqual((obs, cfg), before)
                used = b.created[0].inputs[-1][0]
                self.assertIsNot(used, obs)
                self.assertIs(used['private'], nested)
                self.assertEqual(used['step'], 40)

    def test_missing_clock_does_not_create_a_zero_match(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                b = Boundary(kind)
                before = len(b.created)
                with self.assertRaises(KeyError):
                    b.call({'player': 0}, b.config())
                self.assertEqual(len(b.created), before)
                self.assertTrue(all(a.calls == 0 for a in b.created))

    def test_bad_clock_fails_before_invoking_actor(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                b = Boundary(kind)
                before = len(b.created)
                with self.assertRaises(ValueError):
                    b.call({'day': 'bad', 'hour': 0}, b.config())
                self.assertEqual(len(b.created), before)
                self.assertTrue(all(a.calls == 0 for a in b.created))

    def test_none_step_without_public_clock_is_not_zero(self):
        for kind in self.kinds:
            with self.subTest(kind=kind):
                b = Boundary(kind)
                before = len(b.created)
                with self.assertRaises(KeyError):
                    b.call({'step': None}, b.config())
                self.assertEqual(len(b.created), before)

    def test_positive_public_clock_keeps_existing_actor_on_failure(self):
        for kind in self.kinds[1:]:
            with self.subTest(kind=kind):
                b = Boundary(kind)
                b.call({'step': 1}, b.config())
                actor = b.created[0]
                errors = []
                def fail(obs, cfg):
                    errors.append(obs['step'])
                    raise TypeError('body discriminator')
                actor.act = fail
                with self.assertRaisesRegex(TypeError, 'body discriminator'):
                    b.call({'day': 0, 'hour': 2}, b.config())
                self.assertEqual(errors, [2])
                self.assertEqual(len(b.created), 1)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def state_snapshot(actor):
    history = actor.history
    return {
        'calls': actor.calls, 'interventions': actor.interventions,
        'previous': actor.previous, 'previous_sales': actor.previous_sales,
        'last_intervals': actor.last_intervals, 'last_predictions': actor.last_predictions,
        'last_changes': actor.last_changes,
        'history': None if history is None else {
            'period': history.period, 'window': history.window, 'minimum': history.minimum,
            'identified': history.identified, 'censored': history.censored,
            'last': history.last,
            'bins': [[list(key), list(value)] for key, value in sorted(history.bins.items())],
            'records': {p: [v.as_dict() for _, v in sorted(items.items())]
                        for p, items in sorted(history.records.items())}},
        'scheduler': {k: getattr(actor.scheduler, k) for k in
                      ('pending', 'planned', 'observed_harvests', 'diagnostics')},
        'route': actor.scheduler.controller.cur,
    }


def actual_worker(args):
    random.seed(20260907 + args.player)
    raw = Path(args.archive).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA:
        raise ValueError('Unexpected retained archive; specify a separately documented intake')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        frames = [json.loads(line) for line in gzip.decompress(archive.read(MEMBER)).splitlines()]
    source = Path(args.source_dir).resolve()
    if args.entry == 'direct':
        module = load(source / 'policy.py')
        actor = module.ResponsePolicy()
        call = actor.act
        get_actor = lambda: actor
    elif args.entry == 'policy':
        module = load(source / 'policy.py')
        call = module.agent
        get_actor = lambda: module._INSTANCE
    elif args.entry == 'main':
        module = load(source / 'main.py')
        call = module.agent
        get_actor = lambda: module._instance
    else:
        # Consume the existing pinned official raw loader, not another imitation.
        official = load(HERE.parent / 'cloud-pack' / 'official.py')
        namespace = official.contract()
        raw_call, _ = namespace['build_agent'](str(source / 'main.py'), {}, 'kaggriculture')
        call = lambda obs, cfg: raw_call(namespace['structify'](obs), namespace['structify'](cfg))
        def get_actor():
            wrapped = dict(zip(raw_call.__code__.co_freevars,
                               (cell.cell_contents for cell in raw_call.__closure__)))['agent']
            return wrapped.__globals__['_instance']
    actions = []
    states = []
    instances = set()
    error = None
    for index, frame in enumerate(frames[:args.steps]):
        obs = copy.deepcopy(frame['state'][args.player]['observation'])
        obs['remainingOverageTime'] = 0
        if args.clock == 'explicit':
            obs['step'] = index
        else:
            obs.pop('step', None)
            if args.clock == 'none':
                obs['step'] = None
        cfg = copy.deepcopy(frame['configuration'])
        # Never give evaluation-only seed, future frame, rival action or outcome to the actor.
        before = copy.deepcopy((obs, cfg))
        try:
            action = call(obs, cfg)
            actor = get_actor()
            if (obs, cfg) != before:
                raise AssertionError('Caller input changed')
            actions.append(action)
            states.append(digest(state_snapshot(actor)))
            instances.add(id(actor))
        except Exception as exc:
            error = {'index': index, 'type': type(exc).__name__, 'message': str(exc)}
            break
    report = {'entry': args.entry, 'clock': args.clock, 'player': args.player,
              'completed_calls': len(actions), 'requested_calls': args.steps, 'error': error,
              'actor_instances': len(instances), 'actions': actions, 'state_digests': states,
              'actions_sha256': digest(actions), 'state_digests_sha256': digest(states),
              'final_history': None if not states else state_snapshot(get_actor())['history'],
              'interpretation': 'fixed retained inputs; not a new game or timing measurement'}
    Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('actions', 'state_digests', 'final_history')}))
    return 0


def main():
    global SOURCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', default=str(HERE))
    parser.add_argument('--report')
    parser.add_argument('--archive')
    parser.add_argument('--entry', choices=('direct', 'policy', 'main', 'raw'), default='direct')
    parser.add_argument('--clock', choices=('explicit', 'sparse', 'none'), default='sparse')
    parser.add_argument('--player', type=int, choices=(0, 1), default=0)
    parser.add_argument('--steps', type=int, default=96)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    SOURCE = Path(args.source_dir).resolve()
    if args.worker:
        if not args.archive or not args.report or not 1 <= args.steps <= 719:
            parser.error('--worker needs --archive, --report, and 1..719 --steps')
        return actual_worker(args)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ClockCases))
    report = {'methods': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'passed': result.wasSuccessful(), 'log': stream.getvalue()}
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print(stream.getvalue())
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
