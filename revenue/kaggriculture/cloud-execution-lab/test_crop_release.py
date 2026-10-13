# SPDX-License-Identifier: Apache-2.0
"""Focused source/receipt contracts; no game or policy rollout."""
from copy import deepcopy
import unittest

import mechanics as m
from scheduler import parent, post_units
from crop_release import (MAIN, MILK_GLUT, prepare_release, commit_preparation,
                          observed_plant, recipe_compatible, commit_plant,
                          observe_crop, commit_harvest, commit_deposit,
                          offer_crop, commit_crop_sale, observe_crop_sale,
                          funded_services,input_price_bounds,propose_input_repair,
                          commit_input_repair,observe_input_repair)


class CropPreparationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routes = parent.routes()

    def fixture(self):
        tiles = [[None for _ in range(10)] for _ in range(10)]
        tiles[9][3] = m._new_plant('WHEAT', 11, 24)
        tiles[9][3].update(yield_units=4, watered_today=True)
        farm = {'farmer':[4,4], 'hands':[[4,4] for _ in range(11)],
                'money':25000, 'hires_today':11, 'unlocked_quadrants':['NW','NE','SW'],
                'tiles':tiles}
        farm['hands'][9] = [3,9]
        inventory = {p:10000 for p in m.PRODUCTS}
        inventory.update(CARROT=9500, WHEAT=9900)
        obs = {'step':372, 'day':15, 'hour':12, 'player':0,
               'farms':[farm,deepcopy(farm)],
               'private':{'shed':{'WHEAT':5}, 'inventories':[{} for _ in range(12)],
                          'seeds':{'WHEAT':20,'CARROT':5}},
               'market':{'inventory':inventory, 'params':m.MARKET_PARAMS,
                         'prices':{p:m.market_price(p,n) for p,n in inventory.items()}},
               'town':{'unlocked_shops':['PET_CAFE','PET_CAFE','PET_CAFE']}}
        selected = deepcopy(self.routes[MAIN][372])
        f,p = post_units(obs,selected,{})
        post = deepcopy(obs);post['farms'][0]=f;post['private']=p
        return obs,selected,post

    def prepared(self):
        obs,selected,post = self.fixture()
        out,intent,report = prepare_release(m,obs,{},selected,post,self.routes,MAIN)
        self.assertTrue(report['changed'])
        return obs,selected,post,out,intent

    def next_observation(self, post, seeds):
        obs=deepcopy(post);obs.update(step=373,hour=13)
        obs['private']['seeds']['CARROT']=seeds
        return obs

    def test_complete_source_family_and_native_release(self):
        obs,selected,post,out,intent=self.prepared()
        self.assertTrue(recipe_compatible(self.routes,MAIN))
        self.assertIsNone(post['farms'][0]['tiles'][9][3])
        self.assertEqual(out['market'],[['BUY_SEED','CARROT',1]])
        self.assertEqual(out['farmer'],selected['farmer'])
        self.assertEqual(out['hands'],selected['hands'])
        self.assertEqual(intent['seed_floor'],5)
        self.assertEqual(commit_preparation(intent,obs,out)['status'],
                         'awaiting_seed_and_site_observation')

    def test_proposal_and_requested_purchase_are_not_receipts(self):
        obs,selected,post,out,intent=self.prepared()
        self.assertIsNone(commit_preparation(intent,obs,selected))
        changed=deepcopy(out);changed['farmer']=['PASS']
        if changed['farmer']==out['farmer']:changed['farmer']=['NORTH']
        self.assertIsNone(commit_preparation(intent,obs,changed))
        committed=commit_preparation(intent,obs,out)
        nxt=self.next_observation(post,5);raw=deepcopy(self.routes[MAIN][373])
        returned,accepted=observed_plant(committed,nxt,raw,MAIN)
        self.assertFalse(accepted);self.assertEqual(returned,raw)

    def test_new_seed_leaves_all_preexisting_seeds_after_native_planting(self):
        obs,selected,post,out,intent=self.prepared()
        committed=commit_preparation(intent,obs,out)
        nxt=self.next_observation(post,6);raw=deepcopy(self.routes[MAIN][373])
        returned,accepted=observed_plant(committed,nxt,raw,MAIN)
        self.assertTrue(accepted)
        after_farm,after_private=post_units(nxt,returned,{})
        self.assertEqual(after_farm['tiles'][9][3]['crop'],'CARROT')
        self.assertEqual(after_private['seeds']['CARROT'],5)
        self.assertEqual(returned['market'],raw['market'])
        self.assertEqual(returned['farmer'],raw['farmer'])
        self.assertEqual(returned['hands'][:9],raw['hands'][:9])
        self.assertEqual(returned['hands'][10:],raw['hands'][10:])

    def test_joint_seed_demand_cannot_borrow_future_committed_seed(self):
        obs,selected,post,out,intent=self.prepared()
        committed=commit_preparation(intent,obs,out)
        raw=deepcopy(self.routes[MAIN][373]);raw['farmer']=['PLANT','CARROT']
        nxt=self.next_observation(post,6)
        self.assertFalse(observed_plant(committed,nxt,raw,MAIN)[1])
        nxt['private']['seeds']['CARROT']=7
        self.assertFalse(observed_plant(committed,nxt,raw,MAIN)[1])

    def test_actual_site_worker_and_existing_actor_owner_are_required(self):
        obs,selected,post,out,intent=self.prepared()
        committed=commit_preparation(intent,obs,out);raw=deepcopy(self.routes[MAIN][373])
        nxt=self.next_observation(post,6)
        self.assertFalse(observed_plant(committed,nxt,raw,MAIN,actor_owned=True)[1])
        nxt['farms'][0]['tiles'][9][3]={'kind':'WEED'}
        self.assertFalse(observed_plant(committed,nxt,raw,MAIN)[1])
        nxt['farms'][0]['tiles'][9][3]=None;nxt['farms'][0]['hands'][9]=[2,9]
        self.assertFalse(observed_plant(committed,nxt,raw,MAIN)[1])

    def test_engine_accepted_extra_operands_still_consume_shared_seed(self):
        obs,selected,post,out,intent=self.prepared()
        committed=commit_preparation(intent,obs,out)
        raw=deepcopy(self.routes[MAIN][373]);raw['farmer']=['PLANT','CARROT',1]
        nxt=self.next_observation(post,6);nxt['farms'][0]['farmer']=[0,0]
        self.assertFalse(observed_plant(committed,nxt,raw,MAIN)[1])
        nxt['private']['seeds']['CARROT']=7
        returned,accepted=observed_plant(committed,nxt,raw,MAIN)
        self.assertFalse(accepted)
        after_farm,after_private=post_units(nxt,returned,{})
        self.assertEqual(after_farm['tiles'][0][0]['crop'],'CARROT')
        self.assertEqual(after_farm['tiles'][9][3]['crop'],'WHEAT')
        self.assertEqual(after_private['seeds']['CARROT'],6)

    def test_local_route_similarity_does_not_certify_shared_branch(self):
        obs,selected,post=self.fixture();changed=deepcopy(self.routes)
        changed[MILK_GLUT][433]['market'].append(['BUY_PRODUCT','WHEAT',1])
        self.assertFalse(prepare_release(m,obs,{},selected,post,changed,MAIN)[2]['changed'])
        self.assertFalse(recipe_compatible(self.routes,parent.CARROT if hasattr(parent,'CARROT') else 'ab9669b9abfbea4e'))

    def test_marginal_demand_cash_and_shared_inputs_gate_preparation(self):
        obs,selected,post=self.fixture()
        post['farms'][0]['money']=100
        self.assertEqual(prepare_release(m,obs,{},selected,post,self.routes,MAIN)[2]['reason'],
                         'actual_cash_cushion_insufficient')
        post['farms'][0]['money']=25000;post['private']['shed']['WHEAT']=2
        self.assertFalse(prepare_release(m,obs,{},selected,post,self.routes,MAIN)[2]['changed'])
        post['private']['shed']['WHEAT']=5;obs['market']['inventory']['CARROT']=11000
        self.assertEqual(prepare_release(m,obs,{},selected,post,self.routes,MAIN)[2]['reason'],
                         'marginal_product_screen_not_favorable')

    def growing(self):
        obs,selected,post,out,intent=self.prepared()
        intent=commit_preparation(intent,obs,out)
        nxt=self.next_observation(post,6);raw=deepcopy(self.routes[MAIN][373])
        changed,accepted=observed_plant(intent,nxt,raw,MAIN)
        self.assertTrue(accepted)
        intent=commit_plant(intent,nxt,changed,MAIN)
        farm,private=post_units(nxt,changed,{})
        actual=deepcopy(nxt);actual.update(step=374,hour=14)
        actual['farms'][0]=farm;actual['private']=private
        return observe_crop(intent,actual,MAIN),actual

    def test_owned_site_survives_worker_reset_and_compatible_branch(self):
        intent,obs=self.growing();self.assertEqual(intent['status'],'growing')
        self.assertEqual(obs['private']['seeds']['CARROT'],5)
        intent['last_observed_step']=383;obs.update(step=384,day=16,hour=0)
        obs['farms'][0]['hands']=[];obs['private']['inventories']=[{}]
        intent=observe_crop(intent,obs,MAIN)
        self.assertEqual(intent['status'],'growing')
        intent['last_observed_step']=432;obs.update(step=433,day=18,hour=1)
        intent=observe_crop(intent,obs,MILK_GLUT)
        self.assertEqual(intent['status'],'growing')
        obs['step']=435
        self.assertEqual(observe_crop(intent,obs,MILK_GLUT)['status'],'input_recovery_only')

    def harvested(self):
        intent,obs=self.growing()
        # A constructed mature boundary, not execution of the intervening days.
        intent['last_observed_step']=444
        obs.update(step=444,day=18,hour=12)
        obs['farms'][0]['tiles'][9][3]['yield_units']=3
        obs['farms'][0]['hands'][9]=[3,9]
        obs['private']['inventories']=[{} for _ in range(12)]
        raw=deepcopy(self.routes[MAIN][444])
        intent=commit_harvest(intent,obs,raw)
        self.assertEqual(intent['status'],'awaiting_observed_harvest')
        farm,private=post_units(obs,raw,{})
        actual=deepcopy(obs);actual.update(step=445,hour=13)
        actual['farms'][0]=farm;actual['private']=private
        intent=observe_crop(intent,actual,MAIN)
        self.assertEqual(intent['status'],'carried')
        return intent,actual

    def test_harvest_requires_the_returned_actor_and_next_observed_carrier(self):
        intent,obs=self.harvested()
        self.assertEqual(obs['private']['inventories'][10],{'CARROT':3})
        self.assertIsNone(obs['farms'][0]['tiles'][9][3])
        bad=deepcopy(obs);bad['step']=446;bad['private']['inventories'][10]={}
        p=observe_crop(intent,bad,MAIN)
        self.assertEqual(p['status'],'input_recovery_only')
        self.assertEqual(p['wheat_reserve_required'],3)
        growing,raw_obs=self.growing();raw_obs['step']=444;growing['last_observed_step']=444
        returned=deepcopy(self.routes[MAIN][444]);returned['hands'][9]=['PASS']
        self.assertEqual(commit_harvest(growing,raw_obs,returned)['status'],'input_recovery_only')

    def deposited(self):
        intent,obs=self.harvested();intent['last_observed_step']=455
        obs.update(step=455,day=18,hour=23)
        obs['private']['shed']={'WHEAT':17}
        obs['private']['inventories']=[{} for _ in range(12)]
        obs['private']['inventories'][10]={'CARROT':3,'WHEAT':3}
        obs['farms'][0]['hands'][9]=[0,8]
        row={'farmer':['PASS'],'hands':[['PASS'] for _ in range(11)],'market':[]}
        intent=commit_deposit(intent,obs,row,deepcopy(obs))
        self.assertEqual(intent['status'],'awaiting_observed_deposit')
        actual=deepcopy(obs);actual.update(step=456,day=19,hour=0)
        actual['private']['shed']={'WHEAT':20,'CARROT':3}
        actual['private']['inventories']=[{}];actual['farms'][0]['hands']=[]
        actual['farms'][0]['farmer']=[4,4]
        return intent,actual

    def test_deposit_requires_shared_room_and_actual_shed_arrival(self):
        intent,obs=self.deposited()
        good=observe_crop(intent,obs,MAIN)
        self.assertEqual(good['status'],'deposited')
        bad=deepcopy(obs);bad['private']['shed'].pop('CARROT')
        self.assertEqual(observe_crop(intent,bad,MAIN)['status'],'input_recovery_only')
        carried,before=self.harvested();before.update(step=455,day=18,hour=23)
        carried['last_observed_step']=455
        before['private']['shed']={'WHEAT':98}
        row={'farmer':['PASS'],'hands':[['PASS'] for _ in range(11)],
             'market':[['SELL','WHEAT',98]]}
        self.assertEqual(commit_deposit(carried,before,row,before)['status'],'input_recovery_only')
        before['private']['shed']={'WHEAT':95}
        row['market']=[['BUY_PRODUCT','FERTILIZER',3]]
        self.assertEqual(commit_deposit(carried,before,row,before)['status'],'input_recovery_only')

    def test_full_hiring_row_and_inherited_outlet_order_are_preserved(self):
        p,obs=self.deposited();p=observe_crop(p,obs,MAIN)
        raw=deepcopy(self.routes[MAIN][456])
        self.assertEqual(offer_crop(p,obs,raw),(raw,False))
        obs.update(step=457,hour=1);p=observe_crop(p,obs,MAIN)
        raw=deepcopy(self.routes[MAIN][457])
        offered,accepted=offer_crop(p,obs,raw)
        self.assertTrue(accepted);self.assertEqual(offered['market'][:6],raw['market'])
        self.assertEqual(offered['market'][6],['SELL','CARROT',3])
        self.assertEqual(offered['farmer'],raw['farmer']);self.assertEqual(offered['hands'],raw['hands'])
        held=deepcopy(offered);held['market'][6]=[]
        p=commit_crop_sale(p,obs,held,obs,offered=True,seller_completed=True)
        self.assertEqual(p['status'],'deposited')
        self.assertFalse(offer_crop(p,obs,raw)[1])
        self.assertFalse(any(r['kind']=='sale' for r in p['crop_receipts']))

    def test_duplicate_final_lots_share_one_observed_quantity_budget(self):
        import titan_runtime as T
        fills=T.load('_crop_test_fills',T.HERE/'reference/titan-history/observed_fills.py',cache=True)
        p,obs=self.deposited();p=observe_crop(p,obs,MAIN);obs.update(step=457,hour=1)
        p=observe_crop(p,obs,MAIN)
        row={'farmer':['PASS'],'hands':[],
             'market':[['SELL','CARROT',2],[],['SELL','CARROT',2]]}
        p=commit_crop_sale(p,obs,row,obs)
        ledger=fills.ObservedFillLedger()
        ledger.record(obs,{},row,post_unit_shed=obs['private']['shed'],
                      post_unit_inventories=obs['private']['inventories'])
        actual=deepcopy(obs)
        for a in row['market']:
            if not a:continue
            for _ in range(a[2]):
                price=m.market_price('CARROT',actual['market']['inventory']['CARROT'])
                m._commit_unit('SELL','CARROT',price,actual['farms'][0],actual['private'],actual['market'])
        actual.update(step=458,hour=2)
        result=ledger.observe(actual)
        done=observe_crop_sale(p,actual,result)
        self.assertEqual(done['status'],'sold')
        self.assertEqual(done['sale_quantity_remaining'],0)
        self.assertEqual(done['crop_receipts'][-1]['units'],3)
        self.assertIsNone(done['crop_receipts'][-1]['cash_receipt'])
        self.assertEqual(observe_crop_sale(done,actual,result),done)
        foreign=deepcopy(actual);foreign['player']=1
        self.assertEqual(observe_crop_sale(p,foreign,result)['status'],'sale_attribution_unknown')
        wrong=deepcopy(result);wrong['binding']['action_sha256']='different final action'
        self.assertEqual(observe_crop_sale(p,actual,wrong)['status'],'sale_attribution_unknown')
        result['orders'][0]['fill_min']=0
        self.assertEqual(observe_crop_sale(p,actual,result)['status'],'sale_attribution_unknown')

    def test_replacement_stock_never_revives_a_lost_owned_lot(self):
        p,obs=self.deposited();p=observe_crop(p,obs,MAIN)
        obs.update(step=457,hour=1);p=observe_crop(p,obs,MAIN)
        taken=deepcopy(obs);taken['private']['shed']['CARROT']=0
        taken['private']['inventories'][0]={'CARROT':3}
        action={'farmer':['PICKUP','CARROT',3],'hands':[],'market':[]}
        lost=commit_crop_sale(p,obs,action,taken)
        self.assertEqual(lost['status'],'sale_attribution_unknown')
        # Later stock having the same quantity is insufficient after a touch.
        obs.update(step=458,hour=2)
        p=observe_crop(lost,obs,MAIN)
        self.assertEqual(p['status'],'sale_attribution_unknown')
        self.assertFalse(offer_crop(p,obs,{'farmer':['PASS'],'hands':[],'market':[]})[1])
        p,obs=self.deposited();p=observe_crop(p,obs,MAIN)
        missing=deepcopy(obs);missing.update(step=457,hour=1)
        missing['private']['shed']['CARROT']=0
        self.assertEqual(observe_crop(p,missing,MAIN)['status'],'sale_attribution_unknown')
        self.assertEqual(commit_crop_sale(p,obs,{'market':[]},None)['status'],'sale_attribution_unknown')

    def test_funding_includes_due_water_hires_negative_inventory_and_defaults(self):
        obs,selected,post=self.fixture()
        report,reason=funded_services(m,obs,{},post,self.routes[MAIN])
        self.assertIsNone(reason);self.assertEqual(report['paid_hires'],43)
        self.assertEqual([r['step'] for r in report['required_services']],[373,374,407,429,443,444,445])
        self.assertEqual(report['future_sale_cash_credit'],0)
        self.assertGreater(report['ending_cash_lower'],0)
        changed=deepcopy(self.routes[MAIN]);changed[429]['hands'][2]=['PASS']
        self.assertIsNone(funded_services(m,obs,{},post,changed)[0])
        bad=deepcopy(obs);bad['market']['inventory']['FERTILIZER']=-3
        self.assertGreater(input_price_bounds(m,bad,{},self.routes[MAIN])['FERTILIZER']['price_upper'],2100)
        self.assertIsNone(funded_services(m,obs,{'boardSize':12},post,self.routes[MAIN])[0])
        large=deepcopy(obs);large['farms'][0]['tiles'].append([None]*10)
        self.assertIsNone(funded_services(m,large,{},post,self.routes[MAIN])[0])
        stale=deepcopy(post);stale['step']=371
        self.assertIsNone(funded_services(m,obs,{},stale,self.routes[MAIN])[0])
        poor=deepcopy(post);poor['farms'][0]['money']=10000
        self.assertIsNone(funded_services(m,obs,{},poor,self.routes[MAIN])[0])

    def repair_boundary(self):
        p,obs=self.harvested();p['last_observed_step']=455
        obs.update(step=455,day=18,hour=23)
        obs['private']['shed']={'STRAWBERRY':14}
        obs['private']['inventories']=[{} for _ in range(12)]
        obs['private']['inventories'][10]={'CARROT':3,'WHEAT':3}
        obs['private']['inventories'][2]={'WHEAT':22,'MILK':41}
        obs['farms'][0]['hands'][9]=[0,8]
        row={'farmer':['PASS'],'hands':[['PASS'] for _ in range(11)],
             'market':[['SELL','STRAWBERRY',6]]}
        return p,obs,row

    def test_late_repair_preserves_current_rows_and_boundary_capital(self):
        p,obs,row=self.repair_boundary()
        out,proposal,report=propose_input_repair(m,p,obs,{},row,obs,self.routes[MAIN])
        self.assertTrue(report['changed']);self.assertEqual(report['shared_stock_upper'],86)
        self.assertEqual(out['market'],row['market']+[['BUY_PRODUCT','WHEAT',3]])
        self.assertEqual(out['hands'],row['hands']);self.assertEqual(proposal['funding_through'],457)
        self.assertEqual(commit_input_repair(p,proposal,obs,row,obs),p)
        bad=deepcopy(obs);bad['private']['shed']['STRAWBERRY']=29
        self.assertFalse(propose_input_repair(m,p,bad,{},row,bad,self.routes[MAIN])[2]['changed'])
        bad=deepcopy(obs);bad['farms'][0]['money']=54
        self.assertFalse(propose_input_repair(m,p,bad,{},row,bad,self.routes[MAIN])[2]['changed'])
        full=deepcopy(row);full['market']=[['HIRE']]*10
        self.assertFalse(propose_input_repair(m,p,obs,{},full,obs,self.routes[MAIN])[2]['changed'])
        conflict=deepcopy(row);conflict['market'].append(['SELL','WHEAT',1])
        self.assertFalse(propose_input_repair(m,p,obs,{},conflict,obs,self.routes[MAIN])[2]['changed'])
        p['last_observed_step']=454;obs['step']=454
        self.assertFalse(propose_input_repair(m,p,obs,{},row,obs,self.routes[MAIN])[2]['changed'])

    def test_repair_uses_eod_fill_receipt_and_blocks_unknown_duplicates(self):
        import titan_runtime as T
        fills=T.load('_crop_test_fills',T.HERE/'reference/titan-history/observed_fills.py',cache=True)
        p,obs,row=self.repair_boundary()
        out,proposal,report=propose_input_repair(m,p,obs,{},row,obs,self.routes[MAIN])
        p=commit_input_repair(p,proposal,obs,out,obs)
        ledger=fills.ObservedFillLedger()
        ledger.record(obs,{},out,post_unit_shed=obs['private']['shed'],
                      post_unit_inventories=obs['private']['inventories'])
        actual=deepcopy(obs)
        for a in out['market']:
            for _ in range(a[2]):
                price=m.market_price(a[1],actual['market']['inventory'][a[1]]-(a[0]=='BUY_PRODUCT'))
                self.assertTrue(m._commit_unit(a[0],a[1],price,actual['farms'][0],actual['private'],actual['market']))
        # Construct the ordered EOD transfer boundary; no intervening game run.
        for inv in actual['private']['inventories']:
            for item,n in inv.items():actual['private']['shed'][item]=actual['private']['shed'].get(item,0)+n
        actual['private']['inventories']=[{}];actual['farms'][0]['hands']=[]
        actual.update(step=456,day=19,hour=0)
        result=ledger.observe(actual);done=observe_input_repair(p,actual,result)
        self.assertEqual(actual['private']['shed']['WHEAT'],28)
        self.assertEqual(done['input_repair_remaining'],0)
        self.assertEqual(done['input_repair_receipts'][-1]['restored_units'],3)
        self.assertEqual(observe_input_repair(done,actual,result),done)
        bad=deepcopy(result);bad['binding']['action_sha256']='different'
        unknown=observe_input_repair(p,actual,bad)
        self.assertTrue(unknown['input_repair_unknown'])
        self.assertEqual(unknown['input_repair_remaining'],3)
        unknown['last_observed_step']=456
        self.assertFalse(propose_input_repair(m,unknown,actual,{},row,actual,self.routes[MAIN])[2]['changed'])

    def test_runtime_owns_preparation_plant_and_receipt_with_one_projection(self):
        from unittest.mock import patch
        import titan_runtime as T
        import frozen_selected
        obs,raw,post=self.fixture()
        import json
        entry=T.load('_crop_canonical_entry',T.HERE/'main.py')
        agent=entry._new_instance(T.HERE,json.loads((T.HERE/'TITAN-CONFIG.json').read_text()))
        self.assertTrue(agent.features.crop_release)
        agent._initialize();agent.controller.cur=MAIN
        entry._INSTANCE=agent
        with patch.object(frozen_selected,'post_units',wraps=frozen_selected.post_units) as projection:
            first=entry.agent(obs,{})
            self.assertEqual(projection.call_count,1)
        self.assertEqual(first['market'],[['BUY_SEED','CARROT',1]])
        self.assertEqual(agent.spatial.crop_intent['status'],'awaiting_seed_and_site_observation')
        nxt=self.next_observation(post,6);nxt['farms'][0]['money']-=20
        with patch.object(frozen_selected,'post_units',wraps=frozen_selected.post_units) as projection:
            planted=agent.act(nxt,{})
            self.assertEqual(projection.call_count,1)
        self.assertEqual(planted['hands'][9],['PLANT','CARROT'])
        f,p=post_units(nxt,planted,{})
        observed=deepcopy(nxt);observed.update(step=374,hour=14)
        observed['farms'][0]=f;observed['private']=p
        agent.act(observed,{})
        self.assertEqual(agent.spatial.crop_intent['status'],'growing')
        self.assertEqual(observed['private']['seeds']['CARROT'],5)
        self.assertEqual(agent.diagnostics['parent_calls'],1)

    def test_final_idle_guard_cancels_unbound_repair_without_duplicate_purchase(self):
        import titan_runtime as T
        from crop_release import units
        p,obs,row=self.repair_boundary()
        agent=T.TitanAgent(T.Features(crop_release=True,idle_fertilizer=True))
        agent._initialize();agent.controller.cur=MAIN
        agent.spatial.crop_intent=p
        row['hands'][0]=['DROP'];row['market']=[[]]
        obs['farms'][0]['hands'][0]=[4,4]
        obs['private']['inventories'][1]={'FERTILIZER':1}
        out,proposal,report=propose_input_repair(m,p,obs,{},row,obs,self.routes[MAIN])
        self.assertTrue(report['changed'])
        agent.spatial._crop_repair=proposal
        agent.spatial._sale_proposal={'step':455,'slot':0,'worker':1,'quantity':1,
                                      'target':(4,3)}
        agent.consumer.selected_post_units=(deepcopy(obs['farms'][0]),deepcopy(obs['private']))
        agent.consumer.selected_post_units_binding=(455,0,deepcopy(out['farmer']),deepcopy(out['hands']))
        agent.diagnostics={'status':'completed'}
        guarded=agent._finish_production(obs,out,{})
        self.assertEqual(guarded['hands'][0],['PASS'])
        self.assertEqual(guarded['market'],[[]])
        self.assertEqual(agent.spatial.crop_intent['input_repair_remaining'],3)
        self.assertNotIn('input_repair_pending',agent.spatial.crop_intent)
        # If an unbound BUY survives an unforeseen composer, do not buy again.
        unknown=commit_input_repair(p,proposal,obs,out,None)
        self.assertTrue(unknown['input_repair_unknown'])

    def test_preparation_deadline_does_not_commit_an_unemitted_order(self):
        from unittest.mock import patch
        import titan_runtime as T
        obs,raw,post=self.fixture()
        agent=T.TitanAgent(T.Features(crop_release=True))
        agent._initialize();agent.controller.cur=MAIN
        timers=[];real_timer=T.deadline._DeadlineTimer
        def timer(seconds):
            t=real_timer(seconds);timers.append(t);return t
        original=agent.spatial.crop_market
        def cancel(*args):
            original(*args)
            raise timers[-1].expired
        with patch.object(T.deadline,'_DeadlineTimer',side_effect=timer),patch.object(agent.spatial,'crop_market',side_effect=cancel):
            returned=agent.act(obs,{})
        self.assertEqual(agent.diagnostics['status'],'deadline_fallback')
        self.assertEqual(returned['market'],[])
        self.assertIsNone(agent.spatial.crop_intent)

    def test_actual_delivery_uses_the_existing_runtime_fill_ledger(self):
        from unittest.mock import patch
        import titan_runtime as T
        import frozen_selected
        p,obs,row=self.repair_boundary();p['last_observed_step']=454
        agent=T.TitanAgent(T.Features(crop_release=True,market_pressure=True,
            operating_stock=True,idle_fertilizer=True))
        agent._initialize();agent.controller.cur=MAIN;agent.spatial.crop_intent=p
        with patch.object(frozen_selected,'post_units',wraps=frozen_selected.post_units) as projection:
            action=agent.act(obs,{})
            self.assertEqual(projection.call_count,1)
        self.assertEqual(action['market'][-1],['BUY_PRODUCT','WHEAT',3])
        self.assertEqual(agent.spatial.crop_intent['status'],'awaiting_observed_deposit')
        self.assertEqual(agent.history.pending[2],action)
        actual=deepcopy(agent.history.pending[3])
        for a in action['market']:
            if not a:continue
            self.assertIn(a[0],('SELL','BUY_PRODUCT'))
            for _ in range(a[2]):
                price=m.market_price(a[1],actual['market']['inventory'][a[1]]-(a[0]=='BUY_PRODUCT'))
                m._commit_unit(a[0],a[1],price,actual['farms'][0],actual['private'],actual['market'])
        for inv in actual['private']['inventories']:
            for item,n in inv.items():actual['private']['shed'][item]=actual['private']['shed'].get(item,0)+n
        actual['private']['inventories']=[{}];actual['farms'][0]['hands']=[]
        actual['farms'][0]['farmer']=[4,4];actual['farms'][0]['hires_today']=0
        actual.update(step=456,day=19,hour=0)
        ledger=agent.history.bridge.ledger
        with patch.object(ledger,'record',wraps=ledger.record) as record,patch.object(ledger,'observe',wraps=ledger.observe) as observed:
            action456=agent.act(actual,{})
            self.assertEqual(record.call_count,1);self.assertEqual(observed.call_count,1)
        self.assertEqual(agent.spatial.crop_intent['status'],'deposited')
        self.assertEqual(agent.spatial.crop_intent['input_repair_remaining'],0)
        self.assertEqual(actual['private']['shed']['WHEAT'],28)
        self.assertEqual(actual['private']['shed']['CARROT'],3)
        self.assertEqual(sum(a==['HIRE'] for a in action456['market']),9)

    def test_due_debt_reserves_actual_duplicate_sales_and_observed_stock(self):
        import titan_runtime as T
        fills=T.load('_crop_test_fills',T.HERE/'reference/titan-history/observed_fills.py',cache=True)
        for wheat in (3,5):
            p,obs=self.deposited();p=observe_crop(p,obs,MAIN)
            obs.update(step=457,hour=1);p=observe_crop(p,obs,MAIN)
            obs['private']['shed']={'WHEAT':wheat,'CARROT':3,'STRAWBERRY':5}
            row={'farmer':['PASS'],'hands':[],
                 'market':[['SELL','WHEAT',2],['BUY_SEED','WHEAT',1],
                           ['SELL','WHEAT',2],['SELL','STRAWBERRY',1]]}
            out,proposal,report=propose_input_repair(m,p,obs,{},row,obs,self.routes[MAIN])
            self.assertTrue(report['changed']);self.assertEqual(proposal['kind'],'withhold')
            self.assertEqual(proposal['units'],3)
            self.assertEqual(out['market'][1],row['market'][1])
            self.assertEqual(out['market'][3],row['market'][3])
            self.assertEqual(out['market'][2],[])
            self.assertEqual(out['market'][0],[] if wheat==3 else ['SELL','WHEAT',1])
            self.assertFalse(any(a and a[0]=='BUY_PRODUCT' for a in out['market']))
            committed=commit_input_repair(p,proposal,obs,out,obs)
            ledger=fills.ObservedFillLedger()
            ledger.record(obs,{},out,post_unit_shed=obs['private']['shed'],post_unit_inventories=obs['private']['inventories'])
            actual=deepcopy(obs)
            for a in out['market']:
                if not a:continue
                for _ in range(a[2]):
                    price=m.CROPS[a[1]]['seed'] if a[0]=='BUY_SEED' else m.market_price(a[1],actual['market']['inventory'][a[1]])
                    self.assertTrue(m._commit_unit(a[0],a[1],price,actual['farms'][0],actual['private'],actual['market']))
            actual.update(step=458,hour=2);result=ledger.observe(actual)
            done=observe_input_repair(committed,actual,result)
            self.assertEqual(done['input_repair_remaining'],0)
            self.assertEqual(done['input_repair_receipts'][-1]['restored_units'],3)
            replaced=deepcopy(actual);replaced['private']['shed']['WHEAT']-=1
            self.assertTrue(observe_input_repair(committed,replaced,result)['input_repair_unknown'])
            poor=deepcopy(obs);poor['farms'][0]['money']=9
            self.assertFalse(propose_input_repair(m,p,poor,{},row,poor,self.routes[MAIN])[2]['changed'])
            # A different final market guard must not leave an unbound reserve.
            from spatial_tempo import SpatialTempo
            owner=SpatialTempo(m,crop_release=True);owner._crop_repair=proposal
            changed=deepcopy(out);changed['market'][3]=[]
            guarded=owner.guard_crop_returned(obs,changed,obs)
            self.assertEqual(guarded['market'][0],row['market'][0])
            self.assertEqual(guarded['market'][2],row['market'][2])
            self.assertEqual(guarded['market'][3],[])
            self.assertEqual(commit_input_repair(p,proposal,obs,guarded,obs),p)
            self.assertTrue(commit_input_repair(p,proposal,obs,changed,obs)['input_repair_unknown'])


if __name__=='__main__':
    unittest.main()
