# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import f38_s420_only as f38


def _source(extra_block: str = "") -> bytes:
    text = f'''import copy\n\nclass FrozenSelected:\n    def cash_reserve(self, *args):\n        return 7\n\n    def transform(self, obs, config, base, end, now):\n        before = 1\n        budget=self.cash_reserve(obs,config,base,end)\n        self.new_plan_selected = budget\n{extra_block}        keep = before\n        out=copy.deepcopy(base)\n        out.append("due")\n        return out\n'''
    return text.encode()


def _members(source: bytes | None = None, count: int = 7):
    source = _source() if source is None else source
    scheduler = b"HORIZON=8\n"
    main = b"def agent(*args): return None\n"
    config = b'{"consumer":"frozen"}\n'
    members = {
        f38.FROZEN_PATH: source,
        f38.SCHEDULER_PATH: scheduler,
        f38.MAIN_PATH: main,
        f38.CONFIG_PATH: config,
    }
    for idx in range(count - len(members)):
        members[f"other-{idx}.py"] = f"sentinel-{idx}\n".encode()
    return members


def _build(members):
    return f38.build_from_members(
        members,
        expected_frozen_sha256=f38.digest(members[f38.FROZEN_PATH]),
        expected_scheduler_sha256=f38.digest(members[f38.SCHEDULER_PATH]),
        expected_main_sha256=f38.digest(members[f38.MAIN_PATH]),
        expected_config_sha256=f38.digest(members[f38.CONFIG_PATH]),
        expected_member_count=len(members),
    )


class RewriteTests(unittest.TestCase):
    def test_s420_wraps_only_new_plan_block(self):
        original = _source().decode()
        result = f38._rewrite_source_text(original)
        self.assertIn(f38.MARKER, result)
        self.assertIn("        if now < 420:\n            budget=", result)
        self.assertIn("            self.new_plan_selected = budget\n            keep = before\n", result)
        self.assertIn("        out=copy.deepcopy(base)\n", result)
        self.assertIn('        out.append("due")\n', result)
        compile(result, "<test-f38>", "exec")

    def test_horizon_is_not_overridden(self):
        result = f38._rewrite_source_text(_source().decode())
        self.assertNotIn("H3S420_BASELINE_HORIZON", result)
        self.assertNotIn("HORIZON =", result)

    def test_trigger_blocks_new_plan_but_preserves_tail(self):
        namespace = {}
        exec(f38._rewrite_source_text(_source().decode()), namespace)
        before = namespace["FrozenSelected"]()
        self.assertEqual(before.transform(None, None, [], None, 419), ["due"])
        self.assertEqual(before.new_plan_selected, 7)

        at_boundary = namespace["FrozenSelected"]()
        self.assertEqual(at_boundary.transform(None, None, [], None, 420), ["due"])
        self.assertFalse(hasattr(at_boundary, "new_plan_selected"))

    def test_second_application_fails_closed(self):
        once = f38._rewrite_source_text(_source().decode())
        with self.assertRaisesRegex(ValueError, "already present"):
            f38._rewrite_source_text(once)

    def test_missing_start_marker_fails_closed(self):
        source = _source().decode().replace("budget=self.cash_reserve(obs,config,base,end)", "budget=0")
        with self.assertRaisesRegex(ValueError, "start marker drift"):
            f38._rewrite_source_text(source)

    def test_duplicate_end_marker_fails_closed(self):
        source = _source(extra_block="        out=copy.deepcopy(base)\n").decode()
        with self.assertRaisesRegex(ValueError, "end marker drift"):
            f38._rewrite_source_text(source)

    def test_h3_preimage_is_rejected(self):
        source = "H3S420_BASELINE_HORIZON = 3\n" + _source().decode()
        with self.assertRaisesRegex(ValueError, "horizon override"):
            f38._rewrite_source_text(source)


class BuilderTests(unittest.TestCase):
    def test_source_only_single_member_delta_and_hold(self):
        members = _members()
        outputs, receipt = _build(members)
        self.assertEqual(set(outputs), {f38.FROZEN_PATH, "RECEIPT.json"})
        self.assertNotEqual(outputs[f38.FROZEN_PATH], members[f38.FROZEN_PATH])
        self.assertEqual(receipt["changed_members"], [f38.FROZEN_PATH])
        self.assertEqual(receipt["seller_horizon"], 8)
        self.assertEqual(receipt["new_plan_suppression"]["step_gte"], 420)
        self.assertFalse(receipt["candidate_archive_materialized"])
        self.assertFalse(receipt["component_materialized"])
        self.assertEqual(receipt["native_economics_status"], "BLOCKED_BY_RUNTIME_GATE")
        self.assertTrue(receipt["kaggle_submission_hold"])
        parsed = json.loads(outputs["RECEIPT.json"])
        self.assertEqual(parsed, receipt)

    def test_builder_is_deterministic(self):
        members = _members()
        one, receipt_one = _build(members)
        two, receipt_two = _build(members)
        self.assertEqual(one, two)
        self.assertEqual(receipt_one, receipt_two)

    def test_wrong_frozen_identity_rejects(self):
        members = _members()
        with self.assertRaisesRegex(ValueError, "frozen_selected.py"):
            f38.build_from_members(
                members,
                expected_frozen_sha256="0" * 64,
                expected_scheduler_sha256=f38.digest(members[f38.SCHEDULER_PATH]),
                expected_main_sha256=f38.digest(members[f38.MAIN_PATH]),
                expected_config_sha256=f38.digest(members[f38.CONFIG_PATH]),
                expected_member_count=len(members),
            )

    def test_wrong_scheduler_identity_rejects(self):
        members = _members()
        with self.assertRaisesRegex(ValueError, "scheduler.py"):
            f38.build_from_members(
                members,
                expected_frozen_sha256=f38.digest(members[f38.FROZEN_PATH]),
                expected_scheduler_sha256="0" * 64,
                expected_main_sha256=f38.digest(members[f38.MAIN_PATH]),
                expected_config_sha256=f38.digest(members[f38.CONFIG_PATH]),
                expected_member_count=len(members),
            )

    def test_wrong_main_identity_rejects(self):
        members = _members()
        with self.assertRaisesRegex(ValueError, "main.py"):
            f38.build_from_members(
                members,
                expected_frozen_sha256=f38.digest(members[f38.FROZEN_PATH]),
                expected_scheduler_sha256=f38.digest(members[f38.SCHEDULER_PATH]),
                expected_main_sha256="0" * 64,
                expected_config_sha256=f38.digest(members[f38.CONFIG_PATH]),
                expected_member_count=len(members),
            )

    def test_wrong_config_identity_rejects(self):
        members = _members()
        with self.assertRaisesRegex(ValueError, "TITAN-CONFIG.json"):
            f38.build_from_members(
                members,
                expected_frozen_sha256=f38.digest(members[f38.FROZEN_PATH]),
                expected_scheduler_sha256=f38.digest(members[f38.SCHEDULER_PATH]),
                expected_main_sha256=f38.digest(members[f38.MAIN_PATH]),
                expected_config_sha256="0" * 64,
                expected_member_count=len(members),
            )

    def test_member_count_rejects(self):
        members = _members()
        with self.assertRaisesRegex(ValueError, "member count"):
            f38.build_from_members(
                members,
                expected_frozen_sha256=f38.digest(members[f38.FROZEN_PATH]),
                expected_scheduler_sha256=f38.digest(members[f38.SCHEDULER_PATH]),
                expected_main_sha256=f38.digest(members[f38.MAIN_PATH]),
                expected_config_sha256=f38.digest(members[f38.CONFIG_PATH]),
                expected_member_count=len(members) + 1,
            )

    def test_other_member_bytes_are_not_emitted_or_modified(self):
        members = _members()
        sentinel = dict(members)
        outputs, _ = _build(members)
        self.assertEqual(members, sentinel)
        self.assertEqual(set(outputs), {f38.FROZEN_PATH, "RECEIPT.json"})


class MaterializeBoundaryTests(unittest.TestCase):
    def test_archive_hash_rejects_before_support_load(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = root / "wrong.tar.gz"
            baseline.write_bytes(b"not-production20f")
            with self.assertRaisesRegex(ValueError, "archive identity mismatch"):
                f38.materialize(baseline, root / "out.py", root / "receipt.json", publisher=lambda _: None)

    def test_output_paths_must_differ(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            baseline = root / "wrong.tar.gz"
            baseline.write_bytes(b"not-production20f")
            same = root / "same"
            with self.assertRaisesRegex(ValueError, "must differ"):
                f38.materialize(baseline, same, same, publisher=lambda _: None)


if __name__ == "__main__":
    unittest.main()
