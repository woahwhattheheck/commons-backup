# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

import production20f_component as carrier


def fixture_main() -> bytes:
    return (
        b"_CHOICE = None\n"
        b"_INSTANCE = None\n"
        b"def agent(observation, configuration=None):\n"
        b"    global _INSTANCE\n"
        b"    returned = baseline.agent(observation, configuration)\n"
        b"    _INSTANCE = baseline._INSTANCE\n"
        + carrier._RETURN_SEAM
    )


class Production20fComponentTests(unittest.TestCase):
    def test_transform_preserves_parent_commit_then_applies_wf1(self):
        events = []

        class Baseline:
            _INSTANCE = object()

            @staticmethod
            def agent(observation, configuration=None):
                events.append("parent")
                return {"trace": ["parent"]}

        class Choice:
            @staticmethod
            def commit(observation, action):
                events.append("commit")

        adapter = types.ModuleType("wf1_current_adapter")

        def apply_wf1_current(observation, action, configuration, *, enabled=False):
            self.assertTrue(enabled)
            events.append("wf1")
            return {"trace": action["trace"] + ["wf1"]}

        adapter.apply_wf1_current = apply_wf1_current
        namespace = {"baseline": Baseline}
        with mock.patch.dict(sys.modules, {"wf1_current_adapter": adapter}):
            exec(compile(carrier.transform_main(fixture_main()), "main.py", "exec"), namespace)
            namespace["_CHOICE"] = Choice()
            result = namespace["agent"]({"step": 17}, {"episodeSteps": 720})

        self.assertEqual(events, ["parent", "commit", "wf1"])
        self.assertEqual(result, {"trace": ["parent", "wf1"]})

    def test_transform_rejects_missing_or_duplicated_seam(self):
        self.assertRaises(ValueError, carrier.transform_main, b"def agent(): pass\n")
        self.assertRaises(
            ValueError,
            carrier.transform_main,
            fixture_main() + carrier._RETURN_SEAM,
        )

    def test_builder_binds_archive_main_donors_and_manifest(self):
        main_raw = fixture_main()
        archive_raw = carrier.staging_composer.archive_bytes(
            {"main.py": main_raw, "TITAN-CONFIG.json": b"{}\n"}
        )
        with tempfile.TemporaryDirectory() as td:
            donor_root = Path(td)
            donor_pins = {}
            for member, body in {
                "r04_wheat_fert.py": b"def apply_wheat_fertilize(*a, **k): return a[1]\n",
                "wf1_current_adapter.py": b"def apply_wf1_current(*a, **k): return a[1]\n",
            }.items():
                (donor_root / member).write_bytes(body)
                donor_pins[member] = carrier.git_blob_sha(body)

            manifest, sources = carrier.build_component(
                archive_raw,
                expected_archive_sha256=carrier.digest(archive_raw),
                expected_main_sha256=carrier.digest(main_raw),
                donor_root=donor_root,
                donor_pins=donor_pins,
            )

        self.assertEqual(manifest["component_id"], carrier.COMPONENT_ID)
        self.assertTrue(manifest["kaggle_submission_hold"])
        self.assertEqual(set(manifest["replacements"]), {"main.py"})
        self.assertEqual(
            set(manifest["additions"]),
            {"r04_wheat_fert.py", "wf1_current_adapter.py"},
        )
        for group in ("replacements", "additions"):
            for spec in manifest[group].values():
                self.assertEqual(hashlib.sha256(sources[spec["source"]]).hexdigest(),
                                 spec["postimage_sha256"])
        self.assertEqual(json.loads(carrier.manifest_bytes(manifest)), manifest)

    def test_builder_rejects_archive_main_and_addition_drift(self):
        main_raw = fixture_main()
        archive_raw = carrier.staging_composer.archive_bytes({"main.py": main_raw})
        kwargs = {
            "expected_archive_sha256": carrier.digest(archive_raw),
            "expected_main_sha256": carrier.digest(main_raw),
        }
        with self.assertRaisesRegex(ValueError, "archive SHA256 mismatch"):
            carrier.build_component(archive_raw, expected_archive_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "main.py SHA256 mismatch"):
            carrier.build_component(archive_raw, **{**kwargs, "expected_main_sha256": "0" * 64})

        collision = carrier.staging_composer.archive_bytes(
            {"main.py": main_raw, "r04_wheat_fert.py": b"already present\n"}
        )
        with self.assertRaisesRegex(ValueError, "addition already exists"):
            carrier.build_component(
                collision,
                expected_archive_sha256=carrier.digest(collision),
                expected_main_sha256=carrier.digest(main_raw),
            )

    def test_pinned_donor_sources_are_unchanged(self):
        payloads = carrier._donor_payloads()
        for member, expected in carrier.DONOR_PINS.items():
            with self.subTest(member=member):
                self.assertEqual(carrier.git_blob_sha(payloads[member]), expected)


if __name__ == "__main__":
    unittest.main()
