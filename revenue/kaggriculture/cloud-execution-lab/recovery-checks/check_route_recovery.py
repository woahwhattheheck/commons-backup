# SPDX-License-Identifier: Apache-2.0
"""Measure canonical TITAN route continuity across one controlled cancellation.

Uses two actual persistent TitanAgent instances and retained own observations.
No interpreter transition, rival actor, policy body replacement, or new game.
The injected exception is that call's real timer sentinel, not a timed overrun.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import random
import sys
import zipfile

INPUT_ARCHIVE_SHA256 = 'b64a2363365b4e6711c08c38b3398bc44466994ef3d4d75da2a35be9d8488568'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def source_map(root, pins):
    out = {}
    for name, expected in pins.items():
        data = (root / name).read_bytes()
        actual = digest(data)
        if actual != expected:
            raise ValueError('source differs from supplied pin: ' + name)
        out[name] = {'bytes': len(data), 'sha256': actual,
                     'git_blob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}
    return out


def load_payload(archive_path, member):
    if digest(archive_path.read_bytes()) != INPUT_ARCHIVE_SHA256:
        raise ValueError('expected the immutable LARCH own/public-history archive')
    if not member.startswith('runtime/') or not member.endswith('.json.gz'):
        raise ValueError('use one runtime payload, not an offline index')
    with zipfile.ZipFile(archive_path) as archive:
        raw = gzip.decompress(archive.read(member))
    if Path(member).name != digest(raw) + '.json.gz':
        raise ValueError('runtime payload content identity differs')
    payload = json.loads(raw)
    if len(payload['history']) != 718:
        raise ValueError('expected complete prior own history')
    seat = payload['observation']['player']
    for step, record in enumerate(payload['history']):
        obs = record['observation']
        if obs['step'] != step or obs['player'] != seat:
            raise ValueError('own history clock/player mismatch')
    return payload, digest(raw)


def run(args):
    root = args.runtime.resolve()
    pins = json.loads(args.pins.read_text())
    sources = source_map(root, pins)
    if not 1 <= args.cancel_step < args.through <= 718:
        raise ValueError('require 1 <= cancel-step < through <= 718')
    if sys.gettrace() is not None or sys.getprofile() is not None:
        raise RuntimeError('run in a fresh process without an existing tracer')
    sys.path.insert(0, str(root))
    random.seed(20260908)
    runtime = importlib.import_module('titan_runtime')
    scheduler = importlib.import_module('scheduler')
    payload, input_digest = load_payload(args.input_archive, args.member)
    configuration = payload['configuration']
    actors = {name: runtime.TitanAgent(runtime.Features()) for name in ('reference', 'cancelled')}
    counts = {name: {'act': 0, 'parent': 0, 'initialization': 0} for name in actors}
    active_role = None
    injected = []
    checkpoints = {}
    rows = []
    reference_code = scheduler.parent.Agent.act.__code__

    def count(frame, event, _arg):
        if event != 'call' or active_role is None:
            return
        if frame.f_code is reference_code:
            counts[active_role]['parent'] += 1
        if frame.f_code is runtime.TitanAgent._initialize.__code__:
            counts[active_role]['initialization'] += 1

    def cancel(frame, event, _arg):
        actor = actors['cancelled']
        is_self = frame.f_locals.get('self') is actor
        selected_boundary = (args.boundary == 'selected_transform' and event == 'call'
                             and frame.f_code is runtime.TitanAgent.transform_selected.__code__ and is_self)
        parent_boundary = (args.boundary in ('production_entry', 'production_return')
                           and frame.f_code is reference_code
                           and frame.f_locals.get('self') is getattr(actor, 'controller', None)
                           and event == ('call' if args.boundary == 'production_entry' else 'return'))
        if selected_boundary or parent_boundary:
            caller = frame.f_back
            while caller is not None and not (caller.f_code is runtime.TitanAgent.act.__code__
                                             and caller.f_locals.get('self') is actor):
                caller = caller.f_back
            if caller is None:
                raise AssertionError('actual enclosing action timer not found')
            injected.append({'step': caller.f_locals['obs']['step'],
                             'stage': caller.f_locals['stage'],
                             'route_at_injection': actor.controller.cur,
                             'selected_before_injection': deepcopy(actor.selected)})
            raise caller.f_locals['timer'].expired
        return cancel

    def call(role, observation, inject=False):
        nonlocal active_role
        actor = actors[role]
        obs, cfg = deepcopy(observation), deepcopy(configuration)
        before = counts[role].copy()
        active_role = role
        try:
            sys.setprofile(count)
            if inject:
                sys.settrace(cancel)
            output = actor.act(obs, cfg)
        finally:
            sys.settrace(None)
            sys.setprofile(None)
            active_role = None
        counts[role]['act'] += 1
        if obs != observation or cfg != configuration:
            raise AssertionError('caller input was mutated')
        # A trace exception at parent call entry precedes the profiler's call
        # event and executes no parent-body instruction. Other calls each
        # require exactly one observed real parent invocation.
        expected_calls = 0 if inject and args.boundary == 'production_entry' else 1
        if counts[role]['parent'] - before['parent'] != expected_calls:
            raise AssertionError('real parent-call counter differs at injection boundary')
        return output

    old_consumer = None
    expected_route = None
    for step in range(args.through + 1):
        observation = (payload['history'][step]['observation'] if step < 718 else payload['observation'])
        if step == args.cancel_step:
            old_consumer = actors['cancelled'].consumer
            checkpoints['before_cancellation'] = {
                'route': actors['cancelled'].controller.cur,
                'planned': deepcopy(actors['cancelled'].consumer.planned),
                'pending': deepcopy(actors['cancelled'].consumer.pending),
            }
        reference = call('reference', observation)
        actual = call('cancelled', observation, inject=step == args.cancel_step)
        ref_actor, actor = actors['reference'], actors['cancelled']
        if step < args.cancel_step:
            if reference != actual or ref_actor.controller.cur != actor.controller.cur:
                raise AssertionError('pre-cancellation control mismatch at step ' + str(step))
        if step == args.cancel_step:
            if len(injected) != 1 or actor.diagnostics.get('status') != 'deadline_fallback':
                raise AssertionError('injection did not reach the real deadline handler exactly once')
            if args.boundary == 'selected_transform':
                if actual != injected[0]['selected_before_injection']:
                    raise AssertionError('selected fallback was not retained')
                expected_route = injected[0]['route_at_injection']
            else:
                if actual != runtime.deadline.legal_pass(observation):
                    raise AssertionError('pre-selection fallback differs from legal PASS')
                # A route mutation inside an unreturned parent call is not a
                # completed selected-action commitment. The previous route wins.
                expected_route = checkpoints['before_cancellation']['route']
            checkpoints['cancellation'] = {
                'injection': injected[0], 'expected_recovery_route': expected_route,
                'returned_action': deepcopy(actual), 'reference_action': deepcopy(reference),
                'diagnostics': deepcopy(actor.diagnostics), 'ready': actor.ready,
            }
        if step == args.cancel_step + 1:
            checkpoints['first_recovery'] = {
                'new_consumer': actor.consumer is not old_consumer,
                'route': actor.controller.cur, 'expected_route': expected_route,
                'route_preserved': actor.controller.cur == expected_route,
                'planned': deepcopy(actor.consumer.planned),
                'reference_planned': deepcopy(ref_actor.consumer.planned),
            }
        row = {'step': step, 'reference_route': ref_actor.controller.cur,
               'cancelled_route': actor.controller.cur, 'actions_equal': actual == reference,
               'worker_fields_equal': {k:v for k,v in actual.items() if k!='market'} ==
                                      {k:v for k,v in reference.items() if k!='market'},
               'reference_action_sha256': digest(encoded(reference)),
               'cancelled_action_sha256': digest(encoded(actual)),
               'reference_status': ref_actor.diagnostics['status'], 'cancelled_status': actor.diagnostics['status']}
        if actual != reference:
            row.update(reference_action=deepcopy(reference), cancelled_action=deepcopy(actual))
        rows.append(row)
        if step != args.cancel_step and (ref_actor.diagnostics['status'] != 'completed'
                                        or actor.diagnostics['status'] != 'completed'):
            raise AssertionError('unexpected natural fallback; preserve as an incomplete attempt')
    if source_map(root, pins) != sources:
        raise AssertionError('source changed during the measurement')
    after = [r for r in rows if r['step'] > args.cancel_step]
    first = next((r for r in after if not r['actions_equal']), None)
    first_worker = next((r for r in after if not r['worker_fields_equal']), None)
    return {
        'schema': 'titan.route-recovery-observation.v1', 'completed': True,
        'route_continuity': checkpoints['first_recovery']['route_preserved'],
        'boundary': args.boundary, 'cancel_step': args.cancel_step, 'through': args.through,
        'source_ref': args.source_ref, 'sources': sources,
        'driver_sha256': digest(Path(__file__).read_bytes()), 'input_member': args.member,
        'input_sha256': input_digest, 'input_archive_sha256': INPUT_ARCHIVE_SHA256,
        'player': payload['observation']['player'], 'features': vars(actors['reference'].features),
        'checkpoints': checkpoints, 'counts': counts, 'rows': rows,
        'first_post_cancel_difference': first, 'first_post_cancel_worker_difference': first_worker,
        'new_games': 0, 'engine_transitions': 0, 'timed_overrun_reproduced': False,
        'scope': 'Deterministic timer-sentinel injection on fixed retained own observations; not a responsive game or economic attribution.',
        'python': sys.version,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--pins', type=Path, default=Path(__file__).with_name('SOURCE-PINS.json'))
    parser.add_argument('--input-archive', type=Path, required=True)
    parser.add_argument('--member', required=True)
    parser.add_argument('--cancel-step', type=int, default=434)
    parser.add_argument('--through', type=int, default=578)
    parser.add_argument('--boundary', choices=('selected_transform', 'production_entry', 'production_return'), default='selected_transform')
    parser.add_argument('--source-ref', default='9db2f2f94666b3ca126f97ab98d28f9a3814de4f')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-route-continuity', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output exists; retain the earlier result and use a new path')
    report = run(args)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k:report[k] for k in ('completed','route_continuity','player','boundary','cancel_step','through','counts','new_games','engine_transitions')}))
    return 2 if args.require_route_continuity and not report['route_continuity'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
