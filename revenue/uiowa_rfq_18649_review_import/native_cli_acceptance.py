"""Real native CLI acceptance, including no-op and rejected-comment diagnostics.

Every input is a synthetic test fixture. The actual parent compiler, verifier,
review engine and CLI execute; no mocks, replacement validators or skips.
Run: python native_cli_acceptance.py --out /tmp/uiowa124-cli-NEW
Use a fresh output directory. Python -O propagates to every child interpreter.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from revenue.uiowa_rfq_18649_review_import import native_bridge as bridge
from revenue.uiowa_rfq_18649_review_cycle import review as native
from revenue.uiowa_rfq_18649_review_cycle.parent_adapter import compile_inspection

OUT: Path | None = None
TRACES: list[dict] = []
COMMENT = 'SYNTHETIC reviewer note.\nRetain "quoted text", café and a tab:\tend.'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_bytes(native.canonical(value))


def fixture_report() -> dict:
    generation, prime, source_id = "SYN-C7L2-G1", "Fictional CLI test prime", "SYN-C7L2-S1"
    source = {
        "source_id": source_id, "authority_generation": generation,
        "solicitation_id": "18649", "prime_candidate": prime,
        "group": "ESS", "dimension": "software", "evidence_kind": "artifact",
        "source_ref": "synthetic://uiowa124-c7l2/fixture.txt",
        "source_content_sha256": sha(b"SYNTHETIC TEST FIXTURE; not a University observation.\n"),
        "observed_at": "2026-09-19T00:00:00Z",
        "claim": "SYNTHETIC TEST FIXTURE; not a University observation.",
        "maturity": 1, "confidence_bp": 5000,
    }
    authority = {"schema": "uiowa-rfq18649-evidence-authority/v2", "generation": generation,
                 "solicitation_id": "18649", "prime_candidate": prime, "sources": [source]}
    candidate = {"schema": "uiowa-rfq18649-workshare-candidate/v2", "authority_generation": generation,
                 "source_ids": [source_id], "engagement": {"solicitation_id": "18649",
                 "buyer": "University of Iowa", "prime_candidate": prime, "subcontractor": "TJLabs",
                 "base_fee_usd": 24000, "optional_readout_usd": 4000}}
    return compile_inspection(candidate, authority)


def fixture_document(report: dict) -> dict:
    return {"schema": native.DOC_SCHEMA, "status": native.STATUS, "synthetic": True,
            "version": "SYN-C7L2-V1", "parent_version": None,
            "report_receipt_sha256": report["receipt_sha256"], "authority": deepcopy(native.AUTHORITY),
            "findings": [{"id": "SYN-C7L2-F1", "group": "ESS", "dimension": "software",
                          "title": "Synthetic review target", "statement": "Fiction, not an assessment finding.",
                          "source_ids": ["SYN-C7L2-S1"]}],
            "recommendations": [], "applied_cycles": [], "unresolved": []}


def row(**changes) -> dict:
    return {"comment_id": "SYN-C7L2-C1", "reviewer_role": "Fictional practitioner",
            "comment_text": COMMENT, "finding_id": "SYN-C7L2-F1", "report_version": "SYN-C7L2-V1",
            "finding_namespace": bridge.NAMESPACE, "comment_kind": "wording",
            "proposed_edit": "This is proposed text, not an authorized patch.",
            "supplied_decision": "ACCEPT", "fiction_notice": "SYNTHETIC TEST DATA", **changes}


def csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(row()), lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


class NativeCliAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = fixture_report()
        native.verify_inspection(cls.report)
        cls.document = fixture_document(cls.report)
        native.validate_document(cls.document, cls.report)

    def setUp(self):
        if OUT is None:
            temp = tempfile.TemporaryDirectory(prefix="uiowa124-cli-")
            self.addCleanup(temp.cleanup)
            self.case = Path(temp.name)
        else:
            self.case = OUT / self._testMethodName
            self.case.mkdir()
        self.doc = deepcopy(self.document)
        self.doc_path, self.report_path = self.case / "draft.json", self.case / "report.json"
        write_json(self.doc_path, self.doc)
        write_json(self.report_path, self.report)
        self.commands = []

    def tearDown(self):
        TRACES.append({"test": self._testMethodName, "commands": self.commands,
                       "files_sha256": {str(p.relative_to(self.case)): sha(p.read_bytes())
                                        for p in sorted(self.case.rglob("*")) if p.is_file()}})

    def invoke(self, rows=None, *, name="application", document=None, raw=None,
               cycle="SYN-C7L2-ROUND1", version="SYN-C7L2-V2", apply=True, extra=()):
        source = self.case / (name + ".csv")
        source.write_bytes(csv_bytes([row()] if rows is None else rows) if raw is None else raw)
        destination = self.case / name
        command = [sys.executable, *(["-O"] if sys.flags.optimize else []), str(HERE / "native_bridge.py"),
                   str(source), str(document or self.doc_path), str(self.report_path),
                   "--source-id", "SYN-C7L2-SOURCE", "--cycle-id", cycle, "--new-version", version,
                   "--out", str(destination), *(["--apply-open"] if apply else []), *extra]
        protected = {p: p.read_bytes() for p in (source, document or self.doc_path, self.report_path)}
        result = subprocess.run(command, cwd=self.case, capture_output=True, timeout=30, check=False)
        self.commands.append({"argv": [s.replace(str(self.case), "$CASE").replace(str(ROOT), "$ROOT") for s in command],
                              "exit_code": result.returncode, "stdout": result.stdout.decode("utf-8", "replace"),
                              "stderr": result.stderr.decode("utf-8", "replace")})
        for path, before in protected.items():
            self.assertEqual(path.read_bytes(), before, f"input changed: {path}")
        return result, destination

    def prepared(self, dest):
        return native.load(dest / "preparation.json")

    def no_application(self, result, dest, *, expected=1):
        self.assertEqual(result.returncode, expected, result.stderr.decode())
        self.assertTrue((dest / "preparation.json").is_file(), "diagnostics were discarded")
        self.assertFalse((dest / "native-bundle").exists(), "empty/invalid review was applied")
        self.assertFalse((dest / "application-receipt.json").exists(), "non-application called applied")
        self.assertEqual(native.load(dest / "native-comments.json")["comments"], [])
        return self.prepared(dest)

    def test_apply_open_preserves_text_and_never_infers_acceptance(self):
        result, dest = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        native.verify_bundle(dest / "native-bundle")
        prepared = self.prepared(dest)
        comment = prepared["cycle"]["comments"][0]
        self.assertEqual(comment["comment"], COMMENT)
        self.assertEqual(comment["decision"], "OPEN")
        self.assertEqual(comment["owner_role"], "UNASSIGNED")
        self.assertEqual(comment["proposed_changes"], [])
        self.assertEqual(comment["source_ids"], [])
        self.assertEqual(prepared["mapped"][0]["reviewer_role"], "Fictional practitioner")
        self.assertEqual(prepared["mapped"][0]["record"]["values"]["supplied_decision"], "ACCEPT")
        audit = native.load(dest / "native-bundle/audit.json")
        revised = native.load(dest / "native-bundle/revised-draft.json")
        self.assertEqual(audit["changes"], [])
        self.assertEqual(audit["source_changes"], [])
        self.assertEqual(audit["compiler_status_changes"], [])
        self.assertEqual(revised["findings"], self.doc["findings"])
        self.assertTrue(all(v is False for v in revised["authority"].values()))
        self.assertEqual(revised["unresolved"][0]["comment"], COMMENT)

    def test_missing_finding_retains_diagnostics_with_apply_open(self):
        result, dest = self.invoke([row(finding_id="SYN-NOT-PRESENT")])
        prepared = self.no_application(result, dest)
        self.assertEqual(prepared["staged"]["unresolved"][0]["diagnostics"][0]["code"], "UNKNOWN_FINDING")

    def test_stale_report_retains_diagnostics_with_apply_open(self):
        result, dest = self.invoke([row(report_version="SYN-OLD")])
        prepared = self.no_application(result, dest)
        self.assertEqual(prepared["staged"]["unresolved"][0]["diagnostics"][0]["code"], "VERSION_MISMATCH")

    def test_missing_comment_id_retains_unkeyed_source(self):
        result, dest = self.invoke([row(comment_id="")])
        prepared = self.no_application(result, dest)
        self.assertEqual(prepared["staged"]["unkeyed_rows"][0]["values"]["comment_text"], COMMENT)

    def test_unsupported_kind_retains_original_values(self):
        result, dest = self.invoke([row(comment_kind="unknown-kind")])
        prepared = self.no_application(result, dest)
        self.assertEqual(prepared["native_unresolved"][0]["diagnostics"][0]["code"], "NATIVE_KIND_REQUIRED")
        self.assertEqual(prepared["native_unresolved"][0]["record"]["values"]["comment_kind"], "unknown-kind")

    def test_native_control_rejection_retains_exact_text(self):
        value = "SYNTHETIC first\x0bsecond"
        with self.assertRaises(ValueError):
            native.text(value, "comment")
        result, dest = self.invoke([row(comment_text=value)])
        prepared = self.no_application(result, dest)
        rejected = prepared["native_unresolved"][0]
        self.assertEqual(rejected["record"]["values"]["comment_text"], value)
        self.assertEqual(rejected["diagnostics"][0]["code"], "NATIVE_TEXT_REJECTED")

    def test_crlf_tracks_actual_native_policy_without_normalization(self):
        value = 'SYNTHETIC café\r\n"quoted" second line.'
        try:
            native.text(value, "comment")
        except ValueError:
            accepted = False
        else:
            accepted = True
        result, dest = self.invoke([row(comment_text=value)])
        if accepted:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            native.verify_bundle(dest / "native-bundle")
            self.assertEqual(native.load(dest / "native-bundle/comments.json")["comments"][0]["comment"], value)
        else:
            self.no_application(result, dest)
        staged = self.prepared(dest)["staged"]["ready"][0]
        self.assertEqual(staged["values"]["comment_text"], value)
        self.assertEqual(staged["occurrences"][0]["line_start"], 2)
        self.assertEqual(staged["occurrences"][0]["line_end"], 3)

    def test_mixed_valid_and_rejected_keeps_both(self):
        bad = row(comment_id="SYN-C7L2-C2", finding_id="SYN-NOT-PRESENT")
        result, dest = self.invoke([row(), bad])
        self.assertEqual(result.returncode, 1, result.stderr.decode())
        native.verify_bundle(dest / "native-bundle")
        self.assertEqual(len(native.load(dest / "native-bundle/comments.json")["comments"]), 1)
        self.assertEqual(self.prepared(dest)["staged"]["unresolved"][0]["values"], bad)

    def test_preparation_only_retains_rejection_without_creating_bundle(self):
        result, dest = self.invoke([row(comment_kind="unknown-kind")], apply=False)
        self.no_application(result, dest)

    def test_same_cycle_on_revised_document_is_refused(self):
        result, first = self.invoke(name="first")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        revised = first / "native-bundle/revised-draft.json"
        result, dest = self.invoke(name="second", document=revised, version="SYN-C7L2-V3")
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"cycle already applied", result.stderr)
        self.assertFalse(dest.exists())

    def test_old_csv_reimport_is_not_rebound_to_new_version(self):
        result, first = self.invoke(name="first")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        result, dest = self.invoke(name="second", document=first / "native-bundle/revised-draft.json",
                                   cycle="SYN-C7L2-ROUND2", version="SYN-C7L2-V3")
        prepared = self.no_application(result, dest)
        self.assertEqual(prepared["staged"]["unresolved"][0]["diagnostics"][0]["code"], "VERSION_MISMATCH")

    def test_existing_open_comment_is_a_noop_not_another_revision(self):
        result, first = self.invoke(name="first")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        result, dest = self.invoke([row(report_version="SYN-C7L2-V2")], name="second",
                                   document=first / "native-bundle/revised-draft.json",
                                   cycle="SYN-C7L2-ROUND2", version="SYN-C7L2-V3")
        prepared = self.no_application(result, dest, expected=0)
        self.assertEqual(prepared["summary"]["already_present"], 1)
        self.assertEqual(prepared["already_present"][0]["code"], "ALREADY_IN_REVIEW")

    def test_native_id_conflict_is_not_silently_applied(self):
        result, first = self.invoke(name="first")
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        value = "SYNTHETIC replacement of existing comment text"
        result, dest = self.invoke([row(report_version="SYN-C7L2-V2", comment_text=value)], name="second",
                                   document=first / "native-bundle/revised-draft.json",
                                   cycle="SYN-C7L2-ROUND2", version="SYN-C7L2-V3")
        prepared = self.no_application(result, dest)
        self.assertEqual(prepared["native_unresolved"][0]["diagnostics"][0]["code"], "NATIVE_ID_CONFLICT")
        self.assertEqual(prepared["native_unresolved"][0]["record"]["values"]["comment_text"], value)

    def test_empty_csv_does_not_create_review_revision(self):
        result, dest = self.invoke([])
        prepared = self.no_application(result, dest, expected=0)
        self.assertEqual(prepared["summary"]["input_records"], 0)

    def test_existing_output_preserves_every_existing_byte(self):
        dest = self.case / "application"
        dest.mkdir()
        sentinel = dest / "operator-owned.txt"
        sentinel.write_bytes(b"retain this existing artifact\r\n")
        result, actual = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(actual, dest)
        self.assertEqual({p.name for p in dest.iterdir()}, {sentinel.name})
        self.assertEqual(sentinel.read_bytes(), b"retain this existing artifact\r\n")

    def test_corrupt_compiler_report_is_rejected_before_output(self):
        bad = deepcopy(self.report)
        bad["receipt_sha256"] = "0" * 64
        write_json(self.report_path, bad)
        result, dest = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"report receipt mismatch", result.stderr)
        self.assertFalse(dest.exists())

    def test_semantic_tampering_cannot_pass_a_rehashed_receipt(self):
        bad = deepcopy(self.report)
        bad["assessment_matrix"][0]["status"] = "READY"
        del bad["receipt_sha256"]
        bad["receipt_sha256"] = native.digest(bad)
        write_json(self.report_path, bad)
        result, dest = self.invoke()
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"semantic recompile mismatch", result.stderr)
        self.assertFalse(dest.exists())

    def test_invalid_utf8_is_rejected_without_output(self):
        result, dest = self.invoke(raw=b"\xff\xfe\x01")
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"invalid UTF-8", result.stderr)
        self.assertFalse(dest.exists())


def source_manifest() -> dict:
    paths = list((ROOT / "revenue/uiowa_rfq_18649_workshare").glob("workshare_*.py"))
    paths += [HERE / n for n in ("comment_import.py", "native_bridge.py", "native_cli_acceptance.py")]
    paths += [Path(native.__file__), Path(native.__file__).with_name("parent_adapter.py")]
    return {str(p.relative_to(ROOT)): {"sha256": sha(p.read_bytes()),
            "git_blob_sha1": hashlib.sha1(b"blob " + str(p.stat().st_size).encode() + b"\0" + p.read_bytes()).hexdigest()}
            for p in sorted(paths)}


def main() -> int:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case", action="append", help="Run only the named test method; repeat for a bounded batch")
    args = parser.parse_args()
    names = unittest.defaultTestLoader.getTestCaseNames(NativeCliAcceptance)
    chosen = args.case or names
    if len(chosen) != len(set(chosen)) or any(name not in names for name in chosen):
        parser.error("cases must be unique existing NativeCliAcceptance test methods")
    OUT = args.out.resolve()
    OUT.mkdir(parents=True, exist_ok=False)
    sources = source_manifest()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(NativeCliAcceptance(name) for name in chosen))
    if sources != source_manifest():
        raise RuntimeError("source changed during execution")
    receipt = {"schema": "uiowa124-native-cli-acceptance/v1", "seat": "ZZ-KESTREL-C7L2",
               "synthetic": True, "real_parent_compiler": True, "real_native_cli": True,
               "mocked_dependencies": [], "python": platform.python_version(), "optimization": sys.flags.optimize,
               "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "skipped": len(result.skipped), "successful": result.wasSuccessful(),
               "sources": sources, "cases": TRACES,
               "scope": "Cloud-container CLI execution; not hosted CI, human approval or main-merge evidence."}
    write_json(OUT / "receipt.json", receipt)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
