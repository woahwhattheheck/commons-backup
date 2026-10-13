"""New exact-engine admission regressions; reuses the existing offline loader."""
import copy
import importlib.util
import itertools
import json
import os
import ast
import subprocess
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('TITAN_REPO_ROOT', HERE.parents[2]))
ENGINE_DIR = Path(os.environ.get('TITAN_ENGINE_DIR', '/tmp/titan-engine'))
spec = importlib.util.spec_from_file_location('admission_existing_evaluator',
    ROOT / 'revenue/kaggriculture/cloud-eval/evaluate.py')
evaluator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = evaluator
spec.loader.exec_module(evaluator)
engine, ENGINE_HASHES = evaluator.get_engine(ENGINE_DIR)
from terminal_admission import RivalScenario, optimize_terminal_admission, TerminalAdmissionAgent

RECEIPTS = []
S = evaluator.Struct


def setup_case(capacity=3, carried=None, shed=None, player=0):
    cfg = S({k:v.get('default') if isinstance(v,dict) else v
             for k,v in engine.specification['configuration'].items()})
    cfg.seed = 1  # Initialization only; all economic state below is constructed.
    env = S(configuration=cfg,done=False,info={})
    states = [S(observation=S(),action={},status='ACTIVE',reward=0) for _ in range(2)]
    engine.interpreter(states,env)
    for state in states:
        state.observation.step = cfg.episodeSteps-2
    cfg.shedCapacity = capacity
    inv = carried if carried is not None else [{'WHEAT':3},{'WOOL':3}]
    farm = states[player].observation.farms[player]
    farm['farmer'] = [4,4]
    farm['hands'] = [[4,4] for _ in inv[1:]]
    private = states[player].observation.private
    private['inventories'] = copy.deepcopy(inv)
    private['shed'] = copy.deepcopy(shed or {})
    return states,env


def default_action(states,player=0):
    return {'farmer':['DROP'],
            'hands':[['DROP'] for _ in states[player].observation.farms[player]['hands']],
            'market':[['SELL','WHEAT',100],['SELL','WOOL',100]]}


def scenarios(capacity=3):
    return [RivalScenario('idle',{},[],'constructed no-sale hypothesis'),
            RivalScenario('wool-sale',{'WOOL':capacity},[['SELL','WOOL',capacity]],
                          'constructed full-stock sale stress; not inferred private state')]


def solve(states,env,selected,player=0,**kwargs):
    return optimize_terminal_admission(engine,states[player].observation,env.configuration,
        selected,kwargs.pop('scenarios',scenarios(env.configuration.shedCapacity)),
        max_states=kwargs.pop('max_states',1024),max_candidates=kwargs.pop('max_candidates',1024),
        time_budget_s=kwargs.pop('time_budget_s',5),**kwargs)


def transition(states,env,action,scenario,player):
    states,env = copy.deepcopy((states,env))
    rival = 1-player
    states[player].action = copy.deepcopy(action)
    states[rival].action = {'farmer':['PASS'],'hands':[],
                            'market':[list(x) for x in scenario.market]}
    states[rival].observation.private['shed'] = dict(scenario.shed)
    states[rival].observation.private['inventories'] = [{}]
    before = [f['money'] for f in states[0].observation.farms]
    engine.interpreter(states,env)
    after = [f['money'] for f in states[0].observation.farms]
    assert all(state.status=='DONE' for state in states)
    return [after[player]-before[player],after[rival]-before[rival]], states


class AdmissionTests(unittest.TestCase):
    def assert_receipts(self,name,states,env,selected,player=0,**kwargs):
        before = json.dumps([states,env,selected],sort_keys=True)
        action,report = solve(states,env,selected,player,**kwargs)
        self.assertEqual(before,json.dumps([states,env,selected],sort_keys=True))
        for scenario,row in zip(kwargs.get('scenarios',scenarios(env.configuration.shedCapacity)),report['scenarios']):
            outputs = {}
            for label,choice in [('original',selected),('control',report['same_workers_liquidation_action']),('selected',action)]:
                actual,terminal = transition(states,env,choice,scenario,player)
                self.assertEqual(actual,[row[label+'_own'],row[label+'_rival']])
                outputs[label] = {'cash_delta':actual,'own_private':terminal[player].observation.private,
                                  'market_inventory':terminal[0].observation.market['inventory']}
            RECEIPTS.append({'case':name,'player':player,'scenario':scenario.name,
                             'input_observation':states[player].observation,
                             'config':dict(env.configuration),'original':selected,'selected':action,
                             'report_row':row,'terminal_outputs':outputs})
        return action,report

    def test_later_worker_priority_both_positions(self):
        for player in (0,1):
            states,env=setup_case(player=player)
            action,report=self.assert_receipts('later-worker',states,env,default_action(states,player),player)
            self.assertTrue(report['changed'])
            self.assertEqual(action['farmer'],['PASS'])
            self.assertTrue(all(r['margin_gain_vs_liquidation']>0 for r in report['scenarios']))

    def test_pickup_clears_before_later_deposit(self):
        for player in (0,1):
            states,env=setup_case(carried=[{}, {'WOOL':3}],shed={'WHEAT':3},player=player)
            selected=default_action(states,player);selected['farmer']=['PASS']
            action,report=self.assert_receipts('clearance',states,env,selected,player)
            self.assertEqual(action['farmer'],['PICKUP','WHEAT',3])
            self.assertEqual(report['selected_post_unit_shed'].get('WOOL'),3)

    def test_inventory_insertion_order_matters(self):
        states,env=setup_case(carried=[{'WHEAT':3,'WOOL':3}])
        action,report=self.assert_receipts('within-worker',states,env,default_action(states))
        self.assertEqual(action['farmer'],['PLACE','WOOL',3])
        self.assertEqual(report['scenarios'][0]['margin_gain_vs_liquidation'],527)

    def test_partial_pickup_preserves_sellable_low_stock(self):
        states,env=setup_case(capacity=3,carried=[{}, {'WOOL':2}],shed={'WHEAT':3})
        selected=default_action(states);selected['farmer']=['PASS']
        action,report=self.assert_receipts('partial-clearance',states,env,selected)
        self.assertEqual(action['farmer'],['PICKUP','WHEAT',2])
        self.assertEqual(report['selected_post_unit_shed'],{'WHEAT':1,'WOOL':2})

    def test_three_workers_share_one_capacity(self):
        states,env=setup_case(capacity=3,carried=[{'WHEAT':3},{'MILK':2},{'WOOL':3}])
        action,report=self.assert_receipts('three-workers',states,env,default_action(states))
        self.assertEqual(sum(report['selected_post_unit_shed'].values()),3)
        self.assertTrue(report['changed'])

    def test_default_budget_completes_small_discriminator(self):
        states,env=setup_case()
        action,report=solve(states,env,default_action(states),max_states=32,max_candidates=32,time_budget_s=.15)
        self.assertTrue(report['changed'])
        self.assertFalse(report['budget_exhausted'])

    def test_liquidation_without_admission_gets_no_credit(self):
        states,env=setup_case(capacity=100,carried=[{'WOOL':3}])
        selected=default_action(states);selected['market']=[]
        action,report=solve(states,env,selected)
        self.assertEqual(action,selected)
        self.assertEqual(report['reason'],'no_capacity_pressure')
        self.assertEqual(report['nodes_expanded'],0)
        self.assertFalse(report['changed'])

    def test_nonterminal_and_missing_scenarios_preserve(self):
        states,env=setup_case();selected=default_action(states)
        states[0].observation.step=717
        self.assertEqual(solve(states,env,selected)[0],selected)
        states[0].observation.step=718
        action,report=solve(states,env,selected,scenarios=[])
        self.assertEqual(action,selected);self.assertEqual(report['reason'],'no_explicit_rival_scenarios')

    def test_active_purchases_preserve_selected_queue(self):
        states,env=setup_case();selected=default_action(states)
        for order in [['HIRE'],['BUY_LAND'],['BUY_SEED','WHEAT',2],['BUY_PRODUCT','WHEAT',1],['BUY_ANIMAL','SHEEP',1]]:
            selected['market']=[order]
            action,report=solve(states,env,selected)
            self.assertEqual(action,selected);self.assertEqual(report['reason'],'active_non_sale_order')

    def test_market_indices_and_limit_remain(self):
        states,env=setup_case();selected=default_action(states)
        env.configuration.maxMarketOrdersPerTurn=3
        selected['market']=[['BUY_SEED','WHEAT',0],['SELL','WOOL',1],['SELL','WOOL',2]]
        action,report=self.assert_receipts('fixed-slots',states,env,selected)
        self.assertEqual(action['market'][0],selected['market'][0])
        self.assertEqual(action['market'][1],['SELL','WOOL',3])
        self.assertEqual(action['market'][2],['SELL','WOOL',0])
        self.assertEqual(len(action['market']),3)

    def test_no_movement_or_animal_action_replaced(self):
        states,env=setup_case();selected=default_action(states)
        selected['farmer']=['NORTH']
        action,report=solve(states,env,selected)
        self.assertEqual(action['farmer'],selected['farmer'])
        selected['farmer']=['PLACE','GOOSE',1]
        action,report=solve(states,env,selected)
        self.assertEqual(action['farmer'],selected['farmer'])

    def test_nonadjacent_worker_unchanged(self):
        states,env=setup_case();states[0].observation.farms[0]['farmer']=[0,0]
        action,report=solve(states,env,default_action(states))
        self.assertEqual(action['farmer'],['DROP'])

    def test_scenario_contract_and_count_validation(self):
        states,env=setup_case();selected=default_action(states)
        for scenario in [RivalScenario('x',{'WOOL':4},[],'x'),
                         RivalScenario('x',{},[['BUY_PRODUCT','WHEAT',1]],'x'),
                         RivalScenario('x',{'WOOL':-1},[],'x'),
                         RivalScenario('x',{},[],''),RivalScenario('x',{'WOOL':True},[],'x')]:
            with self.assertRaises(ValueError): solve(states,env,selected,scenarios=[scenario])
        for args in [{'max_states':0},{'max_candidates':True},{'time_budget_s':float('nan')}]:
            with self.assertRaises(ValueError): solve(states,env,selected,**args)

    def test_cooperative_expiry_returns_original(self):
        states,env=setup_case();selected=default_action(states)
        with patch('terminal_admission.time.perf_counter',side_effect=[0,1,1]):
            action,report=solve(states,env,selected,time_budget_s=.15)
        self.assertEqual(action,selected);self.assertTrue(report['budget_exhausted'])
        self.assertFalse(report['complete_search'])

    def test_pruned_search_never_claims_exhaustive(self):
        states,env=setup_case()
        _,report=solve(states,env,default_action(states),max_states=1,max_candidates=1)
        self.assertTrue(report['search_truncated']);self.assertFalse(report['complete_search'])

    def test_producer_called_once_and_error_preserved(self):
        states,env=setup_case();selected=default_action(states);calls=[]
        def producer(obs,cfg):calls.append(1);return copy.deepcopy(selected)
        agent=TerminalAdmissionAgent(producer,engine,lambda o,c:scenarios(c.shedCapacity))
        agent.act(states[0].observation,env.configuration);self.assertEqual(len(calls),1)
        states[0].observation.step=717
        self.assertEqual(agent.act(states[0].observation,env.configuration),selected)
        self.assertEqual(len(calls),2)
        def error(obs,cfg):calls.append(1);raise TypeError('original body')
        agent=TerminalAdmissionAgent(error,engine,lambda o,c:[])
        with self.assertRaisesRegex(TypeError,'original body'):agent.act(states[0].observation,env.configuration)
        self.assertEqual(len(calls),3)

    def test_large_clearance_uses_capacity_breakpoint(self):
        states,env=setup_case(capacity=100,carried=[{}, {'WOOL':57}],shed={'WHEAT':100})
        selected=default_action(states);selected['farmer']=['PASS']
        action,report=self.assert_receipts('large-clearance',states,env,selected,
                                          max_states=32,max_candidates=32,time_budget_s=.15,
                                          scenarios=scenarios(100)[:1])
        self.assertTrue(report['changed'])
        self.assertTrue(report['search_truncated'])
        self.assertEqual(action['farmer'],['PICKUP','WHEAT',57])
        self.assertFalse(report['budget_exhausted'])

    def test_late_high_value_sale_stress_veto(self):
        # Rival's earlier full sale can drive wool to the floor before ours.
        # Idle-only clearance is not robust to this supplied second hypothesis.
        states,env=setup_case(capacity=100,carried=[{}, {'WOOL':57}],shed={'WHEAT':100})
        selected=default_action(states);selected['farmer']=['PASS']
        action,report=self.assert_receipts('sale-stress-veto',states,env,selected,
                                          max_states=32,max_candidates=32,time_budget_s=.15)
        self.assertEqual(action,selected)
        self.assertFalse(report['changed'])

    def test_nonpressure_fast_path_avoids_engine_search(self):
        states,env=setup_case(capacity=100,carried=[{'WHEAT':8} for _ in range(10)])
        with patch.object(engine,'_process_market',side_effect=AssertionError('unneeded market call')):
            action,report=solve(states,env,default_action(states))
        self.assertEqual(action,default_action(states))
        self.assertEqual(report['reason'],'no_capacity_pressure')
        self.assertEqual(report['nodes_expanded'],0)

    def test_offline_market_binding_matches_full_engine(self):
        from market_primitives import make_primitives
        path=ROOT/'revenue/kaggriculture/cloud-titan-composition/vendor/sell/mechanics.py'
        mechanics=evaluator.import_file(path,'admission_exact_sell_mechanics')
        runtime=make_primitives(mechanics)
        for player in (0,1):
            states,env=setup_case(player=player)
            selected=default_action(states,player)
            expected,first=solve(states,env,selected,player)
            actual,second=optimize_terminal_admission(runtime,states[player].observation,
                env.configuration,selected,scenarios(),max_states=1024,max_candidates=1024,time_budget_s=5)
            self.assertEqual(expected,actual)
            self.assertEqual(first['scenarios'],second['scenarios'])

    def test_exact_market_definition_provenance(self):
        import market_primitives
        original=ast.parse((ENGINE_DIR/'kaggriculture.py').read_text())
        extract=ast.parse(Path(market_primitives.__file__).read_text())
        for name in ('_refresh_prices','_parse_order','_process_market'):
            a=next(n for n in original.body if isinstance(n,ast.FunctionDef) and n.name==name)
            b=next(n for n in extract.body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.dump(a,include_attributes=False),ast.dump(b,include_attributes=False))

    def test_fresh_standard_library_only_runtime(self):
        states,env=setup_case();selected=default_action(states)
        code="""import sys,json
sys.path[:0]=sys.argv[1:]
import mechanics
from market_primitives import make_primitives
from terminal_admission import RivalScenario,optimize_terminal_admission
packet=json.loads(sys.stdin.read())
a,r=optimize_terminal_admission(make_primitives(mechanics),packet['obs'],packet['cfg'],packet['action'],
    [RivalScenario('idle',{},[],'fixture')],time_budget_s=5,max_states=128,max_candidates=128)
assert not any(n.startswith('kaggle_environments') for n in sys.modules)
print(json.dumps(a))
"""
        run=subprocess.run([sys.executable,'-I','-S','-c',code,str(HERE),
            str(ROOT/'revenue/kaggriculture/cloud-titan-composition/vendor/sell')],
            input=json.dumps({'obs':states[0].observation,'cfg':env.configuration,'action':selected}),
            text=True,capture_output=True,timeout=5,check=True)
        self.assertEqual(json.loads(run.stdout)['farmer'],['PASS'])

    def test_exact_small_independent_sequence_enumeration(self):
        # Independent exhaustive choices on small reached-by-construction states.
        # This oracle never calls the module's candidate generator or projection.
        for wheat,wool,stock in itertools.product(range(3),repeat=3):
            if wheat+wool+stock==0:continue
            states,env=setup_case(capacity=2,carried=[{'WHEAT':wheat},{'WOOL':wool}],shed={'WHEAT':stock})
            selected=default_action(states);sc=scenarios(2)[:1]
            action,report=solve(states,env,selected,scenarios=sc)
            observed=transition(states,env,action,sc[0],0)[0][0]
            baseline=transition(states,env,report.get('same_workers_liquidation_action',selected),sc[0],0)[0][0]
            best=baseline
            first=[['PASS'],['DROP']]+[['PLACE','WHEAT',q] for q in range(1,3)]+[['PICKUP','WHEAT',q] for q in range(1,3)]
            second=[['PASS'],['DROP']]+[['PLACE','WOOL',q] for q in range(1,3)]
            for a,b in itertools.product(first,second):
                trial={'farmer':a,'hands':[b],'market':[['SELL','WHEAT',2],['SELL','WOOL',2]]}
                best=max(best,transition(states,env,trial,sc[0],0)[0][0])
            self.assertEqual(observed,best,(wheat,wool,stock,report))


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(AdmissionTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if os.environ.get('TITAN_ADMISSION_EVIDENCE'):
        Path(os.environ['TITAN_ADMISSION_EVIDENCE']).write_text(json.dumps({
            'kind':'constructed exact-engine cases; no full games',
            'engine_hashes':ENGINE_HASHES,'tests_run':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),
            'recorded_scenario_cases':len(RECEIPTS),'recorded_interpreter_transitions':3*len(RECEIPTS),
            'cases':RECEIPTS},indent=2)+'\n')
    sys.exit(0 if result.wasSuccessful() else 1)
