import copy
import unittest

import proofpatch as pp


def rechain(bundle):
    prev = "0" * 64
    for index, receipt in enumerate(bundle["receipts"]):
        receipt["sequence"] = index
        receipt["prev_digest"] = prev
        body = {k: receipt[k] for k in receipt if k != "entry_digest"}
        receipt["entry_digest"] = pp.digest_json(body)
        prev = receipt["entry_digest"]
    body = {k: bundle[k] for k in bundle if k != "bundle_sha256"}
    bundle["bundle_sha256"] = pp.digest_json(body)
    return bundle


class ProofPatchTests(unittest.TestCase):
    def test_demo_structural_verification_is_deterministic_and_truth_narrowed(self):
        a, b = pp.demo_bundle(), pp.demo_bundle()
        self.assertEqual(a, b)
        result = pp.verify_bundle(a)
        self.assertEqual(result["status"], "STRUCTURAL_EVIDENCE_VERIFIED")
        self.assertFalse(result["executor_replay_verified"])
        self.assertTrue(result["replay_required"])
        self.assertEqual(result["receipt_provenance"], "CALLER_AUTHORED_UNAUTHENTICATED")
        self.assertFalse(result["competition_submission_ready"])

    def test_demo_executor_replay_is_a_separate_state(self):
        result = pp.verify_demo_bundle(pp.demo_bundle())
        self.assertEqual(result["status"], "EXECUTOR_REPLAY_VERIFIED")
        self.assertTrue(result["executor_replay_verified"])
        self.assertFalse(result["replay_required"])
        self.assertEqual(result["executor_id"], "proofpatch-hermetic-demo-v1")

    def test_self_resealed_transcript_can_only_be_structural(self):
        bundle = pp.demo_bundle()
        bundle["receipts"][1]["result"]["stdout"] = "caller rewrote this plausible success"
        rechain(bundle)
        structural = pp.verify_bundle(bundle)
        self.assertEqual(structural["status"], "STRUCTURAL_EVIDENCE_VERIFIED")
        self.assertFalse(structural["executor_replay_verified"])
        with self.assertRaises(pp.ProofError):
            pp.verify_demo_bundle(bundle)

    def test_reproduction_must_still_fail_semantically(self):
        bundle = pp.demo_bundle()
        bundle["receipts"][0]["result"]["exit_code"] = 0
        rechain(bundle)
        with self.assertRaises(pp.ProofError):
            pp.verify_bundle(bundle)

    def test_timeout_and_regression_failure_rejected(self):
        for index, field, value in ((2, "timed_out", True), (2, "exit_code", 1)):
            bundle = pp.demo_bundle()
            bundle["receipts"][index]["result"][field] = value
            rechain(bundle)
            with self.assertRaises(pp.ProofError):
                pp.verify_bundle(bundle)

    def test_receipt_reorder_and_cross_task_replay_rejected(self):
        bundle = pp.demo_bundle()
        bundle["receipts"][1], bundle["receipts"][2] = bundle["receipts"][2], bundle["receipts"][1]
        with self.assertRaises(pp.ProofError):
            pp.verify_bundle(bundle)
        bundle = pp.demo_bundle()
        bundle["task"]["task_id"] = "different-task"
        body = {k: bundle[k] for k in bundle if k != "bundle_sha256"}
        bundle["bundle_sha256"] = pp.digest_json(body)
        with self.assertRaises(pp.ProofError):
            pp.verify_bundle(bundle)

    def test_authority_bits_cannot_be_minted(self):
        for field in ("external_side_effects_authorized", "cloud_spend_authorized", "submission_authorized"):
            bundle = pp.demo_bundle()
            bundle["authority"][field] = True
            body = {k: bundle[k] for k in bundle if k != "bundle_sha256"}
            bundle["bundle_sha256"] = pp.digest_json(body)
            with self.assertRaises(pp.ProofError):
                pp.verify_bundle(bundle)

    def test_path_escape_bool_timeout_and_unsafe_commands_rejected(self):
        for path in ("../x.py", "/tmp/x.py", "a/../x.py", "a\\x.py", "./x.py"):
            with self.subTest(path=path), self.assertRaises(pp.ProofError):
                pp.safe_relpath(path)
        with self.assertRaises(pp.ProofError):
            pp.validate_command({"argv": ["python"], "timeout_s": True})
        for command in (
            {"argv": ["python", "-c", "print(1)"], "timeout_s": 5},
            {"argv": ["python", "https://evil.invalid/x.py"], "timeout_s": 5},
            {"argv": ["python", "-m", "pip"], "timeout_s": 5},
            {"argv": ["bash", "test.sh"], "timeout_s": 5},
        ):
            with self.assertRaises(pp.ProofError):
                pp.validate_command(command)

    def test_missing_fake_outcome_is_terminal(self):
        sandbox = pp.HermeticFakeSandbox({})
        command = {"argv": ["python", "-m", "unittest", "test_calc.py"], "timeout_s": 10}
        with self.assertRaises(pp.ProofError):
            sandbox.run(command, "0" * 64)

    def test_executor_replay_requires_explicit_executor_identity(self):
        with self.assertRaises(pp.ProofError):
            pp.verify_with_executor(pp.demo_bundle(), pp.demo_executor(), "bad executor id with spaces")


if __name__ == "__main__":
    unittest.main()
