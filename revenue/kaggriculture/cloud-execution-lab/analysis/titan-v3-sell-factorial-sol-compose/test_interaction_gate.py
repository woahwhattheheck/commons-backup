# SPDX-License-Identifier: Apache-2.0
"""Adversarial contracts for the TITAN SELL 2x2 interaction gate."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import interaction_gate as gate

OPPONENTS = ("arlene", "v1")
SEEDS = (101, 102)
ARMS = gate.ARM_NAMES


def digest(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()


def default_effect(arm: str, opponent: str, seed: int, seat: int) -> dict:
    del opponent, seed, seat
    values = {
        "control": (0.0, 0.0, False),
        "own_value": (10.0, 0.0, True),
        "certified_pressure": (5.0, 0.0, True),
        "both": (18.0, 0.0, True),
    }
    own, rival, changed = values[arm]
    return {"own": own, "rival": rival, "changed": changed}


def make_reports(effect=default_effect) -> dict[str, dict]:
    reports: dict[str, dict] = {}
    shared = {
        "schema_version": 1,
        "engine_ref": "28b6d8af-test",
        "engine_sha256": "a" * 64,
        "loader_sha256": "b" * 64,
        "evaluator_sha256": "c" * 64,
        "seeds": list(SEEDS),
        "agent_rng_seed": 20260910,
        "limits": {
            "action_timeout": 1.0,
            "startup_timeout": 15.0,
            "game_timeout": 180.0,
        },
        "opponents": {name: {"sha256": digest("opponent", name)} for name in OPPONENTS},
    }
    for arm_offset, arm in enumerate(ARMS):
        games = []
        for opponent in OPPONENTS:
            for seed in SEEDS:
                for seat in (0, 1):
                    row = dict(effect(arm, opponent, seed, seat))
                    own_base = 1000.0 + (seed - SEEDS[0]) * 10 + seat
                    rival_base = 900.0 + (seed - SEEDS[0]) * 5
                    own = own_base + float(row.get("own", 0.0))
                    rival = rival_base + float(row.get("rival", 0.0))
                    changed = bool(row.get("changed", arm != "control"))
                    control_action = digest("action", "control", opponent, seed, seat)
                    control_trace = digest("trace", "control", opponent, seed, seat)
                    action_sha = row.get(
                        "action_sha",
                        digest("action", arm, opponent, seed, seat)
                        if changed
                        else control_action,
                    )
                    trace_sha = row.get(
                        "trace_sha",
                        digest("trace", arm, opponent, seed, seat)
                        if changed
                        else control_trace,
                    )
                    scores = [own, rival] if seat == 0 else [rival, own]
                    games.append(
                        {
                            "opponent": opponent,
                            "seed": seed,
                            "candidate_seat": seat,
                            "status": "complete",
                            "failure": None,
                            "episode_steps": 720,
                            "steps": 719,
                            "candidate_action_count": 719,
                            "candidate_action_sha256": action_sha,
                            "trace_sha256": trace_sha,
                            "scores": scores,
                            "bank_snapshot": list(scores),
                        }
                    )
        reports[arm] = {
            **copy.deepcopy(shared),
            "candidate": {
                "sha256": digest("entrypoint", arm_offset, arm),
                "entrypoint": f"{arm}.py::agent",
            },
            "progress": {
                "state": "complete",
                "planned_games": len(games),
                "recorded_games": len(games),
            },
            "games": games,
        }
    return reports


def make_manifest(reports: dict[str, dict]) -> dict:
    archive_sha = digest("canonical-archive")
    source_manifest_sha = digest("canonical-source-manifest")
    runtime_tree_sha = digest("canonical-runtime-tree")
    own_source = digest("own-value-source")
    pressure_source = digest("certified-pressure-source")
    factor_rows = {
        "own_value": {
            "contract": "TITAN-V3-OWN-VALUE-OBJECTIVE-20260909-01",
            "source_sha256": own_source,
            "source_git_blob_sha1": hashlib.sha1(b"own-value-source").hexdigest(),
            "receipt_sha256": digest("own-value-receipt"),
        },
        "certified_pressure": {
            "contract": gate.PRESSURE_CONTRACT,
            "source_sha256": pressure_source,
            "source_git_blob_sha1": hashlib.sha1(b"certified-pressure-source").hexdigest(),
            "receipt_sha256": digest("certified-pressure-receipt"),
            "inventory_window_mode": "parent_candidate_execution_prefix_union",
            "rival_bound_source": "shedCapacity",
            "market_order_cap_source": "maxMarketOrdersPerTurn",
            "price_floor_source": "PRICE_FLOOR",
        },
    }
    expected = {
        "control": {},
        "own_value": {"own_value": own_source},
        "certified_pressure": {"certified_pressure": pressure_source},
        "both": {
            "own_value": own_source,
            "certified_pressure": pressure_source,
        },
    }
    return {
        "schema_version": 1,
        "operation": gate.MANIFEST_OPERATION,
        "panel_binding": {
            "archive_sha256": archive_sha,
            "source_manifest_sha256": source_manifest_sha,
            "runtime_tree_sha256": runtime_tree_sha,
            "engine_sha256": reports["control"]["engine_sha256"],
            "loader_sha256": reports["control"]["loader_sha256"],
            "evaluator_sha256": reports["control"]["evaluator_sha256"],
        },
        "factors": factor_rows,
        "arms": {
            arm: {
                "candidate_sha256": reports[arm]["candidate"]["sha256"],
                "build_receipt_sha256": digest("build-receipt", arm),
                "archive_sha256": archive_sha,
                "source_manifest_sha256": source_manifest_sha,
                "runtime_tree_sha256": runtime_tree_sha,
                "factors": expected[arm],
            }
            for arm in ARMS
        },
    }


def assess_reports(reports: dict[str, dict], **kwargs) -> dict:
    return gate.assess(reports, make_manifest(reports), **kwargs)


class InteractionGateTests(unittest.TestCase):
    def test_selects_nondominated_composition_and_computes_interaction(self):
        report = assess_reports(make_reports(), git_head="d" * 40)
        self.assertEqual(report["selection"]["verdict"], "SELECT_BOTH")
        self.assertEqual(report["selection"]["selected_arm"], "both")
        self.assertTrue(report["selection"]["composition_nondominated"])
        self.assertEqual(report["grid"]["cells_per_arm"], 8)
        self.assertEqual(report["grid"]["total_games"], 32)
        self.assertEqual(len(report["arm_manifest_binding"]["semantic_sha256"]), 64)
        self.assertEqual(
            set(report["arm_manifest_binding"]["manifest"]["arms"]), set(ARMS)
        )
        factorial = report["overall"]["factorial"]
        self.assertEqual(factorial["own_value_main_effect"]["mean"], 11.5)
        self.assertEqual(factorial["certified_pressure_main_effect"]["mean"], 6.5)
        self.assertEqual(factorial["own_cash_interaction"]["mean"], 3.0)
        self.assertEqual(factorial["margin_interaction"]["mean"], 3.0)
        self.assertFalse(report["selection"]["promotion_authorized"])
        self.assertFalse(report["selection"]["hosted_leaderboard_claim"])

    def test_antagonistic_composition_selects_best_singleton(self):
        values = {
            "control": (0, False),
            "own_value": (10, True),
            "certified_pressure": (5, True),
            "both": (6, True),
        }

        def effect(arm, opponent, seed, seat):
            del opponent, seed, seat
            own, changed = values[arm]
            return {"own": own, "rival": 0, "changed": changed}

        report = assess_reports(make_reports(effect))
        self.assertEqual(report["selection"]["verdict"], "SELECT_OWN_VALUE")
        self.assertFalse(report["selection"]["composition_nondominated"])

    def test_composition_cannot_reenter_on_pooled_mean_after_stratum_harm(self):
        def effect(arm, opponent, seed, seat):
            if arm == "control":
                return {"own": 0, "rival": 0, "changed": False}
            if arm == "own_value":
                return {"own": 10, "rival": 0, "changed": True}
            if arm == "certified_pressure":
                return {"own": 5, "rival": 0, "changed": True}
            # Huge pooled gain, but one full opponent/seat stratum is one dollar
            # below the eligible own-value singleton.
            return {
                "own": 9 if opponent == "arlene" and seat == 0 else 30,
                "rival": 0,
                "changed": True,
            }

        report = assess_reports(make_reports(effect))
        self.assertTrue(report["selection"]["eligible_against_control"]["both"])
        self.assertFalse(report["selection"]["composition_nondominated"])
        self.assertEqual(report["selection"]["selected_arm"], "own_value")

    def test_selects_composition_when_singletons_are_unsafe_but_joint_arm_is_safe(self):
        values = {
            "control": (0, False),
            "own_value": (-2, True),
            "certified_pressure": (-1, True),
            "both": (4, True),
        }

        def effect(arm, opponent, seed, seat):
            del opponent, seed, seat
            own, changed = values[arm]
            return {"own": own, "rival": 0, "changed": changed}

        report = assess_reports(make_reports(effect))
        self.assertEqual(report["selection"]["verdict"], "SELECT_BOTH")
        self.assertEqual(
            report["selection"]["eligible_against_control"],
            {"own_value": False, "certified_pressure": False, "both": True},
        )

    def test_no_safe_advance_when_all_active_arms_regress(self):
        values = {
            "control": (0, False),
            "own_value": (-10, True),
            "certified_pressure": (-5, True),
            "both": (-3, True),
        }

        def effect(arm, opponent, seed, seat):
            del opponent, seed, seat
            own, changed = values[arm]
            return {"own": own, "rival": 0, "changed": changed}

        report = assess_reports(make_reports(effect))
        self.assertEqual(report["selection"]["verdict"], "NO_SAFE_ADVANCE")
        self.assertIsNone(report["selection"]["selected_arm"])

    def test_inactive_when_all_four_action_streams_and_scores_match(self):
        def effect(arm, opponent, seed, seat):
            del arm, opponent, seed, seat
            return {"own": 0, "rival": 0, "changed": False}

        report = assess_reports(make_reports(effect))
        self.assertEqual(report["selection"]["verdict"], "INACTIVE")
        self.assertEqual(
            report["overall"]["pairwise"]["both_vs_control"][
                "candidate_action_changed_cells"
            ],
            0,
        )

    def test_positive_pooled_mean_does_not_override_negative_stratum(self):
        def effect(arm, opponent, seed, seat):
            if arm == "control":
                return {"own": 0, "rival": 0, "changed": False}
            if arm == "own_value":
                delta = -1 if opponent == "v1" and seat == 1 else 20
                return {"own": delta, "rival": 0, "changed": True}
            if arm == "certified_pressure":
                return {"own": 1, "rival": 0, "changed": True}
            return {"own": -2, "rival": 0, "changed": True}

        report = assess_reports(make_reports(effect))
        own = report["overall"]["pairwise"]["own_value_vs_control"]
        self.assertGreater(own["own_cash"]["mean"], 0)
        self.assertFalse(report["selection"]["eligible_against_control"]["own_value"])
        self.assertEqual(report["selection"]["verdict"], "SELECT_CERTIFIED_PRESSURE")

    def test_score_change_without_captured_action_change_is_rejected(self):
        def effect(arm, opponent, seed, seat):
            del opponent, seed, seat
            if arm == "own_value":
                return {"own": 1, "rival": 0, "changed": False}
            return default_effect(arm, "", 0, 0)

        with self.assertRaisesRegex(gate.EvidenceError, "action stream"):
            assess_reports(make_reports(effect))

    def test_equal_action_stream_with_divergent_trace_is_rejected(self):
        reports = make_reports()
        key = reports["control"]["games"][0]
        arm = reports["own_value"]["games"][0]
        arm["candidate_action_sha256"] = key["candidate_action_sha256"]
        # Keep the candidate trace and economics different.
        with self.assertRaisesRegex(gate.EvidenceError, "equal candidate action streams"):
            assess_reports(reports)

    def test_provenance_mismatch_is_rejected(self):
        reports = make_reports()
        reports["both"]["engine_sha256"] = "f" * 64
        with self.assertRaisesRegex(gate.EvidenceError, "provenance differs"):
            assess_reports(reports)

    def test_malformed_provenance_digest_is_rejected(self):
        reports = make_reports()
        for arm in ARMS:
            reports[arm]["loader_sha256"] = "not-a-digest"
        with self.assertRaisesRegex(gate.EvidenceError, "loader_sha256"):
            assess_reports(reports)

    def test_duplicate_cell_is_rejected(self):
        reports = make_reports()
        reports["both"]["games"][-1] = copy.deepcopy(reports["both"]["games"][0])
        with self.assertRaisesRegex(gate.EvidenceError, "duplicate cell"):
            assess_reports(reports)

    def test_incomplete_lifecycle_is_rejected(self):
        reports = make_reports()
        reports["certified_pressure"]["games"][0]["candidate_action_count"] = 718
        with self.assertRaisesRegex(gate.EvidenceError, "719 captured"):
            assess_reports(reports)

    def test_bank_score_mismatch_is_rejected(self):
        reports = make_reports()
        reports["own_value"]["games"][0]["bank_snapshot"][0] += 1
        with self.assertRaisesRegex(gate.EvidenceError, "scores differ"):
            assess_reports(reports)

    def test_boolean_identity_is_rejected(self):
        reports = make_reports()
        reports["both"]["games"][0]["candidate_seat"] = True
        with self.assertRaisesRegex(gate.EvidenceError, "must be an integer"):
            assess_reports(reports)

    def test_nonfinite_score_is_rejected(self):
        reports = make_reports()
        reports["both"]["games"][0]["scores"][0] = float("inf")
        reports["both"]["games"][0]["bank_snapshot"][0] = float("inf")
        with self.assertRaisesRegex(gate.EvidenceError, "must be finite"):
            assess_reports(reports)

    def test_finite_scores_that_overflow_a_delta_are_rejected(self):
        reports = make_reports()
        control = reports["control"]["games"][0]
        candidate = reports["own_value"]["games"][0]
        control["scores"][0] = control["bank_snapshot"][0] = -1e308
        candidate["scores"][0] = candidate["bank_snapshot"][0] = 1e308
        with self.assertRaisesRegex(gate.EvidenceError, "must be finite"):
            assess_reports(reports)

    def test_arm_fingerprints_must_be_distinct(self):
        reports = make_reports()
        reports["both"]["candidate"]["sha256"] = reports["own_value"]["candidate"][
            "sha256"
        ]
        with self.assertRaisesRegex(gate.EvidenceError, "must be distinct"):
            assess_reports(reports)

    def test_manifest_candidate_must_match_executed_report(self):
        reports = make_reports()
        manifest = make_manifest(reports)
        manifest["arms"]["both"]["candidate_sha256"] = digest("wrong-candidate")
        with self.assertRaisesRegex(gate.EvidenceError, "differs from executed report"):
            gate.assess(reports, manifest)

    def test_both_arm_must_reuse_exact_singleton_factor_bytes(self):
        reports = make_reports()
        manifest = make_manifest(reports)
        manifest["arms"]["both"]["factors"]["certified_pressure"] = digest(
            "different-pressure-source"
        )
        with self.assertRaisesRegex(gate.EvidenceError, "exact singleton source bytes"):
            gate.assess(reports, manifest)

    def test_control_cannot_leak_a_factor(self):
        reports = make_reports()
        manifest = make_manifest(reports)
        manifest["arms"]["control"]["factors"]["own_value"] = manifest["factors"][
            "own_value"
        ]["source_sha256"]
        with self.assertRaisesRegex(gate.EvidenceError, "control factor map keys differ"):
            gate.assess(reports, manifest)

    def test_every_arm_must_bind_same_canonical_runtime(self):
        reports = make_reports()
        manifest = make_manifest(reports)
        manifest["arms"]["certified_pressure"]["runtime_tree_sha256"] = digest(
            "foreign-runtime"
        )
        with self.assertRaisesRegex(gate.EvidenceError, "canonical closure differs"):
            gate.assess(reports, manifest)

    def test_pressure_contract_and_delay_bound_are_exact(self):
        reports = make_reports()
        manifest = make_manifest(reports)
        manifest["factors"]["certified_pressure"]["contract"] = "proxy-zero-partition"
        with self.assertRaisesRegex(gate.EvidenceError, "contract fingerprint mismatch"):
            gate.assess(reports, manifest)
        manifest = make_manifest(reports)
        manifest["factors"]["certified_pressure"]["rival_bound_source"] = "proxyQuantity"
        with self.assertRaisesRegex(gate.EvidenceError, "rival_bound_source must be shedCapacity"):
            gate.assess(reports, manifest)

    def test_pressure_manifest_requires_execution_prefix_union(self):
        reports = make_reports()
        manifest = make_manifest(reports)
        manifest["factors"]["certified_pressure"][
            "inventory_window_mode"
        ] = "raw_public_inventory_window"
        with self.assertRaisesRegex(
            gate.EvidenceError, "inventory_window_mode must be parent_candidate_execution_prefix_union"
        ):
            gate.assess(reports, manifest)
        manifest = make_manifest(reports)
        manifest["factors"]["certified_pressure"][
            "market_order_cap_source"
        ] = "uncapped_authored_queue"
        with self.assertRaisesRegex(
            gate.EvidenceError, "market_order_cap_source must be maxMarketOrdersPerTurn"
        ):
            gate.assess(reports, manifest)

    def test_manifest_evaluator_binding_must_match_reports(self):
        reports = make_reports()
        manifest = make_manifest(reports)
        manifest["panel_binding"]["evaluator_sha256"] = digest("foreign-evaluator")
        with self.assertRaisesRegex(gate.EvidenceError, "differs from reports"):
            gate.assess(reports, manifest)

    def test_manifest_rejects_unexpected_fields(self):
        reports = make_reports()
        manifest = make_manifest(reports)
        manifest["arms"]["own_value"]["unbound_note"] = "ignored without this check"
        with self.assertRaisesRegex(gate.EvidenceError, "unexpected"):
            gate.assess(reports, manifest)

    def test_strict_loader_rejects_duplicate_keys_and_nan(self):
        with tempfile.TemporaryDirectory() as tmp:
            duplicate = Path(tmp) / "duplicate.json"
            duplicate.write_text('{"a": 1, "a": 2}', encoding="utf-8")
            with self.assertRaisesRegex(gate.EvidenceError, "duplicate JSON key"):
                gate.strict_load(duplicate, "fixture")
            nonfinite = Path(tmp) / "nan.json"
            nonfinite.write_text('{"a": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(gate.EvidenceError, "non-finite"):
                gate.strict_load(nonfinite, "fixture")

    def test_markdown_reports_decision_and_boundaries(self):
        report = assess_reports(make_reports())
        rendered = gate.markdown(report)
        self.assertIn("SELECT_BOTH", rendered)
        self.assertIn("32", rendered)
        self.assertIn("does not authorize promotion", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
