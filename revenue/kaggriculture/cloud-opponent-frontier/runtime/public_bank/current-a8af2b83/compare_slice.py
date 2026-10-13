"""Read the fixed ORBIT lonespear development slice; never execute policies or games."""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path

SEEDS = (9926001, 9926002)
OPPONENTS = ('lonespear-v18-greedy', 'lonespear-v18-scipy')
GRID = {(o, seed, seat) for o in OPPONENTS for seed in SEEDS for seat in (0, 1)}

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def index_report(report):
    if report.get('complete_grid') is not True:
        raise ValueError('Incomplete fixed slice')
    rows = {}
    for game in report['games']:
        key = (game['opponent'], game['seed'], game['candidate_seat'])
        if key in rows:
            raise ValueError('Repeated game cell')
        if key not in GRID:
            raise ValueError('Unexpected game cell')
        if (game['status'] != 'complete' or game.get('failure') is not None
                or game['steps'] != 719 or game['retained_rows'] != 720):
            raise ValueError('Fixed complete-game comparison cannot conceal a failed or partial cell')
        scores = game['scores']
        if len(scores) != 2 or any(isinstance(v, bool) or not math.isfinite(v) for v in scores):
            raise ValueError('Invalid final scores')
        rows[key] = game
    if set(rows) != GRID:
        raise ValueError('Missing fixed-grid cells')
    return rows

def physical_state(observations, seat):
    """Keep all fields except the evaluated farm's money and its private seed stocks."""
    value = copy.deepcopy(observations)
    for obs in value:
        if 'farms' in obs:
            obs['farms'][seat].pop('money', None)
        if obs.get('player') == seat:
            obs.get('private', {}).pop('seeds', None)
    return value

def seed_change(before, after):
    if not before or before[0] != 'BUY_SEED' or len(before) != 3:
        return None
    if after == []:
        return {'product': before[1], 'removed_units': before[2]}
    if len(after) == 3 and after[:2] == before[:2] and 0 <= after[2] < before[2]:
        return {'product': before[1], 'removed_units': before[2] - after[2]}
    return None

def trace_comparison(control_dir, current_dir, b, c):
    seat = c['candidate_seat']
    bp = control_dir / b['retained_trace']
    cp = current_dir / c['retained_trace']
    for path, game in ((bp, b), (cp, c)):
        if sha(path) != game['retained_trace_sha256']:
            raise ValueError('Original trace digest differs: ' + path.name)
    counts = {'rows': 0, 'decisions': 0, 'own_action_changes': 0, 'rival_action_changes': 0,
              'worker_action_changes': 0, 'non_seed_market_changes': 0,
              'physical_state_changes': 0}
    edits = []
    with gzip.open(bp, 'rt', encoding='utf-8') as bf, gzip.open(cp, 'rt', encoding='utf-8') as cf:
        for i, (bl, cl) in enumerate(itertools.zip_longest(bf, cf)):
            if bl is None or cl is None:
                raise ValueError('Unequal trace lengths')
            br, cr = json.loads(bl), json.loads(cl)
            if br['index'] != i or cr['index'] != i or br['kind'] != cr['kind']:
                raise ValueError('Misaligned trace rows')
            counts['rows'] += 1
            if i == 0:
                if br['kind'] != 'initial' or br['after'] != cr['after']:
                    raise ValueError('Initial state differs between paired games')
                continue
            if (br['before'][seat]['step'] != i-1 or cr['before'][seat]['step'] != i-1):
                raise ValueError('Misaligned decision steps')
            counts['decisions'] += 1
            ba, ca = br['actions'][seat], cr['actions'][seat]
            if br['actions'][1-seat] != cr['actions'][1-seat]:
                counts['rival_action_changes'] += 1
            if (ba['farmer'], ba['hands']) != (ca['farmer'], ca['hands']):
                counts['worker_action_changes'] += 1
            if physical_state(br['after'],seat) != physical_state(cr['after'],seat):
                counts['physical_state_changes'] += 1
            if ba != ca:
                counts['own_action_changes'] += 1
                changes = []
                for slot, (old, new) in enumerate(itertools.zip_longest(ba['market'],ca['market'])):
                    if old == new:
                        continue
                    seed = seed_change(old, new) if old is not None and new is not None else None
                    if seed is None:
                        counts['non_seed_market_changes'] += 1
                    changes.append({'slot':slot,'control':old,'current':new,'seed_reduction':seed})
                prev = cr['before'][seat]['farms'][seat]['money'] - br['before'][seat]['farms'][seat]['money']
                following = cr['after'][seat]['farms'][seat]['money'] - br['after'][seat]['farms'][seat]['money']
                edits.append({'step':i-1,'market_changes':changes,
                              'own_cash_delta_before':prev,'own_cash_delta_after':following,
                              'paired_incremental_cash':following-prev,
                              'control_seeds_after':br['after'][seat]['private']['seeds'],
                              'current_seeds_after':cr['after'][seat]['private']['seeds']})
            final_b, final_c = br, cr
    if counts['rows'] != 720 or counts['decisions'] != 719:
        raise ValueError('Incomplete full trace')
    for row, game in ((final_b, b),(final_c,c)):
        money = [row['after'][p]['farms'][p]['money'] for p in (0,1)]
        if money != game['scores']:
            raise ValueError('Trace terminal cash does not match original report')
    return {'counts':counts,'edits':edits,
            'final_control_seeds':final_b['after'][seat]['private']['seeds'],
            'final_current_seeds':final_c['after'][seat]['private']['seeds']}

def verdict(scores, seat):
    return 'W' if scores[seat] > scores[1-seat] else 'L' if scores[seat] < scores[1-seat] else 'T'

def compare(control_dir, current_dir):
    control_dir, current_dir = Path(control_dir), Path(current_dir)
    br = json.loads((control_dir/'report.json').read_text())
    cr = json.loads((current_dir/'report.json').read_text())
    bindex, cindex = index_report(br), index_report(cr)
    for field in ('evaluator_sha256','loader_sha256','engine_sha256','bank_sha256','limits','seeds','seed_role'):
        if br[field] != cr[field]:
            raise ValueError('Paired execution inputs differ: '+field)
    result = {'schema':'orbit.current-lonespear-comparison.v1',
              'scope':'Fixed two-seed development slice; same source family under two assignment modes; no held or hosted rating claim',
              'control_report_sha256':sha(control_dir/'report.json'),
              'current_report_sha256':sha(current_dir/'report.json'),
              'pairs':[],'unique_full_games':16,'retries':0}
    for key in sorted(GRID):
        b, c = bindex[key], cindex[key]
        seat=key[2]
        delta_own = c['scores'][seat]-b['scores'][seat]
        delta_rival = c['scores'][1-seat]-b['scores'][1-seat]
        trace=trace_comparison(control_dir,current_dir,b,c)
        result['pairs'].append({'opponent':key[0],'seed':key[1],'seat':seat,
            'control_scores':b['scores'],'current_scores':c['scores'],
            'control_verdict':verdict(b['scores'],seat),'current_verdict':verdict(c['scores'],seat),
            'own_cash_delta':delta_own,'rival_cash_delta':delta_rival,'margin_delta':delta_own-delta_rival,
            'current_candidate_call_max_seconds':c['actors'][seat]['max_call_seconds'],
            'current_candidate_rpc_max_seconds':c['actors'][seat]['max_rpc_seconds'],
            'control_trace_sha256':b['retained_trace_sha256'],'current_trace_sha256':c['retained_trace_sha256'],
            'trace':trace})
    rows=result['pairs']
    result['summary']={'pairs':len(rows),'current_wtl':{v:sum(r['current_verdict']==v for r in rows) for v in 'WTL'},
       'control_wtl':{v:sum(r['control_verdict']==v for r in rows) for v in 'WTL'},
       'wtl_flips':sum(r['control_verdict']!=r['current_verdict'] for r in rows),
       'own_cash_delta_total':sum(r['own_cash_delta'] for r in rows),
       'rival_cash_delta_total':sum(r['rival_cash_delta'] for r in rows),
       'own_improved':sum(r['own_cash_delta']>0 for r in rows),
       'own_unchanged':sum(r['own_cash_delta']==0 for r in rows),
       'own_worsened':sum(r['own_cash_delta']<0 for r in rows),
       'max_candidate_call_seconds':max(r['current_candidate_call_max_seconds'] for r in rows),
       'max_candidate_rpc_seconds':max(r['current_candidate_rpc_max_seconds'] for r in rows),
       'trace_totals':{k:sum(r['trace']['counts'][k] for r in rows) for k in rows[0]['trace']['counts']},
       'observed_cash_change_at_seed_edits':sum(e['paired_incremental_cash'] for r in rows for e in r['trace']['edits'])}
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('control',type=Path)
    parser.add_argument('current',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    result=compare(args.control,args.current)
    with args.output.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(result['summary'],indent=2))
