"""Regression and end-to-end proof for Commons #14184 (synthetic data only)."""
from __future__ import annotations

import copy
import errno
import itertools
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from . import custody
from .core import (
    ValidationError, canonical_json_bytes, compile_cockpit, format_utc,
    sha256_bytes, verify_cockpit,
)

NOW = datetime(2026, 9, 17, 20, tzinfo=timezone.utc)
POLICY = {"max_source_age_minutes": 60, "critical_window_minutes": 10,
          "high_window_minutes": 20}


def sample(statuses=("PROVEN", "PROVEN", "MISSING"), now=NOW):
    opportunities = []
    for i, status in enumerate(statuses):
        label = str(i)
        opportunities.append({
            "id": "opp-" + label, "owner_ref": "owner-" + label,
            "route_state": "PRIME", "deadline_utc": None,
            "source": {"packet_id": "source-" + label,
                       "packet_sha256": "a" * 64,
                       "captured_at": format_utc(now), "complete": True},
            "gates": [{"id": "gate-" + label, "action_key": "FORM",
                       "action_label": "Owner form", "requirement_sha256": "b" * 64,
                       "generation": 1, "category": "LEGAL", "status": status,
                       "blocking": status != "NOT_APPLICABLE", "owner_required": True,
                       "evidence": [{"ref": "evidence-" + label, "sha256": "c" * 64}],
                       "prerequisites": []}],
        })
    return {"schema_version": 1, "snapshot_id": "recovery-synthetic",
            "opportunities": opportunities}


def compile_(p):
    return compile_cockpit(p, POLICY, as_of=NOW)


class ActionRecoveryTests(unittest.TestCase):
    def test_completed_members_cannot_inflate_any_live_projection(self):
        out = compile_(sample())
        row = out["rows"][0]
        self.assertEqual("NORMAL", row["priority_band"])
        self.assertEqual("OWNER_ACTION_NOW", row["state"])
        self.assertEqual(["opp-2"], row["affected_opportunity_ids"])
        self.assertEqual(["gate-2"], row["gate_ids"])
        self.assertEqual(["source-2"], row["source_packet_ids"])
        self.assertEqual([{"ref": "evidence-2", "sha256": "c" * 64}], row["evidence_refs"])
        self.assertEqual(["OWNER_REQUIRED_MISSING"], row["reason_codes"])
        self.assertEqual(1, row["blocking_gate_count"])
        self.assertEqual(1, out["summary"]["affected_live_opportunity_count"])

    def test_completed_deadlines_cannot_inflate_urgency(self):
        p = sample()
        p["opportunities"][0]["deadline_utc"] = format_utc(NOW + timedelta(seconds=30))
        row = compile_(p)["rows"][0]
        self.assertEqual("NORMAL", row["priority_band"])
        self.assertIsNone(row["earliest_deadline_utc"])
        self.assertIsNone(row["minutes_remaining"])

    def test_completed_prerequisite_lineage_does_not_leak_to_live_group(self):
        p = sample()
        completed = p["opportunities"][0]
        prereq = copy.deepcopy(completed["gates"][0])
        prereq.update(id="prerequisite", action_key="PREREQUISITE", action_label="Prerequisite")
        completed["gates"][0]["prerequisites"] = ["prerequisite"]
        completed["gates"].append(prereq)
        row = next(r for r in compile_(p)["rows"] if r["action_key"] == "FORM")
        self.assertEqual([], row["prerequisite_gate_ids"])
        self.assertEqual(["gate-2"], row["gate_ids"])

    def test_all_completed_members_remain_visible_as_non_action(self):
        p = sample(("PROVEN", "NOT_APPLICABLE", "PROVEN"))
        out = compile_(p)
        row = out["rows"][0]
        self.assertEqual("NO_ACTION_PROVEN", row["state"])
        self.assertEqual("TERMINAL", row["priority_band"])
        self.assertEqual(["opp-0", "opp-1", "opp-2"], row["affected_opportunity_ids"])
        self.assertEqual(3, len(row["evidence_refs"]))
        self.assertEqual(0, row["blocking_gate_count"])
        self.assertEqual(0, out["summary"]["affected_live_opportunity_count"])

    def test_three_real_unresolved_opportunities_still_have_high_breadth(self):
        row = compile_(sample(("MISSING",) * 3))["rows"][0]
        self.assertEqual("HIGH", row["priority_band"])
        self.assertEqual(3, len(row["affected_opportunity_ids"]))

    def test_all_125_status_combinations_preserve_unresolved_only_membership(self):
        states = ("PROVEN", "NOT_APPLICABLE", "MISSING", "HOLD", "PENDING_EXTERNAL")
        for statuses in itertools.product(states, repeat=3):
            with self.subTest(statuses=statuses):
                p = sample(statuses)
                out = compile_(p)
                row = out["rows"][0]
                indices = [i for i, s in enumerate(statuses) if s not in {"PROVEN", "NOT_APPLICABLE"}]
                expected = indices or list(range(3))
                for field, prefix in (("affected_opportunity_ids", "opp-"),
                                      ("gate_ids", "gate-"), ("source_packet_ids", "source-")):
                    self.assertEqual([prefix + str(i) for i in expected], row[field])
                self.assertEqual(len(indices), row["blocking_gate_count"])
                if indices:
                    self.assertNotIn("GATE_PROVEN", row["reason_codes"])
                    self.assertNotIn("GATE_NOT_APPLICABLE", row["reason_codes"])
                self.assertEqual(len(indices), out["summary"]["affected_live_opportunity_count"])
                self.assertFalse(out["authority"]["external_actions_authorized"])
                p["opportunities"].reverse()
                self.assertEqual(canonical_json_bytes(out), canonical_json_bytes(compile_(p)))

    def test_source_exact_boundary_and_each_later_second(self):
        for excess in range(-1, 60):
            with self.subTest(excess=excess):
                p = sample(("MISSING",))
                p["opportunities"][0]["source"]["captured_at"] = format_utc(
                    NOW - timedelta(minutes=60, seconds=excess))
                row = compile_(p)["rows"][0]
                expected = "SOURCE_REFRESH_REQUIRED" if excess > 0 else "OWNER_ACTION_NOW"
                self.assertEqual(expected, row["state"])

    def test_current_verification_expires_one_second_after_source_boundary(self):
        p = sample(("MISSING",))
        p["opportunities"][0]["source"]["captured_at"] = format_utc(NOW - timedelta(minutes=60))
        out = compile_(p)
        self.assertTrue(verify_cockpit(p, POLICY, out, current_as_of=NOW))
        self.assertFalse(verify_cockpit(p, POLICY, out, current_as_of=NOW + timedelta(seconds=1)))

    def test_resealed_inflated_breadth_packet_rejected(self):
        p = sample()
        out = compile_(p)
        out["rows"][0]["affected_opportunity_ids"] = ["opp-0", "opp-1", "opp-2"]
        out["rows"][0]["priority_band"] = "HIGH"
        unsigned = dict(out)
        unsigned.pop("receipt_sha256")
        out["receipt_sha256"] = sha256_bytes(canonical_json_bytes(unsigned))
        self.assertFalse(verify_cockpit(p, POLICY, out, current_as_of=NOW))

    def test_dependency_closure_repair_is_preserved(self):
        p = sample(("PROVEN",))
        unresolved = copy.deepcopy(p["opportunities"][0]["gates"][0])
        unresolved.update(id="missing-parent", status="MISSING", action_key="PARENT", action_label="Parent")
        p["opportunities"][0]["gates"][0]["prerequisites"] = ["missing-parent"]
        p["opportunities"][0]["gates"].append(unresolved)
        with self.assertRaisesRegex(ValidationError, "PROVEN with unmet prerequisites"):
            compile_(p)


class CustodyRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_read_roundtrip_limit_and_empty(self):
        p = self.root / "input"
        p.write_bytes(b"abc")
        self.assertEqual(b"abc", custody.read_regular(p, 3))
        with self.assertRaises(ValidationError):
            custody.read_regular(p, 2)
        p.write_bytes(b"")
        self.assertEqual(b"", custody.read_regular(p, 0))

    def test_unsupported_primitives_fail_before_any_file_mutation(self):
        out = self.root / "out"
        with patch.object(os, "supports_dir_fd", set()):
            with self.assertRaisesRegex(ValidationError, "unavailable"):
                custody.write_bundle([(out, b"data")])
        self.assertFalse(out.exists())

    def test_final_and_ancestor_symlinks_refused_for_both_directions(self):
        real = self.root / "real"
        real.mkdir()
        inp = real / "input"
        inp.write_bytes(b"keep")
        (self.root / "alias").symlink_to(real, target_is_directory=True)
        (self.root / "link").symlink_to(inp)
        for path in (self.root / "link", self.root / "alias" / "input"):
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    custody.read_regular(path)
        for path in (self.root / "link", self.root / "alias" / "output"):
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    custody.write_exclusive(path, b"replace")
        self.assertEqual(b"keep", inp.read_bytes())
        self.assertFalse((real / "output").exists())

    def test_parent_components_walk_descriptors_without_lexical_normalization(self):
        ordinary = self.root / "ordinary"
        ordinary.mkdir()
        target = self.root / "out"
        custody.write_exclusive(str(ordinary) + "/../out", b"data")
        self.assertEqual(b"data", custody.read_regular(str(ordinary) + "/../out"))
        alias = self.root / "alias"
        alias.symlink_to(ordinary, target_is_directory=True)
        with self.assertRaises(ValidationError):
            custody.read_regular(str(alias) + "/../out")
        self.assertEqual(b"data", target.read_bytes())

    def test_ambiguous_or_directory_only_paths_and_invalid_limits_fail(self):
        for path in ("", "bad\0path", "//ambiguous/out", str(self.root) + "/", ".", ".."):
            with self.subTest(path=path):
                with self.assertRaises(ValidationError):
                    custody.write_exclusive(path, b"data")
        p = self.root / "input"
        p.write_bytes(b"x")
        for limit in (-1, True, 2_000_001):
            with self.assertRaises(ValidationError):
                custody.read_regular(p, limit)

    def test_deep_symlink_ancestor_refused(self):
        real = self.root / "real"
        (real / "nested").mkdir(parents=True)
        (real / "nested" / "input").write_bytes(b"private")
        (self.root / "alias").symlink_to(real, target_is_directory=True)
        with self.assertRaises(ValidationError):
            custody.read_regular(self.root / "alias" / "nested" / "input")
        with self.assertRaises(ValidationError):
            custody.write_exclusive(self.root / "alias" / "nested" / "output", b"x")

    def test_fifo_is_refused_before_final_open(self):
        p = self.root / "pipe"
        os.mkfifo(p)
        real_open = os.open
        opened_final = []
        def observe(path, *args, **kwargs):
            if path == "pipe":
                opened_final.append(path)
            return real_open(path, *args, **kwargs)
        with patch.object(os, "open", side_effect=observe):
            with self.assertRaisesRegex(ValidationError, "regular"):
                custody.read_regular(p)
        self.assertEqual([], opened_final)

    def test_same_size_input_replacement_between_inspection_and_open_fails(self):
        p = self.root / "input"
        replacement = self.root / "replacement"
        p.write_bytes(b"first")
        replacement.write_bytes(b"other")
        real_open = os.open
        def swap(path, *args, **kwargs):
            if path == "input":
                replacement.replace(p)
            return real_open(path, *args, **kwargs)
        with patch.object(os, "open", side_effect=swap):
            with self.assertRaisesRegex(ValidationError, "generation"):
                custody.read_regular(p)

    def test_same_inode_mutation_during_read_fails(self):
        p = self.root / "input"
        p.write_bytes(b"a" * 100000)
        real_read = os.read
        changed = False
        def mutate(fd, n):
            nonlocal changed
            chunk = real_read(fd, n)
            if not changed:
                changed = True
                p.write_bytes(b"b" * 100000)
            return chunk
        with patch.object(os, "read", side_effect=mutate):
            with self.assertRaisesRegex(ValidationError, "changed"):
                custody.read_regular(p)

    def test_replaced_input_parent_never_redirects_consumed_bytes(self):
        parent = self.root / "parent"
        parent.mkdir()
        (parent / "input").write_bytes(b"original")
        held = self.root / "retained"
        real_open, real_read = os.open, os.read
        consumed = []
        def swap(path, *args, **kwargs):
            if path == "input":
                parent.rename(held)
                parent.mkdir()
                (parent / "input").write_bytes(b"redirect")
            return real_open(path, *args, **kwargs)
        def observe(fd, n):
            chunk = real_read(fd, n)
            consumed.append(chunk)
            return chunk
        with patch.object(os, "open", side_effect=swap), patch.object(os, "read", side_effect=observe):
            with self.assertRaisesRegex(ValidationError, "directory generation"):
                custody.read_regular(parent / "input")
        self.assertEqual(b"original", b"".join(consumed))
        self.assertEqual(b"redirect", (parent / "input").read_bytes())

    def test_existing_second_output_means_no_payload_written_anywhere(self):
        first, second = self.root / "first", self.root / "second"
        second.write_bytes(b"keep")
        with patch.object(os, "write", wraps=os.write) as writer:
            with self.assertRaises(ValidationError):
                custody.write_bundle([(first, b"one"), (second, b"two")])
            self.assertEqual(0, writer.call_count)
        self.assertFalse(first.exists())
        self.assertEqual(b"keep", second.read_bytes())

    def test_missing_second_parent_rolls_back_empty_first_reservation(self):
        first = self.root / "first"
        with self.assertRaises(ValidationError):
            custody.write_bundle([(first, b"one"), (self.root / "absent" / "two", b"two")])
        self.assertFalse(first.exists())

    def test_duplicate_output_aliases_fail_before_writes(self):
        first = self.root / "out"
        with patch.object(os, "write", wraps=os.write) as writer:
            with self.assertRaises(ValidationError):
                custody.write_bundle([(first, b"one"), (str(self.root) + "/./out", b"two")])
            self.assertEqual(0, writer.call_count)
        self.assertFalse(first.exists())

    def test_every_output_is_reserved_before_the_first_write(self):
        first, second = self.root / "first", self.root / "second"
        real_write = os.write
        observed = []
        def check(fd, data):
            if not observed:
                observed.append((first.exists(), second.exists(), first.stat().st_size, second.stat().st_size))
            return real_write(fd, data)
        with patch.object(os, "write", side_effect=check):
            custody.write_bundle([(first, b"one"), (second, b"two")])
        self.assertEqual([(True, True, 0, 0)], observed)
        self.assertEqual(b"one", first.read_bytes())
        self.assertEqual(b"two", second.read_bytes())
        self.assertEqual(0o600, first.stat().st_mode & 0o777)

    def test_short_writes_are_completed(self):
        out = self.root / "out"
        real_write = os.write
        with patch.object(os, "write", side_effect=lambda fd, data: real_write(fd, data[:2])):
            custody.write_exclusive(out, b"abcdefg")
        self.assertEqual(b"abcdefg", out.read_bytes())

    def test_zero_write_rolls_back_all_outputs(self):
        first, second = self.root / "first", self.root / "second"
        with patch.object(os, "write", return_value=0):
            with self.assertRaisesRegex(ValidationError, "short"):
                custody.write_bundle([(first, b"one"), (second, b"two")])
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())

    def test_second_write_failure_removes_only_this_bundle(self):
        first, second = self.root / "first", self.root / "second"
        keep = self.root / "keep"
        keep.write_bytes(b"untouched")
        real_write = os.write
        count = 0
        def fail_second(fd, data):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError(errno.ENOSPC, "synthetic capacity failure")
            return real_write(fd, data)
        with patch.object(os, "write", side_effect=fail_second):
            with self.assertRaises(ValidationError):
                custody.write_bundle([(first, b"one"), (second, b"two")])
        self.assertFalse(first.exists())
        self.assertFalse(second.exists())
        self.assertEqual(b"untouched", keep.read_bytes())

    def test_fsync_failure_cleans_reserved_files(self):
        out = self.root / "out"
        with patch.object(os, "fsync", side_effect=OSError(errno.EIO, "synthetic fsync failure")):
            with self.assertRaises(ValidationError):
                custody.write_exclusive(out, b"one")
        self.assertFalse(out.exists())

    def test_output_parent_swap_never_writes_or_cleans_replacement_namespace(self):
        parent = self.root / "parent"
        parent.mkdir()
        held = self.root / "retained"
        real_write = os.write
        changed = False
        def swap(fd, data):
            nonlocal changed
            if not changed:
                changed = True
                parent.rename(held)
                parent.mkdir()
                (parent / "first").write_bytes(b"replacement-one")
                (parent / "second").write_bytes(b"replacement-two")
            return real_write(fd, data)
        with patch.object(os, "write", side_effect=swap):
            with self.assertRaisesRegex(ValidationError, "directory generation"):
                custody.write_bundle([(parent / "first", b"one"), (parent / "second", b"two")])
        self.assertEqual([], list(held.iterdir()))
        self.assertEqual(b"replacement-one", (parent / "first").read_bytes())
        self.assertEqual(b"replacement-two", (parent / "second").read_bytes())

    def test_replaced_output_entry_is_not_deleted_by_cleanup(self):
        out = self.root / "out"
        real_write = os.write
        def replace(fd, data):
            out.unlink()
            out.write_bytes(b"alien-entry")
            return real_write(fd, data)
        with patch.object(os, "write", side_effect=replace):
            with self.assertRaisesRegex(ValidationError, "authored generation"):
                custody.write_exclusive(out, b"ours")
        self.assertEqual(b"alien-entry", out.read_bytes())

    def test_corrupted_write_bytes_are_detected_not_just_size(self):
        out = self.root / "out"
        real_write = os.write
        with patch.object(os, "write", side_effect=lambda fd, data: real_write(fd, b"x" * len(data))):
            with self.assertRaisesRegex(ValidationError, "bytes changed"):
                custody.write_exclusive(out, b"ours")
        self.assertFalse(out.exists())

    def test_four_concurrent_writers_have_exactly_one_complete_winner(self):
        first, second = self.root / "first", self.root / "second"
        def publish(i):
            try:
                custody.write_bundle([(first, str(i).encode()), (second, str(i).encode())])
                return i
            except ValidationError:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            winners = [i for i in pool.map(publish, range(4)) if i is not None]
        self.assertEqual(1, len(winners))
        self.assertEqual(str(winners[0]).encode(), first.read_bytes())
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_descriptor_count_stable_after_success_and_failure(self):
        fd_dir = Path("/proc/self/fd")
        if not fd_dir.exists():
            self.skipTest("Linux descriptor census only")
        out = self.root / "out"
        before = len(list(fd_dir.iterdir()))
        custody.write_exclusive(out, b"data")
        for _ in range(20):
            self.assertEqual(b"data", custody.read_regular(out))
            with self.assertRaises(ValidationError):
                custody.write_exclusive(out, b"other")
        self.assertEqual(before, len(list(fd_dir.iterdir())))


class CliRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.input = self.root / "input.json"
        self.policy = self.root / "policy.json"
        self.output = self.root / "cockpit.json"
        self.md = self.root / "cockpit.md"
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.input.write_bytes(canonical_json_bytes(sample(now=now)))
        self.policy.write_bytes(canonical_json_bytes(POLICY))
        self.command = [sys.executable] + (["-O"] if sys.flags.optimize else [])
        self.command += ["-m", "revenue.bid_owner_action_cockpit"]
        self.common = ["--input", str(self.input), "--policy", str(self.policy),
                       "--output", str(self.output)]

    def run_cli(self, action, *extra):
        return subprocess.run(self.command + [action] + self.common + list(extra),
                              cwd=Path(__file__).resolve().parents[2],
                              capture_output=True, text=True, timeout=15)

    def test_real_compile_verify_render_and_retained_files(self):
        result = self.run_cli("compile", "--markdown", str(self.md))
        self.assertEqual(0, result.returncode, result.stderr)
        out = json.loads(self.output.read_bytes())
        self.assertEqual("NORMAL", out["rows"][0]["priority_band"])
        self.assertEqual(["opp-2"], out["rows"][0]["affected_opportunity_ids"])
        self.assertIn("owner decision support only", self.md.read_text())
        result = self.run_cli("verify")
        self.assertEqual((0, "VERIFIED\n"), (result.returncode, result.stdout), result.stderr)
        rendered = self.root / "rendered.md"
        result = self.run_cli("render", "--markdown", str(rendered))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.md.read_bytes(), rendered.read_bytes())

    def test_real_cli_second_output_conflict_does_not_publish_json(self):
        self.md.write_bytes(b"keep")
        result = self.run_cli("compile", "--markdown", str(self.md))
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.output.exists())
        self.assertEqual(b"keep", self.md.read_bytes())
        self.assertNotIn("Traceback", result.stderr)

    def test_real_cli_tampered_output_cannot_verify_or_render(self):
        self.assertEqual(0, self.run_cli("compile").returncode)
        out = json.loads(self.output.read_bytes())
        out["rows"][0]["action_label"] = "Changed"
        self.output.write_bytes(canonical_json_bytes(out))
        self.assertEqual(2, self.run_cli("verify").returncode)
        result = self.run_cli("render", "--markdown", str(self.md))
        self.assertEqual(2, result.returncode)
        self.assertFalse(self.md.exists())


if __name__ == "__main__":
    unittest.main()
