"""Synthetic equivalence and work-bound checks for inclusive bank overlaps."""
import copy
import itertools
import random
import unittest

from bank_check import audit


def claim(key, lo, hi, **extra):
    return dict(claim_id=key, message_ts="1000.000001", bank=[lo, hi], **extra)


def document(rows):
    return dict(snapshot_ts="2000.000000", claims=rows,
                coverage_note="Synthetic fixture; no real bank assignment.")


def exhaustive_conflicts(active):
    """Independent all-pairs reference, retaining the established report order."""
    result = []
    for left, right in itertools.combinations(active, 2):
        lo = max(left["bank"][0], right["bank"][0])
        hi = min(left["bank"][1], right["bank"][1])
        if lo <= hi:
            result.append(dict(left=left["claim_id"], right=right["claim_id"],
                               bank=[lo, hi]))
    return result


class CountingBank(list):
    """Count endpoint accesses rather than depending on a wall-clock threshold."""
    reads = 0

    def __getitem__(self, index):
        type(self).reads += 1
        return super().__getitem__(index)


class ScalingTests(unittest.TestCase):
    def assert_exhaustive(self, rows):
        source = document(rows)
        before = copy.deepcopy(source)
        result = audit(source)
        self.assertEqual(result["conflicts"], exhaustive_conflicts(result["active_claims"]))
        self.assertEqual(source, before)
        return result

    def test_large_disjoint_snapshot_uses_linear_endpoint_reads(self):
        count = 2048
        rows = [claim(str(i), 3 * i + 1, 3 * i + 2) for i in range(count)]
        for row in rows:
            row["bank"] = CountingBank(row["bank"])
        CountingBank.reads = 0
        result = audit(document(list(reversed(rows))))
        self.assertEqual(result["conflicts"], [])
        self.assertLess(CountingBank.reads, 20 * count)

    def test_long_interval_across_sparse_banks_is_not_skipped(self):
        count = 1024
        rows = [claim("outer", 1, 3 * count + 3)]
        rows.extend(claim(str(i), 3 * i + 2, 3 * i + 3) for i in range(count))
        for row in rows:
            row["bank"] = CountingBank(row["bank"])
        CountingBank.reads = 0
        result = audit(document(rows))
        self.assertEqual(len(result["conflicts"]), count)
        self.assertTrue(all(row["left"] == "outer" for row in result["conflicts"]))
        self.assertLess(CountingBank.reads, 30 * len(rows))

    def test_dense_snapshot_retains_every_pair_in_order(self):
        count = 128
        result = self.assert_exhaustive([claim(str(i), 1, 100) for i in range(count)])
        self.assertEqual(len(result["conflicts"]), count * (count - 1) // 2)

    def test_endpoints_nested_equal_starts_and_gaps(self):
        rows = [claim("z", 1, 10), claim("a", 1, 10), claim("inner", 2, 3),
                claim("touch", 10, 10), claim("next", 11, 20),
                claim("outer", 1, 30), claim("later", 40, 50)]
        result = self.assert_exhaustive(rows)
        self.assertIn(dict(left="a", right="touch", bank=[10, 10]), result["conflicts"])
        self.assertFalse(any(row["left"] == "touch" and row["right"] == "next"
                             for row in result["conflicts"]))

    def test_arbitrary_precision_banks(self):
        lo = 10 ** 90
        self.assert_exhaustive([claim("a", lo, lo + 1), claim("b", lo + 1, lo + 2),
                                claim("c", lo + 3, lo + 9)])

    def test_deterministic_random_snapshots_match_exhaustive_order(self):
        rng = random.Random(90210)
        for case in range(200):
            rows = []
            for index in range(rng.randrange(1, 81)):
                lo = rng.randrange(1, 1000)
                rows.append(claim(str(index), lo, lo + rng.randrange(300),
                                  phase=rng.choice(("claimed", "started", "completed"))))
            rng.shuffle(rows)
            with self.subTest(case=case):
                self.assert_exhaustive(rows)

    def test_shuffled_snapshots_keep_complete_report_identical(self):
        rows = [claim("a", 1, 5, label="same", operation_id="same"),
                claim("b", 4, 6, label="same", operation_id="same"),
                claim("c", 7, 9, phase="completed"), claim("d", 5, 8)]
        expected = audit(document(rows))
        for ordering in itertools.permutations(rows):
            self.assertEqual(audit(document(list(ordering))), expected)

    def test_supersession_retirement_and_blocked_records_preserved(self):
        rows = [claim("retired", 1, 100), claim("complete", 50, 60, phase="completed"),
                claim("replacement", 200, 210, supersedes=["retired", "complete"])]
        rows[-1]["message_ts"] = "1000.000002"
        result = self.assert_exhaustive(rows)
        self.assertEqual(result["superseded_claim_ids"], ["retired"])
        self.assertEqual(result["blocked_supersessions"],
                         [dict(old="complete", replacement="replacement")])
        self.assertEqual([row["claim_id"] for row in result["active_claims"]],
                         ["complete", "replacement"])

    def test_supersession_forks_and_operation_reuse_preserved(self):
        rows = [claim("old", 1, 100)]
        for key, lo in (("a", 10), ("b", 15)):
            row = claim(key, lo, lo + 10, supersedes=["old"], operation_id="same")
            row["message_ts"] = "1000.000002"
            rows.append(row)
        result = self.assert_exhaustive(rows)
        self.assertEqual(result["forks"], {"old": ["a", "b"]})
        self.assertEqual(result["reused_active_operation_ids"], {"same": ["a", "b"]})
        self.assertEqual(result["conflicts"], [dict(left="a", right="b", bank=[15, 20])])


if __name__ == "__main__":
    unittest.main()
