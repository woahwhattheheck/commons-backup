from __future__ import annotations

import copy
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from revenue.bidder_qualification_vault.v2.engine import (
    RegistryError,
    compile_registry,
    load_json_strict,
    render_markdown,
    verify_receipt,
)
from revenue.bidder_qualification_vault.v2.test_support import H, evidence, payload, req


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class HostileTests(unittest.TestCase):
    def state(self, p):
        return compile_registry(p)["requirements"][0]["state"]

    def _run_compile_cli(self, text: str, *, optimized: bool) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as td:
            work = pathlib.Path(td)
            source = work / "input.json"
            source.write_text(text, encoding="ascii")
            command = [sys.executable]
            if optimized:
                command.append("-O")
            command.extend([
                "-m", "revenue.bidder_qualification_vault.v2.cli", "compile", str(source),
                "--json-out", str(work / "receipt.json"), "--md-out", str(work / "receipt.md"),
            ])
            env = os.environ.copy()
            env["PYTHONINTMAXSTRDIGITS"] = "4300"
            return subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )

    def _assert_controlled_invalid(self, cp: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(cp.returncode, 2, (cp.stdout, cp.stderr))
        self.assertIn("INVALID:", cp.stdout)
        self.assertNotIn("Traceback", cp.stdout + cp.stderr)
        self.assertNotIn("UnicodeEncodeError", cp.stdout + cp.stderr)

    def test_markdown_never_leaks_private_descriptor_or_issuer(self):
        p = payload([evidence("w9", "W9")], [req("r", "W9")])
        md = render_markdown(compile_registry(p))
        self.assertNotIn("synthetic-private-descriptor", md)
        self.assertNotIn("Synthetic Issuer", md)
        self.assertIn("w9", md)
        self.assertIn(H, md)
        self.assertIn("Candidate/integrity review only", md)
        self.assertIn("Ready for bid consumption: `NO`", md)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(RegistryError, "DUPLICATE_JSON_KEY"):
            load_json_strict('{"a":1,"a":2}')

    def test_bool_not_accepted_as_string_or_list(self):
        p = payload()
        p["evidence"][0]["stages"] = True
        with self.assertRaises(RegistryError):
            compile_registry(p)

    def test_unknown_evidence_field_rejected(self):
        p = payload()
        p["evidence"][0]["secret"] = "nope"
        with self.assertRaisesRegex(RegistryError, "KEYS"):
            compile_registry(p)

    def test_bad_sha_rejected(self):
        p = payload()
        p["evidence"][0]["content_sha256"] = "abc"
        with self.assertRaisesRegex(RegistryError, "INVALID_SHA256"):
            compile_registry(p)

    def test_bad_time_rejected(self):
        p = payload()
        p["as_of"] = "2026-09-14T03:50:00+00:00"
        with self.assertRaisesRegex(RegistryError, "INVALID_UTC_SECONDS"):
            compile_registry(p)

    def test_unsafe_id_rejected(self):
        p = payload()
        p["generation_id"] = "../escape"
        with self.assertRaisesRegex(RegistryError, "UNSAFE_ID"):
            compile_registry(p)

    def test_input_not_mutated(self):
        p = payload()
        original = copy.deepcopy(p)
        compile_registry(p)
        self.assertEqual(p, original)

    def test_no_private_descriptor_in_receipt_json(self):
        p = payload()
        raw = json.dumps(compile_registry(p), sort_keys=True)
        self.assertNotIn("synthetic-private-descriptor", raw)
        self.assertNotIn("Synthetic Issuer", raw)

    def test_fabricated_issuer_labels_never_mint_bid_authority(self):
        p = payload()
        ev = p["evidence"][0]
        self.assertEqual(ev["source_class"], "ISSUER_CONTROLLED")
        self.assertEqual(ev["verification_state"], "VERIFIED")
        self.assertEqual(ev["verifier_class"], "ISSUER")
        out = compile_registry(p)
        self.assertEqual(out["requirements"][0]["state"], "CANDIDATE_VERIFIED")
        self.assertTrue(out["candidate_requirements_satisfied"])
        self.assertFalse(out["ready_for_bid_consumption"])
        self.assertFalse(out["authority"]["current_evidence_authority"])
        self.assertNotIn("CURRENT_VERIFIED", json.dumps(out, sort_keys=True))

    def test_backdated_as_of_cannot_mint_current_readiness(self):
        ev = evidence("w9", "W9", expires="2026-09-15T00:00:00Z")
        historical = payload([ev], [req("r", "W9")])
        old_receipt = compile_registry(historical)
        self.assertEqual(old_receipt["requirements"][0]["state"], "CANDIDATE_VERIFIED")
        self.assertFalse(old_receipt["ready_for_bid_consumption"])
        self.assertTrue(verify_receipt(historical, old_receipt))

        later = copy.deepcopy(historical)
        later["as_of"] = "2026-09-16T00:00:00Z"
        later_receipt = compile_registry(later)
        self.assertEqual(later_receipt["requirements"][0]["state"], "EXPIRED")
        self.assertFalse(later_receipt["ready_for_bid_consumption"])

    def test_lone_surrogate_cli_is_controlled_normal_and_optimized(self):
        p = payload()
        p["evidence"][0]["issuer"] = "\ud800"
        text = json.dumps(p, ensure_ascii=True, sort_keys=True)
        for optimized in (False, True):
            with self.subTest(optimized=optimized):
                self._assert_controlled_invalid(self._run_compile_cli(text, optimized=optimized))

    def test_oversized_integer_cli_is_controlled_normal_and_optimized(self):
        text = '{"oversized":' + ("9" * 5000) + "}"
        for optimized in (False, True):
            with self.subTest(optimized=optimized):
                self._assert_controlled_invalid(self._run_compile_cli(text, optimized=optimized))

    def test_receipt_non_scalar_unicode_tamper_is_false_not_exception(self):
        self.assertFalse(verify_receipt(payload(), {"tamper": "\ud800"}))
