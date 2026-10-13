from __future__ import annotations

import json
import unittest


TEST_MODULES = (
    "revenue.trusted_claim_policy.tests.test_trust",
    "revenue.trusted_claim_policy.tests.test_time",
    "revenue.trusted_claim_policy.tests.test_integrity",
)


def main() -> int:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite(loader.loadTestsFromName(name) for name in TEST_MODULES)
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    summary = {
        "operation": "COMMONS-TRUSTED-CLAIM-POLICY-KERNEL-ZMCR7K5-20260914",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "successful": result.wasSuccessful(),
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
