import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("laborflow", HERE / "compose_laborflow_multi_detour.py")
laborflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(laborflow)


def synthetic_postimage():
    # Minimal source-shaped text containing the six exact current anchors.  It is
    # deliberately not a runtime substitute; the exact production transformer is
    # additionally pinned by the sibling two-seat transform's Git input/output blobs.
    return """from collections import Counter\nfrom typing import Any, Mapping\n\ndef _productive_detour(\n    mechanics: Any, observation: Mapping[str, Any], post_farm: Mapping[str, Any],\n    post_private: Mapping[str, Any], route, events, final_positions, worker, wage,\n    step: int, end: int, board: int, cap: int, limit: int, reserved: set[tuple[int, int]],\n) -> dict | None:\n    stock = 0\n    inventory = {}\n    item = 'WHEAT'\n    quantity = 1\n            if stock + quantity > cap or item not in inventory:\n                continue\n                drop_step = step + 1 + drop_offset\n                conflict = False\n                value = sum(mechanics.market_price(item, inventory[item] + q, params)\n                            for q in range(quantity))\n\ndef proposal():\n    protected = 0; reserved: set[tuple[int, int]] = set(); detours = []\n    first_removed = 1 + existing + len(hires) - best\n    cost_start = len(hires) - best\n    for offset in range(best):\n        worker = first_removed + offset\n        witness = _productive_detour(mechanics, observation, farm, private, route, events, positions,\n                                      worker, costs[cost_start + offset], step, end,\n                                      board, cap, limit, reserved)\n        if witness is None:\n            break\n        detours.append(witness); reserved.add(tuple(witness[\"target\"])); protected += 1\n        break\n    report.update(\n        productive_detours=detours,\n        useful_worker_actions=sum(w[\"useful_worker_actions\"] for w in detours),\n    )\n"""


class TestLaborflowRewrite(unittest.TestCase):
    def test_all_six_anchors_apply_once(self):
        out = laborflow.rewrite_postimage_text(synthetic_postimage())
        self.assertIn("reserved_capacity + quantity", out)
        self.assertIn("reserved_market_units.get(item, 0)", out)
        self.assertIn("drop_step in reserved_drop_steps", out)
        self.assertIn("productive_hires=protected", out)
        self.assertNotIn("protected += 1\n        break", out)

    def test_contiguous_prefix_still_fail_closes_on_first_missing_job(self):
        out = laborflow.rewrite_postimage_text(synthetic_postimage())
        loop = out[out.index("    protected = 0;"):out.index("    report.update(")]
        self.assertIn("if witness is None:\n            break", loop)
        self.assertEqual(loop.count("break"), 1)

    def test_reservations_update_only_after_certificate(self):
        out = laborflow.rewrite_postimage_text(synthetic_postimage())
        loop = out[out.index("    protected = 0;"):out.index("    report.update(")]
        witness_guard = loop.index("if witness is None")
        reserve_capacity = loop.index("reserved_capacity +=")
        reserve_market = loop.index("reserved_market_units[")
        reserve_drop = loop.index("reserved_drop_steps.add")
        self.assertLess(witness_guard, reserve_capacity)
        self.assertLess(reserve_capacity, reserve_market)
        self.assertLess(reserve_market, reserve_drop)

    def test_capacity_and_quote_are_cumulative(self):
        out = laborflow.rewrite_postimage_text(synthetic_postimage())
        self.assertIn("stock + reserved_capacity + quantity > cap", out)
        self.assertIn("base_inventory = inventory[item] + int(reserved_market_units.get(item, 0))", out)
        self.assertIn("mechanics.market_price(item, base_inventory + q, params)", out)

    def test_deposit_tick_collision_is_rejected(self):
        out = laborflow.rewrite_postimage_text(synthetic_postimage())
        self.assertIn("if drop_step in reserved_drop_steps:\n                    continue", out)

    def test_anchor_drift_fails_closed(self):
        broken = synthetic_postimage().replace("stock + quantity > cap", "stock + 2 * quantity > cap")
        with self.assertRaisesRegex(RuntimeError, "cumulative capacity reservation"):
            laborflow.rewrite_postimage_text(broken)

    def test_wrong_input_blob_rejected_before_rewrite(self):
        with self.assertRaisesRegex(RuntimeError, "wrong input blob"):
            laborflow.transform(b"not-current-redundant-hire")


if __name__ == "__main__":
    unittest.main()
