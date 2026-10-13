from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "csu_malt_expansion_independent_golden",
    HERE / "csu_malt_expansion.py",
)
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)

FIXTURE = HERE / "fixtures" / "csu_80_submissions.json"
MANIFEST = HERE / "fixtures" / "manifest.json"

# Independently frozen from the accepted 130-job projection on the current
# merged product.  This literal is intentionally not stored in, or derived
# from, manifest["package_methods"], because that table also drives process().
FROZEN_JOB_PROJECTION_SHA256 = (
    "3371c84ed5f3b85115a74fc9773555912010f1dc8562b87a442f875bc011b5bf"
)

JOB_FIELDS = (
    "job_id",
    "sample_id",
    "method_id",
    "method_version",
    "unit",
    "route",
    "week_route",
    "qc_batch",
)


def job_projection_sha256(ledger) -> str:
    rows = [
        {field: ledger.jobs[job_id][field] for field in JOB_FIELDS}
        for job_id in sorted(ledger.jobs)
    ]
    payload = (
        json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class CSUIndependentGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows, cls.manifest = M.load(FIXTURE, MANIFEST)

    def run_with_manifest(self, manifest):
        rows = copy.deepcopy(self.rows)
        ledger, statuses, _ = M.run(rows, manifest)
        # Existing product acceptance must still pass before this independent
        # oracle is consulted; otherwise the test would not isolate the gap.
        M.verify(rows, manifest, ledger, statuses)
        return ledger, statuses

    def test_frozen_130_job_projection_digest(self) -> None:
        ledger, statuses = self.run_with_manifest(copy.deepcopy(self.manifest))
        self.assertEqual(
            statuses,
            {
                M.CURRENT: 60,
                M.NEXT: 8,
                M.DUP: 4,
                M.UNSUP: 4,
                M.MISS: 4,
            },
        )
        self.assertEqual(len(ledger.jobs), 130)
        self.assertEqual(job_projection_sha256(ledger), FROZEN_JOB_PROJECTION_SHA256)

    def test_coherent_method_version_drift_evades_self_verifier_but_breaks_golden(self) -> None:
        drifted = copy.deepcopy(self.manifest)
        drifted["package_methods"]["CORE"][0]["method_version"] = "2026.99"

        ledger, statuses = self.run_with_manifest(drifted)

        # Same cardinality, status counts, IDs, routes, and manifest-derived
        # method-id expansion still satisfy the current self-consistency gate.
        self.assertEqual(statuses[M.CURRENT], 60)
        self.assertEqual(statuses[M.NEXT], 8)
        self.assertEqual(len(ledger.jobs), 130)
        self.assertEqual(
            sum(job["route"] == "THIRD_PARTY" for job in ledger.jobs.values()),
            6,
        )

        # The independent accepted truth catches the coherent version drift.
        self.assertNotEqual(job_projection_sha256(ledger), FROZEN_JOB_PROJECTION_SHA256)


if __name__ == "__main__":
    unittest.main(verbosity=2)
