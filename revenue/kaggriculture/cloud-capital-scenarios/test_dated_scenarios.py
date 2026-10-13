# SPDX-License-Identifier: Apache-2.0
"""Run with python -B test_dated_scenarios.py -v (stdlib only)."""
from copy import deepcopy
from dataclasses import make_dataclass
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from dated_scenarios import CashScenario, DatedSelector, compare_routes


def row(step, slot, op, delta, item="WOOL", quantity=1):
    order = [op] if op in ("HIRE", "PASS") else [op, item, quantity]
    return dict(step=step, slot=slot, order=order, delta=delta)


def offer(name, *rows):
    return dict(route_id=name, orders=list(rows))


def obs(cash=1000):
    return dict(step=226, player=0, farms=[dict(money=cash), dict(money=777)])


def pair():
    return [offer("main", row(226,0,"BUY_ANIMAL",-100), row(406,0,"SELL",500)),
            offer("sheep", row(226,0,"BUY_ANIMAL",-200), row(406,0,"SELL",1200))]


def scenario(name="nominal", base=500, alt=1200):
    return CashScenario(name, {"main": {(406,0):base}, "sheep": {(406,0):alt}})


class DatedScenarioTests(unittest.TestCase):
    def test_positive_complete_comparison(self):
        result=compare_routes(pair(),obs(),[scenario()])
        self.assertEqual(result["selected"],"sheep")
        self.assertEqual(result["candidates"]["sheep"]["worst_paired_gain"],600)

    def test_dated_drawdown_reverses_static_quote_choice(self):
        result=compare_routes(pair(),obs(),[scenario(),scenario("depleted",500,200)])
        self.assertEqual(result["selected"],"main")
        self.assertEqual(result["candidates"]["sheep"]["worst_paired_gain"],-400)

    def test_missing_candidate_row_is_not_zero_or_discarded_scenario(self):
        incomplete=CashScenario("unknown",{"main":{(406,0):500}})
        result=compare_routes(pair(),obs(),[scenario(),incomplete])
        self.assertEqual(result["selected"],"main")
        self.assertIsNone(result["candidates"]["sheep"]["worst_paired_gain"])
        self.assertEqual(result["scenarios"][1]["routes"]["sheep"]["missing_rows"],[[406,0]])

    def test_missing_incumbent_blocks_paired_comparison(self):
        result=compare_routes(pair(),obs(),[CashScenario("x",{"sheep":{(406,0):900}})])
        self.assertEqual(result["reason"],"incumbent_scenario_incomplete")
        self.assertEqual(result["selected"],"main")

    def test_future_receipt_cannot_fund_earlier_input(self):
        offers=[offer("main",row(227,0,"SELL",100)),
                offer("alt",row(226,0,"BUY_PRODUCT",-20),row(227,0,"SELL",1000))]
        sc=CashScenario("expensive",{"main":{(227,0):100},"alt":{(226,0):-350,(227,0):1000}})
        result=compare_routes(offers,obs(300),[sc])
        alt=result["scenarios"][0]["routes"]["alt"]
        self.assertEqual(alt["final_nominal_cash"],950)
        self.assertEqual(alt["minimum_nominal_cash"],-50)
        self.assertEqual(alt["first_negative"],[226,0])
        self.assertEqual(result["selected"],"main")

    def test_same_turn_sale_can_fund_later_input_in_real_slot_order(self):
        offers=[offer("main",row(226,0,"SELL",100)),
                offer("alt",row(226,0,"SELL",1000),row(226,1,"BUY_PRODUCT",-20))]
        sc=CashScenario("x",{"main":{(226,0):100},"alt":{(226,0):1000,(226,1):-350}})
        self.assertEqual(compare_routes(offers,obs(300),[sc])["selected"],"alt")

    def test_route_specific_and_date_specific_totals(self):
        offers=[offer("main",row(227,0,"SELL",10),row(228,0,"SELL",10)),
                offer("alt",row(227,0,"SELL",10),row(228,0,"SELL",10))]
        sc=CashScenario("x",{"main":{(227,0):300,(228,0):2},"alt":{(227,0):1,(228,0):400}})
        r=compare_routes(offers,obs(),[sc])
        self.assertEqual(r["candidates"]["alt"]["worst_paired_gain"],99)

    def test_buy_product_uses_total_cost_not_unit_times_quantity(self):
        offers=[offer("main",row(226,0,"PASS",0)),
                offer("alt",row(226,0,"BUY_PRODUCT",-6,"FERTILIZER",3),row(227,0,"SELL",20))]
        sc=CashScenario("x",{"alt":{(226,0):-17,(227,0):20}})
        r=compare_routes(offers,obs(),[sc])
        self.assertEqual(r["candidates"]["alt"]["worst_paired_gain"],3)

    def test_fixed_costs_are_preserved(self):
        fixed=[row(226,0,"BUY_ANIMAL",-200),row(226,1,"HIRE",-13),
               row(226,2,"BUY_SEED",-40),row(227,0,"BUY_LAND",-100)]
        offers=[offer("main",row(226,0,"PASS",0)),offer("alt",*fixed,row(228,0,"SELL",400))]
        result=compare_routes(offers,obs(),[CashScenario("x",{"alt":{(228,0):400}})])
        self.assertEqual(result["candidates"]["alt"]["worst_paired_gain"],47)

    def test_worst_paired_gain_not_worst_absolute_cash(self):
        offers=[offer(key,row(226,0,"SELL",1)) for key in ("main","a","b")]
        sc=[CashScenario("high",{k:{(226,0):v} for k,v in zip(("main","a","b"),(900,902,905))}),
            CashScenario("low",{k:{(226,0):v} for k,v in zip(("main","a","b"),(0,5,3))})]
        self.assertEqual(compare_routes(offers,obs(100),sc)["selected"],"b")

    def test_tie_and_required_margin_keep_incumbent(self):
        self.assertEqual(compare_routes(pair(),obs(),[scenario(alt=600)])["selected"],"main")
        self.assertEqual(compare_routes(pair(),obs(),[scenario()],minimum_gain=600)["selected"],"main")

    def test_no_scenarios_and_incumbent_only(self):
        self.assertEqual(compare_routes(pair(),obs(),[])["selected"],"main")
        self.assertEqual(compare_routes(pair()[:1],obs(),[scenario()])["selected"],"main")

    def test_explicit_zero_is_valid_but_missing_is_unknown(self):
        result=compare_routes(pair(),obs(),[scenario(base=0,alt=0)])
        self.assertTrue(result["scenarios"][0]["routes"]["sheep"]["complete"])
        self.assertEqual(result["selected"],"main")

    def test_nonfinite_and_wrong_sign_scenario_values_cannot_select(self):
        for value in (float("nan"),float("inf"),-1,True,None):
            with self.subTest(value=value):
                result=compare_routes(pair(),obs(),[scenario(alt=value)])
                self.assertEqual(result["selected"],"main")
                self.assertEqual(result["scenarios"][0]["routes"]["sheep"]["invalid_rows"],[[406,0]])
                json.dumps(result,allow_nan=False)

    def test_positive_buy_cost_is_invalid(self):
        offers=[offer("main",row(226,0,"PASS",0)),offer("alt",row(226,0,"BUY_PRODUCT",-10))]
        result=compare_routes(offers,obs(),[CashScenario("x",{"alt":{(226,0):10}})])
        self.assertFalse(result["candidates"]["alt"]["complete"])

    def test_no_mutation(self):
        offers,ob,sc=pair(),obs(),[scenario()]
        before=deepcopy((offers,ob,sc))
        compare_routes(offers,ob,sc)
        self.assertEqual((offers,ob,sc),before)

    def test_dataclass_routequote_callback_and_last_report(self):
        Quote=make_dataclass("Quote",["route_id","orders"])
        offers=[Quote(**v) for v in pair()]
        selector=DatedSelector([scenario()])
        self.assertEqual(selector(offers,obs()),"sheep")
        self.assertTrue(selector.last_report["changed"])

    def test_bad_route_order_and_fixed_credit_rejected(self):
        rows=[row(226,0,"PASS",0),row(226,0,"PASS",0)]
        for bad in (rows,[row(225,0,"PASS",0)],[row(226,-1,"PASS",0)],
                    [row(226,0,"HIRE",5)],[row(226,0,"PASS",1)],
                    [row(226,0,"SELL",float("nan"))]):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                compare_routes([offer("main",*bad)],obs(),[CashScenario("x",{})])

    def test_duplicate_route_scenario_and_negative_margin_rejected(self):
        with self.assertRaises(ValueError): compare_routes(pair()*2,obs(),[scenario()])
        with self.assertRaises(ValueError): compare_routes(pair(),obs(),[scenario(),scenario()])
        with self.assertRaises(ValueError): compare_routes(pair(),obs(),[scenario()],minimum_gain=-1)

    def test_json_scenario_duplicate_and_cli(self):
        data={"name":"x","flows":{"main":[{"step":406,"slot":0,"delta":500}],
                                  "sheep":[{"step":406,"slot":0,"delta":1200}]}}
        self.assertEqual(CashScenario.from_dict(data).flows["main"][(406,0)],500)
        duplicate=deepcopy(data);duplicate["flows"]["main"]*=2
        with self.assertRaises(ValueError): CashScenario.from_dict(duplicate)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"input.json"
            p.write_text(json.dumps(dict(offers=pair(),observation=obs(),scenarios=[data])))
            run=subprocess.run([sys.executable,"-B",str(Path(__file__).with_name("dated_scenarios.py")),str(p)],
                               check=True,capture_output=True,text=True)
            self.assertEqual(json.loads(run.stdout)["selected"],"sheep")

    def test_accumulation_and_paired_difference_overflow_fall_back(self):
        offers=[offer("main",row(226,0,"BUY_ANIMAL",-1.7e308)),
                offer("alt",row(226,0,"SELL",1))]
        result=compare_routes(offers,obs(1),[CashScenario("x",{"alt":{(226,0):1.7e308}})])
        self.assertEqual(result["selected"],"main")
        self.assertFalse(result["candidates"]["alt"]["complete"])
        json.dumps(result,allow_nan=False)
        result=compare_routes(pair(),obs(1.7e308),[scenario(alt=1.7e308)])
        self.assertEqual(result["selected"],"main")
        json.dumps(result,allow_nan=False)

    def test_cli_missing_file_has_controlled_error(self):
        run=subprocess.run([sys.executable,"-B",str(Path(__file__).with_name("dated_scenarios.py")),
                            "/nonexistent/astra-date-input.json"],capture_output=True,text=True)
        self.assertEqual(run.returncode,2)
        self.assertNotIn("Traceback",run.stderr)

    def test_one_thousand_independent_integer_oracle_cases(self):
        rng=random.Random(447)
        for case in range(1000):
            cash=rng.randrange(0,600)
            n=rng.randrange(2,6)
            costs=[rng.randrange(0,500) for _ in range(n)]
            offers=[offer(str(i),row(226,0,"BUY_ANIMAL",-costs[i]),
                          row(227,0,"SELL",1),row(228,0,"BUY_PRODUCT",-1)) for i in range(n)]
            totals=[[(rng.randrange(0,900),rng.randrange(0,500)) for _ in range(n)] for _ in range(3)]
            scenarios=[CashScenario(str(s),{str(i):{(227,0):sale,(228,0):-buy}
                                              for i,(sale,buy) in enumerate(values)})
                       for s,values in enumerate(totals)]
            winner,best="0",0
            for i in range(1,n):
                balances=[[cash,cash-costs[i],cash-costs[i]+values[i][0],
                           cash-costs[i]+values[i][0]-values[i][1]] for values in totals]
                gains=[-costs[i]+sale_i-buy_i+costs[0]-values[0][0]+values[0][1]
                       for values in totals for sale_i,buy_i in [values[i]]]
                if min(min(b) for b in balances)>=0 and min(gains)>best:
                    winner,best=str(i),min(gains)
            self.assertEqual(compare_routes(offers,obs(cash),scenarios)["selected"],winner,case)


if __name__=="__main__":
    unittest.main()
