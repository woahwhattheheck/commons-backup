import copy, unittest, os
from pathlib import Path
import analyze

class TraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev=analyze.evaluator()
        cls.engine,_=cls.ev.get_engine(Path(os.environ.get('KAG_ENGINE_DIR', 'engine-cache')))
    def fixture(self):
        ev=self.ev; engine=self.engine
        cfg=ev.Struct({k:v.get('default') if isinstance(v,dict) else v for k,v in engine.specification['configuration'].items()})
        cfg.seed=4242001
        env=ev.Struct(configuration=cfg,done=False,info={})
        state=[ev.Struct(observation=ev.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)]
        engine.interpreter(state,env)
        frames=[]
        for step in range(25):
            for s in state: s.observation.step=step
            if step==0: frames.append(copy.deepcopy(state))
            for s in state: s.action={'farmer':['PASS'],'market':[['BUY_PRODUCT','WHEAT',2]] if step==0 else ([['SELL','WHEAT',1],['HIRE']] if step==1 else [])}
            engine.interpreter(state,env)
            for s in state: s.observation.step=step+1
            frames.append(copy.deepcopy(state))
        return {'steps':frames,'configuration':dict(cfg),'info':env.info}
    def test_reconcile_and_corruption(self):
        replay=self.fixture(); result=analyze.analyze(replay,self.engine,self.ev)
        self.assertEqual(result['transition_statuses'],{'RECONCILED':25},str(result['transitions'][0]['audit']))
        self.assertEqual(result['verified_transition_totals'][0]['purchases']['WHEAT'],2)
        self.assertEqual(result['verified_transition_totals'][0]['sales_units']['WHEAT'],1)
        self.assertEqual(result['verified_transition_totals'][0]['cash_residual'],0)
        replay['steps'][1][0]['observation']['farms'][0]['money']+=1
        result=analyze.analyze(replay,self.engine,self.ev)
        self.assertGreater(result['transition_statuses'].get('MISMATCH',0),0)
    def test_missing_private(self):
        replay=self.fixture()
        del replay['steps'][0][1]['observation']['private']
        result=analyze.analyze(replay,self.engine,self.ev)
        self.assertEqual(result['transitions'][0]['audit']['status'],'UNAVAILABLE')
if __name__=='__main__': unittest.main()
