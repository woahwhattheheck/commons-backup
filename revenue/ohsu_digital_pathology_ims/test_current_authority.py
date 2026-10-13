# SPDX-License-Identifier: Apache-2.0
import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import current_authority
from current_authority import (
    CURRENT_SCHEMA,
    HISTORICAL_SCHEMA,
    PRODUCTION_ROOT_DISPLAY,
    QualificationError,
    evaluate_current,
    evaluate_current_bytes,
    evaluate_historical_with_root,
    probe_trusted_root_for_testing,
)
from test_qualification import HEX_A, HEX_B, NOW, bind_manifest, qualified_payload


def _trusted_root(payload):
    return payload["requirements_manifest"]["completeness_attestation"]["sha256"]


class HistoricalAuthorityTests(unittest.TestCase):
    def test_exact_injected_root_is_historical_only(self):
        payload = qualified_payload()
        receipt = evaluate_historical_with_root(
            payload,
            evaluated_at=NOW,
            trusted_completeness_sha256=_trusted_root(payload),
        )
        self.assertEqual(receipt["schema"], HISTORICAL_SCHEMA)
        self.assertEqual(
            receipt["historical_candidate_decision"],
            "READY_FOR_INTERNAL_BID_REVIEW",
        )
        self.assertEqual(receipt["decision"], "HOLD")
        self.assertIn("HISTORICAL_INTEGRITY_ONLY", receipt["holds"])
        self.assertFalse(receipt["current_authority"])

    def test_missing_injected_root_is_historical_hold(self):
        payload = qualified_payload()
        receipt = evaluate_historical_with_root(
            payload,
            evaluated_at=NOW,
            trusted_completeness_sha256=None,
        )
        self.assertEqual(receipt["decision"], "HOLD")
        self.assertIn(
            "TRUSTED_COMPLETENESS_ROOT_MISSING_OR_INVALID",
            receipt["holds"],
        )
        self.assertFalse(receipt["current_authority"])

    def test_reminted_easy_universe_cannot_match_retained_root(self):
        payload = qualified_payload()
        retained_root = _trusted_root(payload)
        payload["minimum_qualifications"] = [
            {
                "id": "easy",
                "mandatory": True,
                "text": "Easy synthetic substitute",
            }
        ]
        payload["evidence"] = [
            {
                "requirement_id": "easy",
                "result": "PASS",
                "reference": "artifact://easy",
                "sha256": HEX_B,
            }
        ]
        bind_manifest(payload)
        self.assertNotEqual(_trusted_root(payload), retained_root)
        receipt = evaluate_historical_with_root(
            payload,
            evaluated_at=NOW,
            trusted_completeness_sha256=retained_root,
        )
        self.assertIn("TRUSTED_COMPLETENESS_ROOT_MISMATCH", receipt["holds"])
        self.assertFalse(receipt["current_authority"])


class CurrentAuthoritySurfaceTests(unittest.TestCase):
    def test_current_signatures_have_no_root_clock_or_launcher_selector(self):
        self.assertEqual(list(inspect.signature(evaluate_current).parameters), ["payload"])
        self.assertEqual(list(inspect.signature(evaluate_current_bytes).parameters), ["raw"])
        self.assertFalse(hasattr(current_authority, "TRUSTED_ROOT_PATH"))
        self.assertFalse(hasattr(current_authority, "_utc_now_string"))
        self.assertFalse(hasattr(current_authority, "_load_trusted_completeness_root"))

    def test_imported_child_entrypoint_cannot_emit_current_authority(self):
        with self.assertRaises(RuntimeError):
            current_authority._child_main(["--isolated-current-child"])

    def test_parent_module_rebinding_does_not_cross_fresh_process(self):
        payload = qualified_payload()

        def forbidden(*args, **kwargs):
            raise AssertionError("parent monkeypatch crossed isolated boundary")

        with (
            mock.patch.object(
                current_authority,
                "PRODUCTION_ROOT_DISPLAY",
                "/tmp/attacker-controlled-root",
            ),
            mock.patch.object(
                current_authority,
                "evaluate_current_bytes",
                side_effect=forbidden,
            ),
            mock.patch.object(
                current_authority,
                "TRUSTED_ROOT_PATH",
                "/tmp/legacy-attacker-root",
                create=True,
            ),
            mock.patch.object(
                current_authority,
                "_utc_now_string",
                side_effect=forbidden,
                create=True,
            ),
            mock.patch.object(
                current_authority,
                "_load_trusted_completeness_root",
                side_effect=forbidden,
                create=True,
            ),
            mock.patch.object(
                current_authority,
                "_probe_retained_root",
                side_effect=forbidden,
            ),
            mock.patch.object(
                current_authority,
                "_candidate_attestation_sha256",
                side_effect=forbidden,
            ),
            mock.patch.object(
                current_authority.json,
                "loads",
                side_effect=forbidden,
            ),
            mock.patch.object(
                current_authority,
                "CURRENT_SCHEMA",
                "attacker-current-schema",
            ),
            mock.patch.object(current_authority.subprocess, "run", side_effect=forbidden),
        ):
            receipt = evaluate_current(payload)

        self.assertEqual(receipt["schema"], CURRENT_SCHEMA)
        self.assertEqual(
            receipt["trusted_completeness_root_source"],
            PRODUCTION_ROOT_DISPLAY,
        )
        self.assertFalse(receipt["current_authority"])
        self.assertEqual(receipt["decision"], "HOLD")
        self.assertTrue(
            {
                "TRUSTED_COMPLETENESS_ROOT_MISSING_OR_INVALID",
                "TRUSTED_COMPLETENESS_ROOT_MISMATCH",
            }
            & set(receipt["holds"])
        )

    def test_current_bytes_reject_duplicate_json_keys_in_child(self):
        with self.assertRaises(QualificationError):
            evaluate_current_bytes(b'{"opportunity":{},"opportunity":{}}')


@unittest.skipUnless(os.name == "posix", "POSIX descriptor custody only")
class RetainedRootCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.directory = Path(self.tmp.name)
        self.root = self.directory / "trusted_completeness.sha256"
        self.uid = os.getuid()
        os.chmod(self.directory, 0o700)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_root(self, value=HEX_A, mode=0o600):
        self.root.write_text(value + "\n", encoding="ascii")
        os.chmod(self.root, mode)

    def _probe(self, hook=None):
        return probe_trusted_root_for_testing(
            self.root,
            expected_uid=self.uid,
            after_read_hook=hook,
        )

    def test_secure_regular_single_link_root_is_accepted_by_probe_only(self):
        self._write_root()
        result = self._probe()
        self.assertEqual(result["custody"], "VERIFIED")
        self.assertEqual(result["value"], HEX_A)
        self.assertNotIn("current_authority", result)

    def test_symlink_root_is_rejected_without_following(self):
        target = self.directory / "target"
        target.write_text(HEX_A + "\n", encoding="ascii")
        os.chmod(target, 0o600)
        self.root.symlink_to(target.name)
        result = self._probe()
        self.assertEqual(result["custody"], "UNAVAILABLE")
        self.assertIsNone(result["value"])

    def test_group_or_other_readable_root_is_rejected(self):
        self._write_root(mode=0o644)
        result = self._probe()
        self.assertEqual(result["custody"], "UNAVAILABLE")

    def test_multi_link_root_is_rejected(self):
        self._write_root()
        os.link(self.root, self.directory / "alias")
        result = self._probe()
        self.assertEqual(result["custody"], "UNAVAILABLE")

    def test_malformed_and_oversize_roots_are_rejected(self):
        self.root.write_text("not-a-digest\n", encoding="ascii")
        os.chmod(self.root, 0o600)
        self.assertEqual(self._probe()["custody"], "UNAVAILABLE")
        self.root.write_text(("a" * 66) + "\n", encoding="ascii")
        os.chmod(self.root, 0o600)
        self.assertEqual(self._probe()["custody"], "UNAVAILABLE")

    def test_pathname_successor_swap_after_read_is_rejected(self):
        self._write_root()
        detached = self.directory / "detached-root"

        def swap_generation():
            self.root.rename(detached)
            self._write_root()

        result = self._probe(hook=swap_generation)
        self.assertEqual(result["custody"], "UNAVAILABLE")
        self.assertIsNone(result["value"])
        self.assertEqual(detached.read_text(encoding="ascii"), HEX_A + "\n")


if __name__ == "__main__":
    unittest.main()
