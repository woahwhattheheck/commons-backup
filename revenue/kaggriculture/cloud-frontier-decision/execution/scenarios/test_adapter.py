# SPDX-License-Identifier: Apache-2.0
import json,sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]/'cloud-market-forecast'))
from forecast_market_mechanics import market_price,SHOPS,TOWN_CENTER_PRODUCTS
from adapter import infer_rival_flow,simulate_sell_turn,supply_scenarios,score_paired_plans,town_units

class AdapterCases(unittest.TestCase):
    def test_all_48_recorded_transitions(self):
        data=json.loads((HERE/'fixtures.json').read_text())
        self.assertEqual(len(data['fixtures']),48)
        for f in data['fixtures']:
            with self.subTest(fixture=f['id']):
                live=f['live_input'];ev=f['evaluation_only'];before=live['before'];cfg=live['configuration']
                quote=lambda p,i:market_price(p,i,before['market'].get('params'))
                identified=infer_rival_flow(**live,quote=quote,shops=SHOPS,center_products=TOWN_CENTER_PRODUCTS)
                for p,row in identified['products'].items():
                    self.assertEqual(row['status'],'identified_interval')
                    actual=ev['market_supply_units'][1].get(p,0)
                    self.assertLessEqual(row['rival_market_supply_units_range'][0],actual)
                    self.assertGreaterEqual(row['rival_market_supply_units_range'][1],actual)
                    count=ev['sale_units'][1].get(p,0)
                    self.assertLessEqual(row['rival_sale_units_range'][0],count)
                    self.assertGreaterEqual(row['rival_sale_units_range'][1],count)
                # EVALUATION ONLY ground truth tests transition parity. These fields
                # were deliberately not passed to observation-only identification.
                r=simulate_sell_turn(before['market']['inventory'],live['own_orders'],ev['rival_orders'],ev['own_post_unit_shed'],ev['rival_fill_cap'],quote)
                self.assertEqual(r['cash'],ev['cash']);self.assertEqual(r['sale_units'],ev['sale_units']);self.assertEqual(r['market_supply_units'],ev['market_supply_units'])
                demand=town_units(before,cfg,before['step'],before['step']+1,SHOPS,TOWN_CENTER_PRODUCTS)
                self.assertEqual({p:n-demand.get(p,0) for p,n in r['inventory'].items()},ev['inventory_after_town'])
                scenarios={'scenarios':[{'id':'recorded_evaluation_only','orders':{before['step']:ev['rival_orders']},'initial_rival_stock':ev['rival_fill_cap']}]}
                scores=score_paired_plans(before,cfg,ev['own_post_unit_shed'],{}, {before['step']:live['own_orders']},scenarios,before['step'],quote=quote,shops=SHOPS,center_products=TOWN_CENTER_PRODUCTS)
                self.assertEqual(scores['evaluations'][0]['candidate']['cash'],ev['cash'])
                self.assertEqual(scores['evaluations'][0]['baseline']['cash'],ev['no_own_sale_cash'])
                delta=[ev['cash'][i]-ev['no_own_sale_cash'][i] for i in (0,1)]
                self.assertEqual(scores['evaluations'][0]['game_cash_margin_delta'],delta[0]-delta[1])
    def simple(self,step=4,inventory=0):
        return {'step':step,'market':{'inventory':{'WOOL':inventory}},'town':{'unlocked_shops':['YARN_STORE']*4}}
    def test_profit_is_not_margin(self):
        obs=self.simple();cfg={'episodeSteps':720,'shedCapacity':100}
        q=lambda p,i:max(1,100-i)
        ss={'scenarios':[{'id':'no_rival','initial_rival_stock':{},'orders':{}}, {'id':'competitive','initial_rival_stock':{'WOOL':10},'orders':{4:[['SELL','WOOL',10]]}}]}
        r=score_paired_plans(obs,cfg,{'WOOL':10},{4:[['SELL','WOOL',10]]},{5:[['SELL','WOOL',10]]},ss,5,quote=q,shops=SHOPS,center_products=[])['evaluations']
        self.assertEqual(r[0]['own_cash_receipt_delta'],80)
        self.assertEqual((r[1]['own_cash_receipt_delta'],r[1]['rival_cash_receipt_delta'],r[1]['game_cash_margin_delta']),(25,45,-20))
    def test_floor_does_not_identify_sales(self):
        before=self.simple(step=1,inventory=2);after=self.simple(step=2,inventory=2)
        r=infer_rival_flow(before,after,[['SELL','WOOL',4]],{},quote=lambda p,i:max(1,3-i),shops=SHOPS,center_products=[],own_sale_units={'WOOL':4})['products']['WOOL']
        self.assertEqual(r['rival_market_supply_units_range'],[0,0]);self.assertEqual(r['rival_sale_units_range'],[0,100])
    def test_joint_floor_and_recovery(self):
        q=lambda p,i:max(1,3-i)
        a=simulate_sell_turn({'WOOL':0},[['SELL','WOOL',4]],[['SELL','WOOL',4]],{'WOOL':5},{'WOOL':5},q)
        self.assertEqual(a['cash'],[6,6]);self.assertEqual(a['inventory']['WOOL'],2)
        b=simulate_sell_turn({'WOOL':a['inventory']['WOOL']-2},[['SELL','WOOL',1]],[['SELL','WOOL',1]],a['stock'][0],a['stock'][1],q)
        self.assertEqual(b['cash'],[3,3])
    def test_order_alignment_not_arbitrary_front_running(self):
        q=lambda p,i:100-i
        a=simulate_sell_turn({'WOOL':0},[['SELL','WOOL',2]],[['SELL','WOOL',2]],{'WOOL':2},{'WOOL':2},q)
        b=simulate_sell_turn({'WOOL':0},[['SELL','WOOL',2]],[['PASS'],['SELL','WOOL',2]],{'WOOL':2},{'WOOL':2},q)
        self.assertEqual(a['cash'],[198,198]);self.assertEqual(b['cash'],[199,195])
    def test_buy_sell_ambiguity(self):
        before={'step':1,'market':{'inventory':{'WHEAT':10000}},'town':{}}
        after={'step':2,'market':{'inventory':{'WHEAT':9999}},'town':{}}
        r=infer_rival_flow(before,after,[],{},quote=market_price,shops=SHOPS,center_products=[])['products']['WHEAT']
        self.assertEqual(r['rival_net_market_flow_range'],[-1,-1]);self.assertTrue(r['gross_buy_sell_ambiguity'])
        self.assertEqual(r['rival_market_supply_units_range'],[0,999])
    def test_nonconsecutive_unknown(self):
        r=infer_rival_flow(self.simple(1),self.simple(4),[],{},quote=market_price,shops=SHOPS,center_products=[])
        self.assertEqual(r['status'],'unknown')
    def test_scenario_history_is_causal(self):
        s=supply_scenarios(self.simple(),{},'WOOL',5)
        self.assertEqual(s['history_status'],'unavailable');self.assertEqual(len(s['scenarios']),3)
        with self.assertRaises(ValueError):supply_scenarios(self.simple(),{},'WOOL',5,[{'start':4,'end':5}])
    def test_recent_scenarios_preserve_interval_and_capacity(self):
        record=infer_rival_flow(self.simple(1),self.simple(2,3),[['SELL','WOOL',2]],{},quote=lambda p,i:100-i,shops=SHOPS,center_products=[])
        ss=supply_scenarios(self.simple(2,3),{},'WOOL',4,[record])
        self.assertEqual([s.get('rate_units_per_turn') for s in ss['scenarios'][1:3]],[1,3])
        self.assertTrue(all(s['probability'] is None for s in ss['scenarios']))
        self.assertTrue(all(sum(s['initial_rival_stock'].values())<=100 for s in ss['scenarios']))
    def test_missing_own_receipt_stays_interval(self):
        r=infer_rival_flow(self.simple(1),self.simple(2,3),[['SELL','WOOL',2]],{},quote=lambda p,i:100-i,shops=SHOPS,center_products=[])['products']['WOOL']
        self.assertEqual(r['rival_market_supply_units_range'],[1,3])
        r=infer_rival_flow(self.simple(1),self.simple(2,3),[['SELL','WOOL',2]],{},quote=lambda p,i:100-i,shops=SHOPS,center_products=[],own_sale_units={'WOOL':2})['products']['WOOL']
        self.assertEqual(r['rival_market_supply_units_range'],[1,1])
    def test_unsupported_orders_are_explicit(self):
        with self.assertRaises(ValueError):simulate_sell_turn({'WOOL':0},[['HIRE']],[],{}, {},market_price)
    def test_capacity_and_terminal(self):
        with self.assertRaises(ValueError):supply_scenarios(self.simple(),{},'WOOL',719)
        with self.assertRaises(ValueError):score_paired_plans(self.simple(),{}, {'WOOL':101},{},{},{'scenarios':[{'id':'none','orders':{},'initial_rival_stock':{}}]},5,quote=market_price,shops=SHOPS,center_products=[])
if __name__=='__main__':unittest.main()
