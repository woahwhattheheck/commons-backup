# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("p02_build", HERE / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def fake_parent():
    return (
        b"import baseline_main as baseline\n"
        b"import full_production_context\n"
        b"\n"
        b"def agent(observation, configuration=None):\n"
        b"    returned = baseline.agent(observation, configuration)\n"
        b"    if True:\n"
        b"        pass\n"
        b"    return returned\n"
    )


class P02BuildContracts(unittest.TestCase):
    def setUp(self):
        self.parent = fake_parent()
        self.helper = b"# helper\n"
        self.baseline = {
            "main.py": self.parent,
            "baseline_main.py": b"# embedded parent\n",
            "r04_full_router.py": b"# router\n",
        }
        self.main_sha = build.digest(self.parent)
        self.helper_blob = build._git_blob(self.helper)

    def compose(self, baseline=None, helper=None):
        return build.compose(
            self.baseline if baseline is None else baseline,
            self.helper if helper is None else helper,
            expected_main_sha=self.main_sha,
            expected_helper_blob=self.helper_blob,
        )

    def test_compose_preserves_embedded_baseline_and_only_adds_helper(self):
        files, before, after = self.compose()
        self.assertEqual(before, self.parent)
        self.assertEqual(files["baseline_main.py"], b"# embedded parent\n")
        self.assertEqual(files["r04_full_router.py"], b"# router\n")
        self.assertEqual(files["goose_capacity_economy.py"], self.helper)
        self.assertNotEqual(after, before)
        self.assertIn(b"import goose_capacity_economy as p02\n", after)
        self.assertIn(b"return p02.apply_goose_capacity_economy(", after)

    def test_rejects_wrong_parent_identity(self):
        with self.assertRaisesRegex(ValueError, "main.py identity drift"):
            build.compose(
                self.baseline,
                self.helper,
                expected_main_sha="0" * 64,
                expected_helper_blob=self.helper_blob,
            )

    def test_rejects_preexisting_helper(self):
        baseline = dict(self.baseline)
        baseline["goose_capacity_economy.py"] = b"foreign"
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.compose(baseline=baseline)

    def test_rejects_ambiguous_public_return_seam(self):
        baseline = dict(self.baseline)
        baseline["main.py"] = self.parent + b"    return returned\n"
        with self.assertRaisesRegex(ValueError, "public return seam"):
            build.compose(
                baseline,
                self.helper,
                expected_main_sha=build.digest(baseline["main.py"]),
                expected_helper_blob=self.helper_blob,
            )

    def test_publish_pair_delegates_exact_payloads_to_shared_custody(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tar_path = root / "candidate.tar.gz"
            receipt_path = root / "receipt.json"
            record = {"schema": "x", "candidate_archive_sha256": hashlib.sha256(b"abc").hexdigest()}
            with mock.patch.object(build, "publish_exclusive") as publish:
                result = build.publish_pair(tar_path, receipt_path, b"abc", record)
            self.assertIs(result, record)
            publish.assert_called_once()
            pairs = publish.call_args.args[0]
            self.assertEqual(pairs[0], (tar_path, b"abc"))
            self.assertEqual(pairs[1][0], receipt_path)
            self.assertIn(b'"schema": "x"', pairs[1][1])

    def test_publish_pair_collision_rolls_back_owned_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tar_path = root / "candidate.tar.gz"
            receipt_path = root / "receipt.json"
            receipt_path.write_bytes(b"foreign")
            with self.assertRaises(FileExistsError):
                build.publish_pair(tar_path, receipt_path, b"abc", {"x": 1})
            self.assertFalse(tar_path.exists())
            self.assertEqual(receipt_path.read_bytes(), b"foreign")

    def test_publish_pair_success_verifies_exact_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tar_path = root / "candidate.tar.gz"
            receipt_path = root / "receipt.json"
            record = {"schema": "x", "candidate_archive_sha256": hashlib.sha256(b"abc").hexdigest()}
            build.publish_pair(tar_path, receipt_path, b"abc", record)
            self.assertEqual(tar_path.read_bytes(), b"abc")
            self.assertIn(b'"schema": "x"', receipt_path.read_bytes())

    def test_publication_alias_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "same"
            with self.assertRaisesRegex(ValueError, "distinct"):
                build.publish_pair(path, path, b"x", {})

    def test_shared_publication_failure_propagates_without_private_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tar_path = root / "candidate.tar.gz"
            receipt_path = root / "receipt.json"
            root_error = OSError("shared publication failure")
            with mock.patch.object(build, "publish_exclusive", side_effect=root_error) as publish:
                with self.assertRaisesRegex(OSError, "shared publication failure"):
                    build.publish_pair(tar_path, receipt_path, b"abc", {"x": 1})
            publish.assert_called_once()
            self.assertFalse(tar_path.exists())
            self.assertFalse(receipt_path.exists())


if __name__ == "__main__":
    unittest.main()
