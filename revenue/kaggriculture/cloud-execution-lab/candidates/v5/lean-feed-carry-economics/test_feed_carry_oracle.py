from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import feed_carry_oracle as o


def digest(char: str) -> str:
    return char * 64


def snapshot(*, on_hand=None, cash=100, obligations=None, market=None):
    return {
        "feed_on_hand": on_hand or {"Corn": 0, "Pasture": 0, "Straw": 0},
        "cash": cash,
        "purchase_order": ["Straw", "Pasture", "Corn"],
        "current_authored": copy.deepcopy(o.CURRENT_POLICY),
        "market": market
        or {
            "Corn": {"available": 20, "action_cap": 20, "unit_price": 3},
            "Pasture": {"available": 20, "action_cap": 20, "unit_price": 2},
            "Straw": {"available": 20, "action_cap": 20, "unit_price": 1},
        },
        "obligations": obligations
        if obligations is not None
        else [
            {
                "feed": "Straw",
                "units": 1,
                "boundary_step": 20,
                "source": "animal:sheep:1",
                "source_proven": True,
                "executable": True,
            },
            {
                "feed": "Pasture",
                "units": 2,
                "boundary_step": 20,
                "source": "animal:cow:1",
                "source_proven": True,
                "executable": True,
            },
            {
                "feed": "Corn",
                "units": 1,
                "boundary_step": 20,
                "source": "animal:pig:1",
                "source_proven": True,
                "executable": True,
            },
            {
                "feed": "Corn",
                "units": 9,
                "boundary_step": 40,
                "source": "future:ignored",
                "source_proven": True,
                "executable": True,
            },
        ],
    }


def window(
    arm: str,
    *,
    cash_use=True,
    satisfied=True,
    productivity=0,
    survival=0,
    snap=None,
):
    snap = snap or snapshot()
    oracle = o.compute_reserve_oracle(snap)
    active = arm == o.ARM_MIN and oracle["reachable_excess"]
    decision = {
        "authoritative": True,
        "source": "instrumented_runtime",
        "step": 10,
        "oracle_sha256": oracle["oracle_sha256"],
        "executable_purchase": oracle["arms"][arm]["executable"],
        "candidate_active": active,
    }
    uses = []
    if active:
        decision.update(
            {
                "parent_executable_purchase": oracle["arms"][o.ARM_CURRENT][
                    "executable"
                ],
                "units_removed": oracle["units_removed"],
                "cash_liberated": oracle["cash_tied_in_discretionary_feed"],
                "liberation_id": "lib-1",
            }
        )
        if cash_use:
            uses = [
                {
                    "authoritative": True,
                    "source": "runtime_cash_ledger",
                    "step": 12,
                    "liberation_id": "lib-1",
                    "category": "seed",
                    "amount": min(
                        1, oracle["cash_tied_in_discretionary_feed"]
                    ),
                }
            ]
    return {
        "window_id": "w1",
        "snapshot": snap,
        "decision": decision,
        "cash_uses": uses,
        "obligation_check": {
            "authoritative": True,
            "source": "instrumented_runtime",
            "horizon_step": oracle["next_boundary_step"],
            "satisfied": satisfied,
            "productivity_loss": productivity,
            "survival_loss": survival,
        },
    }


def run(
    split,
    arm,
    opponent,
    seed,
    seat,
    *,
    delta=0,
    cash_use=True,
    satisfied=True,
    productivity=0,
    survival=0,
    snap=None,
):
    base_own, rival = 100, 90
    own = base_own + (delta if arm == o.ARM_MIN else 0)
    return {
        "run_id": f"{split}-{opponent}-{seed}-{seat}-{arm}",
        "split": split,
        "arm": arm,
        "opponent": opponent,
        "seed": seed,
        "seat": seat,
        "pair_id": f"{split}-{opponent}-{seed}",
        "decision_windows": [
            window(
                arm,
                cash_use=cash_use,
                satisfied=satisfied,
                productivity=productivity,
                survival=survival,
                snap=snap,
            )
        ],
        "result": {
            "own": own,
            "rival": rival,
            "margin": own - rival,
            "outcome": "win",
        },
    }


def document(
    *,
    dev_delta=1,
    holdout_delta=1,
    cash_use=True,
    satisfied=True,
    productivity=0,
    survival=0,
):
    runs = []
    for split, opponent, seed, delta in [
        ("dev", "random", 7, dev_delta),
        ("dev", "tit_for_tat", 17, dev_delta),
        ("holdout", "do_nothing", 101, holdout_delta),
    ]:
        for arm in o.ARMS:
            for seat in o.SEATS:
                runs.append(
                    run(
                        split,
                        arm,
                        opponent,
                        seed,
                        seat,
                        delta=delta,
                        cash_use=cash_use,
                        satisfied=satisfied,
                        productivity=productivity,
                        survival=survival,
                    )
                )
    return {
        "schema": o.SCHEMA,
        "authority": {
            "archive_sha256": o.D2_ARCHIVE_SHA256,
            "archive_member_count": o.D2_MEMBER_COUNT,
            "runtime_member": o.D2_RUNTIME_MEMBER,
            "hosted_python": o.D2_HOSTED_PYTHON,
            "current_policy": copy.deepcopy(o.CURRENT_POLICY),
            "evidence_source": "instrumented_runtime",
            "holdout_sealed_before_dev": True,
            "dev_manifest_sha256": digest("a"),
            "holdout_manifest_sha256": digest("b"),
        },
        "candidate_selection": {
            "arm": o.ARM_MIN,
            "selected_before_holdout": True,
            "selection_manifest_sha256": digest("c"),
        },
        "runs": runs,
    }


class OracleTests(unittest.TestCase):
    def test_owned_feed_offsets_fresh_cost(self):
        result = o.compute_reserve_oracle(
            snapshot(on_hand={"Corn": 1, "Pasture": 1, "Straw": 1})
        )
        self.assertEqual(
            result["min_provable_fresh"],
            {"Corn": 0, "Pasture": 1, "Straw": 0},
        )

    def test_only_next_proven_boundary_counts(self):
        result = o.compute_reserve_oracle(snapshot())
        self.assertEqual(result["source_bound_obligations"]["Corn"], 1)
        self.assertEqual(result["next_boundary_step"], 20)

    def test_unproven_obligation_does_not_count(self):
        snap = snapshot(
            obligations=[
                {
                    "feed": "Corn",
                    "units": 9,
                    "boundary_step": 1,
                    "source": "hidden",
                    "source_proven": False,
                    "executable": True,
                }
            ]
        )
        result = o.compute_reserve_oracle(snap)
        self.assertEqual(
            result["min_provable_fresh"],
            {"Corn": 0, "Pasture": 0, "Straw": 0},
        )

    def test_current_excess_and_cash_tied(self):
        result = o.compute_reserve_oracle(snapshot())
        self.assertTrue(result["reachable_excess"])
        self.assertEqual(
            result["units_removed"],
            {"Corn": 1, "Pasture": 3, "Straw": 0},
        )
        self.assertEqual(result["cash_tied_in_discretionary_feed"], 9)

    def test_market_cap_and_order_are_applied(self):
        market = {
            "Corn": {"available": 20, "action_cap": 20, "unit_price": 3},
            "Pasture": {"available": 1, "action_cap": 1, "unit_price": 2},
            "Straw": {"available": 20, "action_cap": 20, "unit_price": 1},
        }
        result = o.compute_reserve_oracle(snapshot(market=market))
        self.assertEqual(
            result["arms"][o.ARM_CURRENT]["executable"]["Pasture"], 1
        )
        self.assertFalse(result["min_satisfies_obligations"])
        self.assertFalse(result["reachable_excess"])

    def test_no_candidate_when_min_is_not_subset(self):
        obligations = [
            {
                "feed": "Corn",
                "units": 3,
                "boundary_step": 1,
                "source": "animals",
                "source_proven": True,
                "executable": True,
            }
        ]
        result = o.compute_reserve_oracle(snapshot(obligations=obligations))
        self.assertFalse(result["min_is_subset_of_current"])
        self.assertFalse(result["reachable_excess"])


class EvidenceTests(unittest.TestCase):
    def test_positive_full_contract_promotes(self):
        report = o.analyze_document(document())
        self.assertEqual(
            report["promotion"]["conclusion"],
            "PROMOTE_RESEARCH_CANDIDATE",
        )

    def test_cash_not_used_is_falsifier(self):
        report = o.analyze_document(document(cash_use=False))
        self.assertEqual(report["promotion"]["conclusion"], "NO_PROMOTION")

    def test_obligation_failure_is_falsifier(self):
        report = o.analyze_document(document(satisfied=False))
        self.assertEqual(report["promotion"]["conclusion"], "NO_PROMOTION")

    def test_productivity_loss_is_falsifier(self):
        report = o.analyze_document(document(productivity=1))
        self.assertEqual(report["promotion"]["conclusion"], "NO_PROMOTION")

    def test_holdout_disappearance_is_falsifier(self):
        report = o.analyze_document(document(holdout_delta=0))
        self.assertEqual(report["promotion"]["conclusion"], "NO_PROMOTION")

    def test_seat_sign_flip_is_falsifier(self):
        evidence = document()
        for row in evidence["runs"]:
            if row["arm"] == o.ARM_MIN and row["seat"] == 2:
                row["result"] = {
                    "own": 99,
                    "rival": 90,
                    "margin": 9,
                    "outcome": "win",
                }
        report = o.analyze_document(evidence)
        self.assertEqual(report["promotion"]["conclusion"], "NO_PROMOTION")

    def test_wrong_archive_fails(self):
        evidence = document()
        evidence["authority"]["archive_sha256"] = digest("d")
        with self.assertRaises(o.EvidenceError):
            o.analyze_document(evidence)

    def test_bad_oracle_digest_fails(self):
        evidence = document()
        evidence["runs"][0]["decision_windows"][0]["decision"][
            "oracle_sha256"
        ] = digest("e")
        with self.assertRaises(o.EvidenceError):
            o.analyze_document(evidence)

    def test_missing_seat_fails(self):
        evidence = document()
        evidence["runs"] = [row for row in evidence["runs"] if row["seat"] == 1]
        with self.assertRaises(o.EvidenceError):
            o.analyze_document(evidence)

    def test_holdout_overlap_fails(self):
        evidence = document()
        for row in evidence["runs"]:
            if row["split"] == "holdout":
                row["opponent"] = "random"
                row["seed"] = 7
                row["pair_id"] = "holdout-random-7"
        with self.assertRaises(o.EvidenceError):
            o.analyze_document(evidence)


class OutputTests(unittest.TestCase):
    def test_deterministic_report_and_outputs(self):
        evidence = document()
        first = o.analyze_document(copy.deepcopy(evidence))
        second = o.analyze_document(copy.deepcopy(evidence))
        self.assertEqual(first["report_sha256"], second["report_sha256"])
        with tempfile.TemporaryDirectory() as directory:
            x = o.write_outputs(first, Path(directory) / "x")
            y = o.write_outputs(second, Path(directory) / "y")
            self.assertEqual(x, y)

    def test_existing_output_refused(self):
        report = o.analyze_document(document())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out"
            o.write_outputs(report, path)
            with self.assertRaises(o.EvidenceError):
                o.write_outputs(report, path)


if __name__ == "__main__":
    unittest.main()
