from __future__ import annotations

import inspect
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

from tools.outbound_send_guard import _muse_election_v2_tests_core as _core_tests
from tools.outbound_send_guard import muse_current_authority_v2 as current_auth
from tools.outbound_send_guard import muse_election_v2 as gate


class MuseElectionV2Tests(_core_tests.MuseElectionV2Tests):
    """Run the predecessor hostile suite through the sealed public boundary."""

    def compile(
        self,
        req=None,
        snapshot=None,
        observed=_core_tests.OBSERVED,
        prior=(),
        complete=True,
    ):
        # Test-only direct dependency rebinding keeps the frozen predecessor
        # fixtures deterministic. Arbitrary same-process mutation is explicitly
        # outside the production authority threat model; application callers
        # have no supported observed_at API/CLI input.
        req = req or _core_tests.request()
        snapshot = snapshot or _core_tests.happy(req)
        old = current_auth._utc_now
        current_auth._utc_now = lambda: gate._utc(observed, "test.observed_at")
        try:
            return gate.compile_receipt(
                req,
                snapshot,
                prior_receipts=prior,
                ledger_complete=complete,
            )
        finally:
            current_auth._utc_now = old

    def test_happy_selected_and_bound(self):
        req = _core_tests.request()
        receipt = self.compile(req)
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertIn(current_auth.UNAUTHENTICATED_SNAPSHOT_REASON, receipt["payload"]["reasons"])
        self.assertIn(current_auth.CURRENT_POSITIVE_DISABLED_REASON, receipt["payload"]["reasons"])
        self.assertTrue(gate.verify_receipt(receipt))
        self.assertFalse(gate.verify_selected_binding(req, receipt))
        self.assertEqual(receipt["payload"]["authority_mode"], current_auth.AUTHORITY_MODE)
        self.assertFalse(receipt["payload"]["snapshot_authenticated"])
        self.assertFalse(receipt["payload"]["external_send_authorized"])
        self.assertFalse(receipt["payload"]["side_effects_authorized"])

    def test_other_candidate_selected_means_not_selected(self):
        mine = _core_tests.request()
        other = _core_tests.request(
            _core_tests.candidate("Z-OTHER", "9" * 64, "OP-B", "claim-b"),
            rid="req-00000002",
        )
        snapshot = _core_tests.snap(
            [
                _core_tests.msg(_core_tests.sts(5), _core_tests.SENDER, mine["message"]),
                _core_tests.msg(_core_tests.sts(6), _core_tests.OTHER, other["message"]),
                _core_tests.msg(_core_tests.sts(15), _core_tests.MUSE, _core_tests.selected_text(other)),
            ]
        )
        receipt = self.compile(mine, snapshot)
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertIn(current_auth.UNAUTHENTICATED_SNAPSHOT_REASON, receipt["payload"]["reasons"])
        self.assertIn(current_auth.CURRENT_NEGATIVE_DISABLED_REASON, receipt["payload"]["reasons"])
        for name in current_auth._SELECTION_FIELDS + current_auth._WINNER_FIELDS:
            self.assertIsNone(receipt["payload"][name])
        self.assertTrue(gate.verify_receipt(receipt))
        self.assertFalse(gate.verify_selected_binding(mine, receipt))

    def test_explicit_not_selected(self):
        req = _core_tests.request()
        snapshot = _core_tests.snap(
            [
                _core_tests.msg(_core_tests.sts(5), _core_tests.SENDER, req["message"]),
                _core_tests.msg(
                    _core_tests.sts(15),
                    _core_tests.MUSE,
                    _core_tests.selected_text(req, "NOT_SELECTED"),
                ),
            ]
        )
        receipt = self.compile(req, snapshot)
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertIn(current_auth.UNAUTHENTICATED_SNAPSHOT_REASON, receipt["payload"]["reasons"])
        self.assertIn(current_auth.CURRENT_NEGATIVE_DISABLED_REASON, receipt["payload"]["reasons"])
        for name in current_auth._SELECTION_FIELDS + current_auth._WINNER_FIELDS:
            self.assertIsNone(receipt["payload"][name])
        self.assertTrue(gate.verify_receipt(receipt))
        self.assertFalse(gate.verify_selected_binding(req, receipt))

    def test_selected_then_cancelled_not_selected(self):
        req = _core_tests.request()
        snapshot = _core_tests.snap(
            [
                _core_tests.msg(_core_tests.sts(5), _core_tests.SENDER, req["message"]),
                _core_tests.msg(_core_tests.sts(15), _core_tests.MUSE, _core_tests.selected_text(req)),
                _core_tests.msg(
                    _core_tests.sts(16),
                    _core_tests.MUSE,
                    _core_tests.selected_text(req, "CANCELLED"),
                ),
            ]
        )
        receipt = self.compile(req, snapshot)
        self.assertEqual(receipt["payload"]["decision"], "HOLD")
        self.assertIn(current_auth.UNAUTHENTICATED_SNAPSHOT_REASON, receipt["payload"]["reasons"])
        self.assertIn(current_auth.CURRENT_NEGATIVE_DISABLED_REASON, receipt["payload"]["reasons"])
        self.assertIsNone(receipt["payload"]["selection_binding_sha256"])
        self.assertTrue(gate.verify_receipt(receipt))
        self.assertFalse(gate.verify_selected_binding(req, receipt))

    def test_public_error_type_remains_catchable(self):
        self.assertTrue(issubclass(gate.MuseElectionV2Error, ValueError))
        c = _core_tests.candidate()
        c["mystery"] = True
        with self.assertRaises(gate.MuseElectionV2Error):
            gate.normalize_candidate(c)

    def test_candidate_digest_requires_request_generation(self):
        with self.assertRaises(TypeError):
            gate.candidate_digest(_core_tests.candidate())

    def test_compile_signature_has_no_observed_at(self):
        self.assertNotIn("observed_at", inspect.signature(gate.compile_receipt).parameters)

    def test_public_wrapper_has_no_core_escape(self):
        with self.assertRaises(AttributeError):
            getattr(gate, "_core")
        self.assertNotIn("_core", dir(gate))

    def test_legacy_core_is_not_importable(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import importlib; importlib.import_module('tools.outbound_send_guard._muse_election_v2_core')",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(b"_muse_election_v2_core", proc.stderr)

    def test_legacy_core_has_no_python_m_cli(self):
        proc = subprocess.run(
            [sys.executable, "-m", "tools.outbound_send_guard._muse_election_v2_core", "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_threat_model_does_not_claim_same_process_sandboxing(self):
        self.assertIn("same-process", gate.AUTHORITY_THREAT_MODEL)
        self.assertIn("out of scope", gate.AUTHORITY_THREAT_MODEL)

    def test_cli_selected_exit_zero(self):
        # Replacement for the predecessor CLI test: a fresh raw SELECTED
        # snapshot must compile successfully but fail closed to HOLD (exit 4).
        now = datetime.now(timezone.utc).replace(microsecond=0)
        requested = now - timedelta(seconds=20)
        req = gate.prepare_request(
            _core_tests.candidate(),
            request_id="req-00000001",
            requested_at=gate._fmt(requested),
        )

        def slack_ts(value: datetime, frac: int) -> str:
            return f"{int(value.timestamp())}.{frac:06d}"

        snapshot = {
            "schema_version": gate.SNAPSHOT_SCHEMA,
            "complete": True,
            "channel_id": gate.MUSE_DM_CONVERSATION_ID,
            "coverage_started_at": gate._fmt(requested - timedelta(seconds=600)),
            "captured_at": gate._fmt(now - timedelta(seconds=5)),
            "messages": [
                {
                    "message_ts": slack_ts(now - timedelta(seconds=15), 1),
                    "author_user_id": _core_tests.SENDER,
                    "text": req["message"],
                },
                {
                    "message_ts": slack_ts(now - timedelta(seconds=10), 2),
                    "author_user_id": gate.MUSE_USER_ID,
                    "text": gate._decision_message(
                        "SELECTED",
                        req["payload"]["request_id"],
                        req["payload"]["publication_key"],
                        req["payload"]["candidate_sha256"],
                    ),
                },
            ],
        }
        with tempfile.TemporaryDirectory() as td:
            request_path = os.path.join(td, "request.json")
            snapshot_path = os.path.join(td, "snapshot.json")
            with open(request_path, "w", encoding="utf-8") as handle:
                json.dump(req, handle)
            with open(snapshot_path, "w", encoding="utf-8") as handle:
                json.dump(snapshot, handle)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tools.outbound_send_guard.muse_election_v2",
                    "compile",
                    "--request",
                    request_path,
                    "--snapshot",
                    snapshot_path,
                    "--ledger-complete",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(proc.returncode, 4, proc.stderr.decode())
            out = json.loads(proc.stdout)
            self.assertEqual(out["payload"]["decision"], "HOLD")
            self.assertIn(current_auth.CURRENT_POSITIVE_DISABLED_REASON, out["payload"]["reasons"])

    def test_cli_rejects_caller_observed_at(self):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.outbound_send_guard.muse_election_v2",
                "compile",
                "--request",
                "missing-request.json",
                "--snapshot",
                "missing-snapshot.json",
                "--observed-at",
                _core_tests.OBSERVED,
                "--ledger-complete",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn(b"unrecognized arguments: --observed-at", proc.stderr)


if __name__ == "__main__":
    import unittest

    unittest.main()
