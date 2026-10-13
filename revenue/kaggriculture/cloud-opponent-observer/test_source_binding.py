"""Bind the real pinned COK source to the preserved official lazy loader."""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import observe
import stream_observations as stream
from test_stream_observations import fixture

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("T07_COK_SOURCE", HERE / "sources/cok-v10/main.py"))
PACK = Path(os.environ.get("T07_PACK", HERE.parent / "cloud-pack"))


class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "cok.py"
        self.original = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), observe.SOURCE_SHA256)
        self.source.write_bytes(self.original)
        self.changed = self.original + b"\n_V10_V5_GATE_STEP = 73\n"
        self.real_load = observe.load_official

    def load_after(self, change):
        def load(pack):
            change()
            return self.real_load(pack)
        return patch.object(observe, "load_official", side_effect=load)

    def test_changed_source_between_verification_and_capture_is_rejected(self):
        with self.load_after(lambda: self.source.write_bytes(self.changed)):
            with self.assertRaisesRegex(ValueError, "official loader captured"):
                observe.CokObserver(self.source, PACK)
        self.assertEqual(self.source.read_bytes(), self.changed)

    def test_atomic_path_replacement_during_construction_is_rejected(self):
        replacement = self.root / "replacement.py"
        replacement.write_bytes(self.changed)
        with self.load_after(lambda: os.replace(replacement, self.source)):
            with self.assertRaisesRegex(ValueError, "official loader captured"):
                observe.CokObserver(self.source, PACK)

    def test_removed_source_during_capture_is_rejected_before_policy(self):
        with self.load_after(self.source.unlink):
            with self.assertRaises((ValueError, FileNotFoundError)):
                observe.CokObserver(self.source, PACK)

    def test_retained_text_not_a_later_path_read_controls_binding(self):
        # Actual build_agent reads the changed file, then the file is restored.
        # Looking at the final path would miss the differing captured program.
        captured = []
        def load(pack):
            module = self.real_load(pack)
            contract = module.contract()
            actual = contract["build_agent"]
            def build(*args):
                self.source.write_bytes(self.changed)
                result = actual(*args)
                captured.append(inspect.getclosurevars(result[0]).nonlocals["raw_agent"])
                self.source.write_bytes(self.original)
                return result
            contract["build_agent"] = build
            return module
        with patch.object(observe, "load_official", side_effect=load):
            with self.assertRaisesRegex(ValueError, "official loader captured"):
                observe.CokObserver(self.source, PACK)
        self.assertEqual(captured, [self.changed.decode("utf-8")])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_valid_constructor_remains_lazy_and_uses_original_build_agent(self):
        counts = {"build": 0, "compile": 0, "read": 0}
        def load(pack):
            module = self.real_load(pack)
            ns = module.contract()
            build, compile_source, read = ns["build_agent"], ns["get_last_callable"], ns["read_file"]
            def counted_build(*args):
                counts["build"] += 1
                return build(*args)
            def counted_compile(*args, **kwargs):
                counts["compile"] += 1
                return compile_source(*args, **kwargs)
            def counted_read(*args, **kwargs):
                counts["read"] += 1
                return read(*args, **kwargs)
            ns.update(build_agent=counted_build, get_last_callable=counted_compile, read_file=counted_read)
            return module
        with patch.object(observe, "load_official", side_effect=load):
            actor = observe.CokObserver(self.source, PACK)
        self.assertEqual(counts, {"build": 1, "compile": 0, "read": 1})
        before = inspect.getclosurevars(actor.call).nonlocals
        self.assertIsNone(before["agent"])
        self.assertEqual(before["raw_agent"], self.original.decode("utf-8"))
        actor.act(fixture(), {})
        actor.act(fixture(), {})
        self.assertEqual(counts, {"build": 1, "compile": 1, "read": 1})
        self.assertEqual(actor.calls, 2)
        self.assertTrue(actor.last_record["cached_retry"])

    def test_path_change_after_construction_does_not_change_the_actor(self):
        actor = observe.CokObserver(self.source, PACK)
        expected = observe.load_official(PACK).make_agent(self.source)
        self.source.write_bytes(self.changed)
        obs = fixture()
        self.assertEqual(actor.act(obs, {}), expected(copy.deepcopy(obs), {}))
        self.assertTrue(actor.last_record["gate_after"])
        self.assertIsNone(actor.last_record["telemetry_error"])
        self.assertEqual(actor._globals()["_V10_V5_GATE_STEP"], 72)
        with self.assertRaisesRegex(ValueError, "declared T07 revision"):
            observe.CokObserver(self.source, PACK)

    def test_original_missing_and_wrong_source_rejected_without_loading(self):
        for mode in ("missing", "different"):
            if mode == "missing":
                self.source.unlink(missing_ok=True)
            else:
                self.source.write_bytes(self.changed)
            with patch.object(observe, "load_official", side_effect=AssertionError("Unexpected load")):
                with self.assertRaises((ValueError, FileNotFoundError)):
                    observe.CokObserver(self.source, PACK)

    def test_official_newline_normalization_preserves_captured_program(self):
        # Hash describes the initial verified bytes. The official UTF-8 reader
        # normalizes newlines; if its captured text is identical, the program is
        # identical even if the later filesystem representation has changed.
        with self.load_after(lambda: self.source.write_bytes(self.original.replace(b"\n", b"\r\n"))):
            actor = observe.CokObserver(self.source, PACK)
        self.assertEqual(inspect.getclosurevars(actor.call).nonlocals["raw_agent"],
                         self.original.decode("utf-8"))
        actor.act(fixture(), {})
        self.assertTrue(actor.last_record["gate_after"])

    def test_successful_actions_telemetry_and_inputs_match_existing_source(self):
        actors, controls = {}, {}
        calls = 0
        for step in (0, 71, 72, 72, 167, 168, 169, 718):
            for seat in (0, 1):
                if seat not in actors:
                    actors[seat] = observe.CokObserver(self.source, PACK)
                    controls[seat] = observe.load_official(PACK).make_agent(self.source)
                obs = fixture(step, seat, shops=("BAKERY", "YARN_STORE"))
                saved = copy.deepcopy(obs)
                self.assertEqual(actors[seat].act(obs, {}), controls[seat](copy.deepcopy(obs), {}))
                self.assertEqual(obs, saved)
                self.assertIsNone(actors[seat].last_record["telemetry_error"])
                self.assertEqual(actors[seat].last_record["source_sha256"], observe.SOURCE_SHA256)
                calls += 1
        self.assertEqual(calls, 16)
        self.assertEqual(actors[0].calls, 8)
        self.assertEqual(actors[1].calls, 8)

    def test_stream_drift_preserves_previous_completed_outputs(self):
        incoming, telemetry, summary = (self.root / n for n in ("input.jsonl", "telemetry.jsonl", "summary.json"))
        incoming.write_text(json.dumps({"observation": fixture()}) + "\n", encoding="utf-8")
        telemetry.write_bytes(b"previous telemetry\n")
        summary.write_bytes(b"previous summary\n")
        with self.load_after(lambda: self.source.write_bytes(self.changed)):
            with self.assertRaisesRegex(ValueError, "official loader captured"):
                stream.run_jsonl(self.source, PACK, incoming, telemetry, summary)
        self.assertEqual(telemetry.read_bytes(), b"previous telemetry\n")
        self.assertEqual(summary.read_bytes(), b"previous summary\n")
        self.assertFalse([p for p in self.root.iterdir() if p.name.startswith(".")])


if __name__ == "__main__":
    unittest.main()
