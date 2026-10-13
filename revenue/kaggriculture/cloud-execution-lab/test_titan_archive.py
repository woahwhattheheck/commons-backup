# SPDX-License-Identifier: Apache-2.0
"""Changed canonical entrypoint boundaries, using the exact relocated archive."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from test_ordered_selected_sell import OrderedSelectedSellTests, action

ROOT=Path(__file__).resolve().parent
WORKER=r'''
import sys, json, time, pathlib, hashlib, copy
root=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(root))
def audit(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('offline archive test')
sys.addaudithook(audit)
fixture=json.loads(pathlib.Path(sys.argv[2]).read_text());obs=fixture['obs'];cfg=fixture['cfg']
mode=sys.argv[3];started=time.perf_counter()
namespace={'__name__':'titan_raw'}
cfg['__raw_path__']=str(root/'main.py')
exec(compile((root/'main.py').read_text(),str(root/'main.py'),'exec'),namespace)
if mode=='cold':
    output=namespace['agent'](obs,cfg)
    rows=[{'case':'cold_full_main','seconds':time.perf_counter()-started,'diagnostics':namespace['_INSTANCE'].diagnostics,'action':output}]
else:
    from titan_runtime import TitanAgent,Features,deadline
    from frozen_selected import FrozenSelected
    from scheduler import SellScheduler
    rows=[]
    # Mechanical extraction must retain frozen decisions and state exactly.
    frozen=SellScheduler();split=TitanAgent(Features(seed=False));split._initialize()
    for step in (0,100,600,698,718):
        o=copy.deepcopy(obs);o['step']=step;o['day']=step//24;o['hour']=step%24
        expected=frozen.act(copy.deepcopy(o),cfg)
        got=split.act(copy.deepcopy(o),cfg)
        assert got==expected,(step,got,expected)
    rows.append({'case':'frozen_selected_parity_five_windows','passed':True})
    for consumer in ('frozen','ordered'):
        for money in (170,100000):
            agent=TitanAgent(Features(consumer=consumer));agent._initialize()
            o=copy.deepcopy(obs);o['step']=100;o['day']=4;o['hour']=4
            o['farms'][0]['money']=money
            selected={'farmer':['PASS'],'hands':[['PASS']],'market':[['BUY_SEED','WHEAT',17],['HIRE']]}
            route=[{'farmer':['PASS'],'hands':[['PASS']],'market':[]} for _ in range(720)];route[100]=selected
            agent.controller.R={'case':route};agent.controller.cur='case'
            if consumer=='ordered':
                agent.consumer.budget=agent.consumer.budget.__class__(agent.controller.R)
            else:agent.seed_budget=agent.seed_budget.__class__(agent.controller.R)
            calls=[]
            def select(_obs):calls.append(1);return copy.deepcopy(selected)
            agent.production.act=select
            out=agent.act(o,cfg)
            assert len(calls)==1
            assert out['farmer']==selected['farmer'] and out['hands']==selected['hands']
            assert out['market'][1]==['HIRE']
            assert out['market'][0]==(['BUY_SEED','WHEAT',17] if money==170 else []),out
            report=agent.diagnostics.get('seed_funding',agent.consumer.diagnostics.get('seed_funding'))
            assert report is not None,(consumer,agent.diagnostics,agent.consumer.diagnostics)
            rows.append({'case':consumer+'_funding_'+str(money),'action':out,'funding':report,'parent_calls':len(calls)})
    # Current ordered consumer uses worker-order admission before market slots.
    obj=TitanAgent(Features(consumer='ordered'));obj._initialize()
    o=copy.deepcopy(obs);o['step']=100;o['private']['shed']={'WHEAT':10,'MILK':90}
    o['private']['inventories']=[{}, {'MILK':10}]
    selected={'farmer':['PICKUP','WHEAT',10],'hands':[['DROP']],
              'market':[['SELL','MILK',50],['BUY_PRODUCT','WHEAT',1],['SELL','MILK',50]]}
    route=[{'farmer':['PASS'],'hands':[['PASS']],'market':[]} for _ in range(720)]
    route[100]=selected;obj.controller.R={'case':route};obj.controller.cur='case'
    obj.consumer.budget=obj.consumer.budget.__class__(obj.controller.R)
    obj.production.act=lambda _:copy.deepcopy(selected)
    out=obj.act(o,cfg)
    post=obj.consumer.last_packet['post_unit_observation']
    assert post['private']['shed']['MILK']==100 and post['private']['shed']['WHEAT']==0
    assert out['farmer']==selected['farmer'] and out['hands']==selected['hands']
    assert out['market'][1]==selected['market'][1]
    assert sum(x[2] for x in out['market'] if x and x[:2]==['SELL','MILK'])<=100
    rows.append({'case':'ordered_worker_and_market_slots','action':out,'post_shed':post['private']['shed']})
    # A committed future harvest is consumed as capacity, never immediate stock.
    obj=TitanAgent(Features(consumer='ordered'));obj._initialize()
    o=copy.deepcopy(obs);o['step']=21;o['day']=0;o['hour']=21
    o['private']['shed']={'CARROT':94};o['private']['inventories']=[{'EGG':2},{}]
    import mechanics as m
    farm=o['farms'][0];x,y=farm['farmer'];farm['tiles'][y][x]=m._new_animal('GOOSE',0)
    farm['tiles'][y][x]['yield_units']=4
    target={'at':[x,y],'product':'EGG','op':['HARVEST'],'units':4,'value_now':200}
    plan={'target':target,'phase':'go','steps':1,'home':(x,y),'started':20,
          'unit':0,'window':4,'errand_id':'cap-20-w0'}
    obj.production.plans={0:copy.deepcopy(plan)};obj.production._commit(plan,target,o,0,20,0)
    selected={'farmer':['PASS'],'hands':[['PASS']],'market':[]}
    route=[copy.deepcopy(selected) for _ in range(720)];obj.controller.R={'case':route};obj.controller.cur='case'
    obj.consumer.budget=obj.consumer.budget.__class__(obj.controller.R)
    obj.production.act=lambda _:copy.deepcopy(selected)
    out=obj.act(o,cfg);packet=obj.consumer.last_packet
    assert sum(e['pending_capacity_units'] for e in packet['arrival_contract']['capacity_events'])==4
    assert sum(e['quantity_delta'] for e in packet['projection']['stock_events'] if e['product']=='EGG')==2
    assert not any(x and x[:2]==['SELL','EGG'] for x in out['market'])
    rows.append({'case':'committed_capacity_not_stock','pending_units':4,'projected_existing_cargo':2})
    # Actual selected-action timeout preserves precisely the selected fallback.
    obj=TitanAgent(Features(budget_seconds=.015,reserve_seconds=.002));obj._initialize()
    selected={'farmer':['PASS'],'hands':[['PASS']],'market':[['SELL','CARROT',1]]}
    obj.production.act=lambda _:copy.deepcopy(selected)
    def spin(*args):
        while True:pass
    obj.transform_selected=spin
    before=time.perf_counter();out=obj.act(obs,cfg);elapsed=time.perf_counter()-before
    assert out==selected and obj.diagnostics['fallback_stage']=='selected_transform'
    assert elapsed<1 and not obj.ready
    rows.append({'case':'selected_timeout','seconds':elapsed,'diagnostics':obj.diagnostics})
    # Timeout during construction uses visible terminal whole-lot DROP+SELL.
    obj=TitanAgent(Features(budget_seconds=.015,reserve_seconds=.002));obj._initialize=spin
    o=copy.deepcopy(obs);o['step']=718;o['private']['shed']={'MILK':98};o['private']['inventories']=[{'CARROT':4},{}]
    before=time.perf_counter();out=obj.act(o,cfg);elapsed=time.perf_counter()-before
    assert out==deadline.terminal_liquidation_fallback(o,cfg)
    assert ['SELL','CARROT',2] in out['market'] and elapsed<1
    rows.append({'case':'cold_terminal_timeout','seconds':elapsed,'action':out})
    # Actual T05 owner is invoked by the opt-in consumer, not merely imported.
    obj=TitanAgent(Features(terminal_route=True));o=copy.deepcopy(obs);o['step']=718
    out=obj.act(o,cfg);assert obj.production.parent_calls==1
    rows.append({'case':'terminal_owner_consumed','action':out,'seconds':obj.diagnostics['elapsed_seconds']})
for module in list(sys.modules.values()):
    p=getattr(module,'__file__',None)
    if p and '/commons-work/' in p:raise AssertionError('original repository import: '+p)
assert all(r.get('seconds',0)<1 for r in rows)
print(json.dumps(rows))
'''

def main():
    OrderedSelectedSellTests.setUpClass();helper=OrderedSelectedSellTests()
    obs,cfg,state,env=helper.fixture(100,{'CARROT':1})
    archive=ROOT/'exports/titan-current.tar.gz'
    report={'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'engine_sha256':helper.helper.hashes,'new_games':0,'cases':[]}
    with tempfile.TemporaryDirectory(prefix='titan-clean-',dir='/tmp') as folder:
        work=Path(folder);runtime=work/'runtime';runtime.mkdir()
        with tarfile.open(archive) as tar:tar.extractall(runtime,filter='data')
        source=(runtime/'SOURCE.json').read_bytes();report['source_manifest_sha256']=hashlib.sha256(source).hexdigest()
        for p, row in json.loads(source)['runtime'].items():
            assert hashlib.sha256((runtime/p).read_bytes()).hexdigest()==row['sha256'],p
        worker=work/'worker.py';worker.write_text(WORKER)
        for seat in (0,1):
            cold=copy.deepcopy(state[seat].observation);cold['step']=0;cold['day']=0;cold['hour']=0
            fixture=work/'fixture.json';fixture.write_text(json.dumps({'obs':cold,'cfg':cfg}))
            result=subprocess.run([sys.executable,'-I',str(worker),str(runtime),str(fixture),'cold'],cwd=work,capture_output=True,text=True,timeout=10,check=True)
            report['cases'].extend(json.loads(result.stdout))
        fixture.write_text(json.dumps({'obs':obs,'cfg':cfg}))
        result=subprocess.run([sys.executable,'-I',str(worker),str(runtime),str(fixture),'boundaries'],cwd=work,capture_output=True,text=True,timeout=15)
        if result.returncode:raise RuntimeError(result.stderr)
        report['cases'].extend(json.loads(result.stdout))
        # Feed the exact returned funding queues through official market execution.
        for case in report['cases']:
            if '_funding_' in case['case']:
                money=int(case['case'].split('_')[-1]);s,e=helper.helper.fixture(step=100,cash=money)
                s[0].action=case['action'];helper.engine._process_market(s,e)
                expected_hands=0 if money==170 else 1
                assert len(s[0].observation['farms'][0]['hands'])==expected_hands
                case['official_hands']=expected_hands
    report['maximum_measured_action_seconds']=max(c.get('seconds',0) for c in report['cases'])
    report['episode_allowance']='Full-game wall/episode allowance to be recorded by Claude/WIDEFIELD for this exact archive; boundary timings alone are not episode proof.'
    (ROOT/'runtime/integrated-selected/CURRENT-TESTS.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'cases':len(report['cases']),'max_seconds':report['maximum_measured_action_seconds'],'archive':report['archive_sha256']}))
if __name__=='__main__':main()
