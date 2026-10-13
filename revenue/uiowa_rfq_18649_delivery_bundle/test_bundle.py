"""Regression tests for exact-byte transport, not assessment semantics."""
from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

try:
    from . import bundle, examples
except ImportError:
    import bundle
    import examples


def compiler_contract_pair():
    """Fictional shape fixture, NOT compiler output or University evidence."""
    report, handoff = examples.synthetic_pair()
    report["schema"] = "uiowa-rfq18649-workshare-report/v2"
    report["fixture_notice"] = "CONTRACT_STUB_NOT_COMPILER_OUTPUT"
    del report["synthetic_demo"]
    handoff["synthetic_demo"] = False
    for rows in (report["assessment_matrix"], handoff["cell_notes"]):
        for row in rows:
            if row["dimension"] == "software_development":
                row["dimension"] = "software"
    return report, handoff


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.report, self.handoff = examples.synthetic_pair()

    def pair(self):
        return bundle.canonical(self.report), bundle.canonical(self.handoff)

    def pack(self):
        return bundle.build_bundle(*self.pair())

    def fails(self, code, fn, *args):
        with self.assertRaises(bundle.BundleError) as cm:
            fn(*args)
        self.assertEqual(cm.exception.code, code)

    def pair_fails(self, code):
        self.fails(code, bundle.build_bundle, *self.pair())

    def test_roundtrip_and_explicit_scope(self):
        receipt = bundle.verify_bundle(self.pack())
        self.assertEqual(receipt["status"], "PACKAGING_INTEGRITY_VERIFIED")
        self.assertEqual(receipt["verification_scope"], bundle.SCOPE)
        self.assertIsNone(receipt["independent_digest_match"])
        self.assertIs(receipt["parent_compiler_receipt_recomputed"], False)
        self.assertTrue(all(v is False for v in receipt["authority"].values()))
        self.assertIs(receipt["binding"]["synthetic_demo"], True)

    def test_deterministic_rebuild(self):
        self.assertEqual(self.pack(), self.pack())

    def test_exact_input_whitespace_and_unicode_survive(self):
        self.handoff["cell_notes"][0]["analyst_note"] = "Review café — α\nsecond line"
        report = json.dumps(self.report, indent=4).encode() + b"\r\n"
        handoff = json.dumps(self.handoff, ensure_ascii=False).encode() + b"\n\n"
        data = bundle.build_bundle(report, handoff)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.read("report.json"), report)
            self.assertEqual(archive.read("handoff.json"), handoff)
        bundle.verify_bundle(data)

    def test_whitespace_changes_archive_digest_not_receipt_binding(self):
        report, handoff = self.pair()
        a = bundle.build_bundle(report, handoff)
        b = bundle.build_bundle(report + b"\n", handoff)
        self.assertNotEqual(bundle.sha256(a), bundle.sha256(b))
        self.assertEqual(bundle.verify_bundle(a)["binding"], bundle.verify_bundle(b)["binding"])

    def test_independent_hash_matches(self):
        data = self.pack()
        self.assertIs(bundle.verify_bundle(data, bundle.sha256(data))["independent_digest_match"], True)

    def test_independent_hash_detects_whole_bundle_replacement(self):
        before = self.pack()
        self.handoff["cell_notes"][0]["analyst_note"] = "Different valid draft"
        after = self.pack()
        bundle.verify_bundle(after)  # Self-consistency is not authenticity.
        self.fails("ARCHIVE_DIGEST", bundle.verify_bundle, after, bundle.sha256(before))

    def test_digest_shape(self):
        for digest in ("", "A" * 64, "0" * 63, 0, False, []):
            with self.subTest(digest=digest):
                self.fails("EXPECTED_DIGEST", bundle.verify_bundle, self.pack(), digest)

    def test_duplicate_json_keys_nested(self):
        self.fails("JSON_DUPLICATE_KEY", bundle.parse_object, b'{"nested":{"a":1,"a":2}}', "input")

    def test_duplicate_root_key(self):
        report, handoff = self.pair()
        duplicate = report.replace(b'{', b'{"mode":"other",', 1)
        self.fails("JSON_DUPLICATE_KEY", bundle.build_bundle, duplicate, handoff)

    def test_nonfinite_json(self):
        for value in (b"NaN", b"Infinity", b"-Infinity", b"1e9999", b"-1e9999"):
            with self.subTest(value=value):
                self.fails("JSON_NONFINITE", bundle.parse_object, b'{"x":' + value + b'}', "input")

    def test_invalid_json_utf8_and_shape(self):
        for raw in (b"\xff", b"{", b'{"a":true,}', b"\xef\xbb\xbf{}"):
            with self.subTest(raw=raw):
                self.fails("JSON_INVALID", bundle.parse_object, raw, "input")
        for raw in (b"[]", b"null", b"0", b'"text"'):
            self.fails("JSON_OBJECT", bundle.parse_object, raw, "input")

    def test_json_limit(self):
        self.fails("JSON_SIZE", bundle.parse_object, b" " * (bundle.MAX_JSON_BYTES + 1), "input")

    def test_report_mode(self):
        self.report["mode"] = "CURRENT"
        self.pair_fails("REPORT_MODE")

    def test_report_authority_truthy_or_missing(self):
        original = copy.deepcopy(self.report)
        for field in ("current_evidence_review_authority", "authority_root_supplied_out_of_band"):
            for value in (True, None, 0, "false"):
                with self.subTest(field=field, value=value):
                    self.report = copy.deepcopy(original)
                    self.report["trust"][field] = value
                    self.pair_fails("REPORT_AUTHORITY")
        self.report["trust"] = []
        self.pair_fails("REPORT_AUTHORITY")

    def test_handoff_authority_every_flag_and_unknown_flag(self):
        original = copy.deepcopy(self.handoff)
        for field in bundle.AUTHORITY_KEYS:
            for value in (True, 0, None):
                self.handoff = copy.deepcopy(original)
                self.handoff["authority"][field] = value
                self.pair_fails("HANDOFF_AUTHORITY")
        self.handoff = original
        self.handoff["authority"]["extra_authority"] = False
        self.pair_fails("HANDOFF_AUTHORITY")

    def test_handoff_authority_missing_flag(self):
        del self.handoff["authority"]["recognized_revenue"]
        self.pair_fails("HANDOFF_AUTHORITY")

    def test_receipt_shape(self):
        for value in ("x" * 64, "A" * 64, 1, None, [], "0" * 63):
            self.report["receipt_sha256"] = value
            self.pair_fails("REPORT_RECEIPT")

    def test_report_binding_all_fields(self):
        original = copy.deepcopy(self.handoff)
        for field in ("report_receipt_sha256", "report_mode", "aggregate_state"):
            self.handoff = copy.deepcopy(original)
            self.handoff[field] = "changed"
            self.pair_fails("REPORT_BINDING")

    def test_handoff_status_and_schema(self):
        self.handoff["status"] = "APPROVED"
        self.pair_fails("HANDOFF_SCHEMA")
        self.handoff["status"] = "DRAFT_NON_AUTHORITATIVE"
        self.handoff["schema"] = "future/v2"
        self.pair_fails("HANDOFF_SCHEMA")

    def test_synthetic_label_cannot_be_silently_changed(self):
        self.handoff["synthetic_demo"] = False
        self.pair_fails("SYNTHETIC_LABEL")
        self.handoff["synthetic_demo"] = True
        self.report["synthetic_demo"] = False
        self.pair_fails("SYNTHETIC_LABEL")

    def test_synthetic_flag_must_be_boolean(self):
        self.report["synthetic_demo"] = 1
        self.pair_fails("SYNTHETIC_LABEL")

    def test_unmarked_untrusted_report_stays_draft_not_real_data_claim(self):
        self.report["schema"] = "external-untrusted-report/v1"
        del self.report["synthetic_demo"]
        self.handoff["synthetic_demo"] = False
        data = self.pack()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            notes = archive.read("README.txt")
        self.assertIn(b"false does not prove real data", notes)
        self.assertIn(b"NOT AN APPROVED ASSESSMENT", notes)

    def test_missing_duplicate_unknown_report_cells(self):
        original = copy.deepcopy(self.report)
        self.report["assessment_matrix"].pop()
        self.pair_fails("CELL_COVERAGE")
        self.report = copy.deepcopy(original)
        self.report["assessment_matrix"][1] = self.report["assessment_matrix"][0]
        self.pair_fails("CELL_COVERAGE")
        self.report = original
        self.report["assessment_matrix"][0]["group"] = "UNKNOWN"
        self.pair_fails("CELL_COVERAGE")

    def test_missing_handoff_cell(self):
        self.handoff["cell_notes"].pop()
        self.pair_fails("CELL_COVERAGE")

    def test_cell_order_is_not_identity(self):
        self.handoff["cell_notes"].reverse()
        bundle.verify_bundle(self.pack())

    def test_nonobject_or_unhashable_cell_diagnostic(self):
        self.report["assessment_matrix"][0] = []
        self.pair_fails("CELL_SHAPE")
        self.report, self.handoff = examples.synthetic_pair()
        self.report["assessment_matrix"][0]["group"] = []
        self.pair_fails("CELL_SHAPE")

    def test_cell_status_mismatch(self):
        self.handoff["cell_notes"][0]["compiler_status"] = "READY"
        self.pair_fails("CELL_BINDING")

    def test_note_disposition_and_shape(self):
        self.handoff["cell_notes"][0]["disposition"] = "APPROVED"
        self.pair_fails("NOTE_DISPOSITION")
        self.handoff["cell_notes"][0]["disposition"] = "UNREVIEWED"
        self.handoff["cell_notes"][0]["analyst_note"] = []
        self.pair_fails("NOTE_SHAPE")

    def test_archive_empty_oversize_or_garbage(self):
        self.fails("ARCHIVE_SIZE", bundle.verify_bundle, b"")
        self.fails("ARCHIVE_SIZE", bundle.verify_bundle, b"x" * (bundle.MAX_ARCHIVE_BYTES + 1))
        self.fails("ARCHIVE_INVALID", bundle.verify_bundle, b"not a zip")

    def test_manifest_hash_mutation(self):
        files = bundle.payloads(*self.pair())
        value = json.loads(files["manifest.json"])
        value["entries"][0]["sha256"] = "a" * 64
        files["manifest.json"] = bundle.canonical(value)
        self.fails("MANIFEST_MISMATCH", bundle.verify_bundle, bundle.encode_archive(files))

    def test_payload_mutation_without_manifest_update(self):
        files = bundle.payloads(*self.pair())
        files["handoff.json"] += b"\n"
        self.fails("MANIFEST_MISMATCH", bundle.verify_bundle, bundle.encode_archive(files))

    def test_manifest_authority_or_readme_mutation(self):
        files = bundle.payloads(*self.pair())
        files["README.txt"] = b"Approved"
        self.fails("MANIFEST_MISMATCH", bundle.verify_bundle, bundle.encode_archive(files))

    def test_extra_missing_and_traversal_members(self):
        original = bundle.payloads(*self.pair())
        for name in ("extra.txt", "../report.json", "/report.json"):
            files = dict(original)
            files[name] = b"extra"
            self.fails("ARCHIVE_MEMBERS", bundle.verify_bundle, bundle.encode_archive(files))
        files = dict(original)
        del files["README.txt"]
        self.fails("ARCHIVE_MEMBERS", bundle.verify_bundle, bundle.encode_archive(files))

    def test_duplicate_members(self):
        data = io.BytesIO(self.pack())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(data, "a") as archive:
                archive.writestr("report.json", self.pair()[0])
        self.fails("ARCHIVE_MEMBERS", bundle.verify_bundle, data.getvalue())

    def test_noncanonical_zip_order_metadata_or_trailing_bytes(self):
        self.fails("ARCHIVE_NONCANONICAL", bundle.verify_bundle, self.pack() + b"extra")
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            for name, raw in bundle.payloads(*self.pair()).items():
                archive.writestr(name, raw)
        self.fails("ARCHIVE_NONCANONICAL", bundle.verify_bundle, data.getvalue())

    def test_compressed_archive_rejected_before_decompression(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in bundle.payloads(*self.pair()).items():
                archive.writestr(name, raw)
        self.fails("ARCHIVE_FORMAT", bundle.verify_bundle, data.getvalue())

    def test_corrupted_crc(self):
        data = self.pack()
        self.assertIn(b"Fictional rehearsal", data)
        bad = data.replace(b"Fictional rehearsal", b"ChangedXX rehearsal", 1)
        self.fails("ARCHIVE_INVALID", bundle.verify_bundle, bad)


    def use_compiler_contract(self):
        self.report, self.handoff = compiler_contract_pair()

    def test_compiler_v2_grid_roundtrip_is_non_authoritative(self):
        self.use_compiler_contract()
        receipt = bundle.verify_bundle(self.pack())
        self.assertIs(receipt["binding"]["synthetic_demo"], False)
        self.assertIs(receipt["parent_compiler_receipt_recomputed"], False)
        self.assertEqual(receipt["verification_scope"], bundle.SCOPE)
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertIn("NOT_COMPILER_OUTPUT", self.report["fixture_notice"])

    def test_compiler_explicit_false_marker_preserved(self):
        self.use_compiler_contract()
        self.report["synthetic_demo"] = False
        receipt = bundle.verify_bundle(self.pack())
        self.assertIs(receipt["binding"]["synthetic_demo"], False)

    def test_compiler_all_three_software_cells_survive_as_written(self):
        self.use_compiler_contract()
        before = copy.deepcopy((self.report, self.handoff))
        data = self.pack()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            report = json.loads(archive.read("report.json"))
            handoff = json.loads(archive.read("handoff.json"))
        for rows in (report["assessment_matrix"], handoff["cell_notes"]):
            self.assertEqual({(row["group"], row["dimension"]) for row in rows
                              if row["dimension"] == "software"},
                             {("ESS", "software"), ("RIS", "software"), ("IAM", "software")})
            self.assertNotIn("software_development", {row["dimension"] for row in rows})
        self.assertEqual((self.report, self.handoff), before)

    def test_compiler_unicode_whitespace_and_receipt_exact_bytes(self):
        self.use_compiler_contract()
        self.handoff["cell_notes"][0]["analyst_note"] = "FICTIONAL: café 🙂\nsecond line"
        report = json.dumps(self.report, ensure_ascii=False, indent=3).encode() + b"\r\n"
        handoff = json.dumps(self.handoff, ensure_ascii=False, indent=1).encode() + b"\n\n"
        data = bundle.build_bundle(report, handoff)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.read("report.json"), report)
            self.assertEqual(archive.read("handoff.json"), handoff)
        self.assertEqual(bundle.verify_bundle(data)["binding"]["report_receipt_sha256"],
                         self.report["receipt_sha256"])

    def test_compiler_cell_order_and_determinism(self):
        self.use_compiler_contract()
        self.handoff["cell_notes"].reverse()
        self.report["assessment_matrix"].reverse()
        first = self.pack()
        self.assertEqual(first, self.pack())
        bundle.verify_bundle(first, bundle.sha256(first))

    def test_compiler_schema_rejects_long_grid_even_on_both_inputs(self):
        self.report["schema"] = "uiowa-rfq18649-workshare-report/v2"
        del self.report["synthetic_demo"]
        self.handoff["synthetic_demo"] = False
        self.pair_fails("CELL_COVERAGE")

    def test_demo_schema_rejects_short_grid_even_on_both_inputs(self):
        for rows in (self.report["assessment_matrix"], self.handoff["cell_notes"]):
            for row in rows:
                if row["dimension"] == "software_development":
                    row["dimension"] = "software"
        self.pair_fails("CELL_COVERAGE")

    def test_compiler_mixed_report_grid_rejected_per_group(self):
        for group in ("ESS", "RIS", "IAM"):
            with self.subTest(group=group):
                self.use_compiler_contract()
                for rows in (self.report["assessment_matrix"], self.handoff["cell_notes"]):
                    next(row for row in rows if row["group"] == group
                         and row["dimension"] == "software")["dimension"] = "software_development"
                self.pair_fails("CELL_COVERAGE")

    def test_compiler_cross_grid_handoff_rejected(self):
        self.use_compiler_contract()
        for row in self.handoff["cell_notes"]:
            if row["dimension"] == "software":
                row["dimension"] = "software_development"
        self.pair_fails("CELL_COVERAGE")

    def test_demo_cross_grid_handoff_rejected(self):
        for row in self.handoff["cell_notes"]:
            if row["dimension"] == "software_development":
                row["dimension"] = "software"
        self.pair_fails("CELL_COVERAGE")

    def test_external_schema_canonical_grid_remains_explicitly_untrusted(self):
        self.use_compiler_contract()
        self.report["schema"] = "external-untrusted-report/v1"
        result = bundle.verify_bundle(self.pack())
        self.assertIs(result["parent_compiler_receipt_recomputed"], False)
        self.assertIsNone(result["independent_digest_match"])
        self.assertIs(result["binding"]["synthetic_demo"], False)

    def test_external_schema_legacy_long_grid_preserved(self):
        self.report["schema"] = "external-untrusted-report/v1"
        self.report["synthetic_demo"] = False
        self.handoff["synthetic_demo"] = False
        bundle.verify_bundle(self.pack())

    def test_external_schema_cannot_mix_vocabularies(self):
        self.report["schema"] = "external-untrusted-report/v1"
        self.report["synthetic_demo"] = False
        self.handoff["synthetic_demo"] = False
        self.report["assessment_matrix"][0]["dimension"] = "software"
        self.handoff["cell_notes"][0]["dimension"] = "software"
        self.pair_fails("CELL_COVERAGE")

    def test_compiler_missing_duplicate_and_invalid_shape_diagnostics(self):
        for change, code in (("missing", "CELL_COVERAGE"), ("duplicate", "CELL_COVERAGE"),
                             ("object", "CELL_SHAPE"), ("dimension", "CELL_SHAPE")):
            with self.subTest(change=change):
                self.use_compiler_contract()
                rows = self.report["assessment_matrix"]
                if change == "missing":
                    rows.pop()
                elif change == "duplicate":
                    rows[1] = rows[0].copy()
                elif change == "object":
                    rows[0] = []
                else:
                    rows[0]["dimension"] = []
                self.pair_fails(code)

    def test_compiler_status_and_authority_boundaries_retained(self):
        self.use_compiler_contract()
        self.handoff["cell_notes"][0]["compiler_status"] = "READY"
        self.pair_fails("CELL_BINDING")
        for flag in bundle.AUTHORITY_KEYS:
            self.use_compiler_contract()
            self.handoff["authority"][flag] = True
            self.pair_fails("HANDOFF_AUTHORITY")

    def test_named_schema_marker_coherence_still_required(self):
        self.use_compiler_contract()
        self.report["synthetic_demo"] = True
        self.handoff["synthetic_demo"] = True
        self.pair_fails("SYNTHETIC_LABEL")
        self.report, self.handoff = examples.synthetic_pair()
        del self.report["synthetic_demo"]
        self.handoff["synthetic_demo"] = False
        self.pair_fails("SYNTHETIC_LABEL")

    def test_demo_archive_digest_is_byte_identical_to_published_fixture(self):
        self.assertEqual(bundle.sha256(self.pack()),
                         "e90a6a740e1336c2dfdbd761bec1ef878a5ec3aaf24ca8d6e9987744157b089c")

    def test_legacy_matrix_default_still_uses_demo_cells(self):
        self.assertEqual(len(bundle.matrix(self.report["assessment_matrix"], "legacy")), 12)
        self.use_compiler_contract()
        self.fails("CELL_COVERAGE", bundle.matrix, self.report["assessment_matrix"], "legacy")

    def test_compiler_archive_tamper_requires_revalidation(self):
        self.use_compiler_contract()
        original = self.pack()
        self.handoff["cell_notes"][0]["analyst_note"] = "FICTIONAL revised handoff"
        updated = self.pack()
        bundle.verify_bundle(updated)
        self.fails("ARCHIVE_DIGEST", bundle.verify_bundle, updated, bundle.sha256(original))

    def test_parent_constant_declarations_match_compiler_contract(self):
        # Declaration check only. This does not run or certify the compiler.
        import ast
        parent = Path(__file__).resolve().parents[1] / "uiowa_rfq_18649_workshare" / "workshare_constants.py"
        if not parent.is_file():
            if os.environ.get("UIOWA_REQUIRE_PARENT_CONTRACT") == "1":
                self.fail("parent constant declarations required for contract canary")
            self.skipTest("parent declarations absent; standalone tests do not verify compiler declarations")
        values = {}
        for statement in ast.parse(parent.read_text(encoding="utf-8")).body:
            if isinstance(statement, ast.Assign):
                for name in statement.targets:
                    if isinstance(name, ast.Name) and name.id in {"REPORT_SCHEMA", "GROUPS", "DIMENSIONS"}:
                        values[name.id] = ast.literal_eval(statement.value)
        self.assertEqual(values["REPORT_SCHEMA"], bundle.COMPILER_REPORT_SCHEMA)
        expected = frozenset((g, d) for g in values["GROUPS"] for d in values["DIMENSIONS"])
        self.assertEqual(expected, bundle.COMPILER_CELLS)
        report, _ = compiler_contract_pair()
        self.assertEqual({(row["group"], row["dimension"]) for row in report["assessment_matrix"]}, expected)


class CommandTests(unittest.TestCase):
    def run_cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(Path(bundle.__file__).resolve()), *map(str, args)],
                              cwd=cwd, capture_output=True, text=True, timeout=15)

    def test_pack_verify_in_separate_directory_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            source, target = Path(a), Path(b)
            r, h = examples.synthetic_pair()
            (source / "report.json").write_bytes(bundle.canonical(r))
            (source / "handoff.json").write_bytes(bundle.canonical(h))
            output = target / "handoff.zip"
            args = ("pack", "--report", source / "report.json", "--handoff", source / "handoff.json",
                    "--output", output)
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            digest = json.loads(result.stdout)["archive_sha256"]
            second = self.run_cli("verify", "handoff.zip", "--expected-sha256", digest, cwd=target)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIs(json.loads(second.stdout)["independent_digest_match"], True)
            before = output.read_bytes()
            duplicate = self.run_cli(*args)
            self.assertEqual(duplicate.returncode, 2)
            self.assertEqual(json.loads(duplicate.stderr)["error"], "FILE_IO")
            self.assertEqual(before, output.read_bytes())
            self.assertEqual(sorted(p.name for p in target.iterdir()), ["handoff.zip"])

    def test_cli_missing_input_is_structured_error(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_cli("verify", Path(folder) / "absent.zip")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)["error"], "INPUT_FILE")

    def test_cli_invalid_handoff_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report, handoff = examples.synthetic_pair()
            handoff["report_receipt_sha256"] = "a" * 64
            (root / "report.json").write_bytes(bundle.canonical(report))
            (root / "handoff.json").write_bytes(bundle.canonical(handoff))
            result = self.run_cli("pack", "--report", root / "report.json", "--handoff",
                                  root / "handoff.json", "--output", root / "out.zip")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr)["error"], "REPORT_BINDING")
            self.assertFalse((root / "out.zip").exists())

    def test_hash_seed_does_not_change_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            script = ("import examples,bundle; r,h=examples.synthetic_pair(); "
                      "print(bundle.sha256(bundle.build_bundle(bundle.canonical(r),bundle.canonical(h))))")
            results = []
            for seed in ("1", "42", "random"):
                env = dict(os.environ, PYTHONHASHSEED=seed)
                p = subprocess.run([sys.executable, "-c", script], env=env,
                                   cwd=Path(bundle.__file__).parent, capture_output=True, text=True,
                                   timeout=15)
                self.assertEqual(p.returncode, 0, p.stderr)
                results.append(p.stdout)
            self.assertEqual(len(set(results)), 1)


    def test_compiler_contract_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report, handoff = compiler_contract_pair()
            original = bundle.canonical(report), bundle.canonical(handoff)
            (root / "report.json").write_bytes(original[0])
            (root / "handoff.json").write_bytes(original[1])
            result = self.run_cli("pack", "--report", root / "report.json", "--handoff",
                                  root / "handoff.json", "--output", root / "out.zip")
            self.assertEqual(result.returncode, 0, result.stderr)
            digest = json.loads(result.stdout)["archive_sha256"]
            checked = self.run_cli("verify", root / "out.zip", "--expected-sha256", digest)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertIs(json.loads(checked.stdout)["binding"]["synthetic_demo"], False)
            self.assertEqual((root / "report.json").read_bytes(), original[0])
            self.assertEqual((root / "handoff.json").read_bytes(), original[1])

    def test_compiler_contract_cli_grid_rejection_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report, handoff = compiler_contract_pair()
            handoff["cell_notes"][0]["dimension"] = "software_development"
            (root / "report.json").write_bytes(bundle.canonical(report))
            (root / "handoff.json").write_bytes(bundle.canonical(handoff))
            result = self.run_cli("pack", "--report", root / "report.json", "--handoff",
                                  root / "handoff.json", "--output", root / "out.zip")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr)["error"], "CELL_COVERAGE")
            self.assertFalse((root / "out.zip").exists())

    def test_compiler_contract_hash_seed_determinism(self):
        script = ("import test_bundle,bundle; r,h=test_bundle.compiler_contract_pair(); "
                  "print(bundle.sha256(bundle.build_bundle(bundle.canonical(r),bundle.canonical(h))))")
        observed = []
        for seed in ("1", "42", "random"):
            result = subprocess.run([sys.executable, "-c", script],
                                    cwd=Path(bundle.__file__).parent,
                                    env=dict(os.environ, PYTHONHASHSEED=seed),
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            observed.append(result.stdout)
        self.assertEqual(len(set(observed)), 1)


if __name__ == "__main__":
    unittest.main()
