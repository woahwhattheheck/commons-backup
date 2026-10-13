#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Focused tests for the retained unit-capacity occurrence analyzer."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import sys
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ANALYZER_PATH = HERE / "check_unit_capacity_occurrence.py"
sys.path.insert(0, str(HERE))


def load_analyzer():
    spec = importlib.util.spec_from_file_location("unit_capacity_occurrence_under_test", ANALYZER_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load occurrence analyzer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load_analyzer()


def event(index, op, before, after, discarded=0, action=None):
    return {
        "unit_index": index,
        "op": op,
        "action": action or [op],
        "before_shed": before,
        "after_shed": after,
        "shed_delta": after - before,
        "discarded_units": discarded,
    }


def manifest_for(files):
    return {
        "schema": A.MANIFEST_SCHEMA,
        "files": {
            name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in files.items()
        },
    }


def write_zip(path, files):
    payloads = dict(files)
    payloads["MANIFEST.json"] = (
        json.dumps(manifest_for(files), sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(payloads):
            archive.writestr(name, payloads[name])
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PhaseMetricTests(unittest.TestCase):
    def test_reached_place_then_pickup_has_three_unit_hidden_peak(self):
        events = [
            event(0, "PLACE", 46, 52, action=["PLACE", "MELON", 6]),
            event(2, "PLACE", 52, 58, action=["PLACE", "MELON", 6]),
            event(6, "PLACE", 58, 64, action=["PLACE", "MELON", 6]),
            event(7, "PLACE", 64, 70, action=["PLACE", "MELON", 6]),
            event(9, "PICKUP", 70, 67, action=["PICKUP", "WHEAT", 3]),
        ]
        result = A.phase_metrics(46, events, 100)
        self.assertTrue(result["positive_then_negative"])
        self.assertEqual(result["interior_peak_shed"], 70)
        self.assertEqual(result["end_unit_shed"], 67)
        self.assertEqual(result["hidden_peak_above_start_and_end"], 3)
        self.assertFalse(result["hidden_peak_hit_capacity"])

    def test_starting_occupancy_can_dominate_later_internal_rise(self):
        events = [
            event(1, "PICKUP", 25, 20),
            event(8, "PLACE", 20, 23),
            event(10, "PICKUP", 23, 21),
        ]
        result = A.phase_metrics(25, events, 100)
        self.assertTrue(result["positive_then_negative"])
        self.assertEqual(result["hidden_peak_above_start_and_end"], 0)
        self.assertEqual(result["peak_shed"], 25)

    def test_drop_overflow_and_later_pickup_are_separate_signals(self):
        events = [
            event(0, "DROP", 98, 100, discarded=3),
            event(1, "PICKUP", 100, 96),
        ]
        result = A.phase_metrics(98, events, 100)
        self.assertTrue(result["drop_then_pickup"])
        self.assertTrue(result["hidden_peak_hit_capacity"])
        self.assertEqual(result["discarded_units"], 3)
        self.assertEqual(result["hidden_peak_above_start_and_end"], 2)

    def test_no_events_is_invalid(self):
        with self.assertRaisesRegex(ValueError, "no interpreter calls"):
            A.phase_metrics(0, [], 100)


class ArchiveTests(unittest.TestCase):
    def minimal_files(self):
        return {
            A.ENGINE_MEMBERS[0]: b"pass\n",
            A.ENGINE_MEMBERS[1]: b"{}\n",
            A.ENGINE_MEMBERS[2]: b"def resolve_episode_seed(env): return 1\n",
        }

    def test_whole_manifest_and_archive_digest_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.zip"
            digest = write_zip(path, self.minimal_files())
            members, source = A.read_verified_archive(path, digest)
            self.assertEqual(source["archive_sha256"], digest)
            self.assertEqual(source["manifested_files"], 3)
            self.assertEqual(set(members), {*self.minimal_files(), "MANIFEST.json"})
            with self.assertRaisesRegex(ValueError, "archive SHA-256 mismatch"):
                A.read_verified_archive(path, "0" * 64)

    def test_manifest_identity_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.zip"
            files = self.minimal_files()
            payloads = dict(files)
            manifest = manifest_for(files)
            manifest["files"][A.ENGINE_MEMBERS[0]]["bytes"] += 1
            payloads["MANIFEST.json"] = json.dumps(manifest).encode()
            with zipfile.ZipFile(path, "w") as archive:
                for name, data in payloads.items():
                    archive.writestr(name, data)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "manifest identity mismatch"):
                A.read_verified_archive(path, digest)

    def test_complete_stream_aliases_are_deduplicated(self):
        rows = b'{"configuration":{},"state":[]}\n{"configuration":{},"state":[]}\n'
        frames = gzip.compress(rows, mtime=0)
        result = json.dumps(
            {"status": "complete", "candidate_seat": 0, "steps": 1, "seed": 7}
        ).encode()
        members = {
            "evaluation/a.frames.jsonl.gz": frames,
            "evaluation/a.json": result,
            "evaluation/b.frames.jsonl.gz": frames,
            "evaluation/b.json": result,
            "evaluation/c.frames.jsonl.gz": frames,
            "evaluation/c.json": json.dumps({"status": "failed"}).encode(),
        }
        streams = A.discover_complete_streams(members)
        self.assertEqual(len(streams), 1)
        self.assertEqual(len(streams[0]["aliases"]), 2)


class EndToEndReplayTests(unittest.TestCase):
    def engine_files(self):
        source = REPO / "revenue/kaggriculture/cloud-execution-lab/reference/engine"
        if not source.exists():
            self.skipTest("repository reference engine is unavailable")
        return {
            A.ENGINE_MEMBERS[0]: (source / "kaggriculture.py").read_bytes(),
            A.ENGINE_MEMBERS[1]: (source / "kaggriculture.json").read_bytes(),
            A.ENGINE_MEMBERS[2]: (source / "utils.py").read_bytes(),
        }

    def build_short_archive(self, path):
        files = self.engine_files()
        engine = A.load_engine(files, "unit_capacity_short_fixture")
        configuration = A.Struct(
            {
                key: value.get("default") if isinstance(value, dict) else value
                for key, value in engine.specification["configuration"].items()
            }
        )
        configuration.episodeSteps = 4
        configuration.seed = 31337
        environment = A.Struct(configuration=configuration, done=False, info={})
        state = [
            A.Struct(observation=A.Struct(), action={}, status="ACTIVE", reward=0)
            for _ in range(2)
        ]
        engine.interpreter(state, environment)
        rows = [
            {
                "configuration": A.plain(configuration),
                "frame": 0,
                "info": A.plain(environment.info),
                "state": A.plain(state),
            }
        ]
        for step in range(3):
            for seat in range(2):
                state[seat].observation.step = step
                state[seat].observation.remainingOverageTime = 0
                state[seat].action = {"farmer": ["PASS"], "hands": [], "market": []}
            engine.interpreter(state, environment)
            rows.append(
                {
                    "configuration": A.plain(configuration),
                    "frame": step + 1,
                    "info": A.plain(environment.info),
                    "state": A.plain(state),
                }
            )
        frame_payload = gzip.compress(
            b"".join(A.encoded(row) + b"\n" for row in rows), mtime=0
        )
        result = {
            "status": "complete",
            "candidate_seat": 0,
            "steps": 3,
            "seed": 31337,
            "arm": "short-pass-fixture",
            "scores": [state[0].reward, state[1].reward],
            "trace_sha256": "fixture-not-a-scored-trace",
        }
        files["evaluation/short.frames.jsonl.gz"] = frame_payload
        files["evaluation/short.json"] = json.dumps(result, sort_keys=True).encode()
        return write_zip(path, files)

    def test_short_recorded_stream_replays_without_policy_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "short.zip"
            digest = self.build_short_archive(archive)
            result = A.analyze(archive, digest)
        summary = result["summary"]
        self.assertEqual(summary["unique_complete_stream_seat_pairs"], 1)
        self.assertEqual(summary["verified_recorded_transitions"], 3)
        self.assertEqual(summary["candidate_unit_actions"], 3)
        self.assertEqual(summary["policy_calls"], 0)
        self.assertEqual(summary["new_scored_games"], 0)
        self.assertEqual(summary["positive_then_negative_phases"], 0)


class SummaryTests(unittest.TestCase):
    def test_maxima_are_not_summed_across_streams(self):
        base = {
            "counters": {
                "phases": 1,
                "unit_actions": 1,
                "max_shed_occupancy": 100,
                "max_hidden_peak_units": 3,
            },
            "aliases": [{}],
            "occurrences": [],
        }
        other = copy.deepcopy(base)
        other["counters"]["max_shed_occupancy"] = 81
        other["counters"]["max_hidden_peak_units"] = 2
        report = A.summarize([base, other], {"archive_sha256": "x"})
        self.assertEqual(report["summary"]["max_shed_occupancy"], 100)
        self.assertEqual(report["summary"]["max_hidden_peak_units"], 3)

    def test_occurrence_signatures_ignore_absolute_occupancy(self):
        row = {
            "step": 10,
            "shed_changes": [
                {"unit_index": 0, "action": ["PLACE", "MILK", 3], "shed_delta": 3}
            ],
        }
        changed = copy.deepcopy(row)
        changed["pre_shed"] = 50
        self.assertEqual(A.occurrence_signature(row), A.occurrence_signature(changed))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args, unittest_args = parser.parse_known_args(argv)
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    text = stream.getvalue()
    print(text, end="")
    report = {
        "schema": "titan.unit-capacity-occurrence-tests.v1",
        "tests_run": result.testsRun,
        "failures": [str(test) for test, _ in result.failures],
        "errors": [str(test) for test, _ in result.errors],
        "skipped": [
            {"test": str(test), "reason": reason} for test, reason in result.skipped
        ],
        "successful": result.wasSuccessful(),
        "analyzer_sources_sha256": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in A.SOURCE_FILES},
        "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "policy_calls": 0,
        "new_scored_games": 0,
        "log": text,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
