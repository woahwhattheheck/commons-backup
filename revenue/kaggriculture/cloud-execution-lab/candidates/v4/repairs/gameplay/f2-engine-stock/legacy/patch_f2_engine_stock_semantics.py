#!/usr/bin/env python3
"""Remove F2's non-engine public-stock availability veto.

The official Kaggriculture BUY_PRODUCT commit path checks cash and shed capacity,
then decrements public market inventory without a nonnegative-stock availability
check.  F2 may still require observed inventory to have the engine's literal int
shape, but it must not treat public WHEAT < requested quantity as unexecutable.

Ancestry-neutral donor: exact anchors, two F2 paths only, no shared plumbing.
"""
from __future__ import annotations

import pathlib
import py_compile
import sys

HELPER = pathlib.Path(
    "revenue/kaggriculture/cloud-execution-lab/candidates/v3/overlay/r04_feed_prebuy.py"
)
TEST = pathlib.Path(
    "revenue/kaggriculture/cloud-execution-lab/candidates/v3/overlay/checks/test_v4_feed_prebuy.py"
)


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


def apply(root: pathlib.Path) -> None:
    helper_path = root / HELPER
    test_path = root / TEST
    helper = helper_path.read_text(encoding="utf-8")
    test = test_path.read_text(encoding="utf-8")

    helper = once(
        helper,
        '    wheat_stock = inventory.get("WHEAT")\n'
        '    if type(wheat_stock) is not int or wheat_stock < quantity:\n'
        '        return None\n',
        '    wheat_stock = inventory.get("WHEAT")\n'
        '    # Official BUY_PRODUCT permits public inventory to cross below zero.\n'
        '    # Keep only the literal engine-state shape proof; scarcity is not an\n'
        '    # executability veto.\n'
        '    if type(wheat_stock) is not int:\n'
        '        return None\n',
        "F2 public-stock executability guard",
    )

    old_test = '''    def test_public_wheat_stock_must_cover_exact_prebuy_quantity(self):
        bad_inventories = (
            {"WHEAT": 0},
            {"WHEAT": 1},
            {"WHEAT": True},
            {"WHEAT": 2.0},
            {"WHEAT": -1},
            {"WHEAT": "2"},
            {"WHEAT": None},
            {},
        )
        for inventory in bad_inventories:
            obs = _observation(wheat=0)
            obs["market"]["inventory"] = inventory
            parent = _action()
            with self.subTest(inventory=inventory):
                self.assertIs(_apply(obs, parent), parent)

        obs = _observation(wheat=0)
        del obs["market"]["inventory"]
        parent = _action()
        self.assertIs(_apply(obs, parent), parent)

        obs = _observation(wheat=0)
        obs["market"]["inventory"] = {"WHEAT": 2}
        out = _apply(obs, _action())
        self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])
'''
    new_test = '''    def test_public_wheat_stock_shape_not_availability_controls_execution(self):
        # Official BUY_PRODUCT can legally drive public inventory below zero.
        # Scarce literal-int inventory therefore cannot veto an otherwise proven
        # q=2 F2 order; malformed/non-engine shapes still fail closed.
        for wheat_stock in (2, 1, 0, -1):
            obs = _observation(wheat=0)
            obs["market"]["inventory"] = {"WHEAT": wheat_stock}
            with self.subTest(wheat_stock=wheat_stock):
                out = _apply(obs, _action())
                self.assertEqual(out["market"], [["BUY_PRODUCT", "WHEAT", 2]])

        for bad_stock in (True, 2.0, "2", None):
            obs = _observation(wheat=0)
            obs["market"]["inventory"] = {"WHEAT": bad_stock}
            parent = _action()
            with self.subTest(bad_stock=bad_stock):
                self.assertIs(_apply(obs, parent), parent)

        for inventory in ({}, None, []):
            obs = _observation(wheat=0)
            if inventory is None:
                del obs["market"]["inventory"]
            else:
                obs["market"]["inventory"] = inventory
            parent = _action()
            with self.subTest(inventory=inventory):
                self.assertIs(_apply(obs, parent), parent)
'''
    test = once(test, old_test, new_test, "F2 public-stock regression")

    if "wheat_stock < quantity" in helper:
        raise SystemExit("stale non-engine stock availability veto survived")
    if 'if type(wheat_stock) is not int:' not in helper:
        raise SystemExit("literal public-stock shape guard missing")
    if "for wheat_stock in (2, 1, 0, -1):" not in test:
        raise SystemExit("engine-faithful scarce-stock regression missing")

    helper_path.write_text(helper, encoding="utf-8", newline="\n")
    test_path.write_text(test, encoding="utf-8", newline="\n")
    py_compile.compile(str(helper_path), doraise=True)
    py_compile.compile(str(test_path), doraise=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_f2_engine_stock_semantics.py ROOT")
    apply(pathlib.Path(sys.argv[1]))
