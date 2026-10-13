import importlib.util
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("erdos688_audit", HERE / "audit.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load audit.py")
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def test_primes(self):
        self.assertEqual(audit.primes_upto(20), (2, 3, 5, 7, 11, 13, 17, 19))

    def test_capacity_obstruction(self):
        self.assertLess(audit.capacity_upper_bound(10, (3, 5, 7)), 10)
        self.assertFalse(audit.can_cover(10, (3, 5, 7))[0])

    def test_pruned_solver_matches_brute_oracle(self):
        for n in range(2, 13):
            ps = audit.primes_upto(n)
            for i in range(len(ps)):
                self.assertEqual(
                    audit.can_cover(n, ps[i:])[0],
                    audit.brute_force_can_cover(n, ps[i:]),
                    (n, ps[i:]),
                )

    def test_known_critical_suffixes(self):
        self.assertEqual(audit.critical_prime(43)[0], 3)
        self.assertEqual(audit.critical_prime(66)[0], 2)
        self.assertEqual(audit.critical_prime(67)[0], 3)

    def test_small_receipt_digest(self):
        self.assertEqual(
            audit.build_receipt(2, 20)["mathematical_rows_sha256"],
            "29fac24ef99eac3eb79cba6b26444a9056d40bb18ed4bf74bf1257be33e2725f",
        )


if __name__ == "__main__":
    unittest.main()
