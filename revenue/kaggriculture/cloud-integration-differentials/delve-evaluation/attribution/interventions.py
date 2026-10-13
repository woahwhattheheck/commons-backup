"""Execute the three explicitly fixed-command suffix treatments, without agents."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from attribute import load, read_rows, replay, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, out = args.package.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    ev = load('delve_intervention_eval', root/'source/tree/revenue/kaggriculture/cloud-eval/evaluate.py')
    engine, hashes = ev.get_engine(root/'engine/engine', prepare=False)
    summary = json.loads((root/'evaluation/SUMMARY.json').read_text())
    cells = [c for c in summary['cells'] if c['seed'] == 9965019]
    results = []
    for cell in cells:
        own = cell['player']
        path = (root/'evaluation'/cell['arms']['funded']['result_path']).with_suffix('.frames.jsonl.gz')
        rows = read_rows(path)
        original = rows[361]['state'][own]['action']['market']
        if original[0] != ['SELL','MILK',3]:
            raise ValueError('The development discriminator no longer has the recorded MILK3 sale')
        without = [[]]+original[1:]
        baseline = [cell['arms']['funded'][k] for k in ('own_cash','rival_cash')]
        for label, overrides, insertions in (
            ('suppress360', {360:without}, {}),
            ('due381', {}, {381:('MILK',2)}),
            ('suppress360_due381', {360:without}, {381:('MILK',2)}),
        ):
            value = replay(engine, ev, rows, own, start=360, market_overrides=overrides,
                           insertions=insertions, record_states=True)
            terminal = [value['terminal'][p] for p in (own,1-own)]
            delta = [terminal[i]-baseline[i] for i in (0,1)]
            name = f'9965019-p{own}-{label}-suffix.json.gz'
            data = gzip.compress(json.dumps(value,sort_keys=True,separators=(',',':')).encode(),mtime=0)
            (out/name).write_bytes(data)
            final = value['transitions'][-1]
            row = {'case':label,'player':own,'frames_sha256':digest(path),
                   'terminal_own_rival':terminal,'delta_own_rival':delta,
                   'delta_margin':delta[0]-delta[1],
                   'all_productive_tiles_equal':all(all(x['tiles_equal']) for x in value['transitions']),
                   'final_inventory_delta_own_rival':[final['inventory_delta_by_position'][p] for p in (own,1-own)],
                   'report':name,'sha256':hashlib.sha256(data).hexdigest(),
                   'transitions':len(value['transitions'])}
            results.append(row)
            print(json.dumps(row),flush=True)
    receipt = {'kind':'fixed_recorded_actions_not_responsive_policy',
               'source_sha256':digest(Path(__file__)),
               'driver_sha256':digest(Path(__file__).with_name('attribute.py')),
               'engine_sha256':hashes,'independent_regimes':1,'new_policy_games':0,'cases':results}
    (out/'INTERVENTIONS.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
