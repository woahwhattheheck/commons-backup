"""Exercise the streaming consumer with the actual retained COK source/loader."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import observe
import stream_observations as stream

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("T07_COK_SOURCE", HERE / "sources/cok-v10/main.py"))
PACK = Path(os.environ.get("T07_PACK", HERE.parent / "cloud-pack"))


def fixture(step=72, seat=0, qualifies=True, shops=("BAKERY",)):
    farm = {"money": 1000, "tiles": [[{"kind": "EMPTY"} for _ in range(8)] for _ in range(8)],
            "farmer": [3, 3], "hands": [], "shedCapacity": 100}
    farms = [copy.deepcopy(farm), copy.deepcopy(farm)]
    farms[seat]["money"] = 999 if qualifies else 1000
    values = ["COW"] + ["SHEEP"] * 4 + ["WHEAT"] * 5 + ["MELON"] * 4
    for index, kind in enumerate(values):
        key = "animal" if kind in ("COW", "SHEEP") else "crop"
        farms[1-seat]["tiles"][index//8][index%8] = {
            "kind": "PASTURE" if key == "animal" else "FIELD", key: kind}
    return {"step": step, "day": step//24, "hour": step%24, "player": seat,
            "farms": farms, "town": {"unlocked_shops": list(shops)}, "market": {},
            "private": {"shed": {}, "inventories": [{}]}, "remainingOverageTime": 0}


class StreamingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.input = self.root / "input.jsonl"
        self.out = self.root / "telemetry.jsonl"
        self.summary = self.root / "summary.json"

    def write(self, rows):
        self.input.write_text("".join(json.dumps(row) + "\n" if row is not None else "\n"
                                      for row in rows), encoding="utf-8")

    def run_stream(self):
        return stream.run_jsonl(SOURCE, PACK, self.input, self.out, self.summary)

    def assert_no_temps(self):
        self.assertFalse([p for p in self.root.iterdir() if p.name.startswith('.')])

    def cli(self):
        return subprocess.run([sys.executable, str(HERE / "stream_observations.py"),
            "--source", str(SOURCE), "--pack", str(PACK), "--input", str(self.input),
            "--output", str(self.out), "--summary", str(self.summary)],
            capture_output=True, text=True)

    def test_exact_legacy_outputs_interleaved_matches_seats_and_retries(self):
        rows = []
        baseline_calls = {}
        for step in (0, 71, 72, 72, 168, 169):
            for match, qualifies in (("open", True), ("closed", False)):
                for seat in (0, 1):
                    obs = fixture(step, seat, qualifies, ("BAKERY", "YARN_STORE"))
                    key = match, seat
                    if key not in baseline_calls:
                        baseline_calls[key] = observe.load_official(PACK).make_agent(SOURCE)
                    rows.append({"match_id": match, "observation": obs,
                        "expected_action": baseline_calls[key](copy.deepcopy(obs), {})})
            rows.append(None)
        self.write(rows)
        original = self.input.read_bytes()
        old_out, old_summary = self.root/'old.jsonl', self.root/'old-summary.json'
        expected = observe.run_jsonl(SOURCE, PACK, self.input, old_out, old_summary)
        result = self.run_stream()
        self.assertEqual(result, expected)
        self.assertEqual(self.out.read_bytes(), old_out.read_bytes())
        self.assertEqual(self.summary.read_bytes(), old_summary.read_bytes())
        self.assertEqual(original, self.input.read_bytes())
        self.assertEqual(len(result['actors']), 4)
        self.assertTrue(all(a['expected_action_mismatches'] == 0 for a in result['actors']))
        self.assertTrue(all(a['cached_retries'] == 1 for a in result['actors']))
        self.assert_no_temps()

    def test_iterator_is_lazy_and_calls_original_once_per_row(self):
        calls = []
        actual = observe.CokObserver
        class CountingObserver(actual):
            def act(self, *args, **kwargs):
                calls.append(1)
                return super().act(*args, **kwargs)
        lines = iter([json.dumps({'observation': fixture()}), 'not-json\n'])
        with patch.object(stream, 'CokObserver', CountingObserver):
            iterator = stream.iter_records(SOURCE, PACK, lines)
            self.assertEqual(calls, [])
            record = next(iterator)
            self.assertTrue(record['gate_after'])
            self.assertEqual(len(calls), 1)
            with self.assertRaisesRegex(ValueError, 'line 2'):
                next(iterator)
            self.assertEqual(len(calls), 1)

    def test_late_parse_errors_preserve_both_previous_outputs(self):
        for bad in ('bad json\n', '[]\n', '{}\n', '{"observation":null}\n'):
            self.write([{'observation': fixture()}])
            with self.input.open('a') as f: f.write(bad)
            self.out.write_bytes(b'old telemetry\n'); self.summary.write_bytes(b'old summary\n')
            before = self.input.read_bytes()
            with self.assertRaisesRegex(ValueError, 'line 2'):
                self.run_stream()
            self.assertEqual(self.out.read_bytes(), b'old telemetry\n')
            self.assertEqual(self.summary.read_bytes(), b'old summary\n')
            self.assertEqual(self.input.read_bytes(), before)
            self.assert_no_temps()

    def test_source_failure_and_missing_output_directory_leave_no_artifacts(self):
        self.write([{'observation': fixture()}])
        wrong = self.root / 'wrong.py'; wrong.write_text('print("not executed")\n')
        with self.assertRaises(ValueError):
            stream.run_jsonl(wrong, PACK, self.input, self.out, self.summary)
        self.assertFalse(self.out.exists()); self.assertFalse(self.summary.exists())
        with self.assertRaises(OSError):
            stream.run_jsonl(SOURCE, PACK, self.input, self.out, self.root/'absent'/'summary.json')
        self.assertFalse(self.out.exists()); self.assert_no_temps()

    def test_direct_symbolic_and_hard_link_input_aliases(self):
        self.write([{'observation': fixture()}])
        for original in (self.input, SOURCE):
            before = original.read_bytes()
            for mode in ('direct', 'symlink', 'hardlink'):
                alias = self.root / ('alias-'+mode)
                if mode == 'direct': alias = original
                elif mode == 'symlink': alias.symlink_to(original)
                else: os.link(original, alias)
                for destination in ('telemetry', 'summary'):
                    outputs = (alias, self.summary) if destination == 'telemetry' else (self.out, alias)
                    with self.assertRaises(ValueError):
                        stream.run_jsonl(SOURCE, PACK, self.input, *outputs)
                    self.assertEqual(original.read_bytes(), before)
                if mode != 'direct': alias.unlink()
        self.assert_no_temps()

    def test_output_pair_aliases_and_normal_symlink_destination(self):
        self.write([{'observation': fixture()}]); self.out.write_bytes(b'old\n')
        os.link(self.out, self.summary)
        with self.assertRaises(ValueError): self.run_stream()
        self.assertEqual(self.out.read_bytes(), b'old\n')
        self.summary.unlink()
        target = self.root/'actual-summary.json'
        self.summary.symlink_to(target)
        self.run_stream()
        self.assertTrue(self.summary.is_symlink())
        self.assertEqual(json.loads(target.read_text())['actors'][0]['calls'], 1)

    def test_second_replace_error_restores_existing_outputs(self):
        self.write([{'observation': fixture()}])
        self.out.write_bytes(b'old log'); self.summary.write_bytes(b'old summary')
        real_replace = os.replace
        def fail_summary(source, destination):
            if Path(destination) == self.summary:
                raise OSError('summary target unavailable')
            return real_replace(source, destination)
        with patch.object(stream.os, 'replace', fail_summary):
            with self.assertRaises(OSError): self.run_stream()
        self.assertEqual(self.out.read_bytes(), b'old log')
        self.assertEqual(self.summary.read_bytes(), b'old summary')
        self.assert_no_temps()

    def test_second_replace_error_removes_new_first_output(self):
        self.write([{'observation': fixture()}])
        real_replace = os.replace
        def fail_summary(source, destination):
            if Path(destination) == self.summary: raise OSError('unavailable')
            return real_replace(source, destination)
        with patch.object(stream.os, 'replace', fail_summary):
            with self.assertRaises(OSError): self.run_stream()
        self.assertFalse(self.out.exists()); self.assertFalse(self.summary.exists())
        self.assert_no_temps()

    def test_failed_rollback_retains_original_backup(self):
        self.write([{'observation': fixture()}]); self.out.write_bytes(b'original bytes')
        real_replace = os.replace
        def fail_after_first(source, destination):
            if Path(destination) == self.summary or '.previous.' in str(source):
                raise OSError('unavailable')
            return real_replace(source, destination)
        with patch.object(stream.os, 'replace', fail_after_first):
            with self.assertRaisesRegex(OSError, 'retained original copies'):
                self.run_stream()
        backups = list(self.root.glob('.telemetry.jsonl.previous.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'original bytes')

    def test_action_mismatch_and_empty_input_exit_contract(self):
        self.write([{'observation': fixture(), 'expected_action': {'incorrect': 1}}])
        self.assertEqual(self.cli().returncode, 1)
        self.assertEqual(json.loads(self.summary.read_text())['actors'][0]['expected_action_mismatches'], 1)
        self.input.write_text('\n\n')
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(self.out.read_bytes(), b'')
        self.assertEqual(json.loads(self.summary.read_text())['actors'], [])
        self.input.write_text('[]\n')
        self.assertEqual(self.cli().returncode, 2)
        self.assert_no_temps()

    def test_private_input_is_not_exported(self):
        obs = fixture(); obs['private']['marker'] = 'private-marker-do-not-export'
        self.write([{'observation': obs}]); self.run_stream()
        self.assertNotIn('private-marker', self.out.read_text())
        self.assertNotIn('private-marker', self.summary.read_text())
        self.assertIn('private-marker', self.input.read_text())


if __name__ == '__main__':
    unittest.main()
