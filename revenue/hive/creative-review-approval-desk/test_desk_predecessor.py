#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _validation import InvalidInput, canonical_bytes, read_asset, read_json_file, strict_json_loads

HERE = Path(__file__).resolve().parent


class CreativeReviewDeskPredecessorTests(unittest.TestCase):
    def test_direct_text_lone_surrogate_is_bounded_invalid_input(self) -> None:
        raw = '{"value":"' + chr(0xD800) + '"}'
        with self.assertRaises(InvalidInput):
            strict_json_loads(raw)
        with self.assertRaises(InvalidInput):
            canonical_bytes({"value": chr(0xD800)})

    def test_escaped_json_lone_surrogate_is_bounded_invalid_input(self) -> None:
        with self.assertRaises(InvalidInput):
            strict_json_loads(b'{"value":"\\ud800"}')

    def test_cli_lone_surrogate_returns_structured_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = json.loads((HERE / "demo" / "spec.json").read_text(encoding="utf-8"))
            spec["name"] = chr(0xD800)
            spec_path = root / "spec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            process = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "desk.py"),
                    "create",
                    "--db",
                    str(root / "desk.sqlite3"),
                    "--spec",
                    str(spec_path),
                    "--request-id",
                    "surrogate-predecessor",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(process.returncode, 2)
            self.assertNotIn("Traceback", process.stderr)
            error = json.loads(process.stderr)
            self.assertEqual(error["error"], "InvalidInput")

    @unittest.skipUnless(os.name == "posix", "component no-follow custody requires POSIX")
    def test_parent_symlink_is_rejected_but_real_parent_is_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            asset = real / "asset.bin"
            asset.write_bytes(b"exact creative bytes")
            link_parent = root / "link-parent"
            link_parent.symlink_to(real, target_is_directory=True)

            data, _, size, name = read_asset(asset)
            self.assertEqual(data, b"exact creative bytes")
            self.assertEqual(size, len(data))
            self.assertEqual(name, "asset.bin")
            with self.assertRaises(InvalidInput):
                read_asset(link_parent / "asset.bin")

    @unittest.skipUnless(os.name == "posix", "component no-follow custody requires POSIX")
    def test_final_leaf_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text('{"ok":true}', encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(target)
            self.assertEqual(read_json_file(target), {"ok": True})
            with self.assertRaises(InvalidInput):
                read_json_file(link)

    @unittest.skipUnless(os.name == "posix", "component no-follow custody requires POSIX")
    def test_missing_descriptor_relative_primitive_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text('{"ok":true}', encoding="utf-8")
            with mock.patch.object(os, "supports_dir_fd", set()):
                with self.assertRaises(InvalidInput):
                    read_json_file(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
