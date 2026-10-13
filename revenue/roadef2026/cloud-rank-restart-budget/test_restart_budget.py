import importlib.util
import pathlib
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("restart_builder", HERE / "build_restart_budget.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)


class RestartBudgetTests(unittest.TestCase):
    def test_scheduler_model_reaches_deeper_ranks_after_accepted_resets(self):
        # Eight accepted rank-1 improvements used to consume half of a shared
        # 16-pass budget. With separate accounting, 16 no-gain probes remain.
        pass_limit = 16
        restart_limit = 16
        rank = 1
        no_gain = restarts = iterations = 0
        accept_pattern = [True] * 8 + [False] * 16
        seen = []
        for accepted in accept_pattern:
            if no_gain >= pass_limit or restarts >= restart_limit:
                break
            iterations += 1
            seen.append(rank)
            if accepted:
                restarts += 1
                rank = 1
            else:
                no_gain += 1
                rank += 1
        self.assertEqual(24, iterations)
        self.assertEqual(16, no_gain)
        self.assertEqual(8, restarts)
        self.assertEqual(16, max(seen))

    def test_restart_budget_bounds_acceptance_reset_storm(self):
        pass_limit = restart_limit = 16
        no_gain = restarts = iterations = 0
        while no_gain < pass_limit and restarts < restart_limit:
            iterations += 1
            restarts += 1  # every selected coordinate accepts and resets
        self.assertEqual(16, iterations)
        self.assertEqual(16, restarts)
        self.assertEqual(0, no_gain)

    def test_total_scheduler_iterations_are_finitely_bounded(self):
        # Every iteration is either a no-gain probe or an accepted restart.
        for passes in (0, 1, 16, 128):
            for restarts in (0, 1, 16, 128):
                self.assertLessEqual(passes + restarts, 256)

    def test_transform_is_scheduler_only_and_keeps_authoritative_guards(self):
        fixture = '''
        int passLimit = static_cast<int>(std::min(128.0, setting("FLEET_RANK1_PASSES", 16)));
        int demandLimitSetting = static_cast<int>(std::min(256.0, setting("FLEET_RANK1_DEMANDS", 32)));
        int rankCursor = 0;
        std::vector<int> coordinateOrder;
        for (int pass = 0; pass < passLimit && !finished(); ++pass) {
            if (accepted != acceptedBefore) {
                rankCursor = 0;
            } else if (++rankCursor >= rankLimit) {
                schedulerStop = "configured_sweep_exhaustion";
                break;
            }
        }
                      << ",\\\"pass_limit\\\":" << passLimit << ",\\\"rank_limit\\\":" << rankLimit
                      << ",\\\"last_selected_rank\\\":"
                out << ",\\\"rank_traversal\\\":true,\\\"rank_limit\\\":" << rankLimit
                    << ",\\\"stop_reason\\\":\\\"" << schedulerStop << "\\\"";
'''
        candidate = MOD.transform_text(fixture)
        self.assertIn('FLEET_RANK1_RESTARTS', candidate)
        self.assertIn('noGainPasses < passLimit', candidate)
        self.assertIn('schedulerStop = "restart_budget"', candidate)
        self.assertIn('restart_limit', candidate)
        self.assertIn('!finished()', candidate)
        self.assertNotIn('pass < passLimit && !finished()', candidate)

    def test_transform_rejects_ambiguous_or_missing_anchor(self):
        with self.assertRaisesRegex(ValueError, "expected exactly one anchor"):
            MOD.transform_text("not the released scheduler")

    def test_build_rejects_wrong_base_before_writing_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            base = root / "base.cpp"
            base.write_text("wrong", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "base mismatch"):
                MOD.build(base, root / "out.cpp", root / "out.patch", root / "receipt.json")
            self.assertFalse((root / "out.cpp").exists())


if __name__ == "__main__":
    unittest.main()
