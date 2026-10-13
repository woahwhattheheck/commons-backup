from __future__ import annotations
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import treeguard as g

REPOSITORY = "example/owned-repository"
PYTHON = [sys.executable] + (["-OO"] if sys.flags.optimize > 1 else ["-O"] if sys.flags.optimize else [])


class Memory:
    def __init__(self, fmt="sha1"):
        self.object_format = fmt
        self.objects = {}
        self.calls = []

    def put(self, kind, raw):
        oid = g.object_id(kind, raw, self.object_format)
        self.objects[oid] = (kind, raw)
        return oid

    def blob(self, raw=b"content\n", mode="100644"):
        return g.Entry(mode, self.put("blob", raw))

    def tree(self, entries):
        return self.put("tree", g.tree_encode(entries, self.object_format))

    def commit(self, tree, parents=(), message=b"synthetic fixture"):
        raw = b"tree " + tree.encode() + b"\n"
        for parent in parents:
            raw += b"parent " + parent.encode() + b"\n"
        raw += b"author Test <test@example.invalid> 1 +0000\ncommitter Test <test@example.invalid> 1 +0000\n\n" + message + b"\n"
        return self.put("commit", raw)

    def read(self, oid):
        self.calls.append(oid)
        if oid not in self.objects:
            raise g.GuardError("MISSING_FIXTURE_OBJECT")
        return self.objects[oid]


class Fixture:
    def __init__(self, fmt="sha1"):
        self.store = Memory(fmt)
        self.old = self.store.blob(b"retained product\n")
        self.new = self.store.blob(b"new response\n")
        self.config = self.store.blob(b"run retained tests\n")
        self.product_tree = self.store.tree({b"engine.py": self.old})
        self.workflow_tree = self.store.tree({b"ci.yml": self.config})
        self.base_entries = {b"products": g.Entry("040000", self.product_tree),
                             b".github": g.Entry("040000", self.workflow_tree),
                             b"README.md": self.old}
        self.base_tree = self.store.tree(self.base_entries)
        self.base = self.store.commit(self.base_tree)
        self.good_entries = dict(self.base_entries)
        self.good_entries[b"p"] = g.Entry("040000", self.store.tree({b"response.md": self.new}))
        self.good_tree = self.store.tree(self.good_entries)
        self.good = self.store.commit(self.good_tree, [self.base])
        self.bad_tree = self.store.tree({b"p": self.good_entries[b"p"]})
        self.bad = self.store.commit(self.bad_tree, [self.base], b"one added file; omitted base tree")
        self.contract = {"schema": g.SCHEMA, "repository": REPOSITORY,
                         "object_format": fmt, "base_commit": self.base,
                         "edits": [{"path": "p/response.md", "before": None, "after": self.new.json()}]}

    def run(self, candidate=None, contract=None):
        raw = g.canonical(self.contract if contract is None else contract)
        return g.audit(self.store, raw, g.sha256(raw), REPOSITORY, candidate or self.good)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def check_bad(self, change, code=None):
        c = copy.deepcopy(self.f.contract)
        change(c)
        with self.assertRaises(g.GuardError) as caught:
            self.f.run(contract=c)
        if code:
            self.assertEqual(caught.exception.code, code)

    def test_missing_external_pin(self):
        with self.assertRaisesRegex(g.GuardError, "CONTRACT_PIN_REQUIRED"):
            g.contract_check(g.canonical(self.f.contract), "", REPOSITORY)

    def test_wrong_external_pin(self):
        with self.assertRaisesRegex(g.GuardError, "CONTRACT_PIN_MISMATCH"):
            g.contract_check(g.canonical(self.f.contract), "f" * 64, REPOSITORY)

    def test_duplicate_nested_json_keys(self):
        raw = b'{"edit":{"path":"a","path":"b"}}'
        with self.assertRaisesRegex(g.GuardError, "DUPLICATE_JSON_KEY"):
            g.load_json(raw)

    def test_unknown_field(self):
        self.check_bad(lambda c: c.update(approve=True), "SCHEMA_FIELDS")

    def test_wrong_repository(self):
        self.check_bad(lambda c: c.update(repository="other/repo"), "REPOSITORY_LABEL_MISMATCH")

    def test_unknown_schema(self):
        self.check_bad(lambda c: c.update(schema="new-schema"), "CONTRACT_VERSION")

    def test_invalid_format(self):
        self.check_bad(lambda c: c.update(object_format="md5"), "OBJECT_TYPE_OR_FORMAT")

    def test_bool_as_oid(self):
        self.check_bad(lambda c: c.update(base_commit=True), "INVALID_OBJECT_ID")

    def test_zero_oid(self):
        self.check_bad(lambda c: c.update(base_commit="0" * 40), "ZERO_OBJECT_ID")

    def test_uppercase_oid(self):
        self.check_bad(lambda c: c.update(base_commit="A" * 40), "INVALID_OBJECT_ID")

    def test_moving_ref_rejected(self):
        self.check_bad(lambda c: c.update(base_commit="main"), "INVALID_OBJECT_ID")

    def test_no_edits(self):
        self.check_bad(lambda c: c.update(edits=[]), "EDIT_COUNT_LIMIT")

    def test_duplicate_path(self):
        self.check_bad(lambda c: c["edits"].append(copy.deepcopy(c["edits"][0])), "DUPLICATE_EDIT_PATH")

    def test_ancestor_path_overlap(self):
        self.check_bad(lambda c: c["edits"].append({"path": "p", "before": None, "after": self.f.new.json()}),
                       "OVERLAPPING_EDIT_PATHS")

    def test_subtree_edit_forbidden(self):
        self.check_bad(lambda c: c["edits"][0]["after"].update(mode="040000"), "LEAF_MODE_REQUIRED")

    def test_bool_as_mode(self):
        self.check_bad(lambda c: c["edits"][0]["after"].update(mode=True), "LEAF_MODE_REQUIRED")

    def test_noop_edit_rejected(self):
        self.check_bad(lambda c: c["edits"][0].update(after=None), "NOOP_EDIT")

    def test_changed_contract_bytes_not_blessed(self):
        raw = g.canonical(self.f.contract)
        with self.assertRaisesRegex(g.GuardError, "CONTRACT_PIN_MISMATCH"):
            g.contract_check(raw + b" ", g.sha256(raw), REPOSITORY)

    def test_forbidden_numeric_json(self):
        for token in [b"1.0", b"NaN", b"Infinity", b"-Infinity", b"1e8"]:
            with self.subTest(token=token), self.assertRaises(g.GuardError):
                g.load_json(b'{"value":' + token + b'}')

    def test_unsafe_paths(self):
        for path in ["../x", "/x", "a/../b", "a//b", ".git/config", "a/.GIT/config",
                     "a\\b", "a\nb", "a\tb", "x/*", "x/?", "x/[a]", "a/", "", "x/./y", "\ud800"]:
            with self.subTest(path=repr(path)), self.assertRaises(g.GuardError):
                g.path_check(path)

    def test_path_depth_limit(self):
        with self.assertRaisesRegex(g.GuardError, "INVALID_EDIT_PATH"):
            g.path_check("/".join(["x"] * 65))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def test_valid_add_preserves_unrelated_source(self):
        r = self.f.run()
        self.assertEqual(r["state"], "TREE_MATCH")
        self.assertEqual(r["expected_tree"], self.f.good_tree)
        self.assertEqual(r["root_deltas"], [])
        self.assertFalse(any(r["authority"].values()))

    def test_exact_incident_shape_is_rejected(self):
        r = self.f.run(self.f.bad)
        self.assertEqual(r["state"], "HOLD")
        self.assertIn("UNDECLARED_TREE_CHANGE", r["reasons"])
        self.assertEqual([x["path_display"] for x in r["root_deltas"]], [".github", "README.md", "products"])

    def test_no_tree_size_heuristic_equal_size_replacement_rejects(self):
        entries = dict(self.f.good_entries)
        del entries[b"README.md"]
        entries[b"UNRELATED.md"] = self.f.old
        bad = self.f.store.commit(self.f.store.tree(entries), [self.f.base])
        self.assertEqual(self.f.run(bad)["state"], "HOLD")

    def test_undeclared_nested_replacement_rejects(self):
        e = dict(self.f.good_entries)
        e[b"products"] = g.Entry("040000", self.f.store.tree({b"engine.py": self.f.new}))
        c = self.f.store.commit(self.f.store.tree(e), [self.f.base])
        r = self.f.run(c)
        self.assertEqual(r["state"], "HOLD")
        self.assertEqual(r["root_deltas"][0]["path_display"], "products")

    def test_unapproved_executable_mode_change_rejects(self):
        e = dict(self.f.good_entries)
        e[b"README.md"] = g.Entry("100755", self.f.old.oid)
        c = self.f.store.commit(self.f.store.tree(e), [self.f.base])
        self.assertEqual(self.f.run(c)["state"], "HOLD")

    def test_correct_tree_wrong_parent_is_hold(self):
        wrong = self.f.store.commit(self.f.good_tree, [])
        self.assertEqual(self.f.run(wrong)["reasons"], ["CANDIDATE_NOT_DIRECT_CHILD_OF_BASE"])

    def test_correct_tree_merge_commit_is_hold(self):
        other = self.f.store.commit(self.f.base_tree, [], b"other parent")
        wrong = self.f.store.commit(self.f.good_tree, [self.f.base, other])
        self.assertIn("CANDIDATE_NOT_DIRECT_CHILD_OF_BASE", self.f.run(wrong)["reasons"])

    def test_stale_base_does_not_use_parent_claim(self):
        later = self.f.store.commit(self.f.base_tree, [self.f.base], b"later")
        wrong = self.f.store.commit(self.f.good_tree, [later])
        self.assertEqual(self.f.run(wrong)["state"], "HOLD")

    def test_before_identity_mismatch(self):
        c = copy.deepcopy(self.f.contract)
        c["edits"] = [{"path": "README.md", "before": self.f.new.json(), "after": self.f.old.json()}]
        with self.assertRaisesRegex(g.GuardError, "BEFORE_ENTRY_MISMATCH"):
            self.f.run(contract=c)

    def test_add_cannot_overwrite_existing_leaf(self):
        c = copy.deepcopy(self.f.contract)
        c["edits"][0]["path"] = "README.md"
        with self.assertRaisesRegex(g.GuardError, "BEFORE_ENTRY_MISMATCH"):
            self.f.run(contract=c)

    def test_path_ancestor_cannot_be_file_or_symlink(self):
        c = copy.deepcopy(self.f.contract)
        c["edits"][0]["path"] = "README.md/child"
        with self.assertRaisesRegex(g.GuardError, "PATH_BLOCKED_BY_LEAF"):
            self.f.run(contract=c)

    def test_deletion_requires_exact_old_blob(self):
        c = copy.deepcopy(self.f.contract)
        c["edits"] = [{"path": "README.md", "before": self.f.old.json(), "after": None}]
        e = dict(self.f.base_entries)
        del e[b"README.md"]
        candidate = self.f.store.commit(self.f.store.tree(e), [self.f.base])
        self.assertEqual(self.f.run(candidate, c)["state"], "TREE_MATCH")

    def test_last_leaf_deletion_prunes_directory(self):
        c = copy.deepcopy(self.f.contract)
        c["edits"] = [{"path": "products/engine.py", "before": self.f.old.json(), "after": None}]
        e = dict(self.f.base_entries)
        del e[b"products"]
        candidate = self.f.store.commit(self.f.store.tree(e), [self.f.base])
        self.assertEqual(self.f.run(candidate, c)["state"], "TREE_MATCH")

    def test_explicit_rename_is_delete_plus_add(self):
        c = copy.deepcopy(self.f.contract)
        c["edits"] = [{"path": "README.md", "before": self.f.old.json(), "after": None},
                      {"path": "GUIDE.md", "before": None, "after": self.f.old.json()}]
        e = dict(self.f.base_entries)
        e[b"GUIDE.md"] = e.pop(b"README.md")
        candidate = self.f.store.commit(self.f.store.tree(e), [self.f.base])
        self.assertEqual(self.f.run(candidate, c)["state"], "TREE_MATCH")

    def test_explicit_mode_only_change(self):
        executable = g.Entry("100755", self.f.old.oid)
        c = copy.deepcopy(self.f.contract)
        c["edits"] = [{"path": "README.md", "before": self.f.old.json(), "after": executable.json()}]
        e = dict(self.f.base_entries, **{})
        e[b"README.md"] = executable
        candidate = self.f.store.commit(self.f.store.tree(e), [self.f.base])
        self.assertEqual(self.f.run(candidate, c)["state"], "TREE_MATCH")

    def test_symlink_and_gitlink_are_opaque_entries(self):
        for mode in ["120000", "160000"]:
            with self.subTest(mode=mode):
                c = copy.deepcopy(self.f.contract)
                entry = g.Entry(mode, self.f.base if mode == "160000" else self.f.new.oid)
                c["edits"] = [{"path": "new-item", "before": None, "after": entry.json()}]
                e = dict(self.f.base_entries)
                e[b"new-item"] = entry
                candidate = self.f.store.commit(self.f.store.tree(e), [self.f.base])
                self.assertEqual(self.f.run(candidate, c)["state"], "TREE_MATCH")

    def test_unchanged_subtrees_are_not_expanded(self):
        self.f.run()
        self.assertNotIn(self.f.product_tree, self.f.store.calls)
        self.assertNotIn(self.f.workflow_tree, self.f.store.calls)

    def test_missing_unchanged_subtree_stays_opaque_not_availability_proof(self):
        del self.f.store.objects[self.f.product_tree]
        self.assertEqual(self.f.run()["state"], "TREE_MATCH")

    def test_touched_missing_subtree_cannot_pass(self):
        del self.f.store.objects[self.f.product_tree]
        c = copy.deepcopy(self.f.contract)
        c["edits"] = [{"path": "products/next.py", "before": None, "after": self.f.new.json()}]
        with self.assertRaises(g.GuardError):
            self.f.run(contract=c)

    def test_corrupt_base_object_is_rejected(self):
        self.f.store.objects[self.f.base] = ("commit", b"corrupted")
        with self.assertRaisesRegex(g.GuardError, "OBJECT_HASH_MISMATCH"):
            self.f.run()

    def test_tampered_object_type_is_rejected(self):
        kind, raw = self.f.store.objects[self.f.base]
        self.f.store.objects[self.f.base] = ("tree", raw)
        with self.assertRaisesRegex(g.GuardError, "OBJECT_HASH_MISMATCH"):
            self.f.run()

    def test_sha256_object_format(self):
        f = Fixture("sha256")
        self.assertEqual(f.run()["state"], "TREE_MATCH")
        self.assertEqual(len(f.good_tree), 64)
        self.assertEqual(f.run(f.bad)["state"], "HOLD")

    def test_format_mismatch(self):
        self.f.store.object_format = "sha256"
        with self.assertRaisesRegex(g.GuardError, "OBJECT_FORMAT_MISMATCH"):
            self.f.run()

    def test_edit_order_does_not_change_expected_tree(self):
        c = copy.deepcopy(self.f.contract)
        c["edits"].append({"path": "extra", "before": None, "after": self.f.old.json()})
        e = dict(self.f.good_entries)
        e[b"extra"] = self.f.old
        candidate = self.f.store.commit(self.f.store.tree(e), [self.f.base])
        first = self.f.run(candidate, c)
        c["edits"].reverse()
        second = self.f.run(candidate, c)
        self.assertEqual(first["expected_tree"], second["expected_tree"])
        self.assertEqual(second["state"], "TREE_MATCH")
        self.assertNotEqual(first["contract_sha256"], second["contract_sha256"])

    def test_idempotent_receipts_across_warm_cache(self):
        self.assertEqual(self.f.run(), self.f.run())

    def test_raw_non_utf8_untouched_path_is_preserved(self):
        f = self.f
        e = dict(f.base_entries)
        e[b"\xff\tfile"] = f.old
        f.base_entries, f.base_tree = e, f.store.tree(e)
        f.base = f.store.commit(f.base_tree)
        f.contract["base_commit"] = f.base
        e = dict(e)
        e[b"p"] = f.good_entries[b"p"]
        candidate = f.store.commit(f.store.tree(e), [f.base])
        self.assertEqual(f.run(candidate)["state"], "TREE_MATCH")

    def test_undeclared_empty_subtree_loss_rejects(self):
        f = self.f
        e = dict(f.base_entries)
        e[b"empty"] = g.Entry("040000", f.store.tree({}))
        f.base_tree = f.store.tree(e)
        f.base = f.store.commit(f.base_tree)
        f.contract["base_commit"] = f.base
        candidate = f.store.commit(f.good_tree, [f.base])
        self.assertEqual(f.run(candidate)["state"], "HOLD")


class WitnessTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.report = self.f.run()
        self.raw = g.canonical(self.f.contract)
        self.pin = g.sha256(self.raw)

    def test_valid_offline_replay(self):
        result = g.replay(g.canonical(self.report), self.raw, self.pin, REPOSITORY, self.f.good)
        self.assertEqual(result["state"], "REPLAY_MATCH")
        self.assertFalse(result["merge_authorized"])
        self.assertFalse(result["current_remote_ref_verified"])

    def test_negative_report_can_replay_without_becoming_positive(self):
        report = self.f.run(self.f.bad)
        result = g.replay(g.canonical(report), self.raw, self.pin, REPOSITORY, self.f.bad)
        self.assertEqual(result["replayed_tree_state"], "HOLD")

    def test_tamper_every_load_bearing_report_field(self):
        replacements = {"state": "APPROVED", "expected_tree": "1" * 40, "reasons": ["fake"],
                        "candidate_commit": self.f.bad, "declared_edit_count": 999,
                        "receipt_sha256": "0" * 64, "root_deltas": [{"fake": True}]}
        for key, val in replacements.items():
            report = copy.deepcopy(self.report)
            report[key] = val
            with self.subTest(key=key), self.assertRaises(g.GuardError):
                g.replay(g.canonical(report), self.raw, self.pin, REPOSITORY, self.f.good)

    def test_authority_flip_rejected(self):
        report = copy.deepcopy(self.report)
        report["authority"]["merge_authorized"] = True
        # Rehashing a forged report still cannot make semantic replay succeed.
        del report["receipt_sha256"]
        report["receipt_sha256"] = g.sha256(g.canonical(report))
        with self.assertRaisesRegex(g.GuardError, "REPORT_REPLAY_MISMATCH"):
            g.replay(g.canonical(report), self.raw, self.pin, REPOSITORY, self.f.good)

    def test_candidate_transplant_rejected(self):
        with self.assertRaises(g.GuardError):
            g.replay(g.canonical(self.report), self.raw, self.pin, REPOSITORY, self.f.bad)

    def test_witness_byte_tamper(self):
        witness = copy.deepcopy(self.report["witness"])
        witness["objects"][0]["data_b64"] = base64.b64encode(b"modified").decode()
        with self.assertRaisesRegex(g.GuardError, "OBJECT_HASH_MISMATCH"):
            g.WitnessStore(witness)

    def test_witness_duplicate_object(self):
        w = copy.deepcopy(self.report["witness"])
        w["objects"].append(w["objects"][0])
        with self.assertRaisesRegex(g.GuardError, "DUPLICATE_WITNESS_OBJECT"):
            g.WitnessStore(w)

    def test_witness_missing_object(self):
        report = copy.deepcopy(self.report)
        report["witness"]["objects"] = []
        with self.assertRaisesRegex(g.GuardError, "MISSING_WITNESS_OBJECT"):
            g.replay(g.canonical(report), self.raw, self.pin, REPOSITORY, self.f.good)

    def test_witness_extra_field(self):
        w = copy.deepcopy(self.report["witness"])
        w["truncated"] = True
        with self.assertRaisesRegex(g.GuardError, "SCHEMA_FIELDS"):
            g.WitnessStore(w)

    def test_invalid_base64(self):
        w = copy.deepcopy(self.report["witness"])
        w["objects"][0]["data_b64"] = "not base64"
        with self.assertRaisesRegex(g.GuardError, "INVALID_BASE64"):
            g.WitnessStore(w)


class TreeCodecTests(unittest.TestCase):
    def test_empty_tree_known_sha(self):
        self.assertEqual(g.object_id("tree", b"", "sha1"), "4b825dc642cb6eb9a060e54bf8d69288fbee4904")

    def test_tree_duplicate_name(self):
        raw = b"100644 a\0" + b"\x01" * 20
        with self.assertRaisesRegex(g.GuardError, "DUPLICATE_TREE_NAME"):
            g.tree_decode(raw + raw, "sha1")

    def test_tree_noncanonical_order(self):
        raw = b"100644 z\0" + b"\x01" * 20 + b"100644 a\0" + b"\x02" * 20
        with self.assertRaisesRegex(g.GuardError, "NONCANONICAL_TREE"):
            g.tree_decode(raw, "sha1")

    def test_truncated_binary_tree(self):
        for raw in [b"100644 a\0" + b"1" * 19, b"100644", b"100644 \0" + b"1" * 20]:
            with self.subTest(raw=raw), self.assertRaises(g.GuardError):
                g.tree_decode(raw, "sha1")

    def test_unknown_mode(self):
        with self.assertRaisesRegex(g.GuardError, "INVALID_TREE_MODE"):
            g.tree_decode(b"100600 a\0" + b"1" * 20, "sha1")

    def test_slash_or_traversal_in_tree_name(self):
        for name in [b"a/b", b".", b".."]:
            with self.subTest(name=name), self.assertRaises(g.GuardError):
                g.tree_decode(b"100644 " + name + b"\0" + b"1" * 20, "sha1")


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.raw = g.canonical(self.f.contract)
        self.pin = g.sha256(self.raw)

    def test_plan_includes_exact_tree_base_not_commit_sha(self):
        plan = g.build_plan(self.f.store, self.raw, self.pin, REPOSITORY)
        self.assertEqual(plan["request"]["base_tree"], self.f.base_tree)
        self.assertNotEqual(plan["request"]["base_tree"], self.f.base)
        self.assertEqual(plan["expected_tree"], self.f.good_tree)
        self.assertFalse(plan["candidate_checked"])
        self.assertFalse(plan["remote_mutation_performed"])
        self.assertEqual(plan["state"], "REQUEST_ONLY_NOT_EXECUTED")

    def test_plan_is_exact_leaf_only(self):
        plan = g.build_plan(self.f.store, self.raw, self.pin, REPOSITORY)
        self.assertEqual(plan["request"]["tree"], [
            {"path": "p/response.md", "mode": "100644", "type": "blob", "sha": self.f.new.oid}])

    def test_plan_deletion_has_explicit_null_sha(self):
        c = copy.deepcopy(self.f.contract)
        c["edits"] = [{"path": "README.md", "before": self.f.old.json(), "after": None}]
        raw = g.canonical(c)
        plan = g.build_plan(self.f.store, raw, g.sha256(raw), REPOSITORY)
        self.assertEqual(plan["request"]["tree"], [
            {"path": "README.md", "mode": "100644", "type": "blob", "sha": None}])

    def test_github_plan_rejects_sha256_while_core_audit_supports_it(self):
        f = Fixture("sha256")
        raw = g.canonical(f.contract)
        with self.assertRaisesRegex(g.GuardError, "GITHUB_PLAN_REQUIRES_SHA1"):
            g.build_plan(f.store, raw, g.sha256(raw), REPOSITORY)

    def test_plan_is_deterministic_and_offline_replayable_from_its_witness(self):
        plan = g.build_plan(self.f.store, self.raw, self.pin, REPOSITORY)
        rebuilt = g.build_plan(g.WitnessStore(plan["witness"]), self.raw, self.pin, REPOSITORY)
        self.assertEqual(plan, rebuilt)


class GitHubSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.snapshot = {"sha": self.f.base_tree, "truncated": False, "tree": [
            {"path": name.decode(), "mode": entry.mode, "sha": entry.oid,
             "type": "tree" if entry.mode == "040000" else "blob"}
            for name, entry in self.f.base_entries.items()]}

    def test_complete_nonrecursive_snapshot_recomputes_object(self):
        oid, raw = g.github_tree_object(self.snapshot)
        self.assertEqual(oid, self.f.base_tree)
        self.assertEqual(raw, self.f.store.objects[oid][1])

    def test_truncated_true_unknown_string_or_integer_never_passes(self):
        for value in [True, None, "false", 0, 1]:
            snapshot = copy.deepcopy(self.snapshot)
            snapshot["truncated"] = value
            with self.subTest(value=value), self.assertRaisesRegex(g.GuardError, "TRUNCATED_OR_UNKNOWN"):
                g.github_tree_object(snapshot)

    def test_falsely_complete_missing_row_fails_object_hash(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["tree"].pop()
        with self.assertRaisesRegex(g.GuardError, "GITHUB_TREE_HASH_MISMATCH"):
            g.github_tree_object(snapshot)

    def test_recursive_snapshot_refused_not_mistaken_for_root(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["tree"][0]["path"] = "nested/entry"
        with self.assertRaisesRegex(g.GuardError, "INVALID_TREE_NAME"):
            g.github_tree_object(snapshot)

    def test_type_mode_mismatch_rejected(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["tree"][0]["type"] = "blob"
        with self.assertRaisesRegex(g.GuardError, "GITHUB_TREE_ENTRY_TYPE"):
            g.github_tree_object(snapshot)

    def test_duplicate_name_rejected(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["tree"].append(snapshot["tree"][0])
        with self.assertRaisesRegex(g.GuardError, "DUPLICATE_TREE_NAME"):
            g.github_tree_object(snapshot)

    def test_snapshot_unknown_fields_rejected(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["trust_me"] = True
        with self.assertRaisesRegex(g.GuardError, "GITHUB_TREE_SCHEMA"):
            g.github_tree_object(snapshot)

    def test_bool_blob_size_rejected(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["tree"][0]["size"] = True
        with self.assertRaisesRegex(g.GuardError, "GITHUB_TREE_ENTRY_SIZE"):
            g.github_tree_object(snapshot)

    def test_observed_incident_root_hash_is_independently_reconstructed(self):
        # Exact fields transcribed from the authenticated GitHub read of the
        # 2026-09-18T03:29:55Z commit's root. Not a complete Commons replay.
        observed = {"sha": "44923dbd408d894eb2c8dbf7e372d2be6dcba7d7", "truncated": False,
                    "tree": [{"path": "p", "mode": "040000", "type": "tree",
                              "sha": "b96f96ad0fb790574e1246405a498e13584412e7"}]}
        oid, raw = g.github_tree_object(observed)
        self.assertEqual(oid, observed["sha"])
        self.assertEqual(list(g.tree_decode(raw, "sha1")), [b"p"])

    def test_wrong_shaped_witness_format_fails_closed(self):
        w = self.f.run()["witness"]
        w["object_format"] = []
        with self.assertRaises(g.GuardError):
            g.WitnessStore(w)

    def test_wrong_shaped_witness_type_fails_closed(self):
        w = self.f.run()["witness"]
        w["objects"][0]["type"] = []
        with self.assertRaises(g.GuardError):
            g.WitnessStore(w)


class RealGitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.env = dict(os.environ, GIT_AUTHOR_NAME="Synthetic test", GIT_AUTHOR_EMAIL="test@example.invalid",
                        GIT_COMMITTER_NAME="Synthetic test", GIT_COMMITTER_EMAIL="test@example.invalid",
                        GIT_AUTHOR_DATE="2001-01-01T00:00:00Z", GIT_COMMITTER_DATE="2001-01-01T00:00:00Z",
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.run_git("init", "-q")
        self.f = Fixture()
        for oid, (kind, raw) in self.f.store.objects.items():
            self.assertEqual(self.run_git("hash-object", "-w", "-t", kind, "--stdin", data=raw).decode().strip(), oid)
        self.run_git("update-ref", "refs/heads/main", self.f.base)
        self.contract_path = Path(self.temp.name) / "contract.json"
        self.contract_raw = g.canonical(self.f.contract)
        self.contract_path.write_bytes(self.contract_raw)

    def tearDown(self):
        self.temp.cleanup()

    def run_git(self, *args, data=None):
        result = subprocess.run(["git", "-C", str(self.repo), *args], input=data,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, check=False)
        if result.returncode:
            self.fail(result.stderr.decode("utf-8", "replace"))
        return result.stdout

    def cli(self, candidate=None, extra=()):
        args = [*PYTHON, str(Path(g.__file__).resolve()), "audit", "--repo", str(self.repo),
                "--contract", str(self.contract_path), "--contract-sha256", g.sha256(self.contract_raw),
                "--repository", REPOSITORY, "--candidate", candidate or self.f.good, *extra]
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def test_real_git_cli_audit_then_offline_replay(self):
        path = Path(self.temp.name) / "report.json"
        result = self.cli(extra=["--ref", "refs/heads/main", "--output", str(path)])
        self.assertEqual(result.returncode, 0, result.stderr)
        report = g.load_json(path.read_bytes())
        self.assertEqual(report["state"], "TREE_MATCH")
        replay = subprocess.run([*PYTHON, str(Path(g.__file__).resolve()), "replay",
                                 "--contract", str(self.contract_path), "--contract-sha256", g.sha256(self.contract_raw),
                                 "--repository", REPOSITORY, "--candidate", self.f.good, "--report", str(path)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        self.assertEqual(g.load_json(replay.stdout)["state"], "REPLAY_MATCH")

    def test_real_cli_plan_does_not_write_git_objects(self):
        before = {str(p.relative_to(self.repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in self.repo.rglob("*") if p.is_file()}
        args = [*PYTHON, str(Path(g.__file__).resolve()), "plan", "--repo", str(self.repo),
                "--contract", str(self.contract_path), "--contract-sha256", g.sha256(self.contract_raw),
                "--repository", REPOSITORY, "--ref", "refs/heads/main"]
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = g.load_json(result.stdout)
        self.assertEqual(plan["request"]["base_tree"], self.f.base_tree)
        self.assertFalse(plan["candidate_checked"])
        after = {str(p.relative_to(self.repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in self.repo.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_explicit_optimized_cli_receipt_matches_normal(self):
        common = [str(Path(g.__file__).resolve()), "audit", "--repo", str(self.repo),
                  "--contract", str(self.contract_path), "--contract-sha256", g.sha256(self.contract_raw),
                  "--repository", REPOSITORY, "--candidate", self.f.good]
        normal = subprocess.run([sys.executable, *common], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        optimized = subprocess.run([sys.executable, "-O", *common], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(normal.returncode, 0, normal.stderr)
        self.assertEqual(optimized.returncode, 0, optimized.stderr)
        self.assertEqual(normal.stdout, optimized.stdout)

    def test_replay_needs_no_git_binary(self):
        path = Path(self.temp.name) / "replay-no-git.json"
        self.assertEqual(self.cli(extra=["--output", str(path)]).returncode, 0)
        result = subprocess.run([*PYTHON, str(Path(g.__file__).resolve()), "replay",
                                 "--contract", str(self.contract_path), "--contract-sha256", g.sha256(self.contract_raw),
                                 "--repository", REPOSITORY, "--candidate", self.f.good, "--report", str(path)],
                                env=dict(os.environ, PATH=""), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(g.load_json(result.stdout)["state"], "REPLAY_MATCH")

    def test_real_git_incident_rejects_exit_one(self):
        result = self.cli(self.f.bad)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(g.load_json(result.stdout)["state"], "HOLD")

    def test_real_git_missing_object_is_error_not_green(self):
        result = self.cli("f" * 40)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(result.stdout)

    def test_cli_existing_output_not_overwritten(self):
        path = Path(self.temp.name) / "existing.json"
        path.write_bytes(b"retained")
        result = self.cli(extra=["--output", str(path)])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(path.read_bytes(), b"retained")

    def test_ref_moved_before_audit_rejects(self):
        self.run_git("update-ref", "refs/heads/main", self.f.good)
        result = self.cli(extra=["--ref", "refs/heads/main"])
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"LOCAL_REF_NOT_AT_BASE", result.stderr)

    def test_ref_moves_during_audit_rejects(self):
        real_audit = g.audit
        def moving(*args, **kwargs):
            r = real_audit(*args, **kwargs)
            self.run_git("update-ref", "refs/heads/main", self.f.good)
            return r
        path = Path(self.temp.name) / "no-report.json"
        with mock.patch.object(g, "audit", side_effect=moving):
            rc = g.cli(["audit", "--repo", str(self.repo), "--contract", str(self.contract_path),
                        "--contract-sha256", g.sha256(self.contract_raw), "--repository", REPOSITORY,
                        "--candidate", self.f.good, "--ref", "refs/heads/main", "--output", str(path)])
        self.assertEqual(rc, 2)
        self.assertFalse(path.exists())

    def test_replace_ref_does_not_hide_loss(self):
        self.run_git("replace", self.f.bad, self.f.good)
        # Without --no-replace-objects cat-file would show the substituted commit.
        result = self.cli(self.f.bad)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(g.load_json(result.stdout)["candidate_tree"], self.f.bad_tree)

    def test_parent_environment_cannot_redirect_repository(self):
        with mock.patch.dict(os.environ, {"GIT_DIR": "/not/the/repository", "GIT_NAMESPACE": "fake"}):
            result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_ref_worktree_index_or_object_writes_from_audit(self):
        def snapshot():
            return {str(p.relative_to(self.repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.repo.rglob("*") if p.is_file()}
        before = snapshot()
        self.assertEqual(self.cli().returncode, 0)
        self.assertEqual(before, snapshot())

    def test_hostile_binary_path_names_match_git_mktree(self):
        names = [b"a", b"a.c", b"a0", b"a-z", b"z\tfile", b"newline\nfile", b"\xff", "caf\u00e9".encode(), b"subdir"]
        rng = random.Random(704)
        for iteration in range(40):
            entries = {}
            for name in rng.sample(names, rng.randint(1, len(names))):
                mode = rng.choice(["100644", "100755", "120000", "160000", "040000"])
                oid = self.f.base_tree if mode == "040000" else self.f.base if mode == "160000" else self.f.old.oid
                entries[name] = g.Entry(mode, oid)
            rows = []
            for name, e in entries.items():
                kind = "tree" if e.mode == "040000" else "commit" if e.mode == "160000" else "blob"
                rows.append(f"{e.mode} {kind} {e.oid}\t".encode() + name + b"\0")
            rng.shuffle(rows)
            git_oid = self.run_git("mktree", "-z", "--missing", data=b"".join(rows)).decode().strip()
            raw = g.tree_encode(entries, "sha1")
            self.assertEqual(g.object_id("tree", raw, "sha1"), git_oid, iteration)
            self.assertEqual(g.tree_decode(raw, "sha1"), entries)

    def test_regular_input_symlink_refused(self):
        link = Path(self.temp.name) / "link.json"
        link.symlink_to(self.contract_path)
        with self.assertRaises(g.GuardError):
            g.read_file(str(link))

    def test_fifo_input_refused_without_blocking(self):
        fifo = Path(self.temp.name) / "fifo"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(g.GuardError, "INPUT_NOT_BOUNDED_REGULAR_FILE"):
            g.read_file(str(fifo))

    def test_output_symlink_cannot_modify_target(self):
        target = Path(self.temp.name) / "retained"
        target.write_bytes(b"retained")
        link = Path(self.temp.name) / "output"
        link.symlink_to(target)
        with self.assertRaises(g.GuardError):
            g.publish(str(link), {"data": "new"})
        self.assertEqual(target.read_bytes(), b"retained")

    def test_invalid_ref_is_not_executed(self):
        store = g.GitStore(str(self.repo))
        for ref in ["main", "--help", "refs/heads/x..y", "refs/heads/x.lock", "refs/heads/x\n"]:
            with self.subTest(ref=ref), self.assertRaises(g.GuardError):
                store.ref_oid(ref)

    def test_tiny_runtime_budget_fails_closed(self):
        with self.assertRaises(g.GuardError):
            g.GitStore(str(self.repo), timeout=1e-12)


if __name__ == "__main__":
    unittest.main()
