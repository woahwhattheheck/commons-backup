"""Execute behavioral source defects; every rejection must be an assertion."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
# name, exact preimage, replacement, independent behavioral test
FAULTS = [
    ("floor_fill_erased", 'if ok and op == "SELL":', 'if ok and op == "SELL" and price > 1:',
     "test_floor_sales_are_fills_without_supply_growth"),
    ("requested_not_filled", 'if ok and op == "SELL":', 'if op == "SELL":',
     "test_empty_shed_requested_sales_are_not_fills"),
    ("raw_slot_compaction", 'source[source_row] = ["PASS"]', 'source.pop(source_row)',
     "test_source_slot_placeholder_preserves_atomic_funding_order"),
    ("cross_turn_alias", 'out = [[copy.deepcopy(action) for action in pair] for pair in tape]',
     'out = copy.deepcopy(tape)', "test_cross_turn_alias_does_not_change_unrelated_actions"),
    ("rival_cash_ignored", '"terminal_margin_delta": (delta[seat]-delta[1-seat]) if terminal else None',
     '"terminal_margin_delta": delta[seat] if terminal else None', "test_terminal_margin_accounts_for_rival_cash"),
    ("false_terminal", 'terminal = all(s.status == "DONE" for s in state)', 'terminal = True',
     "test_no_terminal_claim_for_nonterminal_window"),
    ("raw_change_as_fill", 'filled = _fill_timeline(baseline, seat) != _fill_timeline(candidate, seat)',
     'filled = bool(changed)', "test_capped_changes_not_mistaken_for_filled_sales"),
    ("pre_unit_stock_snapshot", 'report["market_entry_shed"] = [copy.deepcopy(x.observation.private["shed"]) for x in s]',
     'report["market_entry_shed"] = [copy.deepcopy(x.observation.private["shed"]) for x in state_before_units]',
     "test_unit_drop_is_available_before_market"),
    ("native_order_discriminator", 'parsed.get("type")', 'parsed.get("op")',
     "test_native_census_uses_official_parsed_type"),
    ("false_retiming_label", 'classification = ("SUPPRESSED_SALE_NOT_RETIMED" if not target_units else',
     'classification = ("REALIZED_RETIMING" if not target_units else',
     "test_native_witness_rejects_false_earlier_fill"),
]


def run():
    original = (ROOT / "sale_window.py").read_text()
    results = []
    for optimized in (False, True):
        for name, before, after, test in FAULTS:
            source = ((ROOT / "run_native.py").read_text() if name in ("native_order_discriminator", "false_retiming_label") else original)
            if source.count(before) != 1:
                raise ValueError("fault preimage mismatch: " + name)
            text = source.replace(before, after)
            if name == "pre_unit_stock_snapshot":
                text = text.replace('current = {}', 'state_before_units = copy.deepcopy(state)\n    current = {}')
            with tempfile.TemporaryDirectory(prefix="harvestclock-fault-") as tmp:
                path = Path(tmp)
                (path / "sale_window.py").write_text(original)
                (path / "run_native.py").write_bytes((ROOT / "run_native.py").read_bytes())
                target = "run_native.py" if name in ("native_order_discriminator", "false_retiming_label") else "sale_window.py"
                (path / target).write_text(text)
                (path / "test_sale_window.py").write_bytes((ROOT / "test_sale_window.py").read_bytes())
                cmd = [sys.executable] + (["-O"] if optimized else []) + [
                    "-m", "unittest", "-v", "test_sale_window.SaleWindowTests." + test]
                completed = subprocess.run(cmd, cwd=path, env=os.environ.copy(), capture_output=True,
                                           text=True, timeout=20)
                log = completed.stdout + completed.stderr
                rejected = completed.returncode == 1 and "FAILED (failures=1)" in log and "AssertionError" in log
                result = {"fault": name, "optimized": optimized, "test": test,
                          "assertion_rejected": rejected, "returncode": completed.returncode, "log": log}
                results.append(result)
                if not rejected:
                    raise RuntimeError(json.dumps(result, indent=2))
    return {"schema": "titan.sale-window-negative.v1", "results": results,
            "all_assertion_rejected": all(row["assertion_rejected"] for row in results)}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
