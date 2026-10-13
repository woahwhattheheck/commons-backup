import copy
import unittest
from decision import hire_cost, sale_receipts, select_hire


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.obs = {'step': 224, 'player': 0, 'farms': [{'money': 1000, 'hires_today': 11}]}
        self.plan = dict(id='rescue', observed_step=224, jointly_feasible=True,
                         first_work_step=225, last_work_step=230, additional_cost=0,
                         baseline_sales=[], with_hire_sales=[dict(product='STRAWBERRY', quantity=2, step=231)])
        self.kw = dict(inventory_scenarios={'low': lambda p,s: 0, 'high': lambda p,s: -10},
                       quote=lambda p,i: max(1, 166-i))

    def decide(self, plan=None, **kw):
        return select_hire(self.obs, {}, [plan or self.plan], **dict(self.kw, **kw))

    def test_late_useful_hire_exact_cost(self):
        r = self.decide()
        self.assertEqual(r['decision'], 'HIRE')  # hour 8, no hour-3 cutoff
        self.assertEqual(r['hire_cost'], 144)
        self.assertEqual(r['conditional_own_cash_profit_range'], [187, 207])
        self.assertEqual([hire_cost(n) for n in range(5)], [1,1,2,3,5])
        self.assertEqual(hire_cost(11, 3), 432)

    def test_already_covered_is_not_incremental(self):
        p = copy.deepcopy(self.plan); p['baseline_sales'] = p['with_hire_sales'][:]
        self.assertEqual(self.decide(p)['decision'], 'KEEP')

    def test_supply_cannibalizes_existing_receipts(self):
        p = copy.deepcopy(self.plan)
        p['baseline_sales'] = [dict(product='STRAWBERRY', quantity=2, step=232)]
        p['with_hire_sales'] += p['baseline_sales']
        r = self.decide(p)
        self.assertEqual(r['conditional_own_cash_profit_range'], [183, 203])
        # Repricing existing output makes the marginal value 4 less than gross.

    def test_lifetime_stale_terminal_and_infeasible(self):
        for change, reason in [({'first_work_step':224},'worker_lifetime'),
                               ({'last_work_step':240},'worker_lifetime'),
                               ({'observed_step':223},'stale_plan'),
                               ({'jointly_feasible':False},'infeasible_plan'),
                               ({'with_hire_sales':[dict(product='STRAWBERRY',quantity=2,step=719)]},'sale_horizon')]:
            p = dict(self.plan, **change)
            self.assertEqual(self.decide(p)['evaluations'][0]['reason'], reason)
        self.obs['step'] = 718
        p = dict(self.plan, observed_step=718, first_work_step=719, last_work_step=719)
        self.assertEqual(self.decide(p)['decision'], 'KEEP')

    def test_cash_and_slots(self):
        self.assertEqual(self.decide(funds_before_hire=143)['reason'], 'cash_shortfall')
        self.assertEqual(self.decide(funds_before_hire=150,cash_reserve=7)['reason'], 'cash_shortfall')
        self.assertEqual(self.decide(free_order_slots=0)['reason'], 'no_order_slot')

    def test_uncertain_or_costly_work_does_not_pass(self):
        r = self.decide(quote=lambda p,i: 1 if i==0 else 166)
        self.assertEqual(r['decision'], 'KEEP') # floor quote persists: 2 - 144, not 167 - 144
        self.assertEqual(self.decide(dict(self.plan, additional_cost=188))['decision'], 'KEEP')
        self.assertEqual(self.decide(quote=lambda p,i: 1)['decision'], 'KEEP')

    def test_objective_choices_preserve_full_profit_vector(self):
        # Explicit illustrative scores, not calibrated probabilities.
        kw = dict(quote=lambda p,i: 20 if i >= 0 else 100)
        worst = self.decide(**kw)
        central = self.decide(**kw, objective='central_scenario', central_scenario='high')
        weighted = self.decide(**kw, objective='weighted', scenario_weights={'low':.1,'high':.9})
        self.assertEqual(worst['decision'], 'KEEP')
        self.assertEqual(central['decision'], 'HIRE')
        self.assertEqual(weighted['decision'], 'HIRE')
        for r in [worst, central, weighted]:
            self.assertEqual(r['evaluations'][0]['scenario_own_cash_profit'], {'low':-104,'high':56})
        self.assertEqual(central['selection_own_cash_profit'], 56)
        self.assertAlmostEqual(weighted['selection_own_cash_profit'], 40)
        self.assertEqual(central['conditional_margin'], [-104,56]) # legacy OWN cash alias

    def test_no_implicit_probabilities_or_scenario_names(self):
        for kw in [dict(objective='weighted'), dict(objective='central_scenario'),
                   dict(objective='weighted',scenario_weights={'low':1}),
                   dict(objective='weighted',scenario_weights={'low':-1,'high':2}),
                   dict(objective='weighted',scenario_weights={'low':1,'high':1}),
                   dict(objective='weighted',scenario_weights={'low':float('nan'),'high':1}),
                   dict(objective='unknown')]:
            with self.assertRaises(ValueError): self.decide(**kw)

    def test_floor_sales_do_not_poison_later_town_recovery(self):
        lots = [dict(product='STRAWBERRY',quantity=4,step=1),
                dict(product='STRAWBERRY',quantity=1,step=5)]
        # First quotes 3,2,1,1; only two units enter supply. Town removes two
        # before the later sale, which must quote 3, not the buggy 1.
        self.assertEqual(sale_receipts(lots,lambda p,s:0 if s==1 else -2,
                                       lambda p,i:max(1,3-i),718),10)

    def test_batch_is_sequential_not_quantity_times_quote(self):
        lots = [dict(product='MILK',quantity=3,step=5)]
        self.assertEqual(sale_receipts(lots,lambda p,s:0,lambda p,i:160-2*i,718),474)
        with self.assertRaises(ValueError):
            sale_receipts(lots,lambda p,s:0,lambda p,i:float('nan'),718)


if __name__ == '__main__': unittest.main()
