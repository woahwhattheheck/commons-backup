#!/usr/bin/env python3
"""Independent field observer and legal setup tests, not a second S8 policy."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_s8_field as field
import reachable_goose as grower
import run_s8_panel as panel
import materialize_s8_field as materialize

RUNTIME = None


class CensusTests(unittest.TestCase):
    def fixture(self, step=167, **tile_fields):
        tile = {"kind": "COOP", "animal": "GOOSE", "placed_day": 0,
                "yield_units": 0, "fed_today": True, "cared_today": False,
                "pending_care_bonus": 0, "fertilizer_available": True,
                "consecutive_unfed": 0}
        tile.update(tile_fields)
        farm = {"farmer": [0, 0], "hands": [], "tiles": [[tile]]}
        obs = {"step": step, "player": 0, "farms": [farm, copy.deepcopy(farm)],
               "private": {"shed": {"FERTILIZER": 4}},
               "market": {"prices": {"EGG": 120, "FERTILIZER": 100}}}
        return obs, {"farmer": ["COLLECT_FERTILIZER"], "hands": [], "market": []}

    def test_exact_old_price_boundary_and_no_mutation(self):
        obs, action = self.fixture()
        before = copy.deepcopy((obs, action))
        c = field.Census(0)
        c.observe(obs, action)
        self.assertEqual(c.counts["h23_collect_price_and_buffer"], 1)
        self.assertEqual((obs, action), before)

    def test_price_rejection_is_distinct_from_physiology(self):
        obs, action = self.fixture()
        obs["market"]["prices"]["EGG"] = 119
        c = field.Census(0); c.observe(obs, action)
        self.assertEqual(c.counts["physiology_opportunity"], 1)
        self.assertEqual(c.counts["h23_collect_price_pass"], 0)

    def test_all_physiology_blocks_are_counted(self):
        cases = [({"fed_today": False}, "fed_uncared_block"),
                 ({"cared_today": True}, "fed_uncared_block"),
                 ({"pending_care_bonus": 1}, "pending_bonus_block"),
                 ({"yield_units": 2}, "no_harvest_room_bound_block"),
                 ({"fertilizer_available": False}, "fertilizer_available_block"),
                 ({"placed_day": 6}, "production_window_block")]
        for kwargs, reason in cases:
            with self.subTest(reason=reason, kwargs=kwargs):
                obs, action = self.fixture(**kwargs)
                c = field.Census(0); c.observe(obs, action)
                self.assertEqual(c.counts[reason], 1)
                self.assertEqual(c.counts["physiology_opportunity"], 0)

    def test_day_and_hour_are_not_conflated(self):
        obs, action = self.fixture(step=166)
        c = field.Census(0); c.observe(obs, action)
        self.assertEqual(c.counts["physiology_opportunity"], 1)
        self.assertEqual(c.counts["h23_collect_physiology"], 0)
        obs["step"] = 28 * 24 + 23
        c = field.Census(0); c.observe(obs, action)
        self.assertEqual(c.counts["production_window_block"], 1)

    def test_shared_site_fails_closed(self):
        obs, action = self.fixture()
        obs["farms"][0]["hands"] = [[0, 0]]
        action["hands"] = [["PASS"]]
        c = field.Census(0); c.observe(obs, action)
        self.assertEqual(c.counts["shared_site_block"], 2)
        self.assertEqual(c.counts["physiology_opportunity"], 0)

    def test_both_seats_select_own_farm(self):
        obs, action = self.fixture()
        obs["player"] = 1
        obs["farms"][0]["tiles"][0][0] = None
        c = field.Census(1); c.observe(obs, action)
        self.assertEqual(c.counts["h23_collect_physiology"], 1)

    def test_runtime_digest_refuses_drift_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("raise RuntimeError('MUST NOT EXECUTE')\n")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                field.play(root, 1, 0, root / "out", expected_package_sha256="0" * 64)

    def test_hash_manifest_ignores_only_interpreter_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("x = 1\n")
            first = field.package_hashes(root)
            (root / "__pycache__").mkdir()
            (root / "__pycache__/main.pyc").write_bytes(b"cache")
            self.assertEqual(first, field.package_hashes(root))
            (root / "main.py").write_text("x = 2\n")
            self.assertNotEqual(first, field.package_hashes(root))


class PairReceiptTests(unittest.TestCase):
    def fixture(self):
        return {"seed": 101, "seat": 0, "configuration_overrides": {},
                "configuration": {"seed": None}, "opponent": "official_starter",
                "engine_sha256": {"kaggriculture.py": "pinned"}, "kind": "disposal",
                "status": "complete", "steps": 719, "scores": [1000, 500],
                "action_sha256": "a", "world_sha256": "b",
                "census": {"effects": {"egg_net_market_out": 5}},
                "helper": {"calls": 719, "transformed_actions": 0, "first_change_step": None}}

    def test_rival_cash_must_be_subtracted(self):
        a = self.fixture(); b = copy.deepcopy(a)
        b["scores"] = [1100, 800]
        result = panel.pair(a, b)
        self.assertEqual((result["delta_own"], result["delta_rival"], result["delta_margin"]), (100, 300, -200))

    def test_noncomparable_pairs_fail_closed(self):
        for key in ("seed", "seat", "configuration_overrides", "configuration", "opponent", "engine_sha256", "kind"):
            with self.subTest(key=key):
                a = self.fixture(); b = copy.deepcopy(a); b[key] = "DIFFERENT"
                with self.assertRaisesRegex(ValueError, "Noncomparable"):
                    panel.pair(a, b)

    def test_incomplete_cells_are_retained_not_wins(self):
        for status, steps in (("failed", 719), ("complete", 718)):
            a = self.fixture(); b = copy.deepcopy(a)
            b.update(status=status, steps=steps)
            result = panel.pair(a, b)
            self.assertFalse(result["complete"])
            self.assertNotIn("delta_margin", result)

    def test_nonfinite_or_malformed_scores_rejected(self):
        for scores in ([float("nan"), 0], [0, float("inf")], [True, 0], [1000], None):
            a = self.fixture(); b = copy.deepcopy(a); b["scores"] = scores
            with self.assertRaisesRegex(ValueError, "cash scores"):
                panel.pair(a, b)

    def test_stale_or_missing_helper_receipt_rejected(self):
        for receipt in (None, {}, {"calls": 718, "transformed_actions": 5},
                        {"calls": 719, "transformed_actions": -1}):
            a = self.fixture(); b = copy.deepcopy(a); b["helper"] = receipt
            with self.assertRaisesRegex(ValueError, "helper receipt"):
                panel.pair(a, b)

    def test_both_action_and_world_parity_are_required(self):
        a = self.fixture(); b = copy.deepcopy(a); b["world_sha256"] = "changed"
        result = panel.pair(a, b)
        self.assertTrue(result["same_action_trace"])
        self.assertFalse(result["same_world_trace"])

    def test_archive_drift_is_rejected_before_import_or_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); archive = root / "wrong.tar.gz"
            archive.write_bytes(b"not the authenticated archive")
            with self.assertRaisesRegex(ValueError, "archive drift"):
                materialize.build(archive, root, root / "out", root / "receipt",
                                  kind="disposal", mode="discard")
            self.assertFalse((root / "out").exists())


class OfficialFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = field.load(RUNTIME / "checks/reference/evaluator/evaluate.py", "s8_field_test_evaluator")
        cls.cache = RUNTIME / "checks/reference/engine"
        cls.loader = RUNTIME / "checks/reference/evaluator/loader.py"

    def run_fixture(self, *, seat=0, disposal=False, observed=True):
        engine, _ = self.ev.get_engine(self.cache, self.loader)
        cfg = self.ev.Struct({k: v.get("default") if isinstance(v, dict) else v
                              for k, v in engine.specification["configuration"].items()})
        if disposal:
            cfg.startingMoney = 10000
        cfg.seed = 101
        env = self.ev.Struct(configuration=cfg, done=False, info={})
        state = [self.ev.Struct(observation=self.ev.Struct(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
        engine.interpreter(state, env)
        self.assertIsNone(cfg.seed)
        census = field.Census(seat)
        original = field.install_observers(engine, census, state[0].observation.farms[seat], state[seat].observation.private) if observed else {}
        trace = hashlib.sha256()
        try:
            for step in range(719):
                for idx in range(2):
                    state[idx].observation.step = step
                    state[idx].action = (grower.parent_action(copy.deepcopy(state[idx].observation), cfg, disposal=disposal)
                                         if idx == seat else {"farmer": ["PASS"], "hands": [], "market": []})
                census.observe(state[seat].observation, state[seat].action)
                engine.interpreter(state, env)
                trace.update(field.encoded([dict(s) for s in state]))
            self.assertEqual([s.status for s in state], ["DONE", "DONE"])
            return trace.hexdigest(), census, state, cfg
        finally:
            for name, function in original.items():
                setattr(engine, name, function)

    def test_full_legal_growth_has_no_injected_state(self):
        _, c, state, _ = self.run_fixture()
        self.assertEqual(c.counts["returned_BUILD_COOP"], 1)
        self.assertEqual(c.counts["returned_PLACE"], 1)
        self.assertEqual(c.effects["goose_effective_FEED"], 30)
        self.assertEqual(c.effects["egg_produced"], 26)
        self.assertEqual(c.effects["egg_harvested"], 26)
        self.assertEqual(c.effects["egg_net_market_out"], 26)
        self.assertEqual(c.effects["fertilizer_collected"], 28)
        self.assertEqual(c.effects["fertilizer_eod_discarded"], 0)
        self.assertEqual(c.counts["h23_collect_physiology"], 26)
        self.assertEqual(c.effects["goose_escaped"], 0)
        self.assertEqual(state[0].observation.farms[0]["tiles"][4][4]["placed_day"], 0)

    def test_disposal_is_real_and_eggs_still_reach_market_both_seats(self):
        for seat in (0, 1):
            with self.subTest(seat=seat):
                _, c, _, cfg = self.run_fixture(seat=seat, disposal=True)
                self.assertEqual(cfg.startingMoney, 10000)
                self.assertEqual(c.effects["fertilizer_collected"], 28)
                self.assertEqual(c.effects["fertilizer_eod_discarded"], 23)
                self.assertEqual(c.effects["fertilizer_eod_admitted"], 5)
                self.assertEqual(c.effects["egg_harvested"], 26)
                self.assertEqual(c.effects["egg_net_market_out"], 26)
                self.assertEqual(c.effects["egg_eod_discarded"], 0)

    def test_passive_observers_leave_full_719_step_states_unchanged(self):
        plain = self.run_fixture(disposal=True, observed=False)
        observed = self.run_fixture(disposal=True, observed=True)
        self.assertEqual(plain[0], observed[0])
        self.assertEqual(plain[2], observed[2])

    def test_official_engine_pin_rejects_changed_transition(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in self.ev.ENGINE_BLOBS:
                (root / name).write_bytes((self.cache / name).read_bytes())
            p = root / "kaggriculture.py"
            p.write_text(p.read_text().replace('base = 1', 'base = 2', 1))
            with self.assertRaisesRegex(ValueError, "Official source mismatch"):
                self.ev.verify_sources(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    args, unknown = parser.parse_known_args()
    RUNTIME = args.runtime.resolve()
    unittest.main(argv=[sys.argv[0], *unknown])
