#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
from pathlib import Path
import tarfile
import tempfile
import unittest

import feed_stock_ablation as subject


class FeedStockAblationTest(unittest.TestCase):
    def sample_runtime(self):
        return (
            "class TitanAgent:\n"
            "    def _operating_stock_selected(self, obs, cfg, selected):\n"
            "        return {'fert': selected}\n"
            "\n"
            "    def _feed_stock_selected(self, obs, cfg, selected):\n"
            "        if selected:\n"
            "            return {'feed': selected}\n"
            "        return selected\n"
            "\n"
            "    def _early_capital_selected(self, obs, cfg, selected):\n"
            "        return selected\n"
        ).encode()

    def test_rewrite_changes_only_feed_method(self):
        raw = self.sample_runtime()
        changed = subject._rewrite_runtime(raw, subject.git_blob_bytes(raw))
        self.assertNotEqual(raw, changed)
        text = changed.decode()
        self.assertIn(
            "def _operating_stock_selected(self, obs, cfg, selected):\n"
            "        return {'fert': selected}",
            text,
        )
        self.assertIn(
            "def _feed_stock_selected(self, obs, cfg, selected):\n"
            "        return selected",
            text,
        )
        self.assertNotIn("return {'feed': selected}", text)
        self.assertIn(
            "def _early_capital_selected(self, obs, cfg, selected):\n"
            "        return selected",
            text,
        )
        compile(text, "<treatment>", "exec")

    def test_rewrite_fails_closed_on_wrong_preimage(self):
        raw = self.sample_runtime()
        with self.assertRaisesRegex(ValueError, "runtime source drift"):
            subject._rewrite_runtime(raw + b"\n", subject.git_blob_bytes(raw))

    def test_rewrite_rejects_signature_drift(self):
        raw = self.sample_runtime().replace(
            b"def _feed_stock_selected(self, obs, cfg, selected):",
            b"def _feed_stock_selected(self, selected):",
        )
        with self.assertRaisesRegex(ValueError, "signature"):
            subject._rewrite_runtime(raw, subject.git_blob_bytes(raw))

    def test_first_divergence(self):
        a = [{"market": []}, {"market": [["SELL", "WHEAT", 2]]}]
        b = [{"market": []}, {"market": [["SELL", "WHEAT", 3]]}]
        result = subject.first_action_divergence(a, b)
        self.assertEqual(1, result["step"])
        self.assertEqual(a[1], result["control"])
        self.assertEqual(b[1], result["feed_stock_off"])
        self.assertIsNone(subject.first_action_divergence(a, a))

    def test_archive_parser_uses_captured_bytes(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name, data in {
                "main.py": b"pass\n",
                "frozen_selected.py": b"pass\n",
                "titan_runtime.py": self.sample_runtime(),
            }.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        captured = buffer.getvalue()
        members = subject.archive_members_bytes(captured)
        self.assertEqual(b"pass\n", members["main.py"])
        self.assertEqual(self.sample_runtime(), members["titan_runtime.py"])

    def test_archive_parser_rejects_unsafe(self):
        for bad_name in ("../main.py", "/main.py"):
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                for name in ("main.py", "frozen_selected.py", bad_name):
                    data = b"x"
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
            with self.assertRaises(ValueError):
                subject.archive_members_bytes(buffer.getvalue())

    def test_extract_refuses_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "payload"
            path.mkdir()
            with self.assertRaises(FileExistsError):
                subject.extract_members({"main.py": b"pass\n"}, path)


if __name__ == "__main__":
    unittest.main()
