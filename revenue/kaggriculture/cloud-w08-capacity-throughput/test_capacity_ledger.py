# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("w08_capacity_ledger", HERE / "capacity_ledger.py")
LEDGER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(LEDGER)


def e(event_id, step, phase, op, *, sequence=0, actor=None, item=None,
      quantity=None, available=None, destination=None):
    event = {"id": event_id, "step": step, "phase": phase,
             "sequence": sequence, "op": op}
    if actor is not None: event["actor"] = actor
    if item is not None: event["item"] = item
    if quantity is not None: event["quantity"] = quantity
    if available is not None: event["available"] = available
    if destination is not None: event["destination"] = destination
    if op == "PLACE" and destination is None:
        event["destination"] = "shed"
    return event


class CapacityLedgerTests(unittest.TestCase):
    def test_intervening_sell_makes_second_worker_deposit_safe(self):
        baseline = [
            e("retained-place", 62, "unit", "PLACE", actor=0, item="WHEAT", quantity=1),
            e("guaranteed-sale", 62, "market", "SELL", item="WHEAT", quantity=1),
        ]
        extra = [
            e("new-harvest", 59, "unit", "HARVEST", actor=1, item="WHEAT", quantity=1),
            e("new-drop", 64, "unit", "DROP", actor=1),
        ]
        report = LEDGER.admit_additive_events(
            capacity=100, initial_shed={"WHEAT": 99},
            initial_carried={0: {"WHEAT": 1}, 1: {}},
            baseline_events=baseline, additive_events=extra,
            required_complete=["new-harvest", "new-drop"])
        self.assertTrue(report["admitted"], report)
        receipts = {row["id"]: row for row in report["candidate"]["receipts"]}
        self.assertEqual(receipts["retained-place"]["realized"], 1)
        self.assertEqual(receipts["guaranteed-sale"]["realized"], 1)
        self.assertEqual(receipts["new-drop"]["realized"], 1)
        self.assertEqual(report["candidate"]["summary"]["discarded_total"], 0)

    def test_without_sell_second_drop_is_real_loss_and_declines(self):
        baseline = [e("retained-place", 62, "unit", "PLACE", actor=0,
                      item="WHEAT", quantity=1)]
        extra = [
            e("new-harvest", 59, "unit", "HARVEST", actor=1, item="WHEAT", quantity=1),
            e("new-drop", 64, "unit", "DROP", actor=1),
        ]
        report = LEDGER.admit_additive_events(
            capacity=100, initial_shed={"WHEAT": 99},
            initial_carried={0: {"WHEAT": 1}, 1: {}},
            baseline_events=baseline, additive_events=extra,
            required_complete=["new-drop"])
        self.assertFalse(report["admitted"])
        self.assertEqual(report["reason"], "required-event-incomplete")
        self.assertEqual(report["required_incomplete"][0]["discarded"], 1)

    def test_market_buy_consumes_freed_slot_before_drop(self):
        baseline = [
            e("sale", 62, "market", "SELL", item="WHEAT", quantity=1, sequence=0),
            e("buy", 62, "market", "BUY_PRODUCT", item="MILK", quantity=1, sequence=1),
        ]
        extra = [
            e("harvest", 59, "unit", "HARVEST", actor=1, item="WHEAT", quantity=1),
            e("drop", 64, "unit", "DROP", actor=1),
        ]
        report = LEDGER.admit_additive_events(
            capacity=100, initial_shed={"WHEAT": 100}, initial_carried={1: {}},
            baseline_events=baseline, additive_events=extra, required_complete=["drop"])
        self.assertFalse(report["admitted"])
        self.assertEqual(report["required_incomplete"][0]["discarded"], 1)
        self.assertEqual(report["candidate"]["final"]["shed"], {"WHEAT": 99, "MILK": 1})

    def test_candidate_cannot_crowd_out_retained_place(self):
        baseline = [e("retained-place", 64, "unit", "PLACE", actor=0,
                      item="MILK", quantity=1, sequence=1)]
        extra = [
            e("harvest", 59, "unit", "HARVEST", actor=1, item="WHEAT", quantity=1),
            e("early-drop", 64, "unit", "DROP", actor=1, sequence=0),
        ]
        report = LEDGER.admit_additive_events(
            capacity=100, initial_shed={"WHEAT": 99},
            initial_carried={0: {"MILK": 1}, 1: {}},
            baseline_events=baseline, additive_events=extra,
            required_complete=["early-drop"])
        self.assertFalse(report["admitted"])
        self.assertEqual(report["reason"], "baseline-regression")
        self.assertEqual(report["baseline_regressions"], [
            {"id": "retained-place", "field": "realized", "baseline": 1, "candidate": 0}
        ])

    def test_place_keeps_unplaced_remainder_but_drop_discards(self):
        common = dict(capacity=2, initial_shed={"WHEAT": 2},
                      initial_carried={0: {"MILK": 2}})
        placed = LEDGER.simulate_capacity(
            **common, events=[e("place", 1, "unit", "PLACE", actor=0,
                                item="MILK", quantity=2)])
        dropped = LEDGER.simulate_capacity(
            **common, events=[e("drop", 1, "unit", "DROP", actor=0)])
        self.assertEqual(placed["final"]["carried"]["0"], {"MILK": 2})
        self.assertEqual(placed["summary"]["discarded_total"], 0)
        self.assertEqual(dropped["final"]["carried"]["0"], {})
        self.assertEqual(dropped["summary"]["discarded"], {"MILK": 2})

    def test_market_occurs_after_all_unit_actions_at_same_step(self):
        events = [
            e("sale", 10, "market", "SELL", item="WHEAT", quantity=1),
            e("drop", 10, "unit", "DROP", actor=0),
        ]
        result = LEDGER.simulate_capacity(
            capacity=1, initial_shed={"WHEAT": 1},
            initial_carried={0: {"MILK": 1}}, events=events)
        receipts = {row["id"]: row for row in result["receipts"]}
        self.assertEqual(receipts["drop"]["discarded"], 1)
        self.assertEqual(receipts["sale"]["realized"], 1)
        self.assertEqual(result["final"]["shed"], {})

    def test_eod_drop_can_use_room_created_by_market(self):
        result = LEDGER.simulate_capacity(
            capacity=3, initial_shed={"WHEAT": 3}, initial_carried={0: {"MILK": 2}},
            events=[
                e("sale", 23, "market", "SELL", item="WHEAT", quantity=2),
                e("eod", 23, "eod", "EOD_DROP"),
            ])
        self.assertEqual(result["final"]["shed"], {"WHEAT": 1, "MILK": 2})
        self.assertEqual(result["summary"]["discarded_total"], 0)

    def test_two_worker_eod_order_and_discard_are_deterministic(self):
        result = LEDGER.simulate_capacity(
            capacity=3, initial_shed={"WHEAT": 1},
            initial_carried={0: {"MILK": 2}, 1: {"WOOL": 2}},
            events=[e("eod", 23, "eod", "EOD_DROP")])
        self.assertEqual(result["final"]["shed"], {"WHEAT": 1, "MILK": 2})
        self.assertEqual(result["summary"]["discarded"], {"WOOL": 2})
        self.assertEqual(result["conservation_errors"], {})

    def test_available_bound_clips_buy_before_capacity(self):
        result = LEDGER.simulate_capacity(
            capacity=5, initial_shed={}, initial_carried={},
            events=[e("buy", 1, "market", "BUY_PRODUCT", item="MILK",
                      quantity=4, available=2)])
        receipt = result["receipts"][0]
        self.assertEqual(receipt["realized"], 2)
        self.assertEqual(result["final"]["shed"], {"MILK": 2})

    def test_inputs_are_not_mutated(self):
        shed = {"WHEAT": 1}; carried = {0: {"MILK": 1}}
        events = [e("drop", 1, "unit", "DROP", actor=0)]
        before = copy.deepcopy((shed, carried, events))
        LEDGER.simulate_capacity(capacity=3, initial_shed=shed,
                                 initial_carried=carried, events=events)
        self.assertEqual((shed, carried, events), before)

    def test_admission_ids_and_event_sequences_fail_closed(self):
        baseline = [e("base", 0, "unit", "PASS")]
        additive = [e("new", 1, "unit", "PASS")]
        with self.assertRaisesRegex(ValueError, "must identify additive events"):
            LEDGER.admit_additive_events(
                capacity=1, initial_shed={}, initial_carried={},
                baseline_events=baseline, additive_events=additive,
                required_complete=["base"],
            )
        with self.assertRaisesRegex(ValueError, "must identify additive events"):
            LEDGER.admit_additive_events(
                capacity=1, initial_shed={}, initial_carried={},
                baseline_events=baseline, additive_events=additive,
                required_complete=["missing"],
            )
        with self.assertRaisesRegex(ValueError, "duplicate required_complete"):
            LEDGER.admit_additive_events(
                capacity=1, initial_shed={}, initial_carried={},
                baseline_events=baseline, additive_events=additive,
                required_complete=["new", "new"],
            )
        with self.assertRaisesRegex(ValueError, "sequence of additive event IDs"):
            LEDGER.admit_additive_events(
                capacity=1, initial_shed={}, initial_carried={},
                baseline_events=baseline, additive_events=additive,
                required_complete="new",
            )
        with self.assertRaisesRegex(ValueError, "sequence of mappings"):
            LEDGER.admit_additive_events(
                capacity=1, initial_shed={}, initial_carried={},
                baseline_events=baseline, additive_events={"id": "new"},
                required_complete=[],
            )

    def test_duplicate_ids_and_bool_quantities_fail_closed(self):
        duplicate = [e("x", 1, "unit", "PASS"), e("x", 2, "unit", "PASS")]
        with self.assertRaisesRegex(ValueError, "duplicate event id"):
            LEDGER.simulate_capacity(capacity=1, initial_shed={}, initial_carried={},
                                     events=duplicate)
        bad = [e("x", 1, "market", "SELL", item="WHEAT", quantity=True)]
        with self.assertRaisesRegex(ValueError, "integer"):
            LEDGER.simulate_capacity(capacity=1, initial_shed={}, initial_carried={},
                                     events=bad)

    def test_duplicate_ordering_keys_are_rejected(self):
        """Ambiguous same-phase sequence must not silently prefer baseline order."""
        baseline = [e("pickup", 1, "unit", "PICKUP", actor=1, item="WHEAT",
                      quantity=1, sequence=0)]
        additive = [e("place", 1, "unit", "PLACE", actor=0, item="MILK",
                      quantity=1, sequence=0)]
        with self.assertRaisesRegex(ValueError, "duplicate ordering key"):
            LEDGER.admit_additive_events(
                capacity=1, initial_shed={"WHEAT": 1},
                initial_carried={0: {"MILK": 1}, 1: {}},
                baseline_events=baseline, additive_events=additive,
                required_complete=["place"])
        additive2 = [e("place", 1, "unit", "PLACE", actor=0, item="MILK",
                       quantity=1, sequence=1)]
        report = LEDGER.admit_additive_events(
            capacity=1, initial_shed={"WHEAT": 1},
            initial_carried={0: {"MILK": 1}, 1: {}},
            baseline_events=baseline, additive_events=additive2,
            required_complete=["place"])
        self.assertTrue(report["admitted"], report)
        baseline_rev = [e("pickup", 1, "unit", "PICKUP", actor=1, item="WHEAT",
                          quantity=1, sequence=1)]
        additive_rev = [e("place", 1, "unit", "PLACE", actor=0, item="MILK",
                          quantity=1, sequence=0)]
        report_rev = LEDGER.admit_additive_events(
            capacity=1, initial_shed={"WHEAT": 1},
            initial_carried={0: {"MILK": 1}, 1: {}},
            baseline_events=baseline_rev, additive_events=additive_rev,
            required_complete=["place"])
        self.assertFalse(report_rev["admitted"])
        self.assertEqual(report_rev["reason"], "required-event-incomplete")

    def test_place_requires_destination_shed_and_rejects_animal_board_path(self):
        """PLACE without destination=shed is rejected; no fabricated animal stock."""
        with self.assertRaisesRegex(ValueError, "destination='shed'"):
            LEDGER.simulate_capacity(
                capacity=5, initial_shed={}, initial_carried={0: {"COW": 1}},
                events=[{"id": "place-cow", "step": 1, "phase": "unit", "op": "PLACE",
                         "actor": 0, "item": "COW", "quantity": 1}])
        with self.assertRaisesRegex(ValueError, "destination='shed'"):
            LEDGER.simulate_capacity(
                capacity=5, initial_shed={}, initial_carried={0: {"COW": 1}},
                events=[{"id": "place-cow", "step": 1, "phase": "unit", "op": "PLACE",
                         "actor": 0, "item": "COW", "quantity": 1,
                         "destination": "barn"}])
        result = LEDGER.simulate_capacity(
            capacity=5, initial_shed={}, initial_carried={0: {"MILK": 1}},
            events=[
                e("place-milk", 1, "unit", "PLACE", actor=0, item="MILK", quantity=1),
                e("pickup-milk", 2, "unit", "PICKUP", actor=0, item="MILK", quantity=1),
            ])
        self.assertEqual([r["realized"] for r in result["receipts"]], [1, 1])
        with self.assertRaisesRegex(ValueError, "destination='shed'"):
            LEDGER.simulate_capacity(
                capacity=5, initial_shed={}, initial_carried={0: {"COW": 1}},
                events=[
                    {"id": "place-cow", "step": 1, "phase": "unit", "op": "PLACE",
                     "actor": 0, "item": "COW", "quantity": 1},
                    e("pickup-cow", 2, "unit", "PICKUP", actor=0, item="COW", quantity=1),
                ])

    def test_witness_runner_survives_place_destination_barrier(self):
        """run_witnesses.py must bind destination=shed; the merge left it crashing."""
        spec = importlib.util.spec_from_file_location(
            "w08_run_witnesses_repair", HERE / "run_witnesses.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        first = module.build_witnesses()
        second = module.build_witnesses()
        self.assertEqual(
            json.dumps(first, sort_keys=True, indent=2),
            json.dumps(second, sort_keys=True, indent=2),
        )
        expected = {
            "intervening_sale_admits_later_deposit": True,
            "missing_sale_rejects_real_discard": False,
            "buy_refills_sale_room_and_rejects": False,
            "candidate_cannot_reduce_retained_place": False,
            "eod_drop_uses_post_market_room": True,
        }
        self.assertEqual(first["observed_admission"], expected)
        place = module.event(
            "retained-place", 62, "unit", "PLACE", actor=0,
            item="WHEAT", quantity=1)
        self.assertEqual(place["destination"], "shed")
        with self.assertRaisesRegex(ValueError, "destination='shed'"):
            LEDGER.simulate_capacity(
                capacity=100, initial_shed={"WHEAT": 99},
                initial_carried={0: {"WHEAT": 1}},
                events=[{
                    "id": "legacy-witness-place", "step": 62, "phase": "unit",
                    "op": "PLACE", "actor": 0, "item": "WHEAT", "quantity": 1,
                }])

    def test_results_json_pins_current_source_identities(self):
        """RESULTS.json must describe the files that actually landed."""
        results = json.loads((HERE / "RESULTS.json").read_text(encoding="utf-8"))
        repo = HERE.parents[2]
        mismatches = []
        for rec_path, rec in results["files"].items():
            payload = (repo / rec_path).read_bytes()
            sha256 = hashlib.sha256(payload).hexdigest()
            git_blob = hashlib.sha1(
                f"blob {len(payload)}\0".encode("ascii") + payload,
                usedforsecurity=False,
            ).hexdigest()
            actual = {
                "bytes": len(payload),
                "sha256": sha256,
                "git_blob": git_blob,
            }
            claimed = {
                "bytes": rec.get("bytes"),
                "sha256": rec.get("sha256"),
                "git_blob": rec.get("git_blob"),
            }
            if actual != claimed:
                mismatches.append({"path": rec_path, "claimed": claimed, "actual": actual})
        self.assertEqual(mismatches, [])

    def test_exhaustive_post_market_room_family_matches_closed_form(self):
        cases = 0
        for cap in range(1, 7):
            for initial in range(cap + 1):
                for placed in range(4):
                    for sold in range(4):
                        for bought in range(4):
                            for produced in range(1, 4):
                                baseline = [
                                    e("place", 1, "unit", "PLACE", actor=0,
                                      item="WHEAT", quantity=placed),
                                    e("sell", 1, "market", "SELL", item="WHEAT",
                                      quantity=sold, sequence=0),
                                    e("buy", 1, "market", "BUY_PRODUCT", item="MILK",
                                      quantity=bought, sequence=1),
                                ]
                                extra = [
                                    e("harvest", 0, "unit", "HARVEST", actor=1,
                                      item="WOOL", quantity=produced),
                                    e("drop", 2, "unit", "DROP", actor=1),
                                ]
                                base = LEDGER.simulate_capacity(
                                    capacity=cap, initial_shed={"WHEAT": initial},
                                    initial_carried={0: {"WHEAT": placed}, 1: {}},
                                    events=baseline)
                                expected = base["final"]["shed_total"] + produced <= cap
                                report = LEDGER.admit_additive_events(
                                    capacity=cap, initial_shed={"WHEAT": initial},
                                    initial_carried={0: {"WHEAT": placed}, 1: {}},
                                    baseline_events=baseline, additive_events=extra,
                                    required_complete=["harvest", "drop"])
                                self.assertEqual(report["admitted"], expected,
                                    (cap, initial, placed, sold, bought, produced, report))
                                cases += 1
        self.assertEqual(cases, 5184)

    def test_exhaustive_early_drop_never_steals_retained_place_capacity(self):
        cases = 0
        for cap in range(1, 9):
            for initial in range(cap + 1):
                for retained in range(5):
                    for produced in range(1, 5):
                        baseline = [e("retained", 1, "unit", "PLACE", actor=0,
                                      item="MILK", quantity=retained, sequence=1)]
                        extra = [
                            e("harvest", 0, "unit", "HARVEST", actor=1,
                              item="WHEAT", quantity=produced),
                            e("drop", 1, "unit", "DROP", actor=1, sequence=0),
                        ]
                        room = cap - initial
                        baseline_place = min(retained, room)
                        expected = (produced <= room and
                                    min(retained, room - produced) == baseline_place)
                        report = LEDGER.admit_additive_events(
                            capacity=cap, initial_shed={"EGG": initial},
                            initial_carried={0: {"MILK": retained}, 1: {}},
                            baseline_events=baseline, additive_events=extra,
                            required_complete=["drop"])
                        self.assertEqual(report["admitted"], expected,
                            (cap, initial, retained, produced, report))
                        cases += 1
        self.assertEqual(cases, 880)


if __name__ == "__main__":
    unittest.main(verbosity=2)
