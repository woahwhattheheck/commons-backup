# SPDX-License-Identifier: Apache-2.0
"""Real-parent clock correspondence through the existing adaptive entrypoints.

Six constructed prefix fixtures (three modes, both seats), not full games or
performance measurements. The official engine advances the accepted explicit
control twice per fixture. A second real actor receives the same observations
without step. Both actors restart on a fresh zero observation. No producer,
optimizer, runtime, or engine body is replaced. All inputs must already be local.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ENTRYPOINT_DIR = HERE
EVALUATOR = HERE.parent.parent / 'cloud-eval' / 'evaluate.py'
ENGINE_DIR = HERE.parent.parent / 'cloud-eval' / 'engine'
ENGINE = None
STRUCT = None
ROWS = []
ATTEMPTS = []
CODE_FILES = set()
TRANSITIONS = 0


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def source_hash(path):
    raw = path.read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(),
            'git_blob': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}


def load_engine():
    global ENGINE, STRUCT
    if not all((ENGINE_DIR / n).is_file() for n in ('kaggriculture.py', 'kaggriculture.json', 'utils.py')):
        raise FileNotFoundError('Supply all three existing pinned engine files; this test does not download')
    spec = importlib.util.spec_from_file_location('entrypoint_clock_evaluator', EVALUATOR)
    evaluator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = evaluator
    spec.loader.exec_module(evaluator)
    ENGINE, _ = evaluator.get_engine(ENGINE_DIR)
    STRUCT = evaluator.Struct


def initial_state():
    cfg = STRUCT({k: v.get('default') if isinstance(v, dict) else v
                  for k, v in ENGINE.specification['configuration'].items() if k != 'seed'})
    farms = [ENGINE._new_farm(int(cfg.boardSize), int(cfg.startingMoney)) for _ in range(2)]
    market, town = ENGINE._new_market(), ENGINE._new_town()
    states = [STRUCT(observation=STRUCT(player=seat, farms=farms, private=ENGINE._new_private(),
                                      market=market, town=town, day=0, hour=0, step=0,
                                      remainingOverageTime=0), action={}, status='ACTIVE', reward=0)
              for seat in range(2)]
    return states, STRUCT(configuration=cfg, done=False, info={})


def raw_entry(path):
    namespace = {}
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), namespace)
    return namespace


def snapshot(actor):
    history = actor.history
    return {'calls': actor.calls, 'previous': deepcopy(actor.previous),
            'previous_sales': deepcopy(actor.previous_sales), 'last': deepcopy(actor.last),
            'counts': deepcopy(actor.counts), 'offer_work': deepcopy(actor.offer_work),
            'history': {'identified': history.identified, 'censored': history.censored,
                        'last': dict(history.last),
                        'records': {p: {str(t): r.as_dict() for t, r in records.items()}
                                    for p, records in history.records.items()}},
            'transform_counts': deepcopy(actor.transformer.counts),
            'active': deepcopy(actor.transformer.selector.active),
            'completed': sorted(actor.transformer.selector.completed)}


def counted_call(namespace, path, observation, cfg):
    """Observe actual Python calls without patching any implementation."""
    lab = HERE.parent.parent / 'cloud-execution-lab'
    tracked = {str((lab / 'integrated_selected.py').resolve()): 'integrated_parent',
               str((lab / 'reference/integrated-selected/claude/arlene_plan.py').resolve()): 'cap_producer',
               str((lab / 'reference/next-panel/vendor/arlene.py').resolve()): 'arlene_actor'}
    counts = dict.fromkeys(tracked.values(), 0)
    prefix = str(HERE.parent.parent.resolve()) + '/'
    def profile(frame, event, arg):
        if event == 'call':
            filename = frame.f_code.co_filename
            if filename.startswith(prefix):
                CODE_FILES.add(filename)
            if frame.f_code.co_name == 'act':
                key = tracked.get(filename)
                if key is not None:
                    counts[key] += 1
    old = sys.getprofile()
    sys.setprofile(profile)
    error_type = None
    try:
        # This is the upstream build_agent supplied-path convention.
        return namespace['agent'](observation, dict(cfg, __raw_path__=str(path))), counts
    except Exception as error:
        error_type = type(error).__name__
        raise
    finally:
        sys.setprofile(old)
        ATTEMPTS.append({'entrypoint': path.name, 'explicit_step': 'step' in observation,
                         'calls': dict(counts), 'error_type': error_type})


class RealEntrypointClockTests(unittest.TestCase):
    def exercise(self, filename):
        global TRANSITIONS
        path = ENTRYPOINT_DIR / filename
        for seat in (0, 1):
            with self.subTest(filename=filename, seat=seat):
                states, env = initial_state()
                actors = {'explicit': raw_entry(path), 'day_hour': raw_entry(path)}
                first_actor, first_runtime, first_action = {}, {}, {}
                for index, step in enumerate((0, 1, 2, 0)):
                    restarting = index == 3
                    source = initial_state()[0][seat].observation if restarting else states[seat].observation
                    actions, snapshots = {}, {}
                    for clock, namespace in actors.items():
                        supplied = deepcopy(source)
                        supplied['step'] = step
                        if clock == 'day_hour':
                            supplied.pop('step')
                        before = deepcopy(supplied)
                        action, counts = counted_call(namespace, path, supplied, env.configuration)
                        self.assertEqual(supplied, before, 'caller observation mutated')
                        self.assertEqual(counts, {'integrated_parent': 1, 'cap_producer': 1, 'arlene_actor': 1})
                        actor, runtime = namespace['_AGENT'], namespace.get('_RUNTIME')
                        self.assertEqual(actor.calls, 1 if restarting else step + 1)
                        self.assertEqual(actor.previous['step'], step)
                        self.assertEqual(actor.transformer.mode,
                                         {'main.py': 'adaptive', 'fixed_main.py': 'fixed', 'static_main.py': 'static'}[filename])
                        if index == 0:
                            first_actor[clock], first_runtime[clock] = actor, runtime
                            first_action[clock] = deepcopy(action)
                        elif restarting:
                            self.assertIsNot(actor, first_actor[clock])
                            self.assertIs(runtime, first_runtime[clock])
                            self.assertEqual(action, first_action[clock])
                            self.assertEqual(actor.history.identified + actor.history.censored, 0)
                        else:
                            self.assertIs(actor, first_actor[clock])
                            self.assertIs(runtime, first_runtime[clock])
                        actions[clock], snapshots[clock] = action, snapshot(actor)
                        ROWS.append({'entrypoint': filename, 'seat': seat, 'clock': clock,
                                     'call_index': index, 'step': step, 'restart': restarting,
                                     'input_sha256': digest(supplied), 'action': deepcopy(action),
                                     'action_sha256': digest(action), 'snapshot_sha256': digest(snapshots[clock]),
                                     'calls': counts, 'history_identified': actor.history.identified,
                                     'history_censored': actor.history.censored,
                                     'offer_work': deepcopy(actor.offer_work), 'runtime_last': deepcopy(actor.last)})
                    self.assertEqual(actions['explicit'], actions['day_hour'])
                    self.assertEqual(snapshots['explicit'], snapshots['day_hour'])
                    if index in (0, 1):
                        for i, state in enumerate(states):
                            state.observation.step = step
                            state.action = actions['explicit'] if i == seat else {'farmer': ['PASS'], 'hands': [], 'market': []}
                        ENGINE.interpreter(states, env)
                        TRANSITIONS += 1
                        self.assertEqual((states[seat].observation.day, states[seat].observation.hour), (0, step + 1))

    def test_adaptive_real_parent_clock_and_reset(self):
        self.exercise('main.py')

    def test_fixed_real_parent_clock_and_reset(self):
        self.exercise('fixed_main.py')

    def test_static_real_parent_clock_and_reset(self):
        self.exercise('static_main.py')


def main():
    global ENTRYPOINT_DIR, EVALUATOR, ENGINE_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entrypoint-dir', type=Path, default=ENTRYPOINT_DIR)
    parser.add_argument('--evaluator', type=Path, default=EVALUATOR)
    parser.add_argument('--engine', type=Path, default=ENGINE_DIR)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    ENTRYPOINT_DIR, EVALUATOR, ENGINE_DIR = args.entrypoint_dir.resolve(), args.evaluator.resolve(), args.engine.resolve()
    load_engine()
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RealEntrypointClockTests)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    text = stream.getvalue()
    print(text, end='')
    # Bind the actual Python source closure loaded in this process and controls.
    paths = {Path(__file__).resolve(), EVALUATOR,
             *(ENTRYPOINT_DIR / n for n in ('main.py', 'fixed_main.py', 'static_main.py')),
             *(ENGINE_DIR / n for n in ('kaggriculture.py', 'kaggriculture.json', 'utils.py'))}
    lab_root = HERE.parent.parent
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            p = Path(filename).resolve()
            if p.suffix == '.py' and p.is_relative_to(lab_root):
                paths.add(p)
    # Include raw compiled/imported files even when absent from sys.modules.
    paths.update(Path(filename) for filename in CODE_FILES)
    sources = {str(p.relative_to(lab_root)) if p.is_relative_to(lab_root) else p.name: source_hash(p)
               for p in sorted(paths) if p.is_file()}
    report = {'scope': 'six constructed real-parent prefix fixtures, not full games or timing evidence',
              'python': sys.version.split()[0], 'methods': result.testsRun, 'successful': result.wasSuccessful(),
              'failures': len(result.failures), 'errors': len(result.errors),
              'full_games': 0, 'game_seeds': [], 'official_prefix_transitions': TRANSITIONS,
              'successful_counted_calls': len(ROWS),
              'actual_call_counts': {name: sum(r['calls'][name] for r in ATTEMPTS)
                                     for name in ('integrated_parent', 'cap_producer', 'arlene_actor')},
              'sources': sources, 'rows': ROWS, 'call_attempts': ATTEMPTS,
              'failure_details': [(str(t), detail) for t, detail in result.failures + result.errors],
              'log': text}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
