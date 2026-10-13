# SPDX-License-Identifier: Apache-2.0
"""Supplied live-policy integration, not new route economics or a game panel."""
from pathlib import Path
import argparse,copy,gzip,hashlib,importlib.util,json,sys,time,unittest
from unittest.mock import patch

P=argparse.ArgumentParser(description=__doc__)
P.add_argument('--root',type=Path,required=True)
P.add_argument('--baseline-prefix',type=Path,required=True,help='Directory containing the recorded 9989001 SELL frames')
P.add_argument('--report',type=Path,required=True)
ARGS=P.parse_args();ROOT=ARGS.root.resolve();T13=ROOT/'cloud-hosted-loss-response'

def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
S=load(T13/'seed_main.py','capital_seed_subject')
C=load(T13/'juniper-funding/capital_arms.py','capital_seed_arms')
RECEIPTS=[];COUNTS={'policy_calls':0,'controller_calls':0,'prefix_actions_checked':0}
FRAMES={seat:[json.loads(l) for l in gzip.open(ARGS.baseline_prefix/f'9989001-p{seat}-sell.frames.jsonl.gz','rt')] for seat in (0,1)}

def obs_at(seat,step):
 row=FRAMES[seat][step];obs=copy.deepcopy(row['state'][seat]['observation']);obs.update(step=step,remainingOverageTime=0)
 return obs,copy.deepcopy(row['configuration'])

def actual_call(run,obs,cfg):
 original=copy.deepcopy((obs,cfg))
 with patch.object(run.policy,'act',wraps=run.policy.act) as p, patch.object(run.controller,'act',wraps=run.controller.act) as c:
  out=run(obs,cfg)
 # For sell=False the supplied policy IS its controller, so tests handle that
 # call separately rather than multiplying wrappers on the same method.
 assert p.call_count==c.call_count==1
 COUNTS['policy_calls']+=p.call_count;COUNTS['controller_calls']+=c.call_count
 assert (obs,cfg)==original
 return out

class CapitalJoinTests(unittest.TestCase):
 def test_supplied_pair_required_before_initialization(self):
  for kw in ({'policy':object()},{'controller':object()}):
   with self.assertRaisesRegex(ValueError,'together'):S.make_agent(T13,**kw)

 def test_injected_actor_does_not_construct_another_scheduler_or_parent(self):
  run=C.make_agent('capital');policy=run.policy;controller=run.controller
  constructors=[];previous=sys.getprofile()
  def profile(frame,event,arg):
   if event=='call' and frame.f_code.co_name=='__init__':
    obj=frame.f_locals.get('self');name=type(obj).__name__
    if name in ('SellScheduler','Agent','CapitalBundleAgent'):constructors.append(name)
  sys.setprofile(profile)
  try:joined=S.make_agent(T13,policy=policy,controller=controller)
  finally:sys.setprofile(previous)
  self.assertEqual(constructors,[])
  self.assertIs(joined.policy,policy);self.assertIs(joined.controller,controller)
  self.assertIs(joined.controller,policy.scheduler.controller)
  self.assertIs(joined.policy.scheduler.planned,policy.scheduler.planned)
  RECEIPTS.append({'case':'same_actor_injection','additional_actor_constructors':constructors})

 def test_exact_default_prefix_is_unchanged_after_optional_arguments(self):
  # Compare default factory against the no-seed capital actor before226, when
  # both are the unchanged frozen SELL. No seed reduction is due in this prefix.
  for seat in (0,1):
   default=S.make_agent(T13,enabled=False);capital=C.make_agent('capital')
   for step in range(4):
    obs,cfg=obs_at(seat,step)
    a=default(obs,cfg);b=actual_call(capital,obs,cfg)
    self.assertEqual(a,b);self.assertEqual(b,FRAMES[seat][step+1]['state'][seat]['action'])
    self.assertEqual(default.policy.planned,capital.policy.scheduler.planned)
    self.assertEqual(default.policy.pending,capital.policy.scheduler.pending)

 def test_reached_route_switch_and_late_budget_use_same_live_controller(self):
  for seat in (0,1):
   run=C.make_agent('funded')
   for step in range(227):
    obs,cfg=obs_at(seat,step);out=actual_call(run,obs,cfg)
    if step<226:
     self.assertEqual(out,FRAMES[seat][step+1]['state'][seat]['action']);COUNTS['prefix_actions_checked']+=1
   chosen=run.policy.selection
   self.assertTrue(chosen['changed']);self.assertEqual(run.controller.cur,'dc76e4003029ac51')
   self.assertEqual(out['market'][-1],['BUY_ANIMAL','SHEEP',1])
   RECEIPTS.append({'case':'reached_original_quote_switch','seat':seat,'selection':chosen,
                    'source_frame':'frozen-SELL9989001 pre-decision226','same_controller':True})
   # Explicitly constructed later inputs, not alleged on-policy YARN states.
   # The current route remains the real selected tail; zero seeds exposes its
   # demand bound without inferring the future inventory of the saved prefix.
   for step,request,bound,wrong_bound in ((600,17,32,8),(624,9,24,0)):
    obs,cfg=obs_at(seat,step);obs['farms'][seat]['money']=100000.;obs['private']['seeds']['WHEAT']=0
    out=actual_call(run,obs,cfg)
    orders=[o for o in out['market'] if o and o[:2]==['BUY_SEED','WHEAT']]
    self.assertEqual(orders,[['BUY_SEED','WHEAT',request]])
    self.assertEqual(run.budget.remaining('WHEAT',step,run.controller.cur),bound)
    wrong=run.budget.apply(out,{'WHEAT':0},step,'7015cc00acfa4922')
    wrong_orders=[o for o in wrong['market'] if o and o[:2]==['BUY_SEED','WHEAT']]
    self.assertEqual(wrong_orders,[['BUY_SEED','WHEAT',wrong_bound]] if wrong_bound else [])
    RECEIPTS.append({'case':'constructed_late_live_route','seat':seat,'step':step,'retained':request,
                     'remaining_yarn':bound,'wrong_main_retained':wrong_bound,'full_game':False})

 def test_supplied_prefix_actor_state_is_not_reset(self):
  run=C.make_agent('capital')
  for step in range(45):
   obs,cfg=obs_at(0,step);actual_call(run,obs,cfg)
  before=copy.deepcopy((run.policy.scheduler.planned,run.policy.scheduler.pending,run.controller.cur))
  joined=S.make_agent(T13,enabled=False,policy=run.policy,controller=run.controller)
  self.assertEqual(before,(joined.policy.scheduler.planned,joined.policy.scheduler.pending,joined.controller.cur))
  obs,cfg=obs_at(0,45);out=actual_call(joined,obs,cfg)
  self.assertEqual(out,FRAMES[0][46]['state'][0]['action'])

 def test_supplied_exception_reaches_caller_once(self):
  run=C.make_agent('funded');obs,cfg=obs_at(0,0);error=TypeError('capital-policy-body')
  with patch.object(run.policy,'act',side_effect=error) as called:
   with self.assertRaises(TypeError) as caught:run(obs,cfg)
  self.assertIs(caught.exception,error);self.assertEqual(called.call_count,1)

 def test_supplied_arlene_retains_one_argument_dispatch(self):
  original=S.make_agent(T13,sell=False);actor=original.controller
  run=S.make_agent(T13,sell=False,policy=actor,controller=actor);obs,cfg=obs_at(0,0)
  with patch.object(actor,'act',wraps=actor.act) as called:out=run(obs,cfg)
  self.assertEqual(called.call_count,1);self.assertEqual(len(called.call_args.args),1)
  self.assertIs(run.policy,actor);self.assertIs(run.controller,actor)
  self.assertIsInstance(out,dict)

 def test_raw_file_entry_without_file_global(self):
  path=T13/'juniper-funding/capital_arms.py';namespace={};exec(compile(path.read_bytes(),str(path),'exec'),namespace)
  for seat in (0,1):
   obs,cfg=obs_at(seat,0);a=namespace['agent'](obs,cfg);b=C.make_agent()(obs,cfg)
   self.assertEqual(a,b);self.assertNotIn('__file__',namespace)

 def test_fresh_actors_have_independent_runtime_state(self):
  a=C.make_agent();b=C.make_agent()
  self.assertIsNot(a.policy,b.policy);self.assertIsNot(a.controller,b.controller)
  a.policy.scheduler.planned['test-marker']={99:1}
  self.assertNotIn('test-marker',b.policy.scheduler.planned)
  a.controller.cur='dc76e4003029ac51';self.assertNotEqual(a.controller.cur,b.controller.cur)

if __name__=='__main__':
 start=time.perf_counter();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CapitalJoinTests))
 report={'methods':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'successful':r.wasSuccessful(),
         'counts':COUNTS,'cases':RECEIPTS,'interpreter_transitions':0,'new_games':0,'wall_seconds':time.perf_counter()-start,
         'sources':{str(p.relative_to(ROOT)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [T13/'seed_main.py',T13/'juniper-funding/capital_arms.py',ROOT/'cloud-capital-bundles/entry.py',ROOT/'cloud-capital-bundles/capital_routes.py']}}
 ARGS.report.write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(not r.wasSuccessful())
