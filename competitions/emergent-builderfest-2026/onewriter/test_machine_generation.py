#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
A = HERE / "acceptance.py"
M = HERE / "state_machine.json"
NEW_DIGEST = "4b15651ae153dff379375d285f3a705a2ce4b87014d5d1e08e2dea490251f553"
OLD_DIGEST = "5d91e5f639d684eb8eb5cca4ddcbcefc8c78cb7c3c060a398d604d2dad599a80"
OLD_INVARIANT = "expired_lease_may_be_recovered_with_an_explicit_route"
NEW_INVARIANT = "ordinary_expired_lease_may_be_recovered_with_an_explicit_route"

spec = importlib.util.spec_from_file_location("onewriter_acceptance_generation", A)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load acceptance")
a = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = a
spec.loader.exec_module(a)


class OneWriterMachineGenerationTests(unittest.TestCase):
    def setUp(self):
        self.machine = a.load_json(M)

    def test_current_machine_authenticates_ordinary_only_stale_recovery(self):
        result = a.validate_machine(copy.deepcopy(self.machine))
        self.assertEqual(result["contract_digest_sha256"], NEW_DIGEST)
        self.assertEqual(self.machine["contract_digest_sha256"], NEW_DIGEST)
        self.assertIn(NEW_INVARIANT, self.machine["invariants"])
        self.assertNotIn(OLD_INVARIANT, self.machine["invariants"])

    def test_prior_authenticated_generation_is_rejected(self):
        stale = copy.deepcopy(self.machine)
        index = stale["invariants"].index(NEW_INVARIANT)
        stale["invariants"][index] = OLD_INVARIANT
        stale["contract_digest_sha256"] = OLD_DIGEST
        with self.assertRaisesRegex(a.ContractError, "invariant list changed|semantic digest mismatch"):
            a.validate_machine(stale)

    def test_verify_machine_cli_accepts_new_generation_normal_and_optimized(self):
        for optimized in (False, True):
            cmd = [sys.executable] + (["-O"] if optimized else []) + [str(A), "verify-machine", str(M)]
            run = subprocess.run(cmd, cwd=HERE, text=True, capture_output=True, check=False)
            with self.subTest(optimized=optimized):
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(json.loads(run.stdout)["contract_digest_sha256"], NEW_DIGEST)

    def test_verify_machine_cli_rejects_prior_generation_normal_and_optimized(self):
        stale = copy.deepcopy(self.machine)
        index = stale["invariants"].index(NEW_INVARIANT)
        stale["invariants"][index] = OLD_INVARIANT
        stale["contract_digest_sha256"] = OLD_DIGEST
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "old-state-machine.json"
            path.write_text(json.dumps(stale, ensure_ascii=False, indent=2), encoding="utf-8")
            for optimized in (False, True):
                cmd = [sys.executable] + (["-O"] if optimized else []) + [str(A), "verify-machine", str(path)]
                run = subprocess.run(cmd, cwd=HERE, text=True, capture_output=True, check=False)
                with self.subTest(optimized=optimized):
                    self.assertEqual(run.returncode, 2)
                    self.assertIn("invariant list changed", run.stderr)


if __name__ == "__main__":
    unittest.main()
