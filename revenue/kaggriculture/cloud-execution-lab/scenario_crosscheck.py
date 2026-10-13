"""Three fixed development-trace receipt cross-checks; no games or policy fitting.

Imports the exact SORREL adapter and the already-frozen v3 MarketPath. Historical
rival actions are evaluation labels only. Public-flow inference is fed separately
with redacted observations and independently reconstructed own sale receipts.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
REF = HERE / "reference/scenario-adapter"
FROZEN = HERE / "runtime/variants/v3"
ADAPTER_SHA = "d90b343162b6092101d6200a851ab07128bb8d829ecb5c50bf73dd1d7a556552"
SCHEDULER_SHA = "32c8610c9827d1686a6f831e2c4b6af4c00d32d2aa04dcf25699d976d6d97dd9"
CASES = (
    {"opponent": "arlene", "step": 195, "product": "MILK", "end": 197,
     "candidate": ((195, 8), (197, 4)), "alignment": "paired"},
    {"opponent": "arlene", "step": 600, "product": "MILK", "end": 601,
     "candidate": ((600, 9), (601, 8)), "alignment": "paired"},
    {"opponent": "apex", "step": 625, "product": "STRAWBERRY", "end": 629,
     "candidate": ((629, 24),), "alignment": "after"},
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def public_market(observation):
    """No farms, either player's private state, action labels, seed or future."""
    return {key: copy.deepcopy(observation[key]) for key in ("step", "market", "town")}


def focal_queue(orders, product, quantity):
    """Explicit SELL-only projection preserving the original focal order index.

    Other-product trades and expenses are outside this local receipt comparison.
    They cannot change this non-buyable product's market inventory or sale stock;
    execution/funding remains the production scheduler's responsibility.
    """
    queue = [["PASS"] for _ in orders]
    index = next(i for i, o in enumerate(orders) if o[:2] == ["SELL", product])
    queue[index] = ["SELL", product, quantity]
    return queue


def run():
    started = time.perf_counter()
    assert sha(REF / "adapter.py") == ADAPTER_SHA
    assert sha(FROZEN / "scheduler.py") == SCHEDULER_SHA
    sys.path.insert(0, str(FROZEN))
    m = load_module("mechanics", FROZEN / "mechanics.py")
    scheduler = load_module("frozen_v3_crosscheck", FROZEN / "scheduler.py")
    adapter = load_module("sorrel_scenario_crosscheck", REF / "adapter.py")
    cfg = {"episodeSteps": 720, "shedCapacity": 100, "maxMarketOrdersPerTurn": 10,
           "turnsPerDay": 24, "townShopSellInterval": 4, "townCenterSellInterval": 24}
    traces = {}
    results = []
    for case in CASES:
        opponent, start, product = case["opponent"], case["step"], case["product"]
        filename = f"baseline-{opponent}-9600803-seat0.jsonl.gz"
        trace_path = HERE / "runtime/baseline-first-traces" / filename
        if opponent not in traces:
            with gzip.open(trace_path, "rt") as stream:
                traces[opponent] = [json.loads(line) for line in stream]
        rows = traces[opponent]
        row = rows[start]
        observed = row["observation"]
        before, after = public_market(observed), public_market(rows[start + 1]["observation"])
        quote = lambda p, inv: m.market_price(p, inv, observed["market"].get("params"))

        # At these non-day-close steps no after-market own deposit occurs. The
        # focal non-buyable product's own shed delta identifies actual sold units.
        _, own_after_units = scheduler.post_units(observed, row["actions"][0], cfg)
        quantity = own_after_units["shed"][product] - rows[start + 1]["observation"]["private"]["shed"][product]
        assert start % 24 != 23 and product not in ("WHEAT", "FERTILIZER")
        own_trace = next(t for t in row["transactions"]
                         if (t["seat"], t["op"], t["item"]) == (0, "SELL", product))
        assert quantity == own_trace["units"]
        flow = adapter.infer_rival_flow(before, after, row["actions"][0]["market"], cfg,
                                        quote=quote, shops=m.SHOPS,
                                        center_products=m.TOWN_CENTER_PRODUCTS,
                                        own_sale_units={product: quantity})
        hypotheses = adapter.supply_scenarios(after, cfg, product, case["end"], history=[flow])
        assert all(item["probability"] is None for item in hypotheses["scenarios"])

        # The following labels are used only for this fixed offline comparison.
        rival_trace = next(t for t in row["transactions"]
                           if (t["seat"], t["op"], t["item"]) == (1, "SELL", product))
        rival_quantity = rival_trace["units"]
        baseline = {start: focal_queue(row["actions"][0]["market"], product, quantity)}
        candidate = {}
        for step, amount in case["candidate"]:
            candidate[step] = (focal_queue(row["actions"][0]["market"], product, amount)
                               if step == start else [["SELL", product, amount]])
        scenario = {"id": "fixed_observed_dev_sales", "probability": None,
                    "conditional": True, "initial_rival_stock": {product: rival_quantity},
                    "orders": {start: focal_queue(row["actions"][1]["market"], product, rival_quantity)},
                    "arrivals": {}}
        vector = adapter.score_paired_plans(before, cfg, own_after_units["shed"], baseline,
                                            candidate, {"scenarios": [scenario]}, case["end"],
                                            quote=quote, shops=m.SHOPS,
                                            center_products=m.TOWN_CENTER_PRODUCTS)
        result = vector["evaluations"][0]
        model = scheduler.MarketPath(product, observed["market"]["inventory"][product],
                                     observed["market"].get("params"), before["town"]["unlocked_shops"],
                                     cfg, start, case["end"])
        model_baseline = model.score(((start, quantity),), quantity, rival_quantity, case["alignment"])
        model_candidate = model.score(case["candidate"], quantity, rival_quantity, case["alignment"])
        assert result["baseline"]["cash"] == list(model_baseline[1:3])
        assert result["candidate"]["cash"] == list(model_candidate[1:3])
        assert result["game_cash_margin_delta"] == model_candidate[0] - model_baseline[0]
        assert result["baseline"]["cash"] == [own_trace["cash"], rival_trace["cash"]]
        # All focal lots are sold inside these fixed plans, so no short-horizon
        # continuation term needs to be equated with the adapter's cash-only value.
        assert model_baseline[3] == model_candidate[3] == 0
        results.append({
            "step": start, "product": product, "opponent": opponent,
            "horizon": case["end"], "quantity": quantity,
            "candidate_fixed_plan": case["candidate"], "rival_alignment": case["alignment"],
            "baseline_cash": result["baseline"]["cash"],
            "candidate_cash": result["candidate"]["cash"],
            "own_delta": result["own_cash_receipt_delta"],
            "rival_delta": result["rival_cash_receipt_delta"],
            "relative_delta": result["game_cash_margin_delta"],
            "own_admissions_baseline": sum(x["market_supply_units"][0].get(product, 0)
                                             for x in result["baseline"]["timeline"]),
            "own_admissions_candidate": sum(x["market_supply_units"][0].get(product, 0)
                                              for x in result["candidate"]["timeline"]),
            "rival_admissions_baseline": sum(x["market_supply_units"][1].get(product, 0)
                                               for x in result["baseline"]["timeline"]),
            "rival_admissions_candidate": sum(x["market_supply_units"][1].get(product, 0)
                                                for x in result["candidate"]["timeline"]),
            "public_flow_inference": flow["products"][product],
            "generated_hypothesis_ids": [x["id"] for x in hypotheses["scenarios"]],
            "trace": filename, "trace_sha256": sha(trace_path),
            "agreement": "actual baseline receipts and both fixed-plan MarketPath cash vectors match exactly"})
    assert sha(FROZEN / "scheduler.py") == SCHEDULER_SHA
    return {"cases": results, "full_games_run": 0, "optimizer_calls": 0,
            "adapter_sha256": ADAPTER_SHA, "frozen_scheduler_sha256": SCHEDULER_SHA,
            "mechanics_sha256": sha(FROZEN / "mechanics.py"),
            "elapsed_seconds": time.perf_counter() - started}


def report(result):
    lines = ["# Bounded SORREL scenario-adapter cross-check", "",
             "Three fixed development-trace cases passed. Adapter and frozen v3 MarketPath",
             "agree exactly on both players' baseline/candidate sale receipts and their",
             "relative cash changes. Zero full games, optimizer searches or held-out reads",
             "were performed; the candidate source remains unchanged.", "",
             "Run `python -B scenario_crosscheck.py`; add `--write-report` to refresh this report.", "",
             "| Seed9600803 case | Fixed own plan | Baseline own/rival | Candidate own/rival | Own delta | Rival delta | Relative delta |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for case in result["cases"]:
        plan = "; ".join(f"{q} at {t}" for t, q in case["candidate_fixed_plan"])
        pair = lambda key: "/".join(str(x) for x in case[key])
        lines.append(f"| {case['step']} {case['product']} vs {case['opponent']} | {plan} | {pair('baseline_cash')} | {pair('candidate_cash')} | {case['own_delta']:+} | {case['rival_delta']:+} | {case['relative_delta']:+} |")
    lines += ["", "The step600 MILK case includes floor admission: the baseline sells17 each but",
              "admits only10 each; splitting9/8 preserves the exact paid-versus-admitted",
              "distinction. Step625 again shows why an own-receipt gain can lose relative",
              "cash: own +93 accompanies rival +138.", "",
              "## Interface and assumptions", "",
              "- `infer_rival_flow` uses adjacent public market/town observations and own",
              "  orders. These three checks supply focal own sale counts reconstructed from",
              "  exact post-unit own shed minus the next observed own shed. Neither rival",
              "  actions nor rival stock labels enter inference. It preserves floor-sale",
              "  ambiguity instead of identifying gross sales from admitted flow.",
              "- `supply_scenarios` consumes only completed inference history: here each",
              "  transition is used from its after-observation. It produces unweighted",
              "  no-supply, recent lower/upper persistence, and two hypothetical full-shed",
              "  order-alignment cases. Those broad scenarios differ from v3's visible",
              "  crop/harvest magnitude and explicit next-turn/delayed-batch hypotheses.",
              "- `score_paired_plans` accepts full SELL-only queues, keeps duplicate slots,",
              "  recomputes both seats' fills/admission and applies supplied arrival capacity.",
              "  It performs no optimization and no wages/buys/production simulation.",
              "- This check explicitly projects only the focal non-buyable product's SELL",
              "  slots; other slots become PASS. Their expenses and production effects are",
              "  outside this bounded receipt comparison. Actual baseline focal receipts",
              "  reconcile exactly, and all initial/final focal stocks obey capacity.",
              "- Fixed realized rival sales are offline evaluation labels. They are not",
              "  forecasts, private-stock inference or permitted future runtime features.",
              "- Adapter scores cash receipts only. MarketPath additionally values retained",
              "  stock at short artificial boundaries. Every compared fixed plan sells its",
              "  complete focal lot, making that continuation term zero in these cases.",
              "  General cash-only adapter output must not replace v3's continuation value.",
              "- Adapter arrivals occur before each supplied turn's market; an EOD receipt",
              "  available next turn must be dated accordingly by its caller.", "",
              "Source: Commons `0a1f0ec35e903c4b6052681ecf976705a29ab902`,",
              "`revenue/kaggriculture/cloud-frontier-decision/execution/scenarios/adapter.py`.",
              "The adapter imports only standard-library `math.ceil`; this cross-check",
              "supplies the already-preserved exact engine quote and town constants.",
              "Apache-2.0 notices are retained under `reference/scenario-adapter/`.", "",
              f"Elapsed local cross-check time: {result['elapsed_seconds']:.4f} seconds.", "",
              "## Exact receipts and source hashes", "", "```json",
              json.dumps(result, indent=2), "```", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    output = run()
    if args.write_report:
        (HERE / "SCENARIO-CROSSCHECK.md").write_text(report(output))
    print(json.dumps(output, indent=2))
