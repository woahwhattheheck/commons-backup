"""Corrected C5 outer-order regression transformer for existing PR #12611 only.

Supersedes raw donor 73a2182c6161af50209f7a4e31c6026d89f6b890.
Apply to overlay/checks/test_v4_c5_wheat_demand.py from #12611 head dfa047cf...
No shared apply_v4.py or gameplay helper change.
"""
from pathlib import Path

path = Path("revenue/kaggriculture/cloud-execution-lab/candidates/v3/overlay/checks/test_v4_c5_wheat_demand.py")
src = path.read_text(encoding="utf-8")
old = '''    def test_c5_is_final_market_transform_and_after_b10_if_present(self):
        source = Path(r04.__file__).read_text(encoding="utf-8")
        c5_at = source.index("if C5_WHEAT_DEMAND:")
        self.assertGreater(c5_at, source.index("if GOOSE_RESCUE:"))
        if "if B10_PUBLIC_SUPPLY_ORDER:" in source:
            self.assertGreater(c5_at, source.index("if B10_PUBLIC_SUPPLY_ORDER:"))
'''
new = '''    def test_c5_is_last_in_converged_market_evidence_chain(self):
        source = Path(r04.__file__).read_text(encoding="utf-8")
        c5_at = source.index("if C5_WHEAT_DEMAND:")
        self.assertGreater(c5_at, source.index("if GOOSE_RESCUE:"))
        # Converged causal chain: M1 -> EOD -> B10 -> C5.
        # M1's WHEAT BUY must remain visible when C5 stores own_buy_upper;
        # EOD must precede B10 so B10 stores its synthetic SELL in own_sell_upper;
        # C5 consumes the completed B10 parent action last.
        for marker in (
            "if M1_WHEAT_TRADE:",
            "if EOD_CAPACITY_RESCUE:",
            "if B10_PUBLIC_SUPPLY_ORDER:",
        ):
            if marker in source:
                self.assertGreater(c5_at, source.index(marker))
        if all(marker in source for marker in (
            "if M1_WHEAT_TRADE:",
            "if EOD_CAPACITY_RESCUE:",
            "if B10_PUBLIC_SUPPLY_ORDER:",
        )):
            self.assertLess(source.index("if M1_WHEAT_TRADE:"),
                            source.index("if EOD_CAPACITY_RESCUE:"))
            self.assertLess(source.index("if EOD_CAPACITY_RESCUE:"),
                            source.index("if B10_PUBLIC_SUPPLY_ORDER:"))
'''
if src.count(old) != 1:
    raise SystemExit("C5 test anchor drift: expected exact old block once")
path.write_text(src.replace(old, new), encoding="utf-8")
