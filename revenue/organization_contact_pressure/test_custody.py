from __future__ import annotations

from revenue.organization_contact_pressure import authority, ledger, storage
from .test_support import *  # noqa: F401,F403


class CustodyTests(GateTestCase):
    def _load_ledger(self, *, now=None):
        active = storage._load_active_key(self.root)
        retained_authority = authority._load_authority(
            self.root,
            active,
            self.fx.organization,
            now or self.fx.now,
        )
        return ledger._load_ledger(self.root, active, retained_authority, now or self.fx.now)

    def test_authentic_ledger_rollback_below_retained_head_fails_closed(self):
        ledger_path = self.root / "ledgers" / f"{self.fx.organization}.json"
        generation_zero = gate.strict_json_loads(ledger_path.read_bytes())
        self.fx.write_ledger([self.fx.event("sent-1", gate.EVENT_SENT)])
        self.fx.write_ledger([], raw_document=generation_zero, write_head=False)

        with self.assertRaisesRegex(gate.VerificationError, "rollback"):
            self._load_ledger()
        receipt = self.fx.compile()
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)
        self.assertIsNone(receipt["ledger_sha256"])

    def test_stale_but_authentic_quiet_ledger_fails_closed(self):
        future = self.fx.now + timedelta(seconds=self.fx.policy["ledger_max_age_seconds"] + 1)

        with self.assertRaisesRegex(gate.VerificationError, "coverage is stale"):
            self._load_ledger(now=future)
        receipt = self.fx.compile(
            self.fx.request(requested_at=future),
            now=future,
        )
        self.assert_decision(gate.HOLD_AUTHORITY, receipt)
        self.assertIsNone(receipt["ledger_sha256"])

    def test_same_generation_identical_state_coverage_refresh_is_allowed(self):
        refreshed_at = self.fx.now + timedelta(seconds=1)
        self.fx.write_ledger([], updated_at=refreshed_at)

        retained = self._load_ledger()
        self.assertEqual(refreshed_at, retained.updated_at)
        self.assert_decision(gate.READY, self.fx.compile())

    def test_same_generation_authenticated_event_state_fork_fails_closed(self):
        self.fx.write_ledger([self.fx.event("sent-a", gate.EVENT_SENT)])
        self.fx.write_ledger(
            [self.fx.event("sent-b", gate.EVENT_SENT)],
            updated_at=self.fx.now + timedelta(seconds=1),
        )

        with self.assertRaisesRegex(gate.VerificationError, "same-generation ledger fork"):
            self._load_ledger()
        self.assert_decision(gate.HOLD_AUTHORITY, self.fx.compile())

    def test_ledger_newer_than_committed_head_fails_closed(self):
        self.fx.write_ledger(
            [self.fx.event("uncommitted-sent", gate.EVENT_SENT)],
            write_head=False,
        )

        with self.assertRaisesRegex(gate.VerificationError, "newer than"):
            self._load_ledger()
        self.assert_decision(gate.HOLD_AUTHORITY, self.fx.compile())

    def test_forged_active_epoch_head_hmac_fails_closed(self):
        head_dir = self.root / "ledger-heads" / self.fx.organization
        (head_path,) = tuple(head_dir.iterdir())
        document = gate.strict_json_loads(head_path.read_bytes())
        document["signature"] = "00" * 32
        self.fx._write_private(head_path, gate._canonical_bytes(document) + b"\n")

        with self.assertRaisesRegex(gate.VerificationError, "HMAC"):
            self._load_ledger()
        self.assert_decision(gate.HOLD_AUTHORITY, self.fx.compile())

    def test_policy_rotation_requires_fresh_policy_epoch_head(self):
        self.fx.policy["policy_generation"] = 8
        self.fx.write_authority()
        document = self.fx.write_ledger([], write_head=False)

        with self.assertRaisesRegex(gate.VerificationError, "verifier/policy epoch"):
            self._load_ledger()
        self.fx.write_ledger_head(document)
        self.assertEqual(0, self._load_ledger().generation)

    def test_authentic_policy_rollback_below_retained_floor_fails_closed(self):
        authority_path = self.root / "authorities" / f"{self.fx.organization}.json"
        ledger_path = self.root / "ledgers" / f"{self.fx.organization}.json"
        generation_seven_authority = authority_path.read_bytes()
        generation_seven_ledger = ledger_path.read_bytes()

        self.fx.policy["policy_generation"] = 8
        self.fx.write_authority()
        self.fx.write_ledger([])
        self.fx._write_private(authority_path, generation_seven_authority)
        self.fx._write_private(ledger_path, generation_seven_ledger)

        with self.assertRaisesRegex(gate.VerificationError, "policy rollback"):
            self._load_ledger()
        self.assert_decision(gate.HOLD_AUTHORITY, self.fx.compile())

    def test_key_rotation_requires_fresh_active_epoch_head(self):
        self.fx.key_id = "primary-20260915"
        self.fx.verifier_id = "commons-host-2"
        self.fx.key = bytes.fromhex("43" * 32)
        self.fx._write_active_key()
        self.fx.write_authority()
        document = self.fx.write_ledger([], write_head=False)

        with self.assertRaisesRegex(gate.VerificationError, "verifier/policy epoch"):
            self._load_ledger()
        self.fx.write_ledger_head(document)
        self.assertEqual(0, self._load_ledger().generation)

    def test_windows_production_root_is_explicitly_unsupported(self):
        with mock.patch.object(storage.os, "name", "nt"):
            with self.assertRaisesRegex(gate.AuthorityUnavailable, "Windows"):
                storage._authority_root()

    def test_output_success_path_detects_replacement_and_preserves_foreign_file(self):
        output = self.root / "receipt.json"
        moved = self.root / "authored.json"
        foreign = b"foreign-successor"
        real_fsync = os.fsync
        calls = 0

        def rename_and_replace(fd):
            nonlocal calls
            real_fsync(fd)
            calls += 1
            if calls == 1:
                output.rename(moved)
                output.write_bytes(foreign)

        with mock.patch.object(storage.os, "fsync", side_effect=rename_and_replace):
            with self.assertRaisesRegex(gate.InputError, "identity changed"):
                gate._write_exclusive(output, b"authored-receipt")
        self.assertEqual(foreign, output.read_bytes())
        self.assertEqual(b"authored-receipt", moved.read_bytes())

    def test_output_late_failure_does_not_unlink_foreign_successor(self):
        output = self.root / "receipt.json"
        moved = self.root / "authored.json"
        foreign = b"foreign-successor"
        real_fsync = os.fsync
        calls = 0

        def rename_replace_then_fail(fd):
            nonlocal calls
            real_fsync(fd)
            calls += 1
            if calls == 1:
                output.rename(moved)
                output.write_bytes(foreign)
            elif calls == 2:
                raise OSError("late parent fsync failure")

        with mock.patch.object(storage.os, "fsync", side_effect=rename_replace_then_fail):
            with self.assertRaisesRegex(gate.InputError, "ambiguous"):
                gate._write_exclusive(output, b"authored-receipt")
        self.assertEqual(foreign, output.read_bytes())
        self.assertEqual(b"authored-receipt", moved.read_bytes())

    def test_exceptional_publication_has_no_pathname_unlink_surface(self):
        self.assertFalse(hasattr(storage, "_unlink_if_authored"))
        self.assertNotIn("unlink", storage._write_exclusive.__code__.co_names)

        output = self.root / "failed-receipt.json"
        authored = b"authored-but-ambiguous"
        real_fsync = os.fsync
        calls = 0

        def fail_parent_fsync(fd):
            nonlocal calls
            real_fsync(fd)
            calls += 1
            if calls == 2:
                raise OSError("forced late failure")

        with mock.patch.object(storage.os, "unlink", side_effect=AssertionError("unlink must not run")):
            with mock.patch.object(storage.os, "fsync", side_effect=fail_parent_fsync):
                with self.assertRaisesRegex(gate.InputError, "ambiguous"):
                    gate._write_exclusive(output, authored)
        self.assertEqual(authored, output.read_bytes())
