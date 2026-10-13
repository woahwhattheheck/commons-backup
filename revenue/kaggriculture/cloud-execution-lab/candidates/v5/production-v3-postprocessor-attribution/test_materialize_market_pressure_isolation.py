# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import materialize_market_pressure_isolation as mp


def _baseline_members(count: int = 5):
    config = {
        "consumer": "frozen",
        "market_pressure": True,
        "early_capital": True,
        "operating_stock": True,
        "sentinel": 7,
    }
    config_raw = json.dumps(config, indent=2).encode() + b"\n"
    members = {mp.CONFIG_PATH: config_raw}
    for idx in range(count - 1):
        members[f"member-{idx}.bin"] = f"body-{idx}".encode()
    return members, config_raw


def _pack(members):
    rows = [[name, hashlib.sha256(body).hexdigest()] for name, body in sorted(members.items())]
    return json.dumps(rows, separators=(",", ":")).encode()


class BuildTests(unittest.TestCase):
    def build(self, members, config_raw):
        return mp.build_from_members(
            members,
            _pack,
            expected_config_sha256=mp.digest(config_raw),
            expected_member_count=len(members),
        )

    def test_single_knob_only_and_retains_early_capital(self):
        members, config_raw = _baseline_members()
        artifacts, treatment = self.build(members, config_raw)
        changed = [name for name in members if members[name] != treatment[name]]
        self.assertEqual(changed, [mp.CONFIG_PATH])
        cfg = json.loads(treatment[mp.CONFIG_PATH])
        self.assertIs(cfg["market_pressure"], False)
        self.assertIs(cfg["early_capital"], True)
        self.assertEqual(cfg["sentinel"], 7)
        for name in members:
            if name != mp.CONFIG_PATH:
                self.assertEqual(treatment[name], members[name])
        self.assertEqual(set(artifacts), {"candidate.tar.gz", mp.CONFIG_PATH, "COMPONENT.json", "RECEIPT.json"})

    def test_component_is_one_replacement_and_held(self):
        members, config_raw = _baseline_members()
        artifacts, treatment = self.build(members, config_raw)
        component = json.loads(artifacts["COMPONENT.json"])
        self.assertEqual(component["schema"], mp.COMPONENT_SCHEMA)
        self.assertEqual(component["component_id"], mp.COMPONENT_ID)
        self.assertEqual(list(component["replacements"]), [mp.CONFIG_PATH])
        repl = component["replacements"][mp.CONFIG_PATH]
        self.assertEqual(repl["preimage_sha256"], mp.digest(config_raw))
        self.assertEqual(repl["postimage_sha256"], mp.digest(treatment[mp.CONFIG_PATH]))
        self.assertTrue(component["kaggle_submission_hold"])

    def test_receipt_binds_candidate_component_and_single_change(self):
        members, config_raw = _baseline_members()
        artifacts, _ = self.build(members, config_raw)
        receipt = json.loads(artifacts["RECEIPT.json"])
        self.assertEqual(receipt["candidate_archive_sha256"], mp.digest(artifacts["candidate.tar.gz"]))
        self.assertEqual(receipt["component_sha256"], mp.digest(artifacts["COMPONENT.json"]))
        self.assertEqual(receipt["config_changes"], {"market_pressure": {"before": True, "after": False}})
        self.assertEqual(receipt["retained_preimage"], {"early_capital": True})
        self.assertEqual(receipt["native_economics_status"], "UNPROVEN")

    def test_wrong_market_pressure_preimage_rejects(self):
        members, _ = _baseline_members()
        cfg = json.loads(members[mp.CONFIG_PATH])
        cfg["market_pressure"] = False
        raw = json.dumps(cfg, indent=2).encode() + b"\n"
        members[mp.CONFIG_PATH] = raw
        with self.assertRaisesRegex(ValueError, "market_pressure preimage"):
            self.build(members, raw)

    def test_early_capital_must_remain_enabled(self):
        members, _ = _baseline_members()
        cfg = json.loads(members[mp.CONFIG_PATH])
        cfg["early_capital"] = False
        raw = json.dumps(cfg, indent=2).encode() + b"\n"
        members[mp.CONFIG_PATH] = raw
        with self.assertRaisesRegex(ValueError, "early_capital preimage"):
            self.build(members, raw)

    def test_config_hash_mismatch_rejects(self):
        members, config_raw = _baseline_members()
        with self.assertRaisesRegex(ValueError, "config identity"):
            mp.build_from_members(
                members,
                _pack,
                expected_config_sha256="0" * 64,
                expected_member_count=len(members),
            )

    def test_member_count_mismatch_rejects(self):
        members, config_raw = _baseline_members()
        with self.assertRaisesRegex(ValueError, "member count"):
            mp.build_from_members(
                members,
                _pack,
                expected_config_sha256=mp.digest(config_raw),
                expected_member_count=len(members) + 1,
            )

    def test_build_is_deterministic(self):
        members, config_raw = _baseline_members()
        one, _ = self.build(members, config_raw)
        two, _ = self.build(members, config_raw)
        self.assertEqual(one, two)


class LoaderTests(unittest.TestCase):
    def test_loader_supports_dataclass_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "fixture.py"
            source.write_text("from dataclasses import dataclass\n@dataclass\nclass Row:\n    value: int\n")
            module = mp._load_module("_mp_dataclass_fixture", source)
            self.assertEqual(module.Row(7).value, 7)


class PublicationTests(unittest.TestCase):
    def test_publish_uses_exact_four_files_in_sorted_order(self):
        artifacts = {
            "candidate.tar.gz": b"candidate",
            mp.CONFIG_PATH: b"config",
            "COMPONENT.json": b"component",
            "RECEIPT.json": b"receipt",
        }
        calls = []
        def publisher(rows):
            calls.extend(rows)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            mp.publish_artifacts(out, artifacts, publisher)
            self.assertEqual([p.name for p, _ in calls], sorted(artifacts))
            self.assertEqual([body for _, body in calls], [artifacts[name] for name in sorted(artifacts)])

    def test_nonempty_output_dir_rejects_before_publisher(self):
        artifacts = {
            "candidate.tar.gz": b"candidate",
            mp.CONFIG_PATH: b"config",
            "COMPONENT.json": b"component",
            "RECEIPT.json": b"receipt",
        }
        called = False
        def publisher(_rows):
            nonlocal called
            called = True
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.mkdir()
            (out / "foreign").write_text("keep")
            with self.assertRaisesRegex(ValueError, "not empty"):
                mp.publish_artifacts(out, artifacts, publisher)
            self.assertFalse(called)
            self.assertEqual((out / "foreign").read_text(), "keep")

    def test_unexpected_artifact_set_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "unexpected"):
                mp.publish_artifacts(Path(tmp) / "out", {"candidate.tar.gz": b"x"}, lambda rows: None)


if __name__ == "__main__":
    unittest.main()
