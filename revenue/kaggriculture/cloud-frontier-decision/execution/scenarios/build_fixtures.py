# SPDX-License-Identifier: Apache-2.0
"""Extract 48 adjacent recorded transitions; no new full games or policy runs."""
import argparse,copy,gzip,hashlib,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def main():
    p=argparse.ArgumentParser();p.add_argument('--engine-dir',type=Path,required=True);a=p.parse_args()
    spec=importlib.util.spec_from_file_location('existing_eval',ROOT/'cloud-eval/evaluate.py')
    ev=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ev;spec.loader.exec_module(ev)
    engine,hashes=ev.get_engine(a.engine_dir)
    cfg={'boardSize':10,'shedCapacity':100,'maxMarketOrdersPerTurn':10,'townShopSellInterval':4,'townCenterSellInterval':24,'turnsPerDay':24,'episodeSteps':720}
    fixtures=[];sources={}
    original_commit=engine._commit_unit
    for mode in ('baseline','cap','demand'):
        file=HERE.parent/'results'/(mode+'.json.gz');sources[str(file.relative_to(ROOT))]=hashlib.sha256(file.read_bytes()).hexdigest()
        report=json.loads(gzip.decompress(file.read_bytes()))
        for game in report['games']:
            frames={f['step']:f for f in game['timeline']};seat=game['candidate_seat']
            for t in (716,717):
                f=frames[t];n=frames[t+1]
                farms=copy.deepcopy(f['farms']);market=ev.structify(copy.deepcopy(f['prices']))
                state=[ev.structify({'observation':{'private':copy.deepcopy(f['private'][i])},'action':copy.deepcopy(f['actions'][i])}) for i in (0,1)]
                farms=ev.structify(farms)
                for s in state:
                    s.observation.farms=farms;s.observation.market=market;s.observation.town=ev.structify(copy.deepcopy(f['shops']))
                env=ev.structify({'configuration':cfg})
                for i,s in enumerate(state):
                    acts=[s.action.get('farmer',['PASS']),*s.action.get('hands',[])]
                    for idx,act in enumerate(acts):engine._apply_unit_action(farms[i],s.observation.private,idx,act,10,t//24,24,100)
                post=[dict(s.observation.private.shed) for s in state]
                sold=[{},{}];supply=[{},{}];cash=[0,0]
                def commit(op,item,price,farm,private,*args,**kw):
                    i=next(i for i,x in enumerate(farms) if x is farm)
                    ok=original_commit(op,item,price,farm,private,*args,**kw)
                    if ok:
                        assert op=='SELL'
                        sold[i][item]=sold[i].get(item,0)+1;cash[i]+=price
                        if price>1:supply[i][item]=supply[i].get(item,0)+1
                    return ok
                engine._commit_unit=commit
                engine._process_market(state,env);engine._town_consume(env,state,t)
                assert dict(market.inventory)==n['prices']['inventory']
                for i in (0,1):
                    assert farms[i]['money']==n['farms'][i]['money']
                    assert dict(state[i].observation.private.shed)==n['private'][i]['shed']
                # Independent official counterfactual for the scorer's baseline: same
                # observed market/stock and historical rival queue, own queue empty.
                alt_farms=ev.structify(copy.deepcopy(f['farms']))
                alt_market=ev.structify(copy.deepcopy(f['prices']))
                alt_state=[]
                for i in (0,1):
                    alt_state.append(ev.structify({'observation':{'private':{'shed':dict(post[i]),'seeds':{}}},'action':{'market':[] if i==seat else f['actions'][i].get('market',[])}}))
                    alt_state[-1].observation.farms=alt_farms;alt_state[-1].observation.market=alt_market
                engine._commit_unit=original_commit
                engine._process_market(alt_state,env)
                alt_cash=[alt_farms[i]['money']-f['farms'][i]['money'] for i in (seat,1-seat)]
                def public(frame):return {'step':frame['step'],'market':frame['prices'],'town':frame['shops']}
                all_own={p:post[seat].get(p,0)-n['private'][seat]['shed'].get(p,0) for p in market.inventory}
                assert all(all_own[p]==sold[seat].get(p,0) for p in all_own)
                fixtures.append({'id':f'{mode}-{game["seed"]}-{game["opponent"]}-{seat}-{t}',
                    'provenance':{'mode':mode,'seed_evaluation_only':game['seed'],'opponent':game['opponent'],'seat':seat,'trace_sha256':game['trace_sha256']},
                    'live_input':{'before':public(f),'after':public(n),'own_orders':f['actions'][seat].get('market',[]),'configuration':cfg,
                                  'own_sale_units':all_own},
                    'evaluation_only':{'own_post_unit_shed':post[seat],'rival_orders':f['actions'][1-seat].get('market',[]),
                        'rival_fill_cap':sold[1-seat],'no_own_sale_cash':alt_cash,'cash':[cash[seat],cash[1-seat]],'sale_units':[sold[seat],sold[1-seat]],
                        'market_supply_units':[supply[seat],supply[1-seat]],'inventory_after_town':n['prices']['inventory']}})
    engine._commit_unit=original_commit
    result={'engine_ref':ev.ENGINE_REF,'engine_sha256':hashes,'source_results':sources,'full_games_run':0,
            'fixture_boundary':'live_input excludes rival private data, rival actions, evaluation seed and future action labels; evaluation_only never enters inference',
            'fixtures':fixtures}
    (HERE/'fixtures.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'captured_adjacent_transitions':len(fixtures),'official_market_cash_inventory_and_shed_matches':len(fixtures),'new_games':0}))
if __name__=='__main__':main()
