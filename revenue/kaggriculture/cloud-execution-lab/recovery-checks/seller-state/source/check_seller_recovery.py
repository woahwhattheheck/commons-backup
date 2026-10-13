"""Source-bound actual TitanAgent seller-state recovery discriminator.

This drives retained OWN observations, not a game or an on-policy evaluation.
Default mode never restores actor state: it detects the current discontinuity.
The optional field-restoration modes are CAUSAL INTERVENTIONS, not a runtime fix.
No producer implementation, optimizer, timer or engine function is replaced.
"""
from __future__ import annotations

import argparse
import ast
import copy
import dataclasses
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
from typing import Any

FIELDS = ('planned', 'pending', 'previous', 'observed_harvests')
INPUT_DIGEST = '6d850535bc06fd9d366119365651e789c32ec8a48c96bedaa992fd19a1ff060e'
DECODED_DIGEST = '75f39921d9a749b50b84101f34f8119b51f9646d2ab725d8453f17fdee66083f'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def load_inputs(path: Path, receipt_path: Path) -> tuple[list[dict], dict]:
    receipt = json.loads(receipt_path.read_text())
    raw = path.read_bytes()
    decoded = gzip.decompress(raw)
    if sha(raw) != receipt['output_file_sha256'] or sha(decoded) != receipt['input_jsonl_sha256']:
        raise ValueError('Input bytes differ from their retained receipt')
    rows = [json.loads(line) for line in decoded.splitlines()]
    if len(rows) != receipt['observation_count']:
        raise ValueError('Incomplete observation sequence')
    for i, row in enumerate(rows):
        obs = row['observation']
        if row['step'] != i or obs['step'] != i or obs['player'] != receipt['candidate_seat']:
            raise ValueError('Input clock or player does not match the retained sequence')
        if not isinstance(row['configuration'], dict):
            raise ValueError('Missing per-observation configuration')
    return rows, receipt


def load_subject(root: Path, pins_path: Path):
    pins = json.loads(pins_path.read_text())
    for name, expected in pins['sha256'].items():
        path = root / name
        if sha(path.read_bytes()) != expected:
            raise ValueError(f'Source identity mismatch: {name}')
    # Run this source-specific checker in a fresh process and a clean extracted
    # source tree. The bundled runtime retains its own original import behavior.
    if list(root.rglob('*.pyc')):
        raise ValueError('Use an extracted source tree without bytecode caches')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root.resolve()))
    path = root / 'titan_runtime.py'
    spec = importlib.util.spec_from_file_location('_seller_recovery_subject', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module, pins


def state(actor) -> dict:
    return {'route': actor.controller.cur,
            **{name: copy.deepcopy(getattr(actor.consumer, name)) for name in FIELDS}}


def state_digest(value: dict) -> str:
    return sha(canonical(value))


def first_projection_line(path: Path) -> int:
    """The real frozen transform's post-observer, pre-unit-projection boundary."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Name) and f.id == 'post_units':
                return node.lineno
    raise ValueError('The subject no longer has the expected frozen observer boundary')


def run(root: Path, pins_path: Path, input_path: Path, receipt_path: Path, *,
        cancel_step: int = 450, boundary: str = 'transform_entry',
        restore: tuple[str, ...] = (), observe_skipped: bool = False,
        through: int = 718, seed: int = 20260907) -> dict:
    rows, receipt = load_inputs(input_path, receipt_path)
    module, pins = load_subject(root, pins_path)
    if not 1 <= cancel_step < through < len(rows):
        raise ValueError('Cancellation must have a completed prefix and a later observation')
    if boundary not in ('transform_entry', 'after_observe', 'transform_return'):
        raise ValueError('Unknown source boundary')
    if set(restore) - set(FIELDS):
        raise ValueError('Restoration fields are not frozen-seller state')
    if observe_skipped and set(restore) != set(FIELDS):
        raise ValueError('Observer advancement requires the complete prior seller checkpoint')
    random.seed(seed)
    reference = module.TitanAgent()
    affected = module.TitanAgent()
    actors = (reference, affected)
    events = [{'parent_calls': 0, 'transform_calls': 0} for _ in actors]
    injections, restorations, records = [], [], []
    projection_line = first_projection_line(root / 'frozen_selected.py')
    checkpoint = None
    input_step = -1

    def profile(frame, event, arg):
        if event != 'call' or frame.f_code.co_name not in ('act', 'transform'):
            return
        owner = frame.f_locals.get('self')
        for i, actor in enumerate(actors):
            if owner is getattr(actor, 'production', None) and frame.f_code.co_name == 'act':
                events[i]['parent_calls'] += 1
            if owner is getattr(actor, 'consumer', None) and frame.f_code.co_name == 'transform':
                events[i]['transform_calls'] += 1

    def hook(frame, event, arg):
        nonlocal checkpoint
        own = frame.f_locals.get('self') is affected
        consumer = frame.f_locals.get('self') is getattr(affected, 'consumer', None)
        match = input_step == cancel_step and (
            (boundary == 'transform_entry' and own and event == 'call'
             and frame.f_code is module.TitanAgent.transform_selected.__code__)
            or (boundary == 'after_observe' and consumer and event == 'line'
                and frame.f_code.co_name == 'transform' and frame.f_lineno == projection_line)
            or (boundary == 'transform_return' and own and event == 'return'
                and frame.f_code is module.TitanAgent.transform_selected.__code__))
        if match:
            scope = frame
            while scope is not None and scope.f_code is not module.TitanAgent.act.__code__:
                scope = scope.f_back
            if scope is None:
                raise RuntimeError('Actual timer scope was not found')
            injections.append({'step': input_step, 'boundary': boundary,
                               'selected': copy.deepcopy(affected.selected),
                               'seller_at_cancellation': state(affected)})
            raise scope.f_locals['timer'].expired
        if (input_step == cancel_step + 1 and event == 'return' and own
                and frame.f_code is module.TitanAgent._initialize.__code__):
            item = {'before': state(affected), 'restored_fields': list(restore),
                    'observer_advanced': observe_skipped}
            for name in restore:
                setattr(affected.consumer, name, copy.deepcopy(checkpoint[name]))
            if observe_skipped:
                # Experimental intervention: use the ORIGINAL observer exactly
                # once on the input seen at the cancelled call. No private rival
                # data, expected action or economic outcome is passed to it.
                skipped = copy.deepcopy(rows[cancel_step]['observation'])
                affected.consumer.observe(skipped)
                affected.consumer.previous = copy.deepcopy(skipped)
            item['after'] = state(affected)
            restorations.append(item)
        return hook

    old_profile, old_trace = sys.getprofile(), sys.gettrace()
    try:
        for input_step, row in enumerate(rows[:through+1]):
            obs0, cfg0 = copy.deepcopy(row['observation']), copy.deepcopy(row['configuration'])
            sys.setprofile(profile)
            try:
                expected = reference.act(obs0, cfg0)
            finally:
                sys.setprofile(old_profile)
            if reference.diagnostics['status'] != 'completed':
                raise RuntimeError(f'Uninjected reference fallback at {input_step}')
            expected_state = state(reference)
            if input_step == cancel_step:
                checkpoint = state(affected)
            obs1, cfg1 = copy.deepcopy(row['observation']), copy.deepcopy(row['configuration'])
            if input_step in (cancel_step, cancel_step+1):
                sys.settrace(hook)
            sys.setprofile(profile)
            try:
                actual = affected.act(obs1, cfg1)
            finally:
                sys.setprofile(old_profile)
                sys.settrace(old_trace)
            required_status = 'deadline_fallback' if input_step == cancel_step else 'completed'
            if affected.diagnostics['status'] != required_status:
                raise RuntimeError(f'Unexpected actor status at {input_step}: {affected.diagnostics}')
            if obs0 != row['observation'] or obs1 != row['observation'] or cfg0 != row['configuration'] or cfg1 != row['configuration']:
                raise AssertionError(f'Input mutation at {input_step}')
            actual_state = state(affected)
            equal, fields = expected == actual, [f for f in ('route',)+FIELDS if expected_state[f] != actual_state[f]]
            if input_step < cancel_step and (not equal or fields):
                raise AssertionError(f'Uncontrolled prefix difference at {input_step}')
            item = {'step': input_step, 'actions_equal': equal, 'different_state_fields': fields,
                    'reference_action': expected, 'affected_action': actual,
                    'reference_state_sha256': state_digest(expected_state),
                    'affected_state_sha256': state_digest(actual_state),
                    'reference_route': reference.controller.cur, 'affected_route': affected.controller.cur,
                    'affected_status': affected.diagnostics['status']}
            if input_step >= cancel_step and (input_step <= cancel_step+4 or not equal):
                item['reference_seller'] = expected_state
                item['affected_seller'] = actual_state
            records.append(item)
    finally:
        sys.settrace(old_trace)
        sys.setprofile(old_profile)
    if len(injections) != 1 or len(restorations) != 1:
        raise AssertionError('Cancellation/recovery did not execute once')
    count = len(records)
    if any(v['parent_calls'] != count for v in events):
        raise AssertionError('Actual original producer call count changed')
    for name, expected in pins['sha256'].items():
        if sha((root / name).read_bytes()) != expected:
            raise AssertionError(f'Source changed during execution: {name}')
    fallback_equal = records[cancel_step]['actions_equal']
    action_differences = [r['step'] for r in records if r['step'] > cancel_step and not r['actions_equal']]
    state_differences = [r['step'] for r in records if r['step'] > cancel_step and r['different_state_fields']]
    result = {
        'schema': 'titan.seller-recovery-discriminator.v1',
        'checker_sha256': sha(Path(__file__).read_bytes()),
        'scope': 'Retained own-observation workload; not a game, response simulation, natural overrun, or timing benchmark',
        'source_pins': pins, 'input_encoded_sha256': sha(input_path.read_bytes()),
        'input_decoded_sha256': receipt['input_jsonl_sha256'], 'input_origin': receipt['origin'],
        'input_receipt_sha256': sha(receipt_path.read_bytes()),
        'original_expected_actions_used_as_runtime_inputs': False,
        'original_outcomes_used_as_runtime_inputs': False,
        'original_actor_source_equals_test_subject': False,
        'features': dataclasses.asdict(reference.features), 'actor_rng_seed': seed,
        'cancel_step': cancel_step, 'boundary': boundary, 'through': through,
        'intervention': {'restore_completed_fields': list(restore), 'observe_skipped': observe_skipped,
                         'production_repair': False},
        'calls_per_actor': count, 'actual_parent_events': events,
        'controlled_injection_count': len(injections), 'injection': injections,
        'completed_prior_seller_checkpoint': checkpoint, 'fresh_recovery': restorations,
        'full_prefix_equal_before_injection': True, 'fallback_equals_uninterrupted_action': fallback_equal,
        'all_routes_equal': all(r['reference_route'] == r['affected_route'] for r in records),
        'later_action_differences': action_differences, 'later_seller_state_differences': state_differences,
        'continuity_precondition_met': fallback_equal,
        'continuity_preserved': fallback_equal and not action_differences,
        'new_games': 0, 'engine_interpreter_calls': 0, 'new_seed_reservations': [],
        'records': records,
    }
    return result


def main() -> int:
    base = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', type=Path, default=base/'runtime')
    p.add_argument('--pins', type=Path, default=base/'SOURCE-PINS.json')
    p.add_argument('--input', type=Path, default=base/'inputs/candidate-inputs.jsonl.gz')
    p.add_argument('--receipt', type=Path, default=base/'inputs/ORIGINAL-INPUT-RECEIPT.json')
    p.add_argument('--step', type=int, default=450)
    p.add_argument('--through', type=int, default=718)
    p.add_argument('--boundary', default='transform_entry')
    p.add_argument('--restore-fields', default='')
    p.add_argument('--observe-skipped', action='store_true')
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--require-continuity', action='store_true')
    args = p.parse_args()
    result = run(args.runtime.resolve(), args.pins, args.input, args.receipt,
                 cancel_step=args.step, through=args.through, boundary=args.boundary,
                 restore=tuple(x for x in args.restore_fields.split(',') if x),
                 observe_skipped=args.observe_skipped)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k:result[k] for k in ('cancel_step','boundary','calls_per_actor',
         'fallback_equals_uninterrupted_action','all_routes_equal','later_action_differences',
         'continuity_precondition_met','continuity_preserved')}))
    if args.require_continuity and not result['continuity_preserved']:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
