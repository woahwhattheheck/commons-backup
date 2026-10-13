# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("c02_build", HERE / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class C02BuildContracts(unittest.TestCase):
    def setUp(self):
        self.delivery = (
            b"def market():\n"
            b"        quantity = min(due, room)\n"
            b"        return quantity\n"
        )
        self.baseline = {
            "main.py": b"# entry\n",
            "delivery_choice.py": self.delivery,
            "r04_full_router.py": b"# route\n",
        }

    def compose(self, baseline=None):
        source = self.baseline if baseline is None else baseline
        return build.compose(
            source,
            expected_delivery_sha256=build.digest(source["delivery_choice.py"]),
        )

    def test_compose_changes_only_exact_purchase_seam(self):
        files, before, after = self.compose()
        self.assertEqual(before, self.delivery)
        self.assertEqual(set(files), set(self.baseline))
        self.assertEqual(files["main.py"], self.baseline["main.py"])
        self.assertEqual(files["r04_full_router.py"], self.baseline["r04_full_router.py"])
        self.assertNotIn(build.PURCHASE_ANCHOR, after)
        self.assertEqual(after.count(build.TREATMENT), 1)

    def test_compose_rejects_delivery_preimage_drift(self):
        with self.assertRaisesRegex(ValueError, "identity drift"):
            build.compose(self.baseline, expected_delivery_sha256="0" * 64)

    def test_compose_rejects_ambiguous_purchase_seam(self):
        baseline = dict(self.baseline)
        baseline["delivery_choice.py"] += build.PURCHASE_ANCHOR
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.compose(baseline)

    def test_compose_rejects_preapplied_treatment(self):
        baseline = dict(self.baseline)
        baseline["delivery_choice.py"] = self.delivery.replace(
            build.PURCHASE_ANCHOR, build.TREATMENT
        )
        with self.assertRaisesRegex(ValueError, "replacement-purchase seam"):
            self.compose(baseline)

    def test_publish_pair_is_create_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tar_path = root / "candidate.tar.gz"
            receipt_path = root / "receipt.json"
            build.publish_pair(tar_path, receipt_path, b"candidate", {"schema": "test"})
            self.assertEqual(tar_path.read_bytes(), b"candidate")
            self.assertIn(b'"schema": "test"', receipt_path.read_bytes())
            with self.assertRaises(FileExistsError):
                build.publish_pair(tar_path, root / "second.json", b"other", {})
            self.assertEqual(tar_path.read_bytes(), b"candidate")
            self.assertFalse((root / "second.json").exists())


if __name__ == "__main__":
    unittest.main()
