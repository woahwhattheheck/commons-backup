# SPDX-License-Identifier: Apache-2.0
"""Execute only newly selected final market actions using existing native helpers.

Selection is loaded as an immutable output. Recorded rival inventory/action is
used exclusively in this offline check after decisions; it is never a scenario
input to the live selector. No full game or random seed is run.
"""
from copy import deepcopy
import hashlib
import json
import lzma
from pathlib import Path
import sys
from terminal_input_cases import dependencies, own_unit_snapshot, historical_post_units
from terminal_inputs import market_cell, _config


def run(root, decisions_path, expected_path):
    root=Path(root);decision_bytes=Path(decisions_path).read_bytes()
    decisions=json.loads(decision_bytes);expected=json.loads(Path(expected_path).read_bytes())
    assert hashlib.sha256(decision_bytes).hexdigest()==expected['decisions_sha256']
    deps=dependencies(root/'dependencies/engine_loader.py',root/'engine',root/'dependencies',root/'dependencies/full_support.py')
    records=json.loads(lzma.decompress((root/'inputs/development-records.json.xz').read_bytes()))
    result=[]
    for decision in decisions:
        if not decision['action_changed']:continue
        raw=json.loads(records[decision['record']]);frame=raw['final_day'][-1]
        obs,cfg=deepcopy(frame['observation']),deepcopy(frame['configuration']);cfg.pop('seed',None)
        player=obs['player'];original=deepcopy(frame['actions'][player])
        post=own_unit_snapshot(deps.engine,obs,cfg,original)
        # Evaluation-only, and never passed to source decision rule.
        private=historical_post_units(raw)
        rival={'id':'evaluation-only-recorded-rival','shed':private['shed'],
               'market':deepcopy(frame['actions'][1-player].get('market',[]))}
        farms=deepcopy(obs['farms']);farms[player]=deepcopy(post['farms'][player])
        cell=market_cell(deps.engine,farms,post['private'],obs['market'],_config(cfg),player,decision['action'],rival)
        row=next(r for r in expected['results'] if r['record']==decision['record'])
        assert cell['own_cash']==row['selected']['own_cash']
        assert cell['rival_cash']==row['selected']['rival_cash']
        result.append({'record':decision['record'],'selected_id':decision['selected_id'],
                       'own_cash':cell['own_cash'],'rival_cash':cell['rival_cash']})
    return {'schema':'titan.cash-tie.native-selected.v1',
            'selected_market_calls':len(result),'own_unit_boundary_captures':len(result),
            'full_games':0,'new_game_seeds':0,'engine_hashes':deps.engine_hashes,
            'decisions_sha256':expected['decisions_sha256'],'cases':result}


if __name__=='__main__':
    report=run(*sys.argv[1:4]);Path(sys.argv[4]).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
