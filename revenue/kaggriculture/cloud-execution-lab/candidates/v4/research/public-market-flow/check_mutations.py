# SPDX-License-Identifier: Apache-2.0
"""Prove the regression suite rejects deliberately incorrect accounting."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

MUTATIONS = (
    ("floor_sales_treated_as_visible", "gross_identifiable = item not in BUYABLE and final_quote > 1", "gross_identifiable = item not in BUYABLE"),
    ("post_town_quote_used_as_market_quote", "final_quote = default_price(item, final_market_stock)", "final_quote = default_price(item, end[item])"),
    ("raw_cap_after_compacting_rows", "for row in rows[:limit]:", "for row in [r for r in rows if type(r) is list][:limit]:"),
    ("duplicate_shops_collapsed", "for shop in shops:", "for shop in set(shops):"),
    ("next_step_used_for_town_tick", "if step % shop_tick == 0:", "if (step + 1) % shop_tick == 0:"),
    ("own_buy_bound_omitted", "upper = min(residual + bought[item], rival_ceiling)", "upper = min(residual, rival_ceiling)"),
    ("negative_public_inventory_rejected", '"inventory_domain", -10**9, 10**9', '"inventory_domain", 0, 10**9'),
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--logs", type=Path)
    args = parser.parse_args()
    engine = args.engine.resolve()
    here = Path(__file__).resolve().parent
    source = (here / "public_market_flow.py").read_text()
    rows = []
    for name, old, new in MUTATIONS:
        if source.count(old) != 1:
            raise RuntimeError(f"Mutation preimage changed: {name}")
        for optimized in (False, True):
            with tempfile.TemporaryDirectory(prefix="titan-flow-mutant-") as tmp:
                root = Path(tmp)
                (root / "public_market_flow.py").write_text(source.replace(old, new))
                shutil.copy2(here / "test_public_market_flow.py", root)
                report = root / "report.json"
                command = [sys.executable] + (["-O"] if optimized else []) + [
                    str(root / "test_public_market_flow.py"), "--engine", str(engine),
                    "--cases", "64", "--report", str(report)]
                run = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
                result = json.loads(report.read_text()) if report.exists() else {}
                killed = (run.returncode != 0 and result.get("tests") == 24
                          and result.get("failures", 0) > 0 and result.get("success") is False)
                row = dict(name=name, optimized=optimized, killed=killed,
                           exit_code=run.returncode, tests=result.get("tests"),
                           failures=result.get("failures"), errors=result.get("errors"))
                rows.append(row)
                if args.logs:
                    args.logs.mkdir(parents=True, exist_ok=True)
                    (args.logs / f"{name}-{'optimized' if optimized else 'normal'}.log").write_text(run.stdout + run.stderr)
                print(json.dumps(row))
    result = {"mutations": len(MUTATIONS), "executions": len(rows),
              "killed": sum(r["killed"] for r in rows),
              "all_killed": all(r["killed"] for r in rows), "results": rows}
    args.report.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["all_killed"] else 1


if __name__ == "__main__":
    sys.exit(main())
