"""Independent offline chronology, verification and partition regressions.

Run from repository root:
  python -m unittest discover -s revenue/nm_ocs_tprm/tests -p 'test_tprm_contract_ibis93c.py' -v

TPRM_REVIEW_SOURCE selects an exact retained tprm.py for before/after review.
Fixtures are fictional. No network, credentials, external targets or live data.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import random
import unittest

SOURCE = Path(os.environ.get(
    "TPRM_REVIEW_SOURCE", str(Path(__file__).resolve().parents[1] / "tprm.py")
)).resolve()
spec = importlib.util.spec_from_file_location("_ibis93c_reviewed_tprm", SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load reviewed source: {SOURCE}")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def fixture(tenant="tenant-a", vendor="shared-vendor"):
    return {
        "schema": "tjlabs.nm-ocs-tprm.assessment.v1",
        "tenant": {"tenant_id": tenant, "display_name": f"Fictional {tenant}"},
        "vendor": {"vendor_id": vendor, "display_name": f"Fictional {vendor}"},
        "factors": {"data_sensitivity": 1, "privilege": 1,
                    "criticality": 1, "internet_exposure": 1},
        "controls": [
            {"framework": "SYNTHETIC", "control_id": "C1", "status": "UNKNOWN",
             "evidence_sha256": None, "note": "Fictional evidence not supplied."},
            {"framework": "SYNTHETIC", "control_id": "C2", "status": "GAP",
             "evidence_sha256": "b" * 64, "note": "Fictional documented gap."},
            {"framework": "SYNTHETIC", "control_id": "C3", "status": "SATISFIED",
             "evidence_sha256": "c" * 64, "note": "Fictional supporting record."},
        ],
        "monitoring_events": [
            {"event_id": "E1", "observed_at": "2026-09-19T00:00:00Z",
             "kind": "MANUAL_REVIEW", "severity": 0, "evidence_sha256": "a" * 64,
             "summary": "Fictional manual observation."}
        ],
        "assessment": {"as_of": "2026-09-19T00:00:00Z", "review_id": "R1",
                       "policy_id": "reference-v1"},
    }


def portfolio(records):
    return {"schema": "tjlabs.nm-ocs-tprm.portfolio.v1", "portfolio_id": "synthetic-portfolio",
            "assessments": records}


def set_path(value, path, replacement):
    parent = value
    for item in path[:-1]:
        parent = parent[item]
    parent[path[-1]] = copy.deepcopy(replacement)


def leaves(value, prefix=()):
    if type(value) is dict:
        for key, item in value.items():
            yield from leaves(item, prefix + (key,))
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from leaves(item, prefix + (index,))
    else:
        yield prefix, value


class ChronologyTests(unittest.TestCase):
    def test_submicrosecond_future_is_rejected(self):
        for width in range(7, 20):
            with self.subTest(fractional_digits=width):
                value = fixture()
                value["monitoring_events"][0]["observed_at"] = (
                    "2026-09-19T00:00:00." + "0" * (width - 1) + "1Z")
                with self.assertRaises(engine.ValidationError):
                    engine.compile_assessment(value)

    def test_fractional_grid_uses_all_digits(self):
        # Independent integer oracle, not the production datetime helper.
        fractions = ["", "0", "0000000", "0000001", "0000002", "000001",
                     "1", "10", "1000000000000000000", "1234567890123456789",
                     "1234567890123456790", "9999999999999999999"]
        for cutoff, observed in itertools.product(fractions, repeat=2):
            with self.subTest(cutoff=cutoff, observed=observed):
                stamp = lambda f: "2026-09-19T00:00:00" + (("." + f) if f else "") + "Z"
                value = fixture()
                value["assessment"]["as_of"] = stamp(cutoff)
                value["monitoring_events"][0]["observed_at"] = stamp(observed)
                future = int(observed.ljust(19, "0")) > int(cutoff.ljust(19, "0"))
                if future:
                    with self.assertRaises(engine.ValidationError):
                        engine.compile_assessment(value)
                else:
                    packet = engine.compile_assessment(value)
                    self.assertTrue(engine.verify_assessment_packet(packet))
                    self.assertEqual(packet["source"]["assessment"]["as_of"], stamp(cutoff))
                    self.assertEqual(packet["source"]["monitoring_events"][0]["observed_at"], stamp(observed))

    def test_calendar_crossings_and_fractional_boundaries(self):
        for earlier, later in [
            ("2026-09-18T23:59:59.9999999999999999999Z", "2026-09-19T00:00:00Z"),
            ("2024-02-29T23:59:59.9Z", "2024-03-01T00:00:00Z"),
            ("2025-12-31T23:59:59Z", "2026-01-01T00:00:00Z"),
        ]:
            for future in (False, True):
                with self.subTest(earlier=earlier, future=future):
                    value = fixture()
                    value["monitoring_events"][0]["observed_at"] = later if future else earlier
                    value["assessment"]["as_of"] = earlier if future else later
                    if future:
                        with self.assertRaises(engine.ValidationError):
                            engine.compile_assessment(value)
                    else:
                        self.assertTrue(engine.verify_assessment_packet(engine.compile_assessment(value)))

    def test_noncontract_timestamp_spellings_rejected_at_both_locations(self):
        invalid = ["20260919T000000Z", "2026-W38-6T00:00:00Z", "2026-09-19X00:00:00Z",
                   "2026-09-19T00:00Z", "2026-09-19T00:00:00,1Z", "2026-09-19T00:00:00.Z",
                   "2026-02-30T00:00:00Z", "2026-09-19T00:00:60Z",
                   "2026-09-19T00:00:00.12345678901234567890Z"]
        for path, stamp in itertools.product(
                [("assessment", "as_of"), ("monitoring_events", 0, "observed_at")], invalid):
            with self.subTest(path=path, stamp=stamp):
                value = fixture()
                set_path(value, path, stamp)
                with self.assertRaises(engine.ValidationError):
                    engine.compile_assessment(value)

    def test_lowercase_t_retained_without_normalizing_evidence(self):
        value = fixture()
        stamp = "2026-09-19t00:00:00.0000000000000000000Z"
        value["assessment"]["as_of"] = stamp
        value["monitoring_events"][0]["observed_at"] = stamp
        packet = engine.compile_assessment(value)
        self.assertEqual(packet["source"]["assessment"]["as_of"], stamp)
        self.assertTrue(engine.verify_assessment_packet(packet))

    def test_future_evidence_cannot_enter_a_portfolio(self):
        records = [fixture("tenant-a"), fixture("tenant-b")]
        records[1]["monitoring_events"][0]["observed_at"] = "2026-09-19T00:00:00.0000001Z"
        with self.assertRaises(engine.ValidationError):
            engine.compile_portfolio(portfolio(records))


class VerifierContractTests(unittest.TestCase):
    def test_enum_container_values_raise_validation_error(self):
        for path, value in itertools.product(
                [("controls", 0, "status"), ("monitoring_events", 0, "kind")],
                [[], {}, ["UNKNOWN"], {"value": "MANUAL_REVIEW"}]):
            with self.subTest(path=path, value=value):
                source = fixture()
                set_path(source, path, value)
                with self.assertRaises(engine.ValidationError):
                    engine.compile_assessment(source)

    def test_malformed_source_is_false_for_assessment_and_portfolio(self):
        for path, value in itertools.product(
                [("controls", 0, "status"), ("monitoring_events", 0, "kind"),
                 ("tenant", "display_name"), ("assessment", "as_of")],
                [None, [], {}, [0], {"key": 1}, False, 7]):
            with self.subTest(path=path, value=value):
                a = engine.compile_assessment(fixture())
                set_path(a["source"], path, value)
                self.assertIs(engine.verify_assessment_packet(a), False)
                p = engine.compile_portfolio(portfolio([fixture()]))
                set_path(p["assessments"][0]["source"], path, value)
                self.assertIs(engine.verify_portfolio_packet(p), False)

    def test_nonserializable_output_is_false_not_exception(self):
        for field in ("reference_tier", "control_status_counts", "findings", "authority", "receipt_sha256"):
            for bad in ({"unexpected-set"}, float("nan"), "\ud800"):
                with self.subTest(field=field, type=type(bad).__name__):
                    a = engine.compile_assessment(fixture())
                    a[field] = bad
                    self.assertIs(engine.verify_assessment_packet(a), False)
        p = engine.compile_portfolio(portfolio([fixture()]))
        for field in ("authority", "tenant_roots", "portfolio_root_sha256"):
            with self.subTest(portfolio_field=field):
                candidate = copy.deepcopy(p)
                candidate[field] = {"unexpected-set"}
                self.assertIs(engine.verify_portfolio_packet(candidate), False)

    def test_recursive_packet_returns_false(self):
        a = engine.compile_assessment(fixture())
        a["findings"] = a
        self.assertIs(engine.verify_assessment_packet(a), False)
        p = engine.compile_portfolio(portfolio([fixture()]))
        p["tenant_roots"] = p
        self.assertIs(engine.verify_portfolio_packet(p), False)

    def test_nonstring_source_keys_are_validation_errors(self):
        value = fixture()
        value[None] = 1
        value[3] = 2
        with self.assertRaises(engine.ValidationError):
            engine.compile_assessment(value)
        packet = engine.compile_assessment(fixture())
        packet["source"] = value
        self.assertIs(engine.verify_assessment_packet(packet), False)

    def test_each_retained_leaf_is_receipt_bound(self):
        a = engine.compile_assessment(fixture())
        for path, old in leaves(a):
            with self.subTest(path=path):
                changed = copy.deepcopy(a)
                replacement = not old if type(old) is bool else (old + 1 if type(old) is int else "changed")
                set_path(changed, path, replacement)
                self.assertIs(engine.verify_assessment_packet(changed), False)
        p = engine.compile_portfolio(portfolio([fixture("tenant-a"), fixture("tenant-b")]))
        for path, old in leaves(p):
            with self.subTest(portfolio_path=path):
                changed = copy.deepcopy(p)
                replacement = not old if type(old) is bool else (old + 1 if type(old) is int else "changed")
                set_path(changed, path, replacement)
                self.assertIs(engine.verify_portfolio_packet(changed), False)


class PortfolioCompositionTests(unittest.TestCase):
    def test_assessment_order_does_not_change_portfolio(self):
        records = [fixture(t, v) for t in ("tenant-a", "tenant-b") for v in ("vendor-a", "vendor-b")]
        expected = engine.compile_portfolio(portfolio(records))
        for perm in itertools.permutations(records):
            with self.subTest(order=[(x["tenant"]["tenant_id"], x["vendor"]["vendor_id"]) for x in perm]):
                self.assertEqual(engine.compile_portfolio(portfolio(list(perm))), expected)

    def test_control_and_event_order_are_independent_of_input_order(self):
        value = fixture()
        extra = copy.deepcopy(value["monitoring_events"][0]); extra["event_id"] = "E2"
        value["monitoring_events"].append(extra)
        expected = engine.compile_assessment(value)
        for controls, events in itertools.product(itertools.permutations(value["controls"]),
                                                  itertools.permutations(value["monitoring_events"])):
            candidate = copy.deepcopy(value)
            candidate["controls"] = list(controls); candidate["monitoring_events"] = list(events)
            self.assertEqual(engine.compile_assessment(candidate), expected)

    def test_only_changed_tenant_partition_changes(self):
        rng = random.Random(9303)
        for iteration in range(64):
            records = [fixture(f"tenant-{t}", f"vendor-{v}") for t in range(3) for v in range(2)]
            old = engine.compile_portfolio(portfolio(records))
            changed = copy.deepcopy(records)
            index = rng.randrange(len(changed))
            changed[index]["controls"][0]["note"] = f"Fictional update {iteration}: λ / 🧪"
            new = engine.compile_portfolio(portfolio(changed))
            changed_tenant = changed[index]["tenant"]["tenant_id"]
            for before, after in zip(old["tenant_roots"], new["tenant_roots"]):
                with self.subTest(iteration=iteration, tenant=before["tenant_id"]):
                    self.assertEqual(before["tenant_root_sha256"] == after["tenant_root_sha256"],
                                     before["tenant_id"] != changed_tenant)
            self.assertNotEqual(old["portfolio_root_sha256"], new["portfolio_root_sha256"])

    def test_tenant_roots_match_independent_digest_calculation(self):
        records = [fixture("tenant-b", "v2"), fixture("tenant-a", "v2"), fixture("tenant-a", "v1")]
        result = engine.compile_portfolio(portfolio(records))
        for root in result["tenant_roots"]:
            members = [p for p in result["assessments"] if p["source"]["tenant"]["tenant_id"] == root["tenant_id"]]
            members.sort(key=lambda p: p["source"]["vendor"]["vendor_id"])
            receipts = [p["receipt_sha256"] for p in members]
            self.assertEqual(root["assessment_receipts"], receipts)
            self.assertEqual(root["tenant_root_sha256"], digest(receipts))
        core = {k: v for k, v in result.items() if k != "portfolio_root_sha256"}
        self.assertEqual(result["portfolio_root_sha256"], digest(core))

    def test_missing_evidence_and_documented_gaps_stay_distinct(self):
        result = engine.compile_assessment(fixture())
        self.assertEqual(result["control_status_counts"], {"GAP": 1, "SATISFIED": 1, "UNKNOWN": 1})
        self.assertEqual({f["kind"] for f in result["findings"]}, {"CONTROL_UNKNOWN", "CONTROL_GAP"})
        self.assertIsNone(result["source"]["controls"][0]["evidence_sha256"])
        self.assertTrue(all(value is False for value in result["authority"].values()))

    def test_duplicate_identity_is_rejected_and_cross_tenant_reuse_preserved(self):
        one = fixture()
        with self.assertRaises(engine.ValidationError):
            engine.compile_portfolio(portfolio([one, copy.deepcopy(one)]))
        distinct = fixture("tenant-b")
        result = engine.compile_portfolio(portfolio([one, distinct]))
        self.assertEqual(len(result["assessments"]), 2)
        self.assertEqual(len(result["tenant_roots"]), 2)
        self.assertTrue(engine.verify_portfolio_packet(result))

    def test_source_and_result_mutations_are_detached(self):
        value = portfolio([fixture("tenant-a"), fixture("tenant-b")])
        snapshot = copy.deepcopy(value)
        result = engine.compile_portfolio(value)
        self.assertEqual(value, snapshot)
        result["assessments"][0]["source"]["controls"][0]["note"] = "changed result"
        self.assertEqual(value, snapshot)
        second = engine.compile_portfolio(value)
        value["assessments"][0]["controls"][0]["note"] = "changed input"
        self.assertTrue(engine.verify_portfolio_packet(second))

    def test_all_reference_factor_combinations(self):
        keys = ("data_sensitivity", "privilege", "criticality", "internet_exposure")
        for values in itertools.product(range(4), repeat=4):
            with self.subTest(values=values):
                value = fixture(); value["factors"] = dict(zip(keys, values))
                total = sum(values)
                expected = "TIER_1" if total >= 10 or (3 in values and total >= 8) else (
                    "TIER_2" if total >= 6 else "TIER_3")
                packet = engine.compile_assessment(value)
                self.assertEqual(packet["reference_tier"], expected)
                self.assertTrue(engine.verify_assessment_packet(packet))
                self.assertTrue(all(v is False for v in packet["authority"].values()))


if __name__ == "__main__":
    unittest.main()
