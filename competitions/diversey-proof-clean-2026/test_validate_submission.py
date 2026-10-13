import hashlib
import inspect
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import validate_submission as validator

BASE = Path(__file__).resolve().parent
NOW = datetime(2026, 9, 14, 21, 0, tzinfo=timezone.utc)
AFTER_DEADLINE = datetime(2026, 9, 22, 5, 0, tzinfo=timezone.utc)

class SubmissionValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "carrier"
        self.authority = self.base / "authority"
        self.root.mkdir(); self.authority.mkdir(); (self.authority / validator.EVENT_DIR_NAME).mkdir()
        for name in [
            "README.md",
            "REQUIREMENTS-EVIDENCE.md",
            "SCIENTIFIC-BASIS.md",
            "PROPOSAL-DRAFT.md",
            "SUBMISSION-CHECKLIST.md",
            "readiness.json",
        ]:
            shutil.copy2(BASE / name, self.root / name)

    def tearDown(self):
        self.temp.cleanup()

    def eval_test(self, *, now_utc=NOW, authority_root=None):
        tagged, errors = validator._validate_with_context_for_tests(
            self.root,
            authority_root=authority_root or self.authority,
            now_utc=now_utc,
        )
        self.assertTrue(tagged.startswith("TEST_ONLY_"))
        return tagged.removeprefix("TEST_ONLY_"), errors

    def manifest(self):
        return json.loads((self.root / "readiness.json").read_text(encoding="utf-8"))

    def write_manifest(self, data):
        (self.root / "readiness.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def arm_ready(self, text="Final proposal materially rewritten and reviewed by the authorized human applicant.\n"):
        final = self.root / "FINAL-HUMAN-PROPOSAL.md"
        final.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(final.read_bytes()).hexdigest()
        data = self.manifest()
        data["state"] = "READY"
        data["human_observations"] = {key: True for key in validator.REQUIRED_GATES}
        data["artifacts"]["final_proposal"] = {"path": final.name, "sha256": digest}
        self.write_manifest(data)
        return final, digest

    def write_release(self, proposal_sha, **updates):
        record = {
            "schema": validator.OWNER_RELEASE_SCHEMA,
            "carrier_id": validator.CARRIER_ID,
            "operation_id": validator.OPERATION_ID,
            "decision": "AUTHORIZE_SUBMISSION",
            "applicant_id": "opaque-applicant-7f3a",
            "reviewer_id": "opaque-reviewer-b291",
            "challenge_agreement_generation": "human-reviewed-2026-09-14",
            "challenge_agreement_sha256": "a" * 64,
            "proposal_sha256": proposal_sha,
            "source_bundle_sha256": validator.source_bundle_sha256(self.root),
            "human_gates": {key: True for key in validator.REQUIRED_GATES},
            "authorized_at_utc": "2026-09-14T20:55:00Z",
            "valid_until_utc": "2026-09-22T03:59:00Z"
        }
        record.update(updates)
        path = self.authority / "owner-release.json"
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def write_event(self, event, proposal_sha, idx=0, predecessor=None, observed_at="2026-09-14T20:58:00Z"):
        record = {
            "schema": validator.EVENT_SCHEMA,
            "carrier_id": validator.CARRIER_ID,
            "operation_id": validator.OPERATION_ID,
            "event": event,
            "provider_source_id": f"opaque-provider-receipt-{idx}",
            "provider_source_sha256": hashlib.sha256(f"provider-{idx}".encode()).hexdigest(),
            "proposal_sha256": proposal_sha,
            "observed_at_utc": observed_at
        }
        if predecessor is not None:
            record["predecessor_event_sha256"] = hashlib.sha256(Path(predecessor).read_bytes()).hexdigest()
        path = self.authority / validator.EVENT_DIR_NAME / f"event-{idx}.json"
        path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def test_baseline_blocked_is_structurally_valid(self):
        self.assertEqual(("BLOCKED", []), self.eval_test())

    def test_duplicate_manifest_key_is_rejected(self):
        raw = (self.root / "readiness.json").read_text()
        (self.root / "readiness.json").write_text(raw[:-2] + ',\n  "state": "READY"\n}\n', encoding="utf-8")
        state, errors = self.eval_test()
        self.assertEqual("UNKNOWN", state)
        self.assertTrue(any("duplicate JSON key: state" in e for e in errors))

    def test_forged_all_true_candidate_cannot_mint_ready(self):
        _, digest = self.arm_ready()
        state, errors = self.eval_test()
        self.assertEqual("READY", state)
        self.assertTrue(any("fixed host path" in e for e in errors))

    def test_valid_external_release_can_authorize_exact_ready_generation(self):
        _, digest = self.arm_ready()
        release = self.write_release(digest)
        state, errors = self.eval_test()
        self.assertEqual("READY", state)
        self.assertEqual([], errors)

    def test_release_for_proposal_a_cannot_be_transplanted_to_proposal_b(self):
        final, digest = self.arm_ready("Proposal A human bytes\n")
        release = self.write_release(digest)
        final.write_text("Proposal B human bytes\n", encoding="utf-8")
        new = hashlib.sha256(final.read_bytes()).hexdigest()
        data = self.manifest(); data["artifacts"]["final_proposal"]["sha256"] = new; self.write_manifest(data)
        _, errors = self.eval_test()
        self.assertTrue(any("owner release proposal_sha256" in e for e in errors))

    def test_source_mutation_invalidates_owner_release(self):
        _, digest = self.arm_ready()
        release = self.write_release(digest)
        (self.root / "README.md").write_text("mutated source\n", encoding="utf-8")
        _, errors = self.eval_test()
        self.assertTrue(any("source_bundle_sha256" in e for e in errors))

    def test_post_deadline_ready_is_expired_by_verifier_clock(self):
        _, digest = self.arm_ready()
        release = self.write_release(digest)
        _, errors = self.eval_test(now_utc=AFTER_DEADLINE)
        self.assertTrue(any("verifier-owned UTC" in e for e in errors))

    def test_final_proposal_symlink_is_rejected(self):
        outside = self.root / "real-final.md"; outside.write_text("human final\n", encoding="utf-8")
        link = self.root / "FINAL-HUMAN-PROPOSAL.md"; link.symlink_to(outside.name)
        data = self.manifest(); data["state"] = "READY"; data["human_observations"] = {k: True for k in validator.REQUIRED_GATES}
        data["artifacts"]["final_proposal"] = {"path": link.name, "sha256": hashlib.sha256(outside.read_bytes()).hexdigest()}; self.write_manifest(data)
        _, errors = self.eval_test()
        self.assertTrue(any("no-follow" in e for e in errors))

    def test_source_symlink_is_rejected(self):
        real = self.root / "real-readme.md"; real.write_text("x\n", encoding="utf-8")
        (self.root / "README.md").unlink(); (self.root / "README.md").symlink_to(real.name)
        state, errors = self.eval_test()
        self.assertEqual("UNKNOWN", state)
        self.assertTrue(any("no-follow" in e for e in errors))

    def test_candidate_cannot_forge_submitted_award_payment_chain(self):
        data = self.manifest()
        for key in ("submitted", "award_received", "payment_received"): data["external_observations"][key] = True
        self.write_manifest(data)
        _, errors = self.eval_test()
        self.assertEqual(3, sum("candidate-controlled" in e for e in errors))

    def test_external_event_chain_is_evidence_bound(self):
        _, digest = self.arm_ready()
        release = self.write_release(digest)
        submitted = self.write_event("SUBMITTED", digest, 1)
        award = self.write_event("AWARD_RECEIVED", digest, 2, predecessor=submitted, observed_at="2026-09-14T20:59:00Z")
        payment = self.write_event("PAYMENT_RECEIVED", digest, 3, predecessor=award, observed_at="2026-09-14T21:00:00Z")
        _, errors = self.eval_test()
        self.assertEqual([], errors)

    def test_payment_without_award_evidence_is_rejected(self):
        payment = self.write_event("PAYMENT_RECEIVED", "b" * 64, idx=9)
        _, errors = self.eval_test()
        self.assertTrue(any("PAYMENT_RECEIVED requires AWARD_RECEIVED" in e for e in errors))

    def test_owner_release_inside_candidate_tree_is_rejected(self):
        _, digest = self.arm_ready()
        outside = self.write_release(digest)
        inside = self.root / validator.OWNER_RELEASE_NAME; shutil.copy2(outside, inside)
        _, errors = self.eval_test(authority_root=self.root)
        self.assertTrue(any("must live outside" in e for e in errors))

    def test_duplicate_key_in_owner_release_is_rejected(self):
        _, digest = self.arm_ready(); release = self.write_release(digest)
        raw = release.read_text(); release.write_text(raw[:-2] + ',\n  "decision": "AUTHORIZE_SUBMISSION"\n}\n')
        _, errors = self.eval_test()
        self.assertTrue(any("duplicate JSON key: decision" in e for e in errors))

    def test_award_must_bind_exact_submission_event_digest(self):
        _, digest = self.arm_ready(); self.write_release(digest)
        submitted = self.write_event("SUBMITTED", digest, 11)
        award = self.write_event("AWARD_RECEIVED", digest, 12, predecessor=submitted, observed_at="2026-09-14T20:59:00Z")
        record = json.loads(award.read_text()); record["predecessor_event_sha256"] = "0" * 64
        award.write_text(json.dumps(record, sort_keys=True) + "\n")
        _, errors = self.eval_test()
        self.assertTrue(any("bind the exact SUBMITTED" in e for e in errors))

    def test_provider_event_time_order_is_monotonic(self):
        _, digest = self.arm_ready(); self.write_release(digest)
        submitted = self.write_event("SUBMITTED", digest, 21, observed_at="2026-09-14T20:59:00Z")
        award = self.write_event("AWARD_RECEIVED", digest, 22, predecessor=submitted, observed_at="2026-09-14T20:58:00Z")
        _, errors = self.eval_test()
        self.assertTrue(any("AWARD_RECEIVED cannot predate SUBMITTED" in e for e in errors))

    def test_every_provider_event_binds_exact_proposal(self):
        _, digest = self.arm_ready(); self.write_release(digest)
        submitted = self.write_event("SUBMITTED", digest, 31)
        award = self.write_event("AWARD_RECEIVED", "c" * 64, 32, predecessor=submitted, observed_at="2026-09-14T20:59:00Z")
        _, errors = self.eval_test()
        self.assertTrue(any("AWARD_RECEIVED proposal_sha256" in e for e in errors))

    def test_provider_source_digest_case_remint_is_rejected(self):
        _, digest = self.arm_ready(); self.write_release(digest)
        submitted = self.write_event("SUBMITTED", digest, 41)
        award = self.write_event(
            "AWARD_RECEIVED",
            digest,
            42,
            predecessor=submitted,
            observed_at="2026-09-14T20:59:00Z",
        )
        submitted_record = json.loads(submitted.read_text())
        award_record = json.loads(award.read_text())
        award_record["provider_source_sha256"] = submitted_record["provider_source_sha256"].upper()
        award.write_text(json.dumps(award_record, sort_keys=True) + "\n")
        _, errors = self.eval_test()
        self.assertTrue(any("provider_source_sha256 must be unique" in e for e in errors))

    def test_public_validate_has_no_authority_or_clock_override(self):
        params = tuple(inspect.signature(validator.validate).parameters)
        self.assertEqual(("root",), params)
        with self.assertRaises(TypeError):
            validator.validate(self.root, authority_root=self.authority)
        with self.assertRaises(TypeError):
            validator.validate(self.root, now_utc=NOW)

    def test_module_global_rebinding_cannot_redirect_current_authority_or_clock(self):
        _, digest = self.arm_ready()
        self.write_release(digest)

        original_root = validator.AUTHORITY_ROOT
        original_datetime = validator.datetime

        class BombDatetime:
            @classmethod
            def now(cls, tz=None):
                raise AssertionError("production validate consulted mutable module datetime")

        try:
            validator.AUTHORITY_ROOT = self.authority
            validator.datetime = BombDatetime
            state, errors = validator.validate(self.root)
        finally:
            validator.AUTHORITY_ROOT = original_root
            validator.datetime = original_datetime

        self.assertEqual("READY", state)
        self.assertTrue(errors)
        self.assertTrue(any("/var/lib/commons-authority/diversey-proof-clean-2026/owner-release.json" in e for e in errors))

    def test_explicit_context_helper_is_mechanically_noncurrent(self):
        _, digest = self.arm_ready()
        self.write_release(digest)
        tagged, errors = validator._validate_with_context_for_tests(
            self.root, authority_root=self.authority, now_utc=NOW
        )
        self.assertEqual("TEST_ONLY_READY", tagged)
        self.assertEqual([], errors)
        self.assertNotEqual("READY", tagged)

    def test_authority_root_symlink_is_rejected(self):
        target = self.base / "real-authority"
        target.mkdir(); (target / validator.EVENT_DIR_NAME).mkdir()
        link = self.base / "authority-link"
        link.symlink_to(target, target_is_directory=True)
        _, errors = self.eval_test(authority_root=link)
        self.assertTrue(any("authority root" in e and "no-follow" in e for e in errors))

    def test_events_directory_symlink_is_rejected(self):
        shutil.rmtree(self.authority / validator.EVENT_DIR_NAME)
        attacker = self.base / "attacker-events"
        attacker.mkdir()
        (self.authority / validator.EVENT_DIR_NAME).symlink_to(attacker, target_is_directory=True)
        _, errors = self.eval_test()
        self.assertTrue(any("provider events directory" in e and "no-follow" in e for e in errors))

    def test_retained_authority_fd_survives_parent_path_swap(self):
        trusted_parent = self.base / "trusted-parent"
        trusted_authority = trusted_parent / "authority"
        trusted_authority.mkdir(parents=True)
        original = b'{"origin":"retained-original"}\n'
        (trusted_authority / validator.OWNER_RELEASE_NAME).write_bytes(original)
        fd = validator._open_dir_chain_nofollow(trusted_authority, "test authority root")
        try:
            old_parent = self.base / "trusted-parent-old"
            trusted_parent.rename(old_parent)
            attacker_parent = self.base / "attacker-parent"
            attacker_authority = attacker_parent / "authority"
            attacker_authority.mkdir(parents=True)
            (attacker_authority / validator.OWNER_RELEASE_NAME).write_bytes(b'{"origin":"attacker-substitute"}\n')
            trusted_parent.symlink_to(attacker_parent, target_is_directory=True)
            observed = validator._read_dir_leaf(fd, validator.OWNER_RELEASE_NAME, "owner release")
            self.assertEqual(original, observed)
        finally:
            os.close(fd)

if __name__ == "__main__":
    unittest.main()
