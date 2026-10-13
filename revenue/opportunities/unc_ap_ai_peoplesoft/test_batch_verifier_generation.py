"""Retained regressions for independent review 5245138893."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import batch_reconcile as m
import _batch_reconcile_core as core
from test_batch_reconcile import AS_OF, snapshot


class VerifierGeneration(unittest.TestCase):
    def setUp(self):
        self.packet = snapshot()
        self.compile = m.compile_review
        self.verify = m.verify_report
        self.error = m.ContractError
        self.report = self.compile(self.packet, as_of=AS_OF)
        self.forged = deepcopy(self.report)
        self.forged["authority"]["payment"] = True

    def reject(self, report=None, packet=None):
        with self.assertRaises(self.error):
            self.verify(self.packet if packet is None else packet,
                        self.forged if report is None else report)

    def test_reported_exported_compiler_rebind_unresealed(self):
        with patch.object(m, "compile_review", lambda _packet, *, as_of: self.forged):
            self.reject()

    def test_saved_verifier_still_accepts_valid_report(self):
        with patch.object(m, "compile_review", side_effect=RuntimeError("public shim")):
            self.assertTrue(self.verify(self.packet, self.report))

    def test_core_compiler_rebind_cannot_change_saved_generation(self):
        with patch.object(core, "compile_review", lambda _packet, *, as_of: self.forged):
            self.reject()
            self.assertTrue(self.verify(self.packet, self.report))

    def test_resealed_forgery_cannot_use_rebound_compiler(self):
        forged = deepcopy(self.forged)
        del forged["receipt_sha256"]
        forged["receipt_sha256"] = m.digest(forged)
        with patch.object(m, "compile_review", lambda _packet, *, as_of: forged):
            self.reject(forged)

    def test_facade_helper_rebinding(self):
        with patch.multiple(m, canonical=lambda _: b"same", _admit=lambda _: None,
                            digest=lambda _: "0"*64, _error=lambda _: None):
            self.reject()
            self.assertTrue(self.verify(self.packet, self.report))

    def test_core_helper_rebinding(self):
        with patch.multiple(core, canonical=lambda _: b"same", _admit=lambda _: None,
                            digest=lambda _: "0"*64, validate=lambda _: self.packet):
            self.reject()
            self.assertTrue(self.verify(self.packet, self.report))

    def test_compare_module_alias_rebinding(self):
        fake = SimpleNamespace(compare_digest=lambda left, right: True)
        with patch.object(m, "hmac", fake), patch.object(core, "hmac", fake):
            self.reject()
            self.assertTrue(self.verify(self.packet, self.report))

    def test_codec_module_alias_rebinding(self):
        fake = SimpleNamespace(dumps=lambda *a, **k: "same", loads=lambda *a, **k: {})
        with patch.object(m, "json", fake), patch.object(core, "json", fake):
            self.reject()
            self.assertTrue(self.verify(self.packet, self.report))

    def test_dependency_function_attribute_rebinding(self):
        # Captured dependency attributes are separate from the publicly aliased
        # stdlib modules. No mutation of a captured function's internals occurs.
        with patch.object(m.hmac, "compare_digest", lambda left, right: True), \
             patch.object(m.json, "dumps", lambda *a, **k: "same"):
            self.reject()
            self.assertTrue(self.verify(self.packet, self.report))

    def test_source_policy_constant_rebinding(self):
        with patch.multiple(core, MAX_DEPTH=100000, MAX_NODES=100000000,
                            MAX_BYTES=100000000, MAX_INT=10**200, VERSION="invented"), \
             patch.object(m, "VERSION", "invented"):
            self.assertTrue(self.verify(self.packet, self.report))
            changed = deepcopy(self.packet)
            changed["schema_version"] = True
            self.reject(packet=changed)
            huge = deepcopy(self.report)
            huge["extra"] = "x"*4_000_001
            self.reject(huge)

    def test_boolean_integer_alias_rejected_with_helper_rebindings(self):
        changed = deepcopy(self.report)
        changed["authority"]["payment"] = 0
        with patch.object(core, "canonical", lambda _: b"same"):
            self.reject(changed)

    def test_changed_input_rejected_after_validation_rebind(self):
        changed = deepcopy(self.packet)
        changed["snapshot_id"] = "OTHER-GENERATION"
        with patch.object(core, "validate", lambda _: self.packet):
            self.reject(self.report, packet=changed)

    def test_saved_compiler_is_also_generation_bound(self):
        with patch.multiple(core, validate=lambda _: {}, _error=lambda _: None,
                            canonical=lambda _: b"same", digest=lambda _: "0"*64):
            self.assertEqual(self.compile(self.packet, as_of=AS_OF), self.report)

    def test_package_import_surface(self):
        root = Path(__file__).resolve().parents[3]
        command = [sys.executable, *(["-O"] if sys.flags.optimize else []), "-c",
                   "from revenue.opportunities.unc_ap_ai_peoplesoft import batch_reconcile as m; "
                   "print(m.VERSION); "
                   "raise SystemExit(0 if callable(m.verify_report) and callable(m.main) else 1)"]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ap-batch-review/1.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
