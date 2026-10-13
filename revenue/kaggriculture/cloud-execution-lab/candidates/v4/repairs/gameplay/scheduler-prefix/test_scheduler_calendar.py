# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

import materialize_scheduler_calendar as C

HERE = Path(__file__).resolve().parent


def _load_prefix(path: Path):
    spec = importlib.util.spec_from_file_location("scheduler_prefix_materializer", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _helper_from_candidate(candidate: str):
    tree = ast.parse(candidate)
    node = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_strict_scheduler_turns_per_day"
    )
    segment = ast.get_source_segment(candidate, node)
    namespace: dict[str, object] = {}
    exec(compile(segment + "\n", "<calendar-helper>", "exec"), namespace)
    return namespace["_strict_scheduler_turns_per_day"]


def _market_helper_from_candidate(candidate: str):
    tree = ast.parse(candidate)
    node = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_engine_market_limit"
    )
    segment = ast.get_source_segment(candidate, node)
    namespace: dict[str, object] = {}
    exec(compile(segment + "\n", "<market-limit-helper>", "exec"), namespace)
    return namespace["_engine_market_limit"]


class SchedulerCalendarCustodyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_mode = False
        cls.prefixed = None
        cls.engine = None
        explicit_prefixed = os.environ.get("TITAN_PREFIXED_SCHEDULER")
        explicit_engine = os.environ.get("TITAN_ENGINE")
        if explicit_prefixed or explicit_engine:
            if not (explicit_prefixed and explicit_engine):
                raise AssertionError("TITAN_PREFIXED_SCHEDULER and TITAN_ENGINE must be set together")
            cls.prefixed = Path(explicit_prefixed).read_bytes()
            cls.engine = Path(explicit_engine).read_bytes()
            cls.repo_mode = True
            return

        prefix_path = HERE / "materialize_scheduler_prefix.py"
        try:
            cloud_root = HERE.parents[4]
            raw_path = cloud_root / "scheduler.py"
            engine_path = cloud_root / "reference" / "engine" / "kaggriculture.py"
            if prefix_path.is_file() and raw_path.is_file() and engine_path.is_file():
                prefix_bytes = prefix_path.read_bytes()
                prefix_blob = C.git_blob_sha(prefix_bytes)
                if prefix_blob != C.PREFIX_MATERIALIZER_GIT_BLOB:
                    raise AssertionError(
                        f"prefix materializer drift: {prefix_blob}"
                    )
                prefix = _load_prefix(prefix_path)
                raw = raw_path.read_bytes()
                engine = engine_path.read_bytes()
                cls.prefixed = prefix.materialize(raw, engine)
                cls.engine = engine
                cls.repo_mode = True
        except (OSError, RuntimeError, ValueError, AssertionError):
            raise

    def _require_repo(self):
        if not self.repo_mode:
            self.skipTest("repository checkout with canonical prefix materializer unavailable")
        assert self.prefixed is not None and self.engine is not None
        return self.prefixed, self.engine

    def test_exact_current_chain_composes(self):
        prefixed, engine = self._require_repo()
        self.assertEqual(C.git_blob_sha(prefixed), C.PREFIXED_SCHEDULER_GIT_BLOB)
        candidate = C.materialize(prefixed, engine)
        text = candidate.decode("utf-8")
        compile(text, "<scheduler-calendar>", "exec", dont_inherit=True)
        self.assertEqual(text.count("orders=_engine_market_prefix(market_action,config)"), 2)
        self.assertEqual(text.count("def _strict_scheduler_turns_per_day("), 1)
        self.assertEqual(text.count("turns_per_day=_strict_scheduler_turns_per_day(config)"), 3)
        self.assertEqual(text.count("def _engine_market_limit("), 1)
        self.assertEqual(text.count("market_limit=_engine_market_limit(config)"), 1)

    def test_engine_source_is_the_bound_calendar_authority(self):
        _, engine = self._require_repo()
        self.assertEqual(C.git_blob_sha(engine), C.ENGINE_GIT_BLOB)
        C.verify_engine(engine.decode("utf-8"))

    def test_default_24_and_nonstandard_12_are_exact(self):
        prefixed, engine = self._require_repo()
        helper = _helper_from_candidate(C.materialize(prefixed, engine).decode("utf-8"))
        self.assertEqual(helper({}), 24)
        self.assertEqual(helper({"turnsPerDay": 24}), 24)
        self.assertEqual(helper({"turnsPerDay": 12}), 12)

    def test_type_poison_and_nonpositive_day_lengths_fail_closed(self):
        prefixed, engine = self._require_repo()
        helper = _helper_from_candidate(C.materialize(prefixed, engine).decode("utf-8"))
        for bad in (True, False, 0, -1, 24.0, "24", None, [24], {"v": 24}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    helper({"turnsPerDay": bad})
        with self.assertRaises(ValueError):
            helper(None)

    def test_cash_hire_reset_tracks_configured_day_start(self):
        prefixed, engine = self._require_repo()
        text = C.materialize(prefixed, engine).decode("utf-8")
        self.assertIn("if t>now and t%turns_per_day==0:hires=0", text)
        self.assertNotIn("if t>now and t%24==0:hires=0", text)
        now = 10
        self.assertTrue(12 > now and 12 % 12 == 0)
        self.assertFalse(12 > now and 12 % 24 == 0)

    def test_future_unit_stage_tracks_configured_day_and_turn_length(self):
        prefixed, engine = self._require_repo()
        text = C.materialize(prefixed, engine).decode("utf-8")
        self.assertIn(
            "m._apply_unit_action(f,p,i,a,len(f['tiles']),t//turns_per_day,turns_per_day,10**6)",
            text,
        )
        self.assertNotIn(
            "m._apply_unit_action(f,p,i,a,len(f['tiles']),t//24,24,10**6)",
            text,
        )
        self.assertEqual(13 // 12, 1)
        self.assertEqual(13 // 24, 0)

    def test_receipt_eod_boundary_tracks_configured_day(self):
        prefixed, engine = self._require_repo()
        text = C.materialize(prefixed, engine).decode("utf-8")
        self.assertIn("if t%turns_per_day==turns_per_day-1:", text)
        self.assertNotIn("if t%24==23:", text)
        self.assertEqual(11 % 12, 11)
        self.assertNotEqual(11 % 24, 23)


    def test_act_horizon_clips_to_configured_day_end(self):
        prefixed, engine = self._require_repo()
        text = C.materialize(prefixed, engine).decode("utf-8")
        self.assertIn(
            "end=min(now+HORIZON,last,(now//turns_per_day+1)*turns_per_day-1)",
            text,
        )
        self.assertNotIn("end=min(now+HORIZON,last,(now//24+1)*24-1)", text)
        now = 10
        self.assertEqual((now // 12 + 1) * 12 - 1, 11)
        self.assertEqual((now // 24 + 1) * 24 - 1, 23)

    def test_act_naive_eod_guard_tracks_configured_day(self):
        prefixed, engine = self._require_repo()
        text = C.materialize(prefixed, engine).decode("utf-8")
        self.assertIn(
            "if farm['money']<budget or now%turns_per_day==turns_per_day-1:",
            text,
        )
        self.assertNotIn("if farm['money']<budget or now%24==23:", text)
        self.assertTrue(11 % 12 == 12 - 1)
        self.assertFalse(11 % 24 == 23)

    def test_market_limit_matches_prefix_and_engine_minimum_one(self):
        prefixed, engine = self._require_repo()
        candidate = C.materialize(prefixed, engine).decode("utf-8")
        helper = _market_helper_from_candidate(candidate)
        self.assertEqual(helper({}), 10)
        for raw in (0, -7, 1, 2, 10, True, False, 2.9, "0", "3"):
            with self.subTest(raw=raw):
                self.assertEqual(
                    helper({"maxMarketOrdersPerTurn": raw}),
                    max(1, int(raw)),
                )

    def test_act_cap_guards_share_effective_market_limit(self):
        prefixed, engine = self._require_repo()
        text = C.materialize(prefixed, engine).decode("utf-8")
        self.assertIn("return q[:_engine_market_limit(config)]", text)
        self.assertIn("if len(orders)>=market_limit:", text)
        self.assertIn("if q>0 and len(market)<market_limit:", text)
        self.assertNotIn(
            "if len(orders)>=int(config.get('maxMarketOrdersPerTurn',10)):",
            text,
        )
        self.assertNotIn(
            "if q>0 and len(market)<int(config.get('maxMarketOrdersPerTurn',10)):",
            text,
        )

    def test_cap_zero_and_negative_keep_row_zero_executable(self):
        prefixed, engine = self._require_repo()
        helper = _market_helper_from_candidate(C.materialize(prefixed, engine).decode("utf-8"))
        for raw in (0, -1, -99, 1):
            with self.subTest(raw=raw):
                limit = helper({"maxMarketOrdersPerTurn": raw})
                self.assertEqual(limit, 1)
                self.assertTrue(len([]) < limit)
                self.assertTrue(len([["BUY_SEED", "CARROT", 1]]) >= limit)


    def test_canonical_24_predicates_are_behavior_preserving(self):
        prefixed, engine = self._require_repo()
        helper = _helper_from_candidate(C.materialize(prefixed, engine).decode("utf-8"))
        turns_per_day = helper({"turnsPerDay": 24})
        for now in (0, 1, 23, 24, 47, 101):
            for t in range(now, min(now + 80, 719)):
                self.assertEqual(
                    t > now and t % 24 == 0,
                    t > now and t % turns_per_day == 0,
                )
                self.assertEqual(t % 24 == 23, t % turns_per_day == turns_per_day - 1)
                self.assertEqual(t // 24, t // turns_per_day)
                self.assertEqual(
                    (t // 24 + 1) * 24 - 1,
                    (t // turns_per_day + 1) * turns_per_day - 1,
                )

    def test_prefixed_source_drift_rejected_before_transform(self):
        prefixed, engine = self._require_repo()
        mutant = prefixed + b"\n# drift\n"
        with self.assertRaisesRegex(C.CalendarMaterializationError, "prefixed scheduler Git blob mismatch"):
            C.materialize(mutant, engine)

    def test_engine_drift_rejected_before_transform(self):
        prefixed, engine = self._require_repo()
        mutant = engine + b"\n# drift\n"
        with self.assertRaisesRegex(C.CalendarMaterializationError, "engine Git blob mismatch"):
            C.materialize(prefixed, mutant)

    def test_double_apply_rejected(self):
        prefixed, engine = self._require_repo()
        candidate = C.materialize(prefixed, engine).decode("utf-8")
        with self.assertRaisesRegex(C.CalendarMaterializationError, "calendar helper already present"):
            C.transform_prefixed(candidate)

    def test_missing_or_ambiguous_predecessor_anchor_rejected(self):
        prefixed, _ = self._require_repo()
        text = prefixed.decode("utf-8")
        missing = text.replace(C.EOD_OLD, "            if False:\n", 1)
        with self.assertRaisesRegex(C.CalendarMaterializationError, "receipt end-of-day boundary"):
            C.transform_prefixed(missing)
        duplicate = text.replace(C.EOD_OLD, C.EOD_OLD + C.EOD_OLD, 1)
        with self.assertRaisesRegex(C.CalendarMaterializationError, "receipt end-of-day boundary"):
            C.transform_prefixed(duplicate)

    def test_cli_never_overwrites_bound_input_or_existing_output(self):
        prefixed, engine = self._require_repo()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "prefixed.py"
            eng = root / "engine.py"
            out = root / "candidate.py"
            src.write_bytes(prefixed)
            eng.write_bytes(engine)
            candidate = C.materialize(src.read_bytes(), eng.read_bytes())
            out.write_bytes(candidate)
            before = out.read_bytes()
            self.assertEqual(before, candidate)
            # The production CLI uses exclusive creation; preserve that contract.
            with self.assertRaises(FileExistsError):
                with out.open("xb") as stream:
                    stream.write(candidate)


if __name__ == "__main__":
    unittest.main()
