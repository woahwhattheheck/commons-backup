#!/usr/bin/env python3
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exact_sha_alt_verifier as v  # noqa: E402


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Verifier Test")
        self.git("config", "user.email", "verifier@example.invalid")
        (self.repo / ".gitignore").write_text("artifact.txt\n", encoding="utf-8")
        (self.repo / "tracked.txt").write_text("original\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.sha = self.git("rev-parse", "HEAD")
        self.receipt = self.root / "receipt.json"

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def spec(self, commands=None, artifacts=None):
        return {
            "repo": str(self.repo),
            "exact_sha": self.sha,
            "commands": commands or [[sys.executable, "-c", "print('ok')"]],
            "artifacts": artifacts or [],
            "timeout_seconds": 5.0,
            "log_preview_bytes": 128,
        }

    def verify_spec(self, spec):
        return v.run_spec(spec, self.receipt)

    def test_happy_path_is_detached_clean_and_explicitly_nonhosted(self):
        row = self.verify_spec(self.spec())
        self.assertEqual(row["outcome"], "PASSED")
        self.assertEqual(row["checkout_sha"], self.sha)
        self.assertEqual(row["post_checkout_sha"], self.sha)
        self.assertTrue(row["detached_head"])
        self.assertTrue(row["pre_tree_clean"])
        self.assertTrue(row["post_tree_clean"])
        self.assertFalse(row["authority"]["hosted_ci_green"])
        self.assertFalse(row["authority"]["merge_authority"])
        self.assertFalse(row["authority"]["credentials_inherited"])
        self.assertEqual(row["verification_kind"], "alternate_nonhosted")
        self.assertFalse(row["policy"]["shell"])
        self.assertEqual(row["policy"]["artifact_patterns"], [])

    def test_exact_head_mismatch_rejected_before_commands(self):
        marker = self.root / "should-not-run"
        spec = self.spec([[sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"]])
        with mock.patch.object(v, "_head_sha", return_value="b" * 40):
            row = self.verify_spec(spec)
        self.assertEqual(row["outcome"], "FAILED")
        self.assertIn("wrong SHA", row["failure"])
        self.assertEqual(row["commands"], [])
        self.assertFalse(marker.exists())

    def test_dirty_tree_before_commands_fails_closed(self):
        marker = self.root / "should-not-run-pre-dirty"
        spec = self.spec([[sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"]])
        with mock.patch.object(v, "_tree_status", side_effect=[["?? injected.txt"], []]):
            row = self.verify_spec(spec)
        self.assertEqual(row["outcome"], "FAILED")
        self.assertIn("checkout is dirty", row["failure"])
        self.assertEqual(row["commands"], [])
        self.assertFalse(marker.exists())

    def test_head_change_after_command_fails_closed(self):
        argv = [
            "git", "-c", "user.name=Verifier Test", "-c",
            "user.email=verifier@example.invalid", "commit", "--allow-empty",
            "-qm", "drift",
        ]
        row = self.verify_spec(self.spec([argv]))
        self.assertEqual(row["outcome"], "FAILED")
        self.assertIn("wrong SHA", row["failure"])
        self.assertNotEqual(row["post_checkout_sha"], self.sha)

    def test_dirty_tree_after_command_fails_closed(self):
        code = "from pathlib import Path; Path('tracked.txt').write_text('changed\\n')"
        row = self.verify_spec(self.spec([[sys.executable, "-c", code]]))
        self.assertEqual(row["outcome"], "FAILED")
        self.assertFalse(row["post_tree_clean"])
        self.assertIn("dirty after commands", row["failure"])

    def test_command_failure_exit_code_and_logs_propagate(self):
        code = "import sys; print('boom-out'); print('boom-err', file=sys.stderr); raise SystemExit(7)"
        row = self.verify_spec(self.spec([[sys.executable, "-c", code]]))
        self.assertEqual(row["outcome"], "FAILED")
        self.assertEqual(row["commands"][0]["exit_code"], 7)
        self.assertIn("boom-out", row["commands"][0]["stdout"]["preview_utf8"])
        self.assertIn("boom-err", row["commands"][0]["stderr"]["preview_utf8"])
        self.assertIn("exited 7", row["failure"])

    def test_ignored_artifact_can_be_hashed_without_dirtying_checkout(self):
        payload = "artifact-body"
        code = f"from pathlib import Path; Path('artifact.txt').write_text({payload!r})"
        row = self.verify_spec(self.spec([[sys.executable, "-c", code]], ["artifact.txt"]))
        self.assertEqual(row["outcome"], "PASSED", row["failure"])
        self.assertTrue(row["post_tree_clean"])
        self.assertEqual(row["artifacts"], [{
            "path": "artifact.txt",
            "bytes": len(payload.encode()),
            "sha256": hashlib.sha256(payload.encode()).hexdigest(),
        }])

    def test_receipt_roundtrip_and_tamper_detection(self):
        row = self.verify_spec(self.spec())
        disk = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(row, disk)
        self.assertTrue(v.verify_receipt(disk))
        tampered = copy.deepcopy(disk)
        tampered["checkout_sha"] = "0" * 40
        self.assertFalse(v.verify_receipt(tampered))

    def test_log_preview_is_bounded_but_hash_covers_full_output(self):
        text = "x" * 10000
        row = self.verify_spec(self.spec([[sys.executable, "-c", f"print({text!r}, end='')"]]))
        log = row["commands"][0]["stdout"]
        self.assertEqual(log["bytes"], len(text))
        self.assertEqual(len(log["preview_utf8"]), 128)
        self.assertTrue(log["preview_truncated"])
        self.assertEqual(log["sha256"], hashlib.sha256(text.encode()).hexdigest())

    def test_cli_run_and_receipt_verification_roundtrip(self):
        spec_path = self.root / "spec.json"
        spec_path.write_text(json.dumps(self.spec()), encoding="utf-8")
        run = subprocess.run(
            [sys.executable, str(HERE / "exact_sha_alt_verifier.py"), "run",
             str(spec_path), "--receipt", str(self.receipt)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        summary = json.loads(run.stdout)
        self.assertEqual(summary["verification_kind"], "alternate_nonhosted")
        verify = subprocess.run(
            [sys.executable, str(HERE / "exact_sha_alt_verifier.py"), "verify-receipt",
             str(self.receipt)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(verify.returncode, 0, verify.stderr)
        self.assertTrue(json.loads(verify.stdout)["receipt_valid"])

    def test_obvious_provider_mutators_and_credential_url_are_rejected(self):
        for argv in (["git", "push"], ["gh", "pr", "merge", "1"], ["curl", "https://example.invalid"], ["npm", "publish"], [sys.executable, "-m", "twine", "upload", "dist/*"]):
            with self.subTest(argv=argv), self.assertRaises(v.VerifyError):
                v._reject_obvious_provider_mutator(list(argv))
        with self.assertRaisesRegex(v.VerifyError, "credentials"):
            v._safe_repo("https://user:token@example.invalid/repo.git")
        with self.assertRaisesRegex(v.VerifyError, "scheme"):
            v._safe_repo("ext::sh -c exploit")
        with self.assertRaisesRegex(v.VerifyError, "scp-style"):
            v._safe_repo("git@example.invalid:repo.git")


if __name__ == "__main__":
    unittest.main()
