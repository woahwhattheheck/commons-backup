"""Self-contained Git-fixture contracts; no TITAN runtime or network required."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

import audit_v4_custody as audit


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.run_git("init", "--object-format=sha1", "--initial-branch=main")
        self.run_git("config", "user.name", "Custody fixture")
        self.run_git("config", "user.email", "fixture@example.invalid")
        self.root = self.repo / audit.WORKSPACE
        self.root.mkdir(parents=True)
        self.source = b"# inert source fixture\nVALUE = 1\n"
        self.test = b"# inert test fixture\n"
        self.source_id = audit.object_id("blob", self.source)
        self.test_id = audit.object_id("blob", self.test)
        self.canonical = {"canonical_branch": "main", "workspace": audit.WORKSPACE}
        self.ledger = {
            "schema": "titan-v4-integration-ledger/v1",
            "canonical_branch": "main", "workspace": audit.WORKSPACE,
            "landed": [{"lane": "fixture", "source_blob": self.source_id,
                        "test_blob": self.test_id}],
            "recovered_not_yet_composed": [],
        }
        self.put("donor/source.py", self.source)
        self.put("donor/checks/test_source.py", self.test)
        self.commit()

    def run_git(self, *args, data=None):
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_NAME="Custody fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                   GIT_COMMITTER_NAME="Custody fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
        return subprocess.run(["git", "-C", str(self.repo), *args], input=data,
                              check=True, capture_output=True, env=env, timeout=15).stdout

    def put(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def commit(self):
        self.put("CANONICAL.json", encoded(self.canonical))
        self.put("INTEGRATION.json", encoded(self.ledger))
        self.run_git("add", "-A")
        self.run_git("commit", "--allow-empty", "-m", "fixture")
        return audit.resolve(self.repo, "main")

    def snapshot(self):
        return audit.read_snapshot(self.repo)

    def result(self):
        return audit.census(self.snapshot())

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = audit.main(["--repo", str(self.repo), *args])
        return code, json.loads(out.getvalue())

    def test_complete_custody_never_means_activation(self):
        result = self.result()
        self.assertTrue(result["custody_complete"])
        self.assertEqual(result["pin_references"], 2)
        self.assertEqual(result["missing_pin_references"], 0)
        for key in ("composition_proven", "production_activation_proven", "economics_proven"):
            self.assertIs(result[key], False)

    def test_absent_bytes_are_reported_not_restored(self):
        (self.root / "donor/source.py").unlink()
        self.commit()
        result = self.result()
        self.assertFalse(result["custody_complete"])
        self.assertEqual(result["missing_pin_references"], 1)
        self.assertFalse((self.root / "donor/source.py").exists())

    def test_hash_mentioned_in_document_is_not_custody(self):
        (self.root / "donor/source.py").unlink()
        self.put("receipt.md", self.source_id.encode())
        self.commit()
        self.assertEqual(self.result()["missing_pin_references"], 1)

    def test_other_branch_and_dangling_blob_are_not_custody(self):
        self.run_git("branch", "old-donor")
        self.run_git("hash-object", "-w", "--stdin", data=self.source)
        (self.root / "donor/source.py").unlink()
        self.commit()
        self.assertEqual(self.result()["missing_pin_references"], 1)

    def test_production_or_sibling_copy_is_not_workspace_custody(self):
        (self.root / "donor/source.py").unlink()
        outside = self.root.parent / "v4-sibling.py"
        outside.write_bytes(self.source)
        self.commit()
        self.assertEqual(self.result()["missing_pin_references"], 1)

    def test_symlink_blob_is_not_ordinary_file_custody(self):
        path = self.root / "donor/source.py"
        path.unlink()
        path.symlink_to("nonexistent-target")
        self.ledger["landed"][0]["source_blob"] = audit.object_id("blob", b"nonexistent-target")
        self.commit()
        reference = next(r for r in self.result()["references"] if "source_blob" in r["pointer"])
        self.assertEqual(reference["paths"], [])
        self.assertEqual(len(reference["nonregular_matches"]), 1)
        self.assertEqual(reference["status"], "missing_exact_bytes")

    def test_executable_regular_file_is_custody(self):
        self.run_git("update-index", "--chmod=+x", audit.WORKSPACE + "/donor/source.py")
        self.run_git("commit", "-m", "executable regular fixture")
        self.assertTrue(self.result()["custody_complete"])

    def test_duplicate_regular_copies_are_visible(self):
        self.put("repairs/source.py", self.source)
        self.commit()
        reference = next(r for r in self.result()["references"] if "source_blob" in r["pointer"])
        self.assertEqual(len(reference["paths"]), 2)
        self.assertEqual(reference["paths"], sorted(reference["paths"]))

    def test_generator_and_multiple_test_pins(self):
        self.ledger["landed"][0] = {"lane": "generator", "generator_blob": self.source_id,
                                    "test_blobs": [self.test_id, self.test_id]}
        self.commit()
        self.assertTrue(self.result()["custody_complete"])
        self.assertEqual(self.result()["pin_references"], 3)

    def test_missing_source_pin_is_explicit_gap(self):
        del self.ledger["landed"][0]["source_blob"]
        self.commit()
        self.assertEqual(self.result()["lane_reference_gaps"][0]["gap"], "missing_source_pin")

    def test_missing_test_pin_is_explicit_gap(self):
        del self.ledger["landed"][0]["test_blob"]
        self.commit()
        self.assertEqual(self.result()["lane_reference_gaps"][0]["gap"], "missing_test_pin")
        self.assertFalse(self.result()["custody_complete"])

    def test_recovered_group_is_censused_but_not_composed(self):
        self.ledger["recovered_not_yet_composed"] = self.ledger.pop("landed")
        self.ledger["landed"] = []
        self.commit()
        self.assertTrue(self.result()["custody_complete"])
        self.assertFalse(self.result()["composition_proven"])

    def test_negative_receipts_do_not_need_gameplay_source(self):
        self.ledger["negative_or_parked"] = [{"lane": "negative", "disposition": "NO_BUILD"}]
        self.commit()
        self.assertTrue(self.result()["custody_complete"])

    def test_pointer_escaping_and_nested_optional_pins(self):
        self.ledger["optional/~"] = {"support_blob": self.test_id}
        self.commit()
        self.assertIn("/optional~1~0/support_blob", [r["pointer"] for r in self.result()["references"]])

    def test_invalid_sha_domains_rejected(self):
        for value in (True, 1, None, "", "a" * 39, "A" * 40, "g" * 40):
            with self.subTest(value=value), self.assertRaises(audit.EvidenceError):
                audit.oid(value)

    def test_empty_or_wrong_typed_pin_lists_rejected(self):
        for value in ([], None, True, self.test_id):
            with self.subTest(value=value):
                self.ledger["landed"][0]["test_blobs"] = value
                self.commit()
                with self.assertRaises(audit.EvidenceError):
                    self.result()

    def test_metadata_contract_mismatches_rejected(self):
        for document, key, value in ((self.canonical, "canonical_branch", "other"),
                                     (self.canonical, "workspace", "other"),
                                     (self.ledger, "canonical_branch", "other"),
                                     (self.ledger, "workspace", "other"),
                                     (self.ledger, "schema", "unknown")):
            original = document[key]
            document[key] = value
            self.commit()
            with self.subTest(key=key), self.assertRaises(audit.EvidenceError):
                self.result()
            document[key] = original

    def test_missing_or_malformed_lane_groups_rejected(self):
        for value in (None, {}, [None], [{"lane": True}], [{"lane": ""}]):
            self.ledger["landed"] = value
            self.commit()
            with self.subTest(value=value), self.assertRaises(audit.EvidenceError):
                self.result()

    def test_empty_census_is_not_green(self):
        self.ledger["landed"] = []
        self.commit()
        with self.assertRaises(audit.EvidenceError):
            self.result()

    def test_duplicate_json_keys_rejected_even_when_equal(self):
        for raw in (b'{"x": 1, "x": 1}', b'{"x":{"a":1,"a":2}}'):
            with self.subTest(raw=raw), self.assertRaises(audit.EvidenceError):
                audit.strict_json(raw)

    def test_nonfinite_and_bad_encoding_json_rejected(self):
        for raw in (b'{"x": NaN}', b'{"x": Infinity}', b'{"x": -Infinity}', b'\xff', b'{'):
            with self.subTest(raw=raw), self.assertRaises(audit.EvidenceError):
                audit.strict_json(raw)

    def test_mixed_metadata_bytes_rejected(self):
        snap = self.snapshot()
        with self.assertRaises(audit.EvidenceError):
            audit.census(replace(snap, ledger=snap.ledger + b" "))

    def test_metadata_symlink_rejected(self):
        p = self.root / "CANONICAL.json"
        p.unlink()
        p.symlink_to("other.json")
        self.run_git("add", "-A")
        self.run_git("commit", "-m", "metadata symlink fixture")
        with self.assertRaises(audit.EvidenceError):
            self.snapshot()

    def test_truncated_record_rejected(self):
        raw = audit.git(self.repo, "ls-tree", "-r", "-t", "-z", self.snapshot().tree)
        with self.assertRaises(audit.EvidenceError):
            audit.parse_tree(raw[:-1])

    def test_omitted_complete_record_rejected(self):
        snap = self.snapshot()
        entries = dict(snap.entries)
        del entries["donor/source.py"]
        with self.assertRaises(audit.EvidenceError):
            audit.verify_tree(entries, snap.tree)

    def test_mixed_tree_blob_rejected(self):
        snap = self.snapshot()
        entries = dict(snap.entries)
        entries["donor/source.py"] = audit.Entry("100644", "blob", self.test_id)
        with self.assertRaises(audit.EvidenceError):
            audit.verify_tree(entries, snap.tree)

    def test_missing_directory_record_rejected(self):
        snap = self.snapshot()
        entries = dict(snap.entries)
        del entries["donor"]
        with self.assertRaises(audit.EvidenceError):
            audit.verify_tree(entries, snap.tree)

    def test_duplicate_path_rejected(self):
        row = b"100644 blob " + self.source_id.encode() + b"\tx\0"
        with self.assertRaises(audit.EvidenceError):
            audit.parse_tree(row + row)

    def test_invalid_path_and_mode_domains_rejected(self):
        for path in ("/x", "a/../x", "a/./x", "a//x", "x/", ""):
            row = b"100644 blob " + self.source_id.encode() + b"\t" + path.encode() + b"\0"
            with self.subTest(path=path), self.assertRaises(audit.EvidenceError):
                audit.parse_tree(row)
        for header in ("100644 tree", "120000 commit", "777777 blob", "40000 tree"):
            with self.subTest(header=header), self.assertRaises(audit.EvidenceError):
                audit.parse_tree((header + " " + self.source_id + "\tx\0").encode())

    def test_git_directory_sorting_and_unusual_utf8_paths(self):
        for name in ("a/x", "a.c", "a0", "z/é.py", "z/tab\tname", "z/new\nline"):
            self.put(name, b"fixture")
        self.commit()
        self.assertTrue(self.result()["complete_tree_verified"])

    def test_gitlink_is_not_regular_custody(self):
        commit = audit.resolve(self.repo, "main")
        self.run_git("update-index", "--add", "--cacheinfo", "160000," + commit + "," + audit.WORKSPACE + "/submodule")
        self.run_git("commit", "-m", "gitlink fixture")
        snap = self.snapshot()
        self.assertEqual(snap.entries["submodule"].mode, "160000")
        self.assertTrue(audit.census(snap)["custody_complete"])

    def test_worktree_edits_cannot_change_pinned_report(self):
        before = self.result()
        self.put("INTEGRATION.json", b"broken worktree, not committed")
        self.put("donor/source.py", b"uncommitted change")
        self.assertEqual(before, self.result())

    def test_old_commit_remains_immutable_after_main_advances(self):
        original = self.snapshot()
        (self.root / "donor/source.py").unlink()
        self.commit()
        self.assertEqual(original, audit.read_snapshot(self.repo, original.commit))
        self.assertTrue(audit.census(original)["custody_complete"])
        self.assertFalse(self.result()["custody_complete"])

    def test_cli_zero_one_two_and_deterministic_output(self):
        before = self.run_git("status", "--porcelain=v1")
        code, first = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual((code, first), self.cli())
        self.assertEqual(before, self.run_git("status", "--porcelain=v1"))
        (self.root / "donor/source.py").unlink()
        self.commit()
        self.assertEqual(self.cli()[0], 1)
        code, error = self.cli("--ref", "no-such-ref")
        self.assertEqual(code, 2)
        self.assertFalse(error["custody_complete"])

    def test_ref_drift_exit_three_keeps_pinned_result(self):
        old = self.snapshot()
        self.put("unrelated.txt", b"new main")
        new = self.commit()
        with patch.object(audit, "read_snapshot", return_value=old):
            code, result = self.cli()
        self.assertEqual(code, 3)
        self.assertEqual(result["commit"], old.commit)
        self.assertEqual(result["ref_at_end"], new)
        self.assertTrue(result["custody_complete"])
        self.assertTrue(result["ref_moved"])

    def test_missing_in_tree_blob_object_is_error_not_custody(self):
        path = self.repo / ".git" / "objects" / self.source_id[:2] / self.source_id[2:]
        path.unlink()
        code, result = self.cli()
        self.assertEqual(code, 2)
        self.assertFalse(result["custody_complete"])

    def test_forged_or_unverified_blob_bytes_rejected(self):
        snap = self.snapshot()
        for blobs in ({}, {**snap.blobs, self.source_id: b"wrong bytes"}):
            with self.subTest(blobs=bool(blobs)), self.assertRaises(audit.EvidenceError):
                audit.census(replace(snap, blobs=blobs))

    def test_no_candidate_python_is_executed(self):
        marker = self.repo / "MUST_NOT_EXIST"
        self.put("donor/evil.py", ("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n").encode())
        self.commit()
        self.assertTrue(self.result()["custody_complete"])
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
