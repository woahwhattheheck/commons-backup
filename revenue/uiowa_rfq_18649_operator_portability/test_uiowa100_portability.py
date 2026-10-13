"""Portable artifact contracts. Minimal stand-ins test packaging, not Iowa findings.

The separate acceptance command must run on a real checkout to establish actual
compiler/workbench integration. These unit-test stand-ins cannot establish it.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

_SPEC = importlib.util.spec_from_file_location("uiowa100_portability_tests_subject", Path(__file__).with_name("uiowa100_portability.py"))
p = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(p)
REVISION = "a" * 40


def reference_report() -> dict:
    return {"mode": "UNTRUSTED_INSPECTION", "aggregate_state": "HOLD_TRUSTED_AUTHORITY_REQUIRED",
            "trust": {"authority_root_supplied_out_of_band": False, "current_evidence_review_authority": False},
            "external_authority": {"buyer_contact": False, "revenue": False},
            "assessment_matrix": [{"group": g, "dimension": d, "status": "HOLD_MISSING_EVIDENCE",
                                    "maturity": None, "confidence_bp": None}
                                   for g in ("ESS", "RIS", "IAM") for d in ("SDLC", "SEC", "OPS", "AI")],
            "receipt_sha256": "b" * 64}


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="uiowa100-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / "source"
        self.root.mkdir()
        for name in p.SEEDS:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# fixture only\n" if name.endswith(".py") else "{}\n", encoding="utf-8")
        (self.root / p.WORKSHARE / "compiler.py").write_text("import workshare_contract\n")
        (self.root / p.WORKSHARE / "workshare_contract.py").write_text("from workshare_core import sample\n")
        (self.root / p.WORKSHARE / "workshare_core.py").write_text("sample = 1\n")

    def package(self):
        archive = self.home / "kit.zip"
        p.pack(self.root, archive, REVISION)
        destination = self.home / "unpacked"
        p.unpack(archive, destination)
        return destination

    def test_source_closure_includes_transitive_local_imports(self):
        files = p.source_closure(self.root)
        self.assertIn(p.WORKSHARE + "/workshare_core.py", files)
        self.assertEqual(len(files), len(p.SEEDS) + 2)

    def test_no_arbitrary_evidence_or_generated_files_collected(self):
        (self.root / p.WORKSHARE / "private-notes.json").write_text("private marker")
        self.assertNotIn(p.WORKSHARE + "/private-notes.json", p.source_closure(self.root))

    def test_missing_import_is_not_silently_omitted(self):
        (self.root / p.WORKSHARE / "workshare_core.py").unlink()
        with self.assertRaisesRegex(p.PortabilityError, "missing local import"):
            p.source_closure(self.root)

    def test_relative_import_requires_adapter(self):
        (self.root / p.WORKSHARE / "workshare_core.py").write_text("from . import helper\n")
        with self.assertRaisesRegex(p.PortabilityError, "relative import"):
            p.source_closure(self.root)

    def test_repeat_pack_is_byte_identical(self):
        first, second = self.home / "one.zip", self.home / "two.zip"
        self.assertEqual(p.pack(self.root, first, REVISION), p.pack(self.root, second, REVISION))
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_existing_output_is_preserved(self):
        target = self.home / "protected.zip"
        target.write_bytes(b"preserve")
        with self.assertRaises(FileExistsError):
            p.pack(self.root, target, REVISION)
        self.assertEqual(target.read_bytes(), b"preserve")

    def test_unpack_relocates_and_verifies_sources(self):
        destination = self.package()
        result = p.verify(destination)
        self.assertEqual(result["state"], "BYTE_INTEGRITY_VERIFIED")
        self.assertIs(result["source_authenticity_established"], False)
        self.assertEqual((destination / p.WORKSHARE / "workshare_core.py").read_bytes(), b"sample = 1\n")

    def test_changed_source_is_not_pass(self):
        destination = self.package()
        (destination / p.WORKSHARE / "compiler.py").write_text("# changed\n")
        with self.assertRaisesRegex(p.PortabilityError, "integrity mismatch"):
            p.verify(destination)

    def test_added_import_shadow_is_detected(self):
        (self.root / p.WORKSHARE / "compiler.py").write_text("import json\nimport workshare_contract\n")
        destination = self.package()
        (destination / p.WORKSHARE / "json.py").write_text("# unexpected shadow\n")
        with self.assertRaisesRegex(p.PortabilityError, "complete runtime closure"):
            p.verify(destination)

    def test_manifest_omitted_dependency_is_detected(self):
        destination = self.package()
        path = destination / p.MANIFEST
        manifest = json.loads(path.read_text())
        manifest["files"] = [r for r in manifest["files"] if not r["path"].endswith("workshare_core.py")]
        path.write_bytes(p.canonical(manifest))
        with self.assertRaisesRegex(p.PortabilityError, "complete runtime closure"):
            p.verify(destination)

    def test_symlink_source_rejected(self):
        target = self.root / p.WORKSHARE / "workshare_core.py"
        target.unlink()
        target.symlink_to(self.root / p.WORKSHARE / "compiler.py")
        with self.assertRaisesRegex(p.PortabilityError, "symlink"):
            p.source_closure(self.root)

    def test_traversal_and_cross_platform_absolute_names_rejected(self):
        for name in ("../escape", "/abs", "a/../b", "a//b", "C:/x", "a\\b", "a/./b"):
            with self.subTest(name=name), self.assertRaises(p.PortabilityError):
                p.relative_name(name)

    def test_unlisted_archive_file_rejected_before_unpack(self):
        archive = self.home / "kit.zip"
        p.pack(self.root, archive, REVISION)
        with zipfile.ZipFile(archive, "a") as handle:
            handle.writestr("extra.json", "{}")
        target = self.home / "rejected"
        with self.assertRaisesRegex(p.PortabilityError, "inventories disagree"):
            p.unpack(archive, target)
        self.assertFalse(target.exists())

    def test_duplicate_json_and_nonfinite_rejected(self):
        for raw in (b'{"files": [], "files": []}', b'{"x": NaN}'):
            with self.subTest(raw=raw), self.assertRaises(p.PortabilityError):
                p.strict_json(raw)

    def test_required_seed_missing_cannot_verify(self):
        destination = self.package()
        path = destination / p.MANIFEST
        manifest = json.loads(path.read_text())
        manifest["files"] = [r for r in manifest["files"] if r["path"] != p.SELF]
        path.write_bytes(p.canonical(manifest))
        with self.assertRaisesRegex(p.PortabilityError, "required runtime"):
            p.verify(destination)

    def test_false_authority_and_ratings_preserved(self):
        good = reference_report()
        self.assertEqual(p.inspection_assertions(good)["cells"], 12)
        cases = []
        for section, field in (("trust", "current_evidence_review_authority"), ("external_authority", "buyer_contact")):
            bad = copy.deepcopy(good)
            bad[section][field] = True
            cases.append(bad)
        bad = copy.deepcopy(good)
        bad["assessment_matrix"][0]["maturity"] = 4
        cases.append(bad)
        bad = copy.deepcopy(good)
        bad["mode"] = "CURRENT"
        cases.append(bad)
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(p.PortabilityError):
                p.inspection_assertions(bad)

    def test_duplicate_or_missing_matrix_cells_rejected(self):
        for matrix in ([], reference_report()["assessment_matrix"][:11], [reference_report()["assessment_matrix"][0]] * 12):
            bad = reference_report()
            bad["assessment_matrix"] = matrix
            with self.subTest(matrix=matrix), self.assertRaises(p.PortabilityError):
                p.inspection_assertions(bad)

    def test_failed_command_retains_failure_receipt(self):
        destination = self.package()
        output = self.home / "failed-run"
        failed = subprocess.CompletedProcess(["python3"], 2, "", "fixture rejection")
        with patch.object(p.subprocess, "run", return_value=failed), self.assertRaises(p.PortabilityError):
            p.rehearse(destination, output)
        receipt = json.loads((output / "receipt.json").read_text())
        self.assertEqual(receipt["state"], "FAIL")
        self.assertEqual(receipt["commands"][0]["exit_code"], 2)
        self.assertNotIn("outputs", receipt)

    def test_malformed_trust_is_a_named_contract_failure(self):
        for value in (None, [], "false"):
            bad = reference_report()
            bad["trust"] = value
            with self.subTest(value=value), self.assertRaisesRegex(p.PortabilityError, "trust record"):
                p.inspection_assertions(bad)

    def test_packaged_runner_bootstraps_without_host_imports(self):
        # A complete harness test using explicitly fake parents, not real Iowa acceptance.
        (self.root / p.SELF).write_bytes(Path(p.__file__).read_bytes())
        (self.root / p.WORKSHARE / "fixtures/synthetic_packet.json").write_bytes(p.canonical(reference_report()))
        compiler = """import json, sys
from pathlib import Path
if sys.argv[1] == 'compile':
    Path(sys.argv[4]).write_text(Path(sys.argv[2]).read_text())
elif sys.argv[1] == 'verify':
    print('UNTRUSTED_INTEGRITY_ONLY ' + 'b' * 64)
elif sys.argv[1] == 'render':
    Path(sys.argv[3]).write_text('# Explicit unit-test stand-in, not an Iowa finding\\n')
"""
        (self.root / p.WORKSHARE / "compiler.py").write_text(compiler)
        (self.root / p.WORKBENCH / "server.py").write_text(
            "class CompilerAdapter:\n    def inspect(self, candidate, authority):\n        return candidate\n")
        result = p.acceptance(self.root, self.home / "bootstrap", REVISION)
        self.assertEqual(result["state"], "PASS_TWO_OPERATOR_REPRODUCTION")
        self.assertEqual(len(result["packaged_runner_invocations"]), 2)
        self.assertTrue(all(r["exit_code"] == 0 for r in result["packaged_runner_invocations"]))
        self.assertEqual(result["commands_per_operator"], 4)
        self.assertEqual(result["browser_acceptance"], "NOT_RUN")

    def test_short_or_missing_revision_rejected(self):
        for revision in ("main", "abcd", "", "g" * 40):
            with self.subTest(revision=revision), self.assertRaises(p.PortabilityError):
                p.source_manifest({}, revision)


if __name__ == "__main__":
    unittest.main()
