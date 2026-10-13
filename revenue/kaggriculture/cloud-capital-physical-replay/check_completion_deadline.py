# SPDX-License-Identifier: Apache-2.0
"""Compare deadline behavior on existing recorded own actions, without new games."""
import argparse
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def file_identity(path):
    raw = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(),
            'git_blob': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()}


class RecordedAction:
    """Test-only one-action source, not a restored controller or policy."""
    def __init__(self, action, step):
        self.cur = 'recorded-own-action'
        self.R = {self.cur: [{}] * step + [deepcopy(action)]}
        self.calls = 0

    def act(self, observation):
        self.calls += 1
        return deepcopy(self.R[self.cur][int(observation['step'])])


def check(args):
    original = load(args.original, 'deadline_original')
    candidate = load(args.candidate, 'deadline_candidate')
    oracle = load(args.oracle, 'deadline_oracle')
    if file_identity(args.original)['git_blob'] != '7955b2c6683420f4b580e30dca15ca8c752f5560':
        raise ValueError('Use the documented original replay source')
    if file_identity(args.oracle)['git_blob'] != '49640c27862d3d132c828fbafc6a8b4957527736':
        raise ValueError('Use the documented unchanged T04 oracle')
    evaluator = load(Path(args.source_root) / 'cloud-eval/evaluate.py', 'deadline_evaluator')
    engine, engine_hashes = evaluator.get_engine(Path(args.engine_root))
    trace_bytes = Path(args.trace).read_bytes()
    if hashlib.sha256(trace_bytes).hexdigest() != 'cb11721af66b438dd1f2d8615033f6b7da11ea70815ed20d2de9863d6bf4b03b':
        raise ValueError('Use the original PRISM 9982019 Arlene p0 frozen-SELL trace')
    frames = {row['step']: row for row in
              (json.loads(line) for line in gzip.decompress(trace_bytes).decode().splitlines())}
    configuration = {k: v.get('default') if isinstance(v, dict) else v
                     for k, v in engine.specification['configuration'].items()}
    configuration['seed'] = None
    checks, private_results = [], {}
    for step in (577, 718):
        observation = deepcopy(frames[step - 1]['observations'][0])
        observation.update(step=step, remainingOverageTime=0)
        action = deepcopy(frames[step]['actions'][0])
        controller = RecordedAction(action, step)
        before = deepcopy(controller.__dict__)
        input_before = deepcopy(observation)
        reports = {}
        for mode in ('on_time', 'return_overdue', 'final_engine_stage_overdue'):
            for label, module in (('original', original), ('candidate', candidate)):
                clock = [0.0]
                class ObservedLateStage:
                    def __getattr__(self, name):
                        return getattr(engine, name)
                    def _decay_plants(self, *a, **kw):
                        result = engine._decay_plants(*a, **kw)
                        clock[0] = 2.0
                        return result
                mechanics = ObservedLateStage() if mode == 'final_engine_stage_overdue' else engine
                def simulate(*a, **kw):
                    result = oracle.simulate_bundle(*a, **kw)
                    clock[0] = 2.0 if mode == 'return_overdue' else clock[0]
                    return result
                with patch.object(module, 'monotonic', lambda: clock[0]):
                    report = module.replay_routes(
                        controller, [controller.cur], observation, configuration,
                        mechanics, simulate, scenarios={'observed_shops_only': oracle.Scenario()},
                        end_step=step, limits=module.ReplayLimits(seconds=1, decisions=1))
                assert controller.__dict__ == before and observation == input_before
                reports[(mode, label)] = report
                case = report['cases'][0]
                checks.append({'step': step, 'mode': mode, 'source': label,
                               'complete': report['complete'], 'status': case['status'],
                               'reason': case.get('reason'), 'scored_cash': case['cash_gain'],
                               'market_rows': len(case['market_rows']),
                               'market_rows_sha256': digest(case['market_rows']),
                               'decisions': report['decisions_executed'],
                               'controller_and_input_unchanged': True})
                private_results[f'{step}/{mode}/{label}'] = report
            old, new = reports[(mode, 'original')], reports[(mode, 'candidate')]
            assert old['complete'] is True
            assert new['cases'][0]['market_rows'] == old['cases'][0]['market_rows']
            assert old['decisions_executed'] == new['decisions_executed'] == 1
            if mode == 'on_time':
                assert {k: v for k, v in old.items() if k != 'wall_seconds'} == {
                    k: v for k, v in new.items() if k != 'wall_seconds'}
            else:
                assert new['complete'] is False
                assert new['cases'][0]['reason'] == 'budget:time'
                assert new['cases'][0]['cash_gain'] is None
                assert 'result' not in new['cases'][0]
    summary = {'schema': 'titan.physical-replay-completion-check.v1',
               'sources': {k: file_identity(getattr(args, k)) for k in ('original', 'candidate', 'oracle', 'trace')},
               'engine_sha256': engine_hashes, 'checks': checks, 'passed': True,
               'scope': '12 conditional single-decision native replays of two retained own actions; '
                        'controlled clock boundaries, no game initialization, actor restoration or speed claim'}
    Path(args.output).write_text(json.dumps(summary, sort_keys=True, indent=2) + '\n')
    if args.private_output:
        Path(args.private_output).write_text(json.dumps(private_results, sort_keys=True) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('original', 'candidate', 'oracle', 'source-root', 'engine-root', 'trace', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--private-output')
    result = check(parser.parse_args())
    print(json.dumps({'passed': result['passed'], 'checks': len(result['checks']), 'scope': result['scope']}))
