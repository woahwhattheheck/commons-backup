"""Contract-driven tests for the offline ReuseLedger workflow; synthetic only.

The existing compiler suite is not rerun. Tests use a separate two-output
fixture, independent digest calculations, real CLI calls, and temporary files.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import reuse_workflow as workflow


HERE = Path(__file__).resolve().parent
FILES = {"manifest.json", "packet.json", "journal.json", "reuse_report.json",
         "reuse_report.md", "reuseledger.py", "reuse_workflow.py", "RECEIPT.json"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fixture():
    return {
        "schema": "nci-reuseledger-manifest/v1", "project": "Fictional workflow review",
        "outputs": [
            {"id": "urn:example:software-1", "kind": "software", "title": "Fictional tool",
             "access": "open", "landing_url": "https://example.invalid/tool",
             "license": "Apache-2.0", "data_use": "Synthetic only", "fixity": None,
             "depends_on": ["urn:example:dataset-1"]},
            {"id": "urn:example:dataset-1", "kind": "dataset", "title": "Fictional data",
             "access": "open", "landing_url": "https://example.invalid/data",
             "license": "CC-BY-4.0", "data_use": "Synthetic only",
             "fixity": {"sha256": "a" * 64, "bytes": 123}, "depends_on": []},
        ],
    }


def event(identifier="urn:reuse-event:fictional-001", **changes):
    value = {
        "schema": "nci-reuseledger-event/v1", "id": identifier, "state": "reported",
        "recorded_on": "2026-09-19", "occurred_on": "2026-09-18",
        "purpose": "Fictional methods comparison; no empirical claim",
        "downstream": {"id": "urn:example:follow-up", "version": None},
        "upstream_ids": ["urn:example:software-1", "urn:example:dataset-1"],
        "credit_refs": None,
    }
    value.update(changes)
    return value


def reseal(journal):
    """Recompute only hash-chain fields, never regenerate upstream bindings."""
    previous = None
    for entry in journal["entries"]:
        entry["previous_entry_sha256"] = previous
        entry["entry_sha256"] = digest(canonical({k: v for k, v in entry.items()
                                                   if k != "entry_sha256"}))
        previous = entry["entry_sha256"]
    journal["semantic_sha256"] = digest(canonical({k: v for k, v in journal.items()
                                                   if k != "semantic_sha256"}))


class WorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="reuse-workflow-review-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = fixture()
        self.raw = (json.dumps(self.manifest, ensure_ascii=False, indent=2) + "\n").encode()
        self.source = self.root / "upstream.json"
        self.source.write_bytes(self.raw)
        self.initial = workflow.init_journal(self.manifest, self.raw)

    def append(self, journal=None, item=None):
        return workflow.record_event(self.manifest, self.raw,
                                     self.initial if journal is None else journal,
                                     event() if item is None else item)

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def cli(self, *args):
        flags = ["-O"] if sys.flags.optimize else []
        return subprocess.run([sys.executable, "-B", *flags, str(HERE / "reuse_workflow.py"),
                               *map(str, args)], capture_output=True, text=True, timeout=20)

    def assert_cli_error(self, result):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("ERROR", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def bundle(self, name="bundle"):
        folder = self.root / name
        folder.mkdir()
        for filename, content in workflow.build_files(self.manifest, self.raw, self.append()).items():
            (folder / filename).write_bytes(content)
        return folder

    def test_offline_cli_lifecycle_and_portable_self_replay(self):
        journal0, journal1 = self.root / "journal0.json", self.root / "journal1.json"
        event_path = self.write_json("event.json", event())
        out = self.root / "handoff"
        for args in [("init", self.source, "--out", journal0),
                     ("record", self.source, journal0, event_path, "--out", journal1),
                     ("bundle", self.source, journal1, "--out", out), ("verify", out)]:
            result = self.cli(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertEqual(set(p.name for p in out.iterdir()), FILES)
        # Deliberately omit -B: portable verification must not create __pycache__.
        flags = ["-O"] if sys.flags.optimize else []
        result = subprocess.run([sys.executable, *flags, str(out / "reuse_workflow.py"),
                                 "verify", str(out)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(set(p.name for p in out.iterdir()), FILES)
        self.assertEqual(workflow.verify_bundle(out)["summary"]["reported_records"], 1)

    def test_credit_unknown_empty_and_declared_remain_distinct(self):
        journal = self.initial
        for number, credit in enumerate([None, [], ["urn:credit:z", "urn:credit:a"]], 1):
            journal = self.append(journal, event(f"urn:reuse-event:credit-{number}", credit_refs=credit))
        files = workflow.build_files(self.manifest, self.raw, journal)
        report = json.loads(files["reuse_report.json"])
        self.assertEqual(report["basis"], "DECLARED_RECORDS_ONLY")
        self.assertEqual(report["summary"], {"total_records": 3, "planned_records": 0,
            "reported_records": 3, "credit_unknown_records": 1, "no_credit_refs_records": 1,
            "declared_credit_refs_records": 1})
        self.assertEqual([r["credit_refs"] for r in report["records"]],
                         [None, [], ["urn:credit:a", "urn:credit:z"]])

    def test_raw_and_semantic_upstream_binding_are_separate(self):
        normalized = copy.deepcopy(self.manifest)
        normalized["outputs"].sort(key=lambda row: row["id"])
        self.assertEqual(self.initial["manifest_file_sha256"], digest(self.raw))
        self.assertEqual(self.initial["manifest_semantic_sha256"], digest(canonical(normalized)))
        reformatted = canonical(self.manifest)
        other = workflow.init_journal(self.manifest, reformatted)
        self.assertEqual(other["manifest_semantic_sha256"], self.initial["manifest_semantic_sha256"])
        self.assertNotEqual(other["manifest_file_sha256"], self.initial["manifest_file_sha256"])
        with self.assertRaises(workflow.WorkflowError):
            workflow.validate_journal(self.manifest, reformatted, self.initial)
        wrong = copy.deepcopy(self.manifest); wrong["project"] = "Another declared project"
        with self.assertRaises(workflow.WorkflowError):
            workflow.init_journal(wrong, self.raw)

    def test_each_upstream_binding_uses_normalized_metadata_and_preserves_null_fixity(self):
        bindings = self.append()["entries"][0]["upstream_bindings"]
        outputs = sorted(self.manifest["outputs"], key=lambda row: row["id"])
        self.assertEqual(bindings, [{"output_id": row["id"],
            "output_metadata_sha256": digest(canonical(row)), "declared_fixity": row["fixity"]}
            for row in outputs])
        self.assertIsNone(bindings[1]["declared_fixity"])

    def test_planned_then_reported_retains_history_and_hash_links(self):
        planned = event("urn:reuse-event:plan", state="planned", occurred_on=None)
        first = self.append(item=planned)
        before = copy.deepcopy(first)
        second = self.append(first, event("urn:reuse-event:report", recorded_on="2026-09-20"))
        self.assertEqual(first, before)
        self.assertEqual(second["entries"][0], before["entries"][0])
        self.assertEqual([x["sequence"] for x in second["entries"]], [1, 2])
        self.assertIsNone(second["entries"][0]["previous_entry_sha256"])
        self.assertEqual(second["entries"][1]["previous_entry_sha256"], first["entries"][0]["entry_sha256"])
        for entry in second["entries"]:
            self.assertEqual(entry["entry_sha256"], digest(canonical({k: v for k, v in entry.items() if k != "entry_sha256"})))
        self.assertEqual(second["semantic_sha256"], digest(canonical({k: v for k, v in second.items() if k != "semantic_sha256"})))
        summary = json.loads(workflow.build_files(self.manifest, self.raw, second)["reuse_report.json"])["summary"]
        self.assertEqual((summary["total_records"], summary["planned_records"], summary["reported_records"]), (2, 1, 1))

    def test_date_rules_and_no_implicit_live_clock(self):
        self.append(item=event(recorded_on="2099-03-01", occurred_on="2099-02-28"))
        bad = [dict(recorded_on="2026-02-29"), dict(recorded_on="2026-9-19"),
               dict(recorded_on=True), dict(state="planned", occurred_on="2026-09-18"),
               dict(occurred_on=None), dict(occurred_on="2026-09-20")]
        for changes in bad:
            with self.subTest(changes=changes), self.assertRaises(workflow.WorkflowError):
                self.append(item=event(**changes))
        first = self.append()
        with self.assertRaises(workflow.WorkflowError):
            self.append(first, event("urn:reuse-event:backdated", recorded_on="2026-09-18"))

    def test_duplicate_event_and_unknown_upstream_are_rejected_without_mutation(self):
        first = self.append(); before = copy.deepcopy(first)
        with self.assertRaises(workflow.WorkflowError):
            self.append(first, event())
        with self.assertRaises(workflow.WorkflowError):
            self.append(first, event("urn:reuse-event:unknown", upstream_ids=["urn:example:absent"]))
        self.assertEqual(first, before)

    def test_event_typed_input_and_exact_shapes(self):
        invalid = [dict(credit_refs="urn:credit:x"), dict(credit_refs=[True]),
                   dict(credit_refs=["urn:credit:x", "urn:credit:x"]), dict(upstream_ids=[]),
                   dict(upstream_ids=["urn:example:dataset-1", "urn:example:dataset-1"]),
                   dict(state="complete"), dict(downstream={"id": "urn:example:down", "version": False}),
                   dict(extra="unexpected"), dict(purpose=" ")]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(workflow.WorkflowError):
                self.append(item=event(**changes))

    def test_duplicate_json_keys_are_rejected_at_nested_event_boundary(self):
        journal = self.write_json("journal.json", self.initial)
        event_text = json.dumps(event()).replace('"version": null', '"version": null, "version": "ambiguous"')
        source = self.root / "duplicate.json"; source.write_text(event_text)
        output = self.root / "should-not-exist.json"
        self.assert_cli_error(self.cli("record", self.source, journal, source, "--out", output))
        self.assertFalse(output.exists())

    def test_nonfinite_json_and_malformed_utf8_fail_cleanly(self):
        journal = self.write_json("journal.json", self.initial)
        for number, raw in enumerate([json.dumps(event()).replace('"credit_refs": null', '"credit_refs": NaN').encode(), b'\xff']):
            source = self.root / f"bad-{number}.json"; source.write_bytes(raw)
            output = self.root / f"bad-out-{number}.json"
            self.assert_cli_error(self.cli("record", self.source, journal, source, "--out", output))
            self.assertFalse(output.exists())

    def test_journal_rejects_resealed_wrong_binding_and_boolean_sequence(self):
        for alteration in ("binding", "sequence"):
            journal = self.append()
            if alteration == "binding":
                journal["entries"][0]["upstream_bindings"][0]["output_metadata_sha256"] = "0" * 64
            else:
                journal["entries"][0]["sequence"] = True
            reseal(journal)
            with self.subTest(alteration=alteration), self.assertRaises(workflow.WorkflowError):
                workflow.validate_journal(self.manifest, self.raw, journal)

    def test_bundle_inventory_receipt_and_declared_record_report(self):
        journal = self.append(); files = workflow.build_files(self.manifest, self.raw, journal)
        self.assertEqual(set(files), FILES)
        self.assertTrue(all(type(value) is bytes for value in files.values()))
        self.assertEqual(files["manifest.json"], self.raw)
        receipt = json.loads(files["RECEIPT.json"])
        self.assertEqual(receipt["schema"], "nci-reuseledger-bundle/v1")
        self.assertEqual(receipt["manifest_file_sha256"], digest(self.raw))
        self.assertEqual(receipt["journal_semantic_sha256"], journal["semantic_sha256"])
        self.assertEqual(receipt["files"], [{"filename": name, "sha256": digest(files[name]), "bytes": len(files[name])}
                                          for name in sorted(FILES - {"RECEIPT.json"})])
        for name in ("packet.json", "journal.json", "reuse_report.json", "RECEIPT.json"):
            self.assertEqual(files[name], (json.dumps(json.loads(files[name]), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())
        report = json.loads(files["reuse_report.json"])
        self.assertEqual(report["schema"], "nci-reuseledger-reuse-report/v1")
        self.assertEqual(report["records"][0]["downstream"]["version"], None)
        self.assertNotIn("reuse_readiness_score", report["summary"])
        # Markdown backslash-escaped hyphens render as the original identifier.
        markdown = files["reuse_report.md"].decode().replace("\\-", "-")
        for value in (event()["id"], event()["purpose"], "2026-09-18", "2026-09-19", "urn:example:dataset-1"):
            self.assertIn(value, markdown)

    def test_verify_recomputes_derived_data_even_after_receipt_resealed(self):
        folder = self.bundle()
        target = folder / "reuse_report.json"
        report = json.loads(target.read_bytes()); report["summary"]["reported_records"] = 999
        target.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
        receipt_path = folder / "RECEIPT.json"; receipt = json.loads(receipt_path.read_bytes())
        for row in receipt["files"]:
            if row["filename"] == target.name:
                row.update(sha256=digest(target.read_bytes()), bytes=len(target.read_bytes()))
        receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        with self.assertRaises(workflow.WorkflowError):
            workflow.verify_bundle(folder)

    def test_bundle_layout_rejects_missing_extra_and_symlink_files(self):
        for alteration in ("missing", "extra", "symlink"):
            folder = self.bundle(alteration)
            if alteration == "missing":
                (folder / "RECEIPT.json").unlink()
            elif alteration == "extra":
                (folder / "unexpected.txt").write_text("not in inventory")
            else:
                target = folder / "manifest.json"; target.unlink(); target.symlink_to(self.source)
            with self.subTest(alteration=alteration), self.assertRaises(workflow.WorkflowError):
                workflow.verify_bundle(folder)

    def test_no_overwrite_for_each_output_command(self):
        journal = self.write_json("journal.json", self.initial)
        item = self.write_json("event.json", event())
        sentinel = self.root / "existing.json"; sentinel.write_bytes(b"preserve existing bytes")
        for args in [("init", self.source, "--out", sentinel),
                     ("record", self.source, journal, item, "--out", sentinel)]:
            self.assert_cli_error(self.cli(*args))
            self.assertEqual(sentinel.read_bytes(), b"preserve existing bytes")
        folder = self.root / "existing-dir"; folder.mkdir(); (folder / "owner.txt").write_text("preserve")
        self.assert_cli_error(self.cli("bundle", self.source, journal, "--out", folder))
        self.assertEqual(list(folder.iterdir()), [folder / "owner.txt"])
        self.assertEqual((folder / "owner.txt").read_text(), "preserve")
        self.assertEqual(self.source.read_bytes(), self.raw)

    def test_invalid_journal_is_rejected_before_bundle_directory_creation(self):
        broken = copy.deepcopy(self.initial); broken["semantic_sha256"] = "0" * 64
        journal = self.write_json("broken.json", broken); output = self.root / "absent"
        self.assert_cli_error(self.cli("bundle", self.source, journal, "--out", output))
        self.assertFalse(output.exists())

    def test_retained_source_tampering_does_not_become_a_trust_anchor(self):
        folder = self.bundle()
        target = folder / "reuseledger.py"; target.write_bytes(target.read_bytes() + b"\n# altered copy\n")
        with self.assertRaises(workflow.WorkflowError):
            workflow.verify_bundle(folder)

    def test_post_import_source_drift_refuses_publication_in_isolated_copy(self):
        for filename in ("reuseledger.py", "reuse_workflow.py"):
            component = self.root / ("isolated-" + filename); component.mkdir()
            for source in ("reuseledger.py", "reuse_workflow.py"):
                shutil.copyfile(HERE / source, component / source)
            (component / "manifest.json").write_bytes(self.raw)
            script = (
                "import json,pathlib,reuse_workflow as w\n"
                "root=pathlib.Path('.')\n"
                "raw=(root/'manifest.json').read_bytes(); m=json.loads(raw)\n"
                "j=w.init_journal(m,raw)\n"
                "(root/'journal.json').write_text(json.dumps(j))\n"
                f"p=root/{filename!r}; p.write_bytes(p.read_bytes()+b'\\n# post-import drift\\n')\n"
                "rc=w.main(['bundle','manifest.json','journal.json','--out','handoff'])\n"
                "if rc!=2 or (root/'handoff').exists(): raise SystemExit('source drift published output')\n"
            )
            flags = ["-O"] if sys.flags.optimize else []
            result = subprocess.run([sys.executable, "-B", *flags, "-c", script], cwd=component,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, filename + result.stdout + result.stderr)
            self.assertIn("ERROR", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
