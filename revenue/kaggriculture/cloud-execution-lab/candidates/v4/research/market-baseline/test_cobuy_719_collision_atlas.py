#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cobuy_719_collision_atlas as atlas


def _route(actions, length=3):
    return list(actions) + [
        {"farmer": ["PASS"], "hands": [], "market": []}
    ] * (length - len(actions))


def _fake_apex_tape(buy_steps: dict[int, tuple[int, int, int]] | None = None) -> str:
    """Build the exact 2x719 tape shape expected by the production parser."""
    buy_steps = buy_steps or {}
    routes = []
    for _ in range(2):
        encoded = []
        for step in range(atlas.TURNS):
            if step in buy_steps:
                op, item, qty = buy_steps[step]
                encoded.append(f'"0 1 {op} {item} {qty}"')
            else:
                encoded.append('"0 0"')
        routes.append("{" + ",".join(encoded) + "}")
    return (
        f"constexpr int kTurns = {atlas.TURNS};\n"
        "constexpr int kRoutes = 2;\n"
        "const char* const kEncodedTapes[kRoutes][kTurns] = {\n"
        + ",\n".join(routes)
        + "\n};\n"
    )


def _apex_contract_text(segment_turns: int = 72):
    main = (
        "action['market'] = market[:10]\n"
        "market = [o for o in market if o[0] == 'SELL']"
    )
    guard = (
        "inline void budget_sales_first(Action& action)\n"
        "if (added > 0 && settings.sales_first) budget_sales_first(result);\n"
        "action.orders[action.n_orders++]"
    )
    policy = (
        f"constexpr int kSegmentTurns = {segment_turns};\n"
        "if (state.step == 0) selected_route = 0;\n"
        "if (state.step % kSegmentTurns != 0) return input;\n"
        "settings.interval_turns = kSegmentTurns;"
    )
    return main, guard, policy


class AtlasUnitTests(unittest.TestCase):
    def test_verified_source_module_executes_authenticated_snapshot_after_path_swap(self):
        good = b"VALUE = 1\n"
        bad = b"VALUE = 999\n"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "source.py"
            path.write_bytes(good)
            expected = atlas.git_blob(good)
            original_read_bytes = Path.read_bytes

            def read_then_swap(self):
                data = original_read_bytes(self)
                if self == path:
                    path.write_bytes(bad)
                return data

            with mock.patch.object(Path, "read_bytes", new=read_then_swap):
                module = atlas._load_verified_source_module(path, expected, "_swap_killer")

            self.assertEqual(module.VALUE, 1)
            self.assertEqual(path.read_bytes(), bad)

    def test_verified_source_module_rejects_wrong_initial_blob(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "source.py"
            path.write_text("VALUE = 2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                atlas._load_verified_source_module(path, atlas.git_blob(b"VALUE = 1\n"), "_bad")

    def test_arlene_intersection_fails_closed_after_sell_prefix(self):
        routes = {
            "a": _route([
                {"market": [["BUY_PRODUCT", "WHEAT", 13]]},
                {"market": [["SELL", "MILK", 1], ["BUY_PRODUCT", "WHEAT", 3]]},
                {"market": [["BUY_PRODUCT", "FERTILIZER", 2]]},
            ]),
            "b": _route([
                {"market": [["BUY_PRODUCT", "WHEAT", 13]]},
                {"market": [["BUY_PRODUCT", "WHEAT", 3]]},
                {"market": [["BUY_PRODUCT", "FERTILIZER", 2]]},
            ]),
        }
        module = SimpleNamespace(
            routes=lambda: routes,
            MAX_ORDERS=atlas.MAX_ORDERS,
            FINAL_EXECUTABLE_STEP=2,
        )
        self.assertEqual(
            atlas._invariant_pulses(atlas.arlene_route_pulses(module)),
            [
                {"step": 0, "row": 0, "item": "WHEAT", "qty": 13},
                {"step": 2, "row": 0, "item": "FERTILIZER", "qty": 2},
            ],
        )

    def test_apex_every_72_turn_guard_boundary_fails_closed_except_opening(self):
        buys = {
            0: (4, 0, 13),
            1: (4, 0, 1),
            72: (4, 0, 2),
            144: (4, 8, 3),
            216: (4, 0, 4),
            288: (4, 8, 5),
            360: (4, 0, 6),
            432: (4, 8, 7),
            504: (4, 0, 8),
            576: (4, 8, 9),
            648: (4, 0, 10),
            718: (4, 0, 11),
        }
        text = _fake_apex_tape(buys)
        per = atlas.apex_route_pulses(text, native_verified_opening=True, guard_interval=72)
        route0 = {(p["step"], p["item"]): p for p in per["0"]}
        self.assertTrue(route0[(0, "WHEAT")]["raw_index_stable"])
        self.assertTrue(route0[(1, "WHEAT")]["raw_index_stable"])
        for step, item in (
            (72, "WHEAT"),
            (144, "FERTILIZER"),
            (216, "WHEAT"),
            (288, "FERTILIZER"),
            (360, "WHEAT"),
            (432, "FERTILIZER"),
            (504, "WHEAT"),
            (576, "FERTILIZER"),
            (648, "WHEAT"),
            (718, "WHEAT"),
        ):
            self.assertFalse(route0[(step, item)]["raw_index_stable"])

        unverified = atlas.apex_route_pulses(text, native_verified_opening=False, guard_interval=72)
        opening = next(p for p in unverified["0"] if p["step"] == 0)
        self.assertFalse(opening["raw_index_stable"])

    def test_apex_pass_rows_compress_like_python_entrypoint(self):
        text = _fake_apex_tape()
        text = text.replace('"0 0"', '"0 2 0 0 1 4 0 2"', 1)
        per = atlas.apex_route_pulses(text, native_verified_opening=True)
        pulse = next(p for p in per["0"] if p["step"] == 0)
        self.assertEqual((pulse["row"], pulse["item"], pulse["qty"]), (0, "WHEAT", 2))

    def test_apex_executable_cap_applies_after_pass_compression(self):
        text = _fake_apex_tape()
        encoded = "0 11 " + " ".join(["0 0 1"] * 10 + ["4 0 7"])
        text = text.replace('"0 0"', f'"{encoded}"', 1)
        per = atlas.apex_route_pulses(text, native_verified_opening=True)
        pulse = next(p for p in per["0"] if p["step"] == 0)
        self.assertEqual((pulse["row"], pulse["item"], pulse["qty"]), (0, "WHEAT", 7))

    def test_repeated_same_item_buys_are_not_collapsed(self):
        own = [
            {"step": 7, "row": 0, "item": "WHEAT", "qty": 2},
            {"step": 7, "row": 3, "item": "WHEAT", "qty": 5},
        ]
        rival = [
            {"step": 7, "row": 0, "item": "WHEAT", "qty": 11},
            {"step": 7, "row": 2, "item": "WHEAT", "qty": 13},
        ]
        pairs = atlas._pair_collisions(own, rival)
        self.assertEqual(len(pairs), 4)
        self.assertEqual(
            {(p["own_row"], p["rival_row"]) for p in pairs},
            {(0, 0), (0, 2), (3, 0), (3, 2)},
        )

    def test_opening_only_does_not_mint_novel_positive_status(self):
        opening = {
            "step": 0,
            "item": "WHEAT",
            "own_row": 0,
            "own_qty": 13,
            "rival_row": 0,
            "rival_qty": 13,
            "same_raw_index": True,
            "row_delta_own_minus_rival": 0,
        }
        status, novel = atlas._classify_collisions([opening])
        self.assertEqual(status, "OPENING_ONLY_GUARDRAIL_NO_NEW_COLLISIONS")
        self.assertEqual(novel, [])
        later = {**opening, "step": 11, "own_qty": 2, "rival_qty": 5}
        status, novel = atlas._classify_collisions([opening, later])
        self.assertEqual(status, "NOVEL_AUTHORITATIVE_COLLISIONS_FOUND")
        self.assertEqual(novel, [later])

    def test_source_contract_binds_effective_72_turn_cadence(self):
        main, guard, policy = _apex_contract_text(72)
        self.assertEqual(
            atlas._assert_apex_source_contracts(main, guard, policy),
            72,
        )
        with self.assertRaises(ValueError):
            main144, guard144, policy144 = _apex_contract_text(144)
            atlas._assert_apex_source_contracts(main144, guard144, policy144)
        with self.assertRaises(ValueError):
            atlas._assert_apex_source_contracts("", "", "")


class ExactCheckoutTests(unittest.TestCase):
    def test_exact_checkout_atlas_is_deterministic_and_preserves_opening(self):
        root = Path(__file__).resolve().parents[7]
        paths = atlas.default_paths(root)
        if not all(path.exists() for path in paths.values()):
            self.skipTest("full source checkout not present")
        first = atlas.build_atlas(**paths)
        second = atlas.build_atlas(**paths)
        self.assertEqual(first, second)
        self.assertEqual(first["source_blobs"]["cobuy_opening_collision.py"], atlas.COBUY_HELPER_BLOB)
        self.assertEqual(first["scope"]["apex_effective_guard_interval"], 72)
        self.assertEqual(
            first["scope"]["guard_boundaries_excluded_without_native_receipt"],
            [72, 144, 216, 288, 360, 432, 504, 576, 648],
        )
        self.assertTrue(first["opening_native_receipt_verified"])
        self.assertTrue(first["controls"]["step0_wheat_collision_present"])
        self.assertTrue(first["controls"]["step0_wheat_same_row"])
        opening = [
            c for c in first["authoritative_collisions"]
            if atlas._is_known_opening_guardrail(c)
        ]
        self.assertEqual(len(opening), 1)
        self.assertEqual(
            (
                opening[0]["own_row"], opening[0]["own_qty"],
                opening[0]["rival_row"], opening[0]["rival_qty"],
            ),
            (0, 13, 0, 13),
        )
        self.assertEqual(
            first["counts"]["novel_authoritative_collisions"],
            len(first["novel_authoritative_collisions"]),
        )
        excluded = set(first["scope"]["guard_boundaries_excluded_without_native_receipt"])
        for collision in first["authoritative_collisions"]:
            self.assertNotIn(collision["step"], excluded)
            self.assertLess(collision["own_row"], atlas.MAX_ORDERS)
            self.assertLess(collision["rival_row"], atlas.MAX_ORDERS)
            self.assertIn(collision["item"], atlas.BUYABLE)
        json.dumps(first, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
