from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gander_starve_cadence as G


class GanderStarveCompositeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = G.build_report()
        cls.safe = cls.report["safe_composite"]

    def test_safe_composite_survives_all_nine_geese(self):
        self.assertTrue(self.safe["survived"])
        self.assertIsNone(self.safe["escaped_day"])
        self.assertEqual(self.safe["living_geese"], 9)
        self.assertEqual(self.safe["max_consecutive_unfed_seen"], 1)

    def test_day1_is_mandatory_after_unfed_eod0(self):
        predecessor = self.report["mandatory_day1_feed_predecessor"]
        self.assertFalse(predecessor["survived"])
        self.assertEqual(predecessor["escaped_day"], 1)
        self.assertEqual(self.safe["feed_days"][0], 1)
        self.assertEqual(self.safe["skip_days"][0], 2)

    def test_official_terminal_boundary_is_interpreter_enforced(self):
        self.assertEqual(self.safe["episode_steps"], 720)
        self.assertEqual(self.safe["final_executable_step"], 718)
        self.assertEqual(self.safe["last_step_executed"], 718)
        self.assertEqual(self.safe["terminal_statuses"], ["DONE", "DONE"])
        self.assertEqual(self.safe["last_eod_day"], 28)
        self.assertTrue(self.safe["terminal_day_feed_is_dead_work"])
        self.assertNotIn(29, self.safe["feed_days"])
        self.assertIn(29, self.safe["skip_days"])
        self.assertTrue(self.safe["source_contract"]["official_episode_horizon_bound"])

    def test_alternation_halves_daily_feed_through_last_real_eod(self):
        self.assertEqual(len(self.safe["feed_days"]), 14)
        self.assertEqual(len(self.safe["skip_days"]), 15)
        self.assertEqual(self.safe["feed_days"][-1], 27)
        self.assertEqual(self.safe["wheat_consumed"], 126)
        self.assertEqual(
            self.safe["wheat_saved_vs_feed_daily_through_last_eod"], 126
        )
        self.assertEqual(self.safe["action_attempts"]["feed_attempts"], 126)
        self.assertEqual(
            self.safe["feed_actions_saved_vs_feed_daily_through_last_eod"], 126
        )
        self.assertEqual(self.safe["egg_total"], 9 * 26)
        self.assertEqual(self.safe["fertilizer_total"], 9 * 29)

    def test_terminal_extraction_avoids_held_cap_clipping(self):
        # Mature EGG is harvested on even skip-feed days plus terminal day 29.
        # At most two production refreshes accumulate between harvest visits.
        self.assertEqual(self.safe["action_attempts"]["harvest_attempts"], 14 * 9)
        self.assertLessEqual(self.safe["max_goose_yield_units_seen"], 2)
        self.assertEqual(self.safe["final_held_egg"], 0)
        self.assertEqual(self.safe["final_pending_fertilizer"], 0)

    def test_same_two_worker_geometry_fits_after_daily_hire(self):
        self.assertEqual(self.safe["action_attempts"]["hire_orders"], 29)
        self.assertLessEqual(self.safe["max_route_actions_after_hire"], 20)
        self.assertEqual(
            self.safe["source_contract"]["gander_day1_service_counts"],
            {
                "PICKUP": 2,
                "FEED": 9,
                "COLLECT_FERTILIZER": 9,
                "DROP": 2,
            },
        )

    def test_alternation_creates_route_capacity_for_all_nine_harvests(self):
        contract = self.safe["source_contract"]
        self.assertEqual(contract["regular_post_hire_unit_slots"], 23)
        self.assertEqual(contract["terminal_post_hire_unit_slots"], 22)
        self.assertEqual(contract["route_lengths"]["feed_fert"], [20, 21])
        self.assertEqual(
            contract["route_lengths"]["skip_feed_fert_harvest"], [19, 20]
        )
        self.assertEqual(contract["route_lengths"]["feed_fert_harvest"], [25, 25])
        self.assertFalse(contract["all_nine_feed_fert_harvest_fits_two_workers"])
        self.assertTrue(contract["terminal_skip_feed_fert_harvest_fits_two_workers"])

    def test_care_is_explicitly_out_of_scope(self):
        self.assertEqual(self.safe["action_attempts"]["care_attempts"], 0)
        self.assertFalse(self.safe["source_contract"]["care_used"])
        self.assertFalse(self.safe["source_contract"]["economics_claim"])
        self.assertTrue(
            self.report["interpretation"]["wheat_savings_are_units_not_cash"]
        )
        self.assertFalse(self.report["interpretation"]["market_prices_modeled"])

    def test_helpers_engine_and_metadata_are_authenticated_before_execution(self):
        contract = self.safe["source_contract"]
        self.assertEqual(
            contract["gander_helper_git_blob"], G.PINNED_GANDER_GIT_BLOB
        )
        self.assertEqual(
            contract["starve_helper_git_blob"], G.PINNED_STARVE_GIT_BLOB
        )
        self.assertEqual(
            contract["engine_metadata_git_blob"],
            G.PINNED_ENGINE_METADATA_GIT_BLOB,
        )
        self.assertEqual(
            contract["engine_metadata_sha256"],
            G.PINNED_ENGINE_METADATA_SHA256,
        )
        self.assertEqual(
            contract["engine_metadata_bytes"], G.PINNED_ENGINE_METADATA_BYTES
        )
        self.assertTrue(contract["immutable_source_snapshots"])
        self.assertTrue(contract["engine_executed_from_authenticated_snapshot"])
        self.assertTrue(contract["engine_metadata_served_from_authenticated_snapshot"])

    def test_current_engine_identity_is_exact(self):
        self.assertEqual(self.safe["engine_git_blob"], G.PINNED_ENGINE_GIT_BLOB)
        self.assertEqual(self.safe["engine_sha256"], G.PINNED_ENGINE_SHA256)
        self.assertEqual(
            self.safe["engine_metadata_git_blob"],
            G.PINNED_ENGINE_METADATA_GIT_BLOB,
        )
        self.assertEqual(
            self.safe["engine_metadata_sha256"],
            G.PINNED_ENGINE_METADATA_SHA256,
        )
        self.assertEqual(
            self.safe["source_contract"]["starve_engine_git_blob"],
            G.PINNED_ENGINE_GIT_BLOB,
        )

    def test_authenticated_sources_and_metadata_cannot_be_swapped_before_execution(self):
        originals = {
            "gander": G.GANDER_PATH.read_bytes(),
            "starve": G.STARVE_PATH.read_bytes(),
            "engine": G.ENGINE_PATH.read_bytes(),
            "metadata": G.ENGINE_PATH.with_suffix(".json").read_bytes(),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            paths = {
                "gander": root / "goose_printer_oracle.py",
                "starve": root / "starvation_cadence.py",
                "engine": root / "kaggriculture.py",
                "metadata": root / "kaggriculture.json",
            }
            for key, path in paths.items():
                path.write_bytes(originals[key])

            real_read_bytes = Path.read_bytes
            reads = {path.resolve(): 0 for path in paths.values()}

            def capture_then_poison(path):
                resolved = path.resolve()
                data = real_read_bytes(path)
                if resolved in reads:
                    reads[resolved] += 1
                    if reads[resolved] > 1:
                        raise AssertionError(f"authenticated source reopened: {resolved}")
                    if resolved == paths["metadata"].resolve():
                        path.write_bytes(b'{"poisoned":true}\n')
                    else:
                        path.write_bytes(
                            b"raise RuntimeError('swapped pathname executed')\n"
                        )
                return data

            with (
                patch.object(G, "GANDER_PATH", paths["gander"]),
                patch.object(G, "STARVE_PATH", paths["starve"]),
                patch.object(G, "ENGINE_PATH", paths["engine"]),
                patch.object(Path, "read_bytes", new=capture_then_poison),
            ):
                gander, starve, engine, identities = G._canonical_sources()

            self.assertEqual(
                reads,
                {path.resolve(): 1 for path in paths.values()},
            )
            self.assertEqual(
                identities["gander_helper_git_blob"], G.PINNED_GANDER_GIT_BLOB
            )
            self.assertEqual(
                identities["starve_helper_git_blob"], G.PINNED_STARVE_GIT_BLOB
            )
            self.assertEqual(identities["engine_git_blob"], G.PINNED_ENGINE_GIT_BLOB)
            self.assertEqual(identities["engine_sha256"], G.PINNED_ENGINE_SHA256)
            self.assertEqual(
                identities["engine_metadata_git_blob"],
                G.PINNED_ENGINE_METADATA_GIT_BLOB,
            )
            self.assertEqual(
                identities["engine_metadata_sha256"],
                G.PINNED_ENGINE_METADATA_SHA256,
            )
            self.assertEqual(
                identities["engine_metadata_bytes"], G.PINNED_ENGINE_METADATA_BYTES
            )
            self.assertEqual(gander.EXPECTED_ENGINE_BLOB, G.PINNED_ENGINE_GIT_BLOB)
            self.assertEqual(starve.ENGINE_GIT_BLOB, G.PINNED_ENGINE_GIT_BLOB)
            self.assertTrue(callable(engine.interpreter))
            self.assertEqual(engine.specification["name"], "kaggriculture")
            self.assertEqual(engine.specification["configuration"]["episodeSteps"], 720)


if __name__ == "__main__":
    unittest.main()
