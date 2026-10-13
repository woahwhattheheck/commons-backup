# SPDX-License-Identifier: Apache-2.0
"""Pinned official-engine price-stream proof; no TITAN policy is installed.

Set EXEC_PACE_ENGINE_DIR and EXEC_PACE_LOADER to already-present source files.
All dependencies authenticate before import; missing bytes never download.
EXEC_PACE_SOURCE selects the repaired helper or the preserved negative control.
"""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("EXEC_PACE_SOURCE", HERE / "r04_exec_adaptive.py"))
DONOR = HERE / "raw/r04_exec_adaptive.py"
PINS = {
    "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}
LOADER_PIN = "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5"
DONOR_PIN = "0ef551145dbcac9884e7d1710bcf11238dafc504"
REPORT = {}


def git_blob(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def warm(module, rows):
    module.reset()
    for row in rows:
        module.note_prices(copy.deepcopy(row))


class OfficialPriceStreams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Authenticate *all* required files before the loader can run.
        engine_dir = Path(os.environ["EXEC_PACE_ENGINE_DIR"])
        loader_path = Path(os.environ["EXEC_PACE_LOADER"])
        for name, expected in PINS.items():
            actual = git_blob(engine_dir / name)
            if actual != expected:
                raise RuntimeError(f"engine blob mismatch: {name}: {actual}")
        if git_blob(loader_path) != LOADER_PIN or git_blob(DONOR) != DONOR_PIN:
            raise RuntimeError("loader/donor blob mismatch")
        loader = load(loader_path, "exec_pace_pinned_engine_loader")
        engine, hashes = loader.get_engine(engine_dir)
        cls.streams = []
        summaries = []
        for seed in (2611151001, 2611151002):
            streams = [[], []]
            def actor(seat):
                def call(obs, cfg):
                    # Keep only the actual public fields the helper consumes.
                    streams[seat].append({"step": obs["step"], "player": obs["player"],
                                          "market": copy.deepcopy(obs["market"])})
                    return engine.starter_agent(obs)
                return call
            game = loader.play(engine, [actor(0), actor(1)], seed)
            if game["steps"] != 719 or game["status"] != ["DONE", "DONE"]:
                raise RuntimeError("unexpected official episode boundary")
            summaries.append({"seed": seed, "callbacks_per_seat": game["steps"],
                              "status": game["status"]})
            cls.streams.extend(streams)
        serialized = json.dumps(cls.streams, sort_keys=True, separators=(",", ":")).encode()
        REPORT.update(engine_blobs=PINS, loader_blob=LOADER_PIN, donor_blob=DONOR_PIN,
                      subject_blob=git_blob(SOURCE), engine_sha256=hashes,
                      trace_sha256=hashlib.sha256(serialized).hexdigest(),
                      episodes=summaries, observed_callbacks=2876,
                      scope="Official starter/starter public-price observations, not TITAN gameplay economics")
        cls.m = load(SOURCE, "exec_pace_engine_subject")

    def setUp(self):
        self.m.reset()

    def positive_window(self):
        for rows in self.streams:
            for end in range(24, len(rows)):
                for good in self.m.GOODS:
                    if rows[end]["market"]["prices"][good] > rows[end-24]["market"]["prices"][good]:
                        return rows[end-24:end+1], good
        self.fail("official source generated no positive endpoint window")

    def test_01_complete_price_streams_match_exact_donor(self):
        donor = load(DONOR, "exec_pace_engine_exact_donor")
        decisions = rising = 0
        for rows in self.streams:
            donor.reset()
            self.m.reset()
            for obs in rows:
                before = copy.deepcopy(obs)
                donor.note_prices(obs)
                self.m.note_prices(obs)
                self.assertEqual(obs, before)
                for good in self.m.GOODS:
                    self.assertEqual(self.m.slope(good), donor.slope(good))
                    self.assertEqual(self.m.rising(good), donor.rising(good))
                    rising += int(self.m.rising(good))
                    decisions += 1
        self.assertEqual(decisions, 20132)
        self.assertGreater(rising, 0)
        REPORT.update(complete_stream_comparisons=decisions, rising_decisions=rising,
                      complete_stream_mismatches=0)

    def test_02_engine_quotes_satisfy_exact_positive_integer_domain(self):
        for rows in self.streams:
            for obs in rows:
                self.assertIn(obs["player"], (0, 1))
                for good in self.m.GOODS:
                    value = obs["market"]["prices"][good]
                    self.assertIs(type(value), int)
                    self.assertGreaterEqual(value, 1)

    def test_03_real_positive_window_duplicate_is_idempotent(self):
        rows, good = self.positive_window()
        warm(self.m, rows)
        expected = self.m.slope(good)
        self.assertTrue(self.m.rising(good))
        self.m.note_prices(copy.deepcopy(rows[-1]))
        self.assertEqual(self.m.slope(good), expected)
        self.assertTrue(self.m.rising(good))

    def test_04_real_quote_does_not_certify_24_missing_quotes(self):
        for rows in self.streams:
            for good in self.m.GOODS:
                modified = copy.deepcopy(rows[:25])
                for row in modified[:-1]:
                    del row["market"]["prices"][good]
                warm(self.m, modified)
                self.assertIsNone(self.m.slope(good))
                self.assertFalse(self.m.rising(good))

    def test_05_real_sparse_observations_restart_warmup(self):
        for rows in self.streams:
            warm(self.m, rows[:241:10])
            for good in self.m.GOODS:
                self.assertIsNone(self.m.slope(good))

    def test_06_invalid_callback_after_real_positive_window_clears(self):
        rows, good = self.positive_window()
        warm(self.m, rows)
        obs = copy.deepcopy(rows[-1])
        obs["step"] = None
        self.m.note_prices(obs)
        self.assertFalse(self.m.rising(good))
        self.assertIsNone(self.m.slope(good))

    def test_07_cross_seat_continuation_restarts_warmup(self):
        rows, good = self.positive_window()
        warm(self.m, rows)
        obs = copy.deepcopy(rows[-1])
        obs["step"] += 1
        obs["player"] = 1 - obs["player"]
        self.m.note_prices(obs)
        self.assertIsNone(self.m.slope(good))

    def test_08_nonfinite_quote_does_not_certify_momentum(self):
        rows, good = self.positive_window()
        warm(self.m, rows[:-1])
        obs = copy.deepcopy(rows[-1])
        obs["market"]["prices"][good] = float("inf")
        self.m.note_prices(obs)
        self.assertFalse(self.m.rising(good))
        self.assertIsNone(self.m.slope(good))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OfficialPriceStreams)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    REPORT.update(tests_run=result.testsRun, failures=len(result.failures),
                  errors=len(result.errors), skipped=len(result.skipped),
                  optimized=not __debug__)
    print(json.dumps(REPORT, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
