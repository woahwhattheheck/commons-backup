# SPDX-License-Identifier: Apache-2.0
"""Exercise this callback on exact HAZEL quotations of the real Arlene programs.

The market snapshot and alternative prices below are CONSTRUCTED discriminators,
not saved match states, forecasts, or an independent game panel. No parent action
or game interpreter is executed. External source files are consumed, not copied.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time
from dated_scenarios import CashScenario, DatedSelector, compare_routes

PARENT_SHA256 = "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4"
HAZEL_BLOB = "00abee3c99641eb0ab1729fd80e6f9a5c783f373"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def blob(path):
    data=Path(path).read_bytes()
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


def run(arlene_path, hazel_path, mechanics_path):
    assert hashlib.sha256(arlene_path.read_bytes()).hexdigest()==PARENT_SHA256
    assert blob(hazel_path)==HAZEL_BLOB
    arlene=load("date_real_arlene",arlene_path)
    hazel=load("date_real_hazel",hazel_path)
    mechanics=load("date_real_mechanics",mechanics_path)
    prices={p:mechanics.market_price(p,mechanics.MARKET_I0) for p in mechanics.PRODUCTS}
    prices.update(WOOL=189,EGG=51)
    observation={"step":226,"player":0,
        "farms":[{"money":10000,"hires_today":0,"unlocked_quadrants":["NW"]},
                 {"money":10000,"hires_today":0,"unlocked_quadrants":["NW"]}],
        "market":{"prices":prices,"inventory":{p:mechanics.MARKET_I0 for p in mechanics.PRODUCTS}}}
    controller=arlene.Agent()
    offers=[hazel.quote_program(key,controller.R[key],observation,{},mechanics)
            for key in (hazel.MAIN,hazel.SHEEP)]
    frozen_routes=deepcopy(controller.R)
    baseline_flows={v.route_id:{(r["step"],r["slot"]):r["delta"] for r in v.orders
                      if r["order"][0] in ("SELL","BUY_PRODUCT")} for v in offers}
    nominal=CashScenario("constructed_current_quote_reproduction",baseline_flows)
    depleted=deepcopy(baseline_flows)
    for v in offers:
        for row in v.orders:
            if row["step"]>=360 and row["order"][0:2]==["SELL","WOOL"]:
                depleted[v.route_id][(row["step"],row["slot"])]=37*row["order"][2]
    decline=CashScenario("constructed_wool_37_after_step360",depleted)
    current_result=compare_routes(offers,observation,[nominal])
    robust_result=compare_routes(offers,observation,[nominal,decline])
    assert current_result["selected"]==hazel.SHEEP
    assert robust_result["selected"]==hazel.MAIN
    for v in offers:
        actual=current_result["scenarios"][0]["routes"][v.route_id]
        assert actual["final_nominal_cash"]==v.final_marked_cash
        assert actual["minimum_nominal_cash"]==v.minimum_marked_cash
    joined=[]
    for player in (0,1):
        ob=deepcopy(observation);ob["player"]=player
        for scenarios,expected in (([nominal],hazel.SHEEP),([nominal,decline],hazel.MAIN)):
            ctrl=arlene.Agent()
            before=deepcopy(ctrl.__dict__)
            selector=DatedSelector(scenarios)
            outer=hazel.choose_before_action(ctrl,ob,{},mechanics,selector=selector)
            assert ctrl.cur==expected and outer["after"]==expected
            assert ctrl.R==frozen_routes
            assert {k:v for k,v in ctrl.__dict__.items() if k!="cur"}=={
                    k:v for k,v in before.items() if k!="cur"}
            joined.append({"player":player,"scenario_count":len(scenarios),
                           "selected":ctrl.cur,"changed":outer["changed"]})
    sparse=deepcopy(baseline_flows)
    removed=next(iter(sparse[hazel.SHEEP]));del sparse[hazel.SHEEP][removed]
    incomplete=compare_routes(offers,observation,[CashScenario("missing_one",sparse)])
    assert incomplete["selected"]==hazel.MAIN
    assert incomplete["scenarios"][0]["routes"][hazel.SHEEP]["missing_rows"]==[list(removed)]
    totals=[]
    for v in offers:
        sales=Counter()
        for row in v.orders:
            if row["order"][0]=="SELL":sales[row["order"][1]]+=row["order"][2]
        totals.append({"route_id":v.route_id,"rows":len(v.orders),
                       "variable_rows":len(baseline_flows[v.route_id]),
                       "planned_sale_quantities":dict(sales),
                       "nominal_purchases":v.purchases,"nominal_labor":v.labor,
                       "nominal_land":v.land})
    times=[]
    for _ in range(100):
        start=time.perf_counter();compare_routes(offers,observation,[nominal,decline])
        times.append((time.perf_counter()-start)*1000)
    return {"schema":"dated-capital-route-check.v1",
      "scope":"actual_source_callback_join_on_constructed_observation_and_price_scenarios",
      "games":0,"new_game_seeds":0,"parent_action_calls":0,
      "pins":{"arlene_sha256":PARENT_SHA256,"hazel_blob":HAZEL_BLOB,
              "mechanics_blob":blob(mechanics_path),
              "runtime_sha256":hashlib.sha256(Path(__file__).with_name("dated_scenarios.py").read_bytes()).hexdigest()},
      "constructed_observation":observation,"route_totals":totals,
      "current_quote_comparison":current_result,"two_scenario_comparison":robust_result,
      "joined_cases":joined,"missing_row_fallback":list(removed),
      "benchmark":{"iterations":100,"scope":"callback_only_two_routes_two_scenarios_imports_and_quoting_excluded",
                   "median_ms":statistics.median(times),"maximum_ms":max(times)},
      "limits":["Not a reached-game or held-out result.",
                "Scenario prices are explicit hypothetical discriminators, not predictions.",
                "All nominal planned quantities/fixed orders remain conditional on successful execution.",
                "Worst paired own-cash improvement is not terminal win utility or a rival-cash comparison."]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arlene",type=Path,required=True)
    parser.add_argument("--hazel",type=Path,required=True)
    parser.add_argument("--mechanics",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report=run(args.arlene,args.hazel,args.mechanics)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print(json.dumps({"joined_cases":len(report["joined_cases"]),"route_rows":sum(x["rows"] for x in report["route_totals"]),
                     "quote_choice":report["current_quote_comparison"]["selected"],
                     "dated_choice":report["two_scenario_comparison"]["selected"],
                     "nominal_gain":report["current_quote_comparison"]["candidates"]["dc76e4003029ac51"]["worst_paired_gain"],
                     "scenario_worst_gain":report["two_scenario_comparison"]["candidates"]["dc76e4003029ac51"]["worst_paired_gain"],
                     "benchmark":report["benchmark"],"games":0},indent=2))


if __name__=="__main__":main()
