import unittest
from dataclasses import replace
from search_kernel import Model, Limits, Infeasible, canonical_key, search

class KernelTests(unittest.TestCase):
    def model(self):
        return Model(lambda s:(0,1), lambda s,a,c:(s[0]+1,s[1]+a*c),
                     lambda s,c:s[1], state_key=lambda s:s, action_key=lambda a:a)
    def run_search(self, model=None, **kw):
        return search(model or self.model(),[(0,0)], [1], 0,
                      limits=kw.pop('limits',Limits(seconds=10,max_depth=3)), **kw)
    def test_deep_plan(self):
        r=self.run_search(); self.assertEqual(r.principal_variation,(1,1,1)); self.assertEqual(r.values,(3,))
    def test_zero_time_explicit_unscored(self):
        r=self.run_search(limits=Limits(seconds=0)); self.assertEqual(r.status,'unscored_fallback');self.assertEqual(r.values,())
    def test_zero_nodes_explicit_unscored(self):
        r=self.run_search(limits=Limits(seconds=10,max_transitions=0)); self.assertEqual(r.transitions,0);self.assertEqual(r.values,())
    def test_mid_scenario_is_not_promoted(self):
        r=search(self.model(),[(0,0),(0,0)],[1,2],0,limits=Limits(seconds=10,max_transitions=3))
        self.assertEqual(r.action,0);self.assertEqual(r.values,(0,0));self.assertEqual(r.completed_depth,0)
    def test_last_completed_depth_retained(self):
        one=self.run_search(limits=Limits(seconds=10,max_depth=1))
        r=self.run_search(limits=Limits(seconds=10,max_depth=3,max_transitions=one.transitions+1))
        self.assertEqual(r.completed_depth,1); self.assertEqual(r.values,(1,))
    def test_no_scenario_specific_first_move(self):
        model=Model(lambda s:('A','B'),lambda s,a,c:a,
                    lambda s,c:10 if s==c else -1, state_key=lambda s:s)
        r=search(model,['',''],['A','B'],'A',limits=Limits(seconds=10,max_depth=1))
        self.assertEqual(sorted(r.values),[-1,10]);self.assertNotEqual(r.values,(10,10))
    def test_intersection_of_feasible_actions(self):
        m=Model(lambda s:(0,1) if s==0 else (0,),lambda s,a,c:a,lambda s,c:s)
        r=search(m,[0,1],['a','b'],0,limits=Limits(seconds=10,max_depth=1));self.assertEqual(r.action,0)
    def test_no_transposition_across_scenarios(self):
        r=search(self.model(),[(0,0)]*2,[1,5],0,limits=Limits(seconds=10,max_depth=1));self.assertEqual(r.values,(1,5))
    def test_cache_reuses_prefixes(self):
        a=self.run_search(cache=True);b=self.run_search(cache=False)
        self.assertEqual(a.principal_variation,b.principal_variation);self.assertLess(a.transitions,b.transitions);self.assertGreater(a.cache_hits,0)
    def test_new_call_cannot_reuse_old_scenario(self):
        a=self.run_search();r=search(self.model(),[(0,0)],[-1],0,limits=Limits(seconds=10,max_depth=2));self.assertEqual(r.values,(0,))
    def test_nan_is_rejected(self):
        with self.assertRaises(ValueError):self.run_search(replace(self.model(),evaluate=lambda s,c:float('nan')))
    def test_infeasible_branch(self):
        m=self.model()
        def transition(s,a,c):
            if a==1:raise Infeasible()
            return (s[0]+1,0)
        r=self.run_search(replace(m,transition=transition));self.assertEqual(r.action,0)
    def test_wait_can_win_after_event(self):
        m=Model(lambda s:('WAIT','SELL') if s[1] else ('WAIT',),
                lambda s,a,c:(s[0]+1, s[1]-(a=='SELL'),s[2]+((100 if s[0] else 1) if a=='SELL' and s[1] else 0)),
                lambda s,c:s[2],extend=lambda ss:ss[0][0]==1)
        r=search(m,[(0,1,0)],[None],'WAIT',limits=Limits(seconds=10,max_depth=1,extensions=1))
        self.assertEqual(r.principal_variation,('WAIT','SELL'));self.assertEqual(r.values,(100,));self.assertEqual(r.selective_depth,2)
    def test_warm_start_does_not_override_better_value(self):
        r=self.run_search(warm_start=(0,0,0));self.assertEqual(r.action,1)
    def test_order_ablation_same_value(self):
        self.assertEqual(self.run_search(ordering=False).values,self.run_search().values)
    def test_fixed_depth_matches_iterative(self):
        self.assertEqual(self.run_search(iterative=False).values,self.run_search().values)
    def test_callback_crossing_deadline_not_admitted(self):
        t=[0]
        m=replace(self.model(),transition=lambda s,a,c:(t.__setitem__(0,2) or (1,0)))
        r=self.run_search(m,limits=Limits(seconds=1),clock=lambda:t[0]);self.assertEqual(r.values,());self.assertEqual(r.transitions,1)
    def test_candidate_generator_bounded(self):
        m=replace(self.model(),candidates=lambda s:range(500))
        with self.assertRaisesRegex(ValueError,'candidate_limit'):self.run_search(m,limits=Limits(seconds=10,candidate_limit=3))
    def test_duplicate_scenario_keys_rejected(self):
        with self.assertRaises(ValueError):search(self.model(),[(0,0)]*2,[1,1],0)
    def test_key_preserves_time_controller_inventory(self):
        base={'step':1,'stock':2,'controller':'a','money':3}
        for k,v in [('step',2),('stock',3),('controller','b'),('money',4)]:
            self.assertNotEqual(canonical_key(base),canonical_key(dict(base,**{k:v})))
    def test_invalid_limits(self):
        for args in ({'seconds':float('inf')},{'max_depth':65},{'max_transitions':-1},{'extensions':1.2},{'candidate_limit':0}):
            with self.assertRaises(ValueError):Limits(**args)

if __name__=='__main__': unittest.main()
