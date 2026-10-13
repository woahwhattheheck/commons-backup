"""Tests of the test driver, using explicit test doubles and injected defects."""
import copy
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cirrus_identity_conformance_tested", ROOT / "conformance.py")
C = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = C
SPEC.loader.exec_module(C)


def test_double(data, defect=None):
    """A deliberately small test double; never used as a production mapper."""
    grouped = {}
    for row in data["records"]:
        grouped.setdefault(C.key(row), []).append(row)
    result = C.Projection()
    for index, (key, rows) in enumerate(sorted(grouped.items())):
        cid = C.encode(key)
        if defect == "unstable":
            cid = "position-" + str(index)
        if defect == "delimiter":
            cid = ":".join(key)
        if defect == "unicode":
            import unicodedata
            cid = unicodedata.normalize("NFC", cid)
        result.records[key] = cid
        result.retained[key] = tuple(sorted({C.encode(row["payload"]) for row in rows}))
        if defect == "last_row":
            result.retained[key] = (C.encode(rows[-1]["payload"]),)
    for query in data["references"]:
        candidates = [k for k in grouped if all(k[("origin", "kind", "local_id", "revision").index(field)] == value
                                               for field, value in query["target"].items())]
        result.references[query["id"]] = ()
        if defect == "guess" and candidates:
            candidates = candidates[:1]
        if len(candidates) == 1 and len(result.retained[candidates[0]]) == 1:
            result.references[query["id"]] = (result.records[candidates[0]],)
        else:
            result.diagnostics += ("unresolved:" + query["id"],)
    for key, rows in grouped.items():
        if len(result.retained[key]) > 1:
            result.diagnostics += ("conflict:" + C.encode(key),)
    if defect == "drop_payload":
        result.retained = {}
    if defect == "mint":
        for query in data["references"]:
            if not result.references[query["id"]]:
                result.references[query["id"]] = ("manufactured",)
    return result


class DriverTests(unittest.TestCase):
    def test_positive_control(self):
        report = C.run(test_double)
        self.assertEqual(report["failed"], 0, report)
        self.assertEqual(report["passed"], 8)

    def test_unstable_ids_are_detected(self):
        report = C.run(lambda d: test_double(d, "unstable"))
        row = next(x for x in report["cases"] if x["case"] == "unrelated_extension")
        self.assertEqual(row["status"], "FAIL")
        self.assertIn("re-keyed", row["detail"])

    def test_last_row_wins_is_detected(self):
        report = C.run(lambda d: test_double(d, "last_row"))
        row = next(x for x in report["cases"] if x["case"] == "duplicate_conflict")
        self.assertEqual(row["status"], "FAIL")

    def test_delimiter_collision_is_detected(self):
        report = C.run(lambda d: test_double(d, "delimiter"))
        row = next(x for x in report["cases"] if x["case"] == "original_spelling")
        self.assertEqual(row["status"], "FAIL")

    def test_unicode_collapse_is_detected(self):
        report = C.run(lambda d: test_double(d, "unicode"))
        row = next(x for x in report["cases"] if x["case"] == "original_spelling")
        self.assertEqual(row["status"], "FAIL")

    def test_unqualified_guess_is_detected(self):
        report = C.run(lambda d: test_double(d, "guess"))
        row = next(x for x in report["cases"] if x["case"] == "unqualified_collision")
        self.assertEqual(row["status"], "FAIL")

    def test_missing_payload_is_detected(self):
        report = C.run(lambda d: test_double(d, "drop_payload"))
        self.assertGreater(report["failed"], 0)

    def test_manufactured_reference_is_detected(self):
        report = C.run(lambda d: test_double(d, "mint"))
        row = next(x for x in report["cases"] if x["case"] == "missing_target")
        self.assertEqual(row["status"], "FAIL")

    def test_exceptions_never_pass(self):
        def broken(data):
            raise ValueError("target rejected everything")
        report = C.run(broken)
        self.assertEqual(report["passed"], 0)
        self.assertEqual(report["failed"], 8)
        self.assertTrue(all(x["error_type"] == "ValueError" for x in report["cases"]))

    def test_repeatable_and_nonmutating(self):
        data = C.fixture()
        before = copy.deepcopy(data)
        C.baseline(test_double, data)
        self.assertEqual(data, before)
        self.assertEqual(C.run(test_double), C.run(test_double))

    def test_explicit_failure_survives_optimized_python(self):
        with self.assertRaises(AssertionError):
            C._require(False, "must not disappear under -O")


if __name__ == "__main__":
    unittest.main()
