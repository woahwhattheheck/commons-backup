# SPDX-License-Identifier: Apache-2.0
"""Capture genuine native actions, then independently audit them offline.

The ledger never runs in either agent process. This is checked-archive evidence,
not a leaderboard replay or current composed-V4 promotion. No network fetches.
"""
from __future__ import annotations
import argparse
import base64
import copy
import csv
import hashlib
import importlib.util
import json
import lzma
import sys
from collections import Counter, defaultdict
from pathlib import Path
import realized_market_ledger as M

MANIFEST_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
ARCHIVE_SHA256 = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'
EVALUATOR_SHA256 = 'e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c'


def verify_native(native: Path, manifest: Path, archive: Path) -> dict:
    for file, expected in ((manifest, MANIFEST_SHA256), (archive, ARCHIVE_SHA256)):
        if hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError(f'checked-release mismatch: {file.name}')
    entries = json.loads(manifest.read_text())['runtime']
    for name, entry in entries.items():
        path = native / name
        if path.is_symlink() or not path.resolve().is_relative_to(native.resolve()):
            raise ValueError(f'unsafe native path: {name}')
        raw = path.read_bytes()
        if len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError(f'native source mismatch: {name}')
    unexpected = [str(p.relative_to(native)) for p in native.rglob('*.py')
                  if str(p.relative_to(native)) not in entries]
    if unexpected:
        raise ValueError(f'unmanifested Python input: {unexpected}')
    return {'archive_sha256': ARCHIVE_SHA256, 'manifest_sha256': MANIFEST_SHA256,
            'runtime_files_verified': len(entries)}


def load_evaluator(reference):
    path = reference/'evaluator/evaluate.py'
    if hashlib.sha256(path.read_bytes()).hexdigest() != EVALUATOR_SHA256:
        raise ValueError('evaluator mismatch')
    spec = importlib.util.spec_from_file_location('_realized_evaluator', path)
    evaluator = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = evaluator
    spec.loader.exec_module(evaluator)
    return evaluator


def capture(native, seed, seat, opponent='official_starter'):
    reference = native/'checks/reference'
    engine, _ = M.load_engine(reference/'engine', reference/'evaluator/loader.py')
    evaluator = load_evaluator(reference)
    original = engine.interpreter
    records = []
    poststates = hashlib.sha256()

    def record(state, env):
        active = bool(state[0].observation.get('farms')) and not env.done
        result = original(state, env)
        if active:
            records.append({'step': state[0].observation.step,
                            'actions': copy.deepcopy([s.action for s in state])})
            poststates.update(M.digest([state, env]).encode())
        return result

    engine.interpreter = record
    specs = [opponent, opponent]
    specs[seat] = str((native/'main.py').resolve())+'::agent'
    try:
        game = evaluator.play(engine, specs, reference/'engine', reference/'evaluator/loader.py',
                              seed, seat, action_timeout=2.0, game_timeout=180.0)
    finally:
        engine.interpreter = original
    if game['status'] != 'complete':
        raise RuntimeError(f'native capture failed: {game}')
    if game['steps'] != len(records) or game['steps'] != game['episode_steps']-1:
        raise ValueError('incomplete native capture')
    return {'seed':seed,'candidate_seat':seat,'opponent':opponent,
            'native_result':game, 'records':records,
            'poststate_stream_sha256':poststates.hexdigest()}


def audit_records(native, captured, effective_csv=None):
    reference = native/'checks/reference'
    engine, loader = M.load_engine(reference/'engine', reference/'evaluator/loader.py')
    state, env = M.new_game(engine, loader, captured['seed'])
    counters = [defaultdict(Counter), defaultdict(Counter)]
    anomalies = []
    effective = []
    trace = hashlib.sha256()
    native_states = hashlib.sha256()
    for index, record in enumerate(captured['records']):
        if record['step'] != index or len(record['actions']) != 2:
            raise ValueError('noncontiguous or non-two-seat replay')
        for seat in range(2):
            state[seat].observation.step = index
            state[seat].observation.remainingOverageTime = 0
            state[seat].action = copy.deepcopy(record['actions'][seat])
        state, env, receipt = M.audit_transition(engine, state, env)
        native_states.update(receipt['full_state_sha256'].encode())
        trace.update(M.digest(receipt).encode())
        for row in receipt['rows']:
            raw = row['raw']
            verb = raw[0] if isinstance(raw,list) and raw and isinstance(raw[0],str) else '<invalid>'
            parsed = row['parsed']
            item = parsed.get('item','') if parsed else ''
            key = verb + (':' + str(item) if item else '')
            c = counters[row['seat']][key]
            c['rows'] += 1
            c['admitted'] += int(row['admitted'])
            c['requested_units'] += row['requested'] or 0
            c['filled_units'] += row['filled']
            c['successful_rows'] += int(row['filled']>0)
            c['attempts'] += row['attempts']
            c['cash_delta'] += row['delta']['cash']
            c[row['status']+'_rows'] += 1
            if row['filled']:
                effective.append({'match_id': f"native-{captured['seed']}-{captured['candidate_seat']}",
                                  'team_id': 'native-b567' if row['seat']==captured['candidate_seat'] else captured['opponent'],
                                  'player':row['seat'], 'step':index, 'verb':verb, 'item':item,
                                  'quantity':row['filled'], 'requested_units':row['requested'],
                                  'cash_delta':row['delta']['cash'], 'raw_slot':row['slot']})
            if row['status'] not in ('filled',):
                anomalies.append({'step':index, **row})
    if native_states.hexdigest() != captured['poststate_stream_sha256']:
        raise AssertionError('native vs replay full-state stream mismatch')
    if not all(s.status=='DONE' for s in state):
        raise ValueError('replay has no terminal state')
    scores = [s.reward for s in state]
    if scores != captured['native_result']['scores']:
        raise AssertionError('terminal score mismatch')
    if effective_csv is not None:
        with Path(effective_csv).open('w', newline='') as output:
            writer=csv.DictWriter(output,fieldnames=['match_id','team_id','player','step','verb','item',
                                                    'quantity','requested_units','cash_delta','raw_slot'])
            writer.writeheader(); writer.writerows(effective)
    return {'seed':captured['seed'],'candidate_seat':captured['candidate_seat'],
            'opponent':captured['opponent'],'steps':len(captured['records']),
            'full_interpreter_calls':2*len(captured['records']),
            'all_native_poststates_match':True,'all_instrumented_poststates_match':True,
            'scores':scores,'receipt_stream_sha256':trace.hexdigest(),
            'captured_records_sha256':M.digest(captured['records']),
            'players':[{k:dict(v) for k,v in sorted(player.items())} for player in counters],
            'nonfull_rows':len(anomalies), 'nonfull_row_witnesses':anomalies[:24],
            'witnesses_are_truncated':len(anomalies)>24}


def read_capture(path, seat=0):
    """Decode a single capture or the two actually-observed seat-symmetric runs.

    The bundle stores one command vocabulary and action stream. Both original
    native runs had exactly reversed actions, checked before packing. Distinct
    native poststate streams and terminal results are retained for both seats.
    """
    data=json.loads(lzma.decompress(base64.b64decode(Path(path).read_text())))
    if data.get('schema') != 'titan.realized-captures.v1':
        return data
    metadata=[g for g in data['games'] if g['candidate_seat']==seat]
    if len(metadata)!=1 or seat not in (0,1):
        raise ValueError('ambiguous capture seat')
    vocab=data['vocabulary']
    def command(index):
        if type(index) is not int or not 0<=index<len(vocab):
            raise ValueError('invalid command vocabulary index')
        return copy.deepcopy(vocab[index])
    result=copy.deepcopy(metadata[0]); result['records']=[]
    for step,packed in enumerate(data['action_rows']):
        if len(packed)!=2:
            raise ValueError('capture requires two seats')
        actions=[]
        for fields in packed:
            if len(fields)!=3:
                raise ValueError('invalid packed action')
            actions.append({'farmer':command(fields[0]),
                            'hands':[command(i) for i in fields[1]],
                            'market':[command(i) for i in fields[2]]})
        result['records'].append({'step':step,'actions':actions if seat==0 else actions[::-1]})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--seed',type=int,default=9923105)
    p.add_argument('--seat',type=int,choices=(0,1),default=0)
    p.add_argument('--replay',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    custody=verify_native(a.native,a.manifest,a.archive)
    if a.replay:
        captured=read_capture(a.replay,a.seat)
    else:
        captured=capture(a.native,a.seed,a.seat)
    a.output.mkdir(parents=True,exist_ok=True)
    result=audit_records(a.native,captured,a.output/'realized_market.csv')
    payload=json.dumps(captured,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    (a.output/'captured.json.xz.b64').write_text(base64.b64encode(lzma.compress(payload)).decode()+'\n')
    result.update(custody=custody,python=sys.version,scope='checked b567 native archive vs official_starter; not field EV/current V4')
    (a.output/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('seed','candidate_seat','steps','scores','nonfull_rows','receipt_stream_sha256')}),flush=True)


if __name__=='__main__':
    main()
