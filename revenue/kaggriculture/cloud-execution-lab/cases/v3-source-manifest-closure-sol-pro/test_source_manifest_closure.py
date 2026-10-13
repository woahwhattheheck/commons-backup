# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import patch_packet
import prove_predecessor
import source_manifest_closure as closure

HERE = Path(__file__).resolve().parent


def source_blob(runtime):
    return (json.dumps({"other": {"kept": True}, "runtime": runtime}, indent=2, sort_keys=True) + "\n").encode()


def entry(blob: bytes, source_path: str):
    return {"bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(), "source_path": source_path}


class SourceManifestClosureTests(unittest.TestCase):
    def test_refresh_closes_changed_and_new_members_preserving_metadata_and_labels(self):
        old = b"old\n"
        new = b"new\n"
        stable = b"stable\n"
        files = {
            "SOURCE.json": source_blob({"a.py": entry(old, "origin/a.py"), "stable.py": entry(stable, "origin/stable.py")}),
            "a.py": new,
            "stable.py": stable,
            "nested/lane.py": b"lane\n",
        }
        refreshed = closure.refresh_source_manifest(files)
        result = dict(files)
        result["SOURCE.json"] = refreshed
        receipt = closure.verify_source_manifest(result)
        parsed = closure.parse_source_manifest(refreshed)
        self.assertEqual(parsed["other"], {"kept": True})
        self.assertEqual(set(parsed["runtime"]), {"a.py", "stable.py", "nested/lane.py"})
        self.assertEqual(parsed["runtime"]["a.py"]["source_path"], "origin/a.py")
        self.assertEqual(parsed["runtime"]["nested/lane.py"]["source_path"], "nested/lane.py")
        self.assertEqual(parsed["runtime"]["a.py"]["sha256"], closure.sha256_bytes(new))
        self.assertEqual(receipt["runtime_files"], 3)
        self.assertEqual(receipt["regular_files"], 4)

    def test_refresh_is_idempotent(self):
        main = b"main\n"
        files = {"SOURCE.json": source_blob({"main.py": entry(main, "main.py")}), "main.py": main}
        first = closure.refresh_source_manifest(files)
        files["SOURCE.json"] = first
        second = closure.refresh_source_manifest(files)
        self.assertEqual(first, second)

    def test_verify_rejects_stale_hash_missing_and_extra_entries(self):
        old = b"old\n"
        new = b"new\n"
        base = {"SOURCE.json": source_blob({"main.py": entry(old, "main.py")}), "main.py": new}
        with self.assertRaisesRegex(closure.SourceManifestError, "mismatches"):
            closure.verify_source_manifest(base)
        missing = {"SOURCE.json": source_blob({}), "main.py": new}
        with self.assertRaisesRegex(closure.SourceManifestError, "missing"):
            closure.verify_source_manifest(missing)
        extra = {"SOURCE.json": source_blob({"main.py": entry(new, "main.py"), "ghost.py": entry(b"x", "ghost.py")}), "main.py": new}
        with self.assertRaisesRegex(closure.SourceManifestError, "extra"):
            closure.verify_source_manifest(extra)

    def test_rejects_self_inclusion_duplicate_json_and_unsafe_names(self):
        self_entry = entry(b"x", "SOURCE.json")
        with self.assertRaisesRegex(closure.SourceManifestError, "exclude"):
            closure.parse_source_manifest(source_blob({"SOURCE.json": self_entry}))
        duplicate = b'{"runtime": {}, "runtime": {}}\n'
        with self.assertRaisesRegex(closure.SourceManifestError, "duplicate JSON key"):
            closure.parse_source_manifest(duplicate)
        nonfinite = b'{"runtime": {}, "metric": NaN}\n'
        with self.assertRaisesRegex(closure.SourceManifestError, "non-finite"):
            closure.parse_source_manifest(nonfinite)
        safe = {"SOURCE.json": source_blob({})}
        for bad in ("../escape.py", "/absolute.py", "./alias.py", "a\\b.py"):
            candidate = dict(safe)
            candidate[bad] = b"x"
            with self.subTest(bad=bad), self.assertRaises(closure.SourceManifestError):
                closure.refresh_source_manifest(candidate)

    def test_source_label_override_must_name_a_real_member(self):
        files = {"SOURCE.json": source_blob({}), "main.py": b"x"}
        with self.assertRaisesRegex(closure.SourceManifestError, "absent package members"):
            closure.refresh_source_manifest(files, source_paths={"ghost.py": "origin"})
        with self.assertRaisesRegex(closure.SourceManifestError, "source_paths must be a mapping"):
            closure.refresh_source_manifest(files, source_paths=[("main.py", "origin")])
        with self.assertRaisesRegex(closure.SourceManifestError, "invalid source label"):
            closure.refresh_source_manifest(files, source_paths={"main.py": ""})
        refreshed = closure.refresh_source_manifest(files, source_paths={"main.py": "generated/by/apply_v3.py"})
        self.assertEqual(closure.parse_source_manifest(refreshed)["runtime"]["main.py"]["source_path"], "generated/by/apply_v3.py")

    def test_exact_packet_patch_is_bounded_and_source_receipts_include_builder(self):
        with tempfile.TemporaryDirectory(prefix="v3-patch-") as temp:
            root = Path(temp)
            (root / "build_v3.py").write_bytes((HERE / "packet_build_v3.py.txt").read_bytes())
            receipt = patch_packet.patch(root, HERE / "source_manifest_closure.py")
            text = (root / "build_v3.py").read_text(encoding="utf-8")
            self.assertEqual(receipt["preimage_build_sha256"], patch_packet.EXPECTED_BUILD_SHA256)
            self.assertEqual(receipt["patched_build_sha256"], "b46b7abbd414ac6f585a6296b99d282f5ef09696771178a60b2ddf94d2e94e4f")
            self.assertEqual(receipt["helper_sha256"], patch_packet.EXPECTED_HELPER_SHA256)
            self.assertEqual(text.count("source_manifest_closure.refresh_source_manifest(files)"), 1)
            self.assertEqual(text.count('shas["build_v3.py"]'), 1)
            self.assertEqual(text.count('shas["source_manifest_closure.py"]'), 1)
            with self.assertRaisesRegex(patch_packet.PatchError, "drift"):
                patch_packet.patch(root, HERE / "source_manifest_closure.py")

    def test_packet_patch_rejects_unreviewed_helper_bytes(self):
        with tempfile.TemporaryDirectory(prefix="v3-patch-helper-") as temp:
            root = Path(temp)
            (root / "build_v3.py").write_bytes((HERE / "packet_build_v3.py.txt").read_bytes())
            helper = root / "unreviewed-helper.py"
            helper.write_text("# drift\n", encoding="utf-8")
            with self.assertRaisesRegex(patch_packet.PatchError, "helper drift"):
                patch_packet.patch(root, helper)
            self.assertFalse((root / "source_manifest_closure.py").exists())
            self.assertEqual(
                hashlib.sha256((root / "build_v3.py").read_bytes()).hexdigest(),
                patch_packet.EXPECTED_BUILD_SHA256,
            )

    def test_executable_predecessor_and_successor(self):
        value = prove_predecessor.report()
        self.assertEqual(value["verdict"], "PREDECESSOR_STALE_SUCCESSOR_CLOSED")
        self.assertFalse(value["predecessor"]["source_bytes_changed"])
        self.assertFalse(value["predecessor"]["closed"])
        self.assertTrue(value["successor"]["source_bytes_changed"])
        self.assertTrue(value["successor"]["closed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
