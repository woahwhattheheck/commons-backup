"""Behavior tests using the actual upstream interpreter and frozen peer source."""
import ast
import os
from pathlib import Path
import tempfile
import unittest
import study
import diagnostics

@unittest.skipUnless(os.environ.get('KAG_STUDY_ROOT'),'Frozen study input not supplied')
class ActualEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['KAG_STUDY_ROOT'])
        study.verify_peer(cls.root)
        cls.ev=study.evaluator()
        cls.engine,_=cls.ev.get_engine(cls.root/'engine',cls.root/'peer/evaluate.py')
        cls.source=(cls.root/'peer/main.py').read_text()
        cls.temp=tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def observation(self, pending):
        cfg=self.ev.Struct({k:v.get('default') if isinstance(v,dict) else v for k,v in self.engine.specification['configuration'].items()})
        cfg.seed=733
        env=self.ev.Struct(configuration=cfg,done=False,info={})
        state=[self.ev.Struct(observation=self.ev.Struct(),action={},status='ACTIVE',reward=0) for _ in range(2)]
        self.engine.interpreter(state,env)
        obs=state[0].observation
        obs.step,obs.day,obs.hour=27*24,27,0
        animal=self.engine._new_animal('COW',0)
        animal.update(fed_today=True,cared_today=False,yield_units=0,pending_care_bonus=pending,fertilizer_available=False)
        obs.farms[0]['tiles'][4][4]=animal
        return obs,cfg

    def generated(self, options, name):
        path=Path(self.temp.name)/(name+'.py')
        path.write_text(study.build_variant(self.source,options))
        return study.load(path,name).agent

    def test_avoid_care_when_bonus_already_fills_capacity(self):
        obs,cfg=self.observation(6)
        old=self.generated(study.VARIANTS['compact22'],'without_triage')
        improved=self.generated(study.VARIANTS['compact_care'],'with_triage')
        self.assertEqual(old(obs,cfg)['farmer'],['CARE'])
        self.assertNotEqual(improved(obs,cfg)['farmer'],['CARE'])

    def test_care_preserved_when_bonus_can_fit(self):
        obs,cfg=self.observation(0)
        improved=self.generated(study.VARIANTS['compact_care'],'care_fits')
        self.assertEqual(improved(obs,cfg)['farmer'],['CARE'])

    def test_every_generated_variant_is_complete(self):
        obs,cfg=self.observation(0)
        for name,options in study.VARIANTS.items():
            with self.subTest(name=name):
                agent=self.generated(options,'variant_'+name)
                action=agent(obs,cfg)
                self.assertIsInstance(action,dict)
                self.assertLessEqual(len(action['market']),10)
                self.assertEqual(action['hands'],[])

    def test_selected_standalone_matches_exact_generated_bytes(self):
        actual=Path(__file__).with_name('main.py').read_bytes()
        expected=study.build_variant(self.source,study.VARIANTS['lean20']).encode()
        self.assertEqual(actual,expected)
        self.assertEqual(study.digest(actual),'d9487c031b50ede06a706acc8bcb40e0b5a681d9b5e92c1a1a96492b26c2dd62')

    def test_only_policy_assignment_changes_executable_source(self):
        def without_policy(source):
            parsed=ast.parse(source)
            parsed.body=[n for n in parsed.body if not (isinstance(n,ast.Assign) and
                         any(isinstance(t,ast.Name) and t.id=='POLICY' for t in n.targets))]
            return ast.dump(parsed)
        standalone=Path(__file__).with_name('main.py').read_text()
        self.assertEqual(without_policy(standalone),without_policy(self.source))

    def test_selected_standalone_empty_observation(self):
        agent=study.load(Path(__file__).with_name('main.py'),'selected_standalone_test').agent
        self.assertEqual(agent({}),{'farmer':['PASS'],'hands':[],'market':[]})

    def test_observer_does_not_change_game_trace(self):
        pair=['official_starter','official_starter']
        kwargs=dict(cache=self.root/'engine',loader=self.root/'peer/evaluate.py',seed=733,candidate_seat=0,episode_steps=49)
        native=self.ev.play(self.engine,pair,**kwargs)
        observer=diagnostics.ObservedEngine(self.engine)
        measured=self.ev.play(observer,pair,**kwargs)
        self.assertEqual(native['status'],'complete')
        self.assertEqual(measured['trace_sha256'],native['trace_sha256'])
        self.assertEqual(measured['scores'],native['scores'])
        report=observer.report()
        self.assertEqual(sum(report['unit_operation_requests'][0].values()),48)
        self.assertEqual(report['daily'][-1]['farms'][0]['money'],native['scores'][0])
        self.assertGreater(len(report['daily']),1)

if __name__=='__main__': unittest.main(verbosity=2)
