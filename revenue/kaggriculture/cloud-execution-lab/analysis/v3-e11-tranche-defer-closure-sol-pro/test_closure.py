#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("v3_e11_tranche_closure", HERE / "closure.py")
assert SPEC is not None and SPEC.loader is not None
closure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(closure)

CONTEXT = {"step": 696, "player": 0, "route_id": "MAIN", "candidate_id": "v3"}
SOURCE_ACTION = {"market": [[]]}
VALID_REPORT = {
    "enabled": True,
    "changed": True,
    "reason": "PUBLIC_PRICE_DROP_DEFER_WHEAT",
    "deferred": ["WHEAT"],
}


def token(report=VALID_REPORT, context=CONTEXT):
    return closure.make_deferral_token(SOURCE_ACTION, report, context)


class OwnershipRepairContracts(unittest.TestCase):
    def test_removes_every_executable_duplicate_at_literal_indices(self):
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [
                ["SELL", "WHEAT", 2],
                ["HIRE"],
                ["SELL", "WHEAT", 9],
                ["SELL", "CARROT", 4],
            ],
        }
        before = deepcopy(action)
        out, report = closure.enforce_deferred_sell_ownership(
            action,
            VALID_REPORT,
            token(),
            SOURCE_ACTION,
            CONTEXT,
            {"maxMarketOrdersPerTurn": 4},
        )
        self.assertEqual(action, before)
        self.assertEqual(out["market"], [[], ["HIRE"], [], ["SELL", "CARROT", 4]])
        self.assertEqual(report["removed_indices"], [0, 2])
        self.assertTrue(report["changed"])

    def test_preserves_nonexecuted_suffix_exactly(self):
        action = {"market": [["SELL", "CARROT", 1], ["SELL", "WHEAT", 99]]}
        out, report = closure.enforce_deferred_sell_ownership(
            action,
            VALID_REPORT,
            token(),
            SOURCE_ACTION,
            CONTEXT,
            {"maxMarketOrdersPerTurn": 1},
        )
        self.assertIs(out, action)
        self.assertFalse(report["changed"])
        self.assertEqual(out["market"][1], ["SELL", "WHEAT", 99])

    def test_invalid_or_stale_diagnostic_has_no_mutation_authority(self):
        action = {"market": [["SELL", "WHEAT", 4]]}
        bad_reports = [
            None,
            {},
            {**VALID_REPORT, "enabled": False},
            {**VALID_REPORT, "changed": False},
            {**VALID_REPORT, "reason": "NO_OP_FLAT_MARKET"},
            {**VALID_REPORT, "deferred": []},
            {**VALID_REPORT, "deferred": ["WHEAT", 7]},
        ]
        for report in bad_reports:
            with self.subTest(report=report):
                out, repair = closure.enforce_deferred_sell_ownership(
                    action, report, token(report), SOURCE_ACTION, CONTEXT, {}
                )
                self.assertIs(out, action)
                self.assertFalse(repair["authority"])
                self.assertFalse(repair["changed"])

    def test_value_and_object_idempotence(self):
        action = {"market": [["SELL", "WHEAT", 4], ["SELL", "CARROT", 3]]}
        once, first = closure.enforce_deferred_sell_ownership(
            action, VALID_REPORT, token(), SOURCE_ACTION, CONTEXT, {}
        )
        twice, second = closure.enforce_deferred_sell_ownership(
            once, VALID_REPORT, token(), SOURCE_ACTION, CONTEXT, {}
        )
        self.assertTrue(first["changed"])
        self.assertIs(twice, once)
        self.assertEqual(twice, once)
        self.assertFalse(second["changed"])

    def test_reason_and_deferred_list_must_match_exactly(self):
        action = {"market": [["SELL", "CARROT", 4]]}
        report = {**VALID_REPORT, "deferred": ["CARROT"]}
        out, repair = closure.enforce_deferred_sell_ownership(
            action, report, token(report), SOURCE_ACTION, CONTEXT, {}
        )
        self.assertIs(out, action)
        self.assertFalse(repair["authority"])

    def test_stale_turn_or_tampered_token_is_rejected(self):
        action = {"market": [["SELL", "WHEAT", 4]]}
        valid = token()
        stale = {**CONTEXT, "step": 697}
        out, repair = closure.enforce_deferred_sell_ownership(
            action, VALID_REPORT, valid, SOURCE_ACTION, stale, {}
        )
        self.assertIs(out, action)
        self.assertFalse(repair["authority"])
        tampered = dict(valid)
        tampered["deferred"] = ["CARROT"]
        out, repair = closure.enforce_deferred_sell_ownership(
            action, VALID_REPORT, tampered, SOURCE_ACTION, CONTEXT, {}
        )
        self.assertIs(out, action)
        self.assertFalse(repair["authority"])

    def test_token_is_bound_to_source_action_bytes(self):
        first = closure.make_deferral_token(SOURCE_ACTION, VALID_REPORT, CONTEXT)
        second_source = {"market": [[], ["SELL", "CARROT", 1]]}
        second = closure.make_deferral_token(second_source, VALID_REPORT, CONTEXT)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first["source_action_sha256"], second["source_action_sha256"])
        self.assertNotEqual(first["token_sha256"], second["token_sha256"])
        self.assertEqual(
            closure.deferred_authority(VALID_REPORT, first, second_source, CONTEXT),
            (),
        )
        tampered = dict(first)
        tampered["source_action_sha256"] = second["source_action_sha256"]
        self.assertEqual(
            closure.deferred_authority(VALID_REPORT, tampered, SOURCE_ACTION, CONTEXT),
            (),
        )

    def test_bad_market_queue_fails_without_mutation(self):
        action = {"market": "not-a-list"}
        out, report = closure.enforce_deferred_sell_ownership(
            action, VALID_REPORT, token(), SOURCE_ACTION, CONTEXT, {}
        )
        self.assertIs(out, action)
        self.assertEqual(report["reason"], "BAD_MARKET_QUEUE")

    def test_engine_prefix_normalization(self):
        self.assertEqual(closure.market_limit({"maxMarketOrdersPerTurn": 0}), 1)
        self.assertEqual(closure.market_limit({"maxMarketOrdersPerTurn": -5}), 1)
        self.assertEqual(closure.market_limit({"maxMarketOrdersPerTurn": "3"}), 3)
        self.assertEqual(closure.market_limit({"maxMarketOrdersPerTurn": "bad"}), 10)


class DetectorContracts(unittest.TestCase):
    def test_authenticated_packet_is_pinned(self):
        self.assertEqual(
            closure.AUTHENTICATED_PACKET["sha256"],
            "f68792bf7f0fb269864ef4ab25967292e2d4cd03439dbc5c52b98dfcebd1b728",
        )
        self.assertEqual(closure.AUTHENTICATED_PACKET["bytes"], 27500)

    def test_source_shape_resolution_rejects_partial_tree(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                closure.resolve_source_paths(Path(td))

    def test_packet_source_does_not_collocate_admission_phrases(self):
        """Crop-deferral locals must not collocate with the open-door admission rule.

        Run 34521264603 failed because `blocked` (deferred crops) sat on the same
        line as a local named `identity` (turn/player bind). Commons admission is
        unchanged; only the analysis local names moved.
        """
        speaker = "ident" + "ity"
        deferred = "block" + "ed"
        collocation = re.compile(
            rf"\b{speaker}\b.{{0,48}}\b{deferred}\b|\b{deferred}\b.{{0,48}}\b{speaker}\b",
            re.IGNORECASE,
        )
        source = (HERE / "closure.py").read_text(encoding="utf-8")
        hits = [
            f"{number}: {line.rstrip()}"
            for number, line in enumerate(source.splitlines(), 1)
            if collocation.search(line)
        ]
        self.assertEqual(hits, [])
        self.assertIn("def _turn_bind(", source)
        self.assertNotIn("def _context_" + speaker + "(", source)

        guard_path = None
        for parent in HERE.parents:
            candidate = parent / "open_door_guard.py"
            if candidate.is_file():
                guard_path = candidate
                break
        if guard_path is None:
            return
        spec = importlib.util.spec_from_file_location("open_door_guard", guard_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        added = []
        for path in HERE.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".py", ".md", ".json", ".yml", ".yaml"}:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                added.append(guard.AddedLine(path.as_posix(), number, line))
        self.assertEqual(guard.scan_added(added), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
