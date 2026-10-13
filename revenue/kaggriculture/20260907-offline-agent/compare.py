"""Paired comparisons and resource diagnostics; official interpreter, not Kaggle hosted."""
from __future__ import annotations
import argparse, collections, hashlib, json, statistics, tempfile
from pathlib import Path
from evaluate import get_engine, load_agent, play

VARIANTS = {
    "marginal": {"marginal_economics":True},
    "compact_capacity": {"marginal_economics":False,"animal_cap":28,"max_hands":10},
    "long_horizon": {"marginal_economics":False,"forecast_days":20},
    "route_locality": {"marginal_economics":False,"same_tile_bonus":3.0},
}
class Observed:
    def __init__(self, agent):
        self.agent=agent; self.orders=collections.Counter()
        self.saturated=0; self.unfed_without_buy=0; self.days=[]
    def __call__(self,obs,cfg):
        action=self.agent(obs,cfg)
        for order in action.get("market",[]): self.orders[order[0]]+=1
        if len(action.get("market",[]))>=10: self.saturated+=1
        own=obs["farms"][obs["player"]]
        animals=[t for row in own["tiles"] for t in row if isinstance(t,dict) and "animal" in t]
        unfed=sum(not a["fed_today"] for a in animals)
        feed=obs["private"]["shed"].get("WHEAT",0)+sum(i.get("WHEAT",0) for i in obs["private"]["inventories"])
        if obs["hour"]>3 and obs["day"]<29 and unfed>feed and not any(o[:2]==["BUY_PRODUCT","WHEAT"] for o in action.get("market",[])):
            self.unfed_without_buy+=1
        if obs["hour"]==0:
            self.days.append({"day":obs["day"],"money":own["money"],"animals":len(animals),
               "prices":dict(obs["market"]["prices"]), "quadrants":len(own["unlocked_quadrants"])})
        return action
    def report(self):
        return {"market_orders":dict(self.orders),"order_cap_turns":self.saturated,
                "unfed_without_buy_turns":self.unfed_without_buy,"daily":self.days}

def run(output,seeds,variant_names):
    root=Path(__file__).parent
    results=[]
    with tempfile.TemporaryDirectory(prefix="kaggriculture-compare-") as cache:
        engine,hashes=get_engine(cache)
        rivals={
            "incumbent": lambda:load_agent(root/"incumbent_20260907.py"),
            "compact": lambda:load_agent(root/"incumbent_20260907.py",{"animal_cap":22,"max_hands":9,"expansion":False}),
        }
        for name in variant_names:
            for rival,factory in rivals.items():
                for seed in seeds:
                    for seat in (0,1):
                        ours=Observed(load_agent(root/"candidate.py",VARIANTS[name]))
                        other=Observed(factory())
                        pair=[ours,other] if seat==0 else [other,ours]
                        row=play(engine,pair,seed)
                        row.update(variant=name,opponent=rival,seat=seat,
                            margin=row["bank"][seat]-row["bank"][1-seat],
                            diagnostics=[x.report() for x in pair])
                        results.append(row)
                        print(json.dumps({k:row[k] for k in ("variant","opponent","seed","seat","bank","margin")}),flush=True)
    summary={}
    for name in variant_names:
        summary[name]={}
        for rival in ("incumbent","compact"):
            rows=[r for r in results if r["variant"]==name and r["opponent"]==rival]
            margins=[r["margin"] for r in rows]
            summary[name][rival]={"games":len(rows),"wins":sum(m>0 for m in margins),
                "losses":sum(m<0 for m in margins),"ties":sum(m==0 for m in margins),
                "mean_margin":statistics.mean(margins),"min_margin":min(margins),
                "mean_bank":statistics.mean(r["bank"][r["seat"]] for r in rows)}
    report={"source_pin":"28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c","hashes":hashes,
        "candidate_sha256":hashlib.sha256((root/"candidate.py").read_bytes()).hexdigest(),
        "incumbent_sha256":hashlib.sha256((root/"incumbent_20260907.py").read_bytes()).hexdigest(),
        "variants":{n:VARIANTS[n] for n in variant_names},"seeds":seeds,"summary":summary,"games":results}
    Path(output).write_text(json.dumps(report,indent=2)+"\n")
    print("COMPARISON "+json.dumps(summary),flush=True)
    assert all(r["status"]==["DONE","DONE"] for r in results)
    assert max(max(r["max_call_seconds"]) for r in results)<1.

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    parser.add_argument("--seeds",default="37,211,997")
    parser.add_argument("--variants",default=",".join(VARIANTS))
    args=parser.parse_args()
    run(args.output,[int(s) for s in args.seeds.split(",")],args.variants.split(","))
