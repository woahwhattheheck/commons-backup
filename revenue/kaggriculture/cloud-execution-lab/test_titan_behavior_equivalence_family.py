#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from titan_behavior_equivalence_test_support import *

class FamilyPreflightTests(unittest.TestCase):
    def test_unique_executables_pass_before_results(self) -> None:
        report = gate.preflight_family(family_raw())
        self.assertEqual("PASS", report["verdict"])
        self.assertFalse(report["outcomes_consumed"])
        self.assertEqual(2, report["unique_executable_identities"])
        self.assertEqual(gate.sha256_json({k: v for k, v in report.items() if k != "receipt_sha256"}), report["receipt_sha256"])

    def test_duplicate_exact_executables_are_refused_pre_result(self) -> None:
        family = family_raw(closures=(digest("a"), digest("a")))
        report = gate.preflight_family(family)
        self.assertEqual("REFUSED_DUPLICATE_EXECUTABLES", report["verdict"])
        group = report["duplicate_executable_groups"][0]
        self.assertEqual(["alpha", "beta"], group["all_candidate_ids"])
        self.assertTrue(group["safe_registration_deduplication"])
        self.assertFalse(report["familywise_semantics"]["retroactive_multiplicity_reduction_allowed"])

    def test_same_closure_different_entrypoints_are_not_exact_aliases(self) -> None:
        family = family_raw(closures=(digest("a"), digest("a")))
        family["candidates"][1]["entrypoint"] = "main.py::other_agent"
        self.assertEqual("PASS", gate.preflight_family(family)["verdict"])

    def test_duplicate_candidate_id_is_rejected(self) -> None:
        family = family_raw()
        family["candidates"][1]["candidate_id"] = "alpha"
        with self.assertRaisesRegex(gate.BehaviorGateError, "duplicate candidate_id"):
            gate.validate_family(family)

    def test_same_archive_with_contradictory_closure_is_rejected(self) -> None:
        family = family_raw(archives=(digest("c"), digest("c")))
        with self.assertRaisesRegex(gate.BehaviorGateError, "contradictory executable"):
            gate.validate_family(family)

    def test_family_digest_is_order_invariant_but_candidate_identity_bound(self) -> None:
        left = family_raw()
        right = copy.deepcopy(left)
        right["candidates"].reverse()
        self.assertEqual(gate.validate_family(left).family_sha256, gate.validate_family(right).family_sha256)
        right["candidates"][0]["archive_sha256"] = digest("f")
        self.assertNotEqual(gate.validate_family(left).family_sha256, gate.validate_family(right).family_sha256)

    def test_declared_family_digest_must_match(self) -> None:
        family = family_raw()
        family["family_sha256"] = digest("f")
        with self.assertRaisesRegex(gate.BehaviorGateError, "family_sha256 mismatch"):
            gate.validate_family(family)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_constants(self) -> None:
        with self.assertRaisesRegex(gate.BehaviorGateError, "duplicate JSON object key"):
            gate.loads_strict('{"a":1,"a":2}')
        with self.assertRaisesRegex(gate.BehaviorGateError, "non-finite JSON constant"):
            gate.loads_strict('{"a":NaN}')

    def test_closure_digest_is_derived_from_complete_member_manifest(self) -> None:
        family = family_raw()
        family["candidates"][0]["executable_closure_sha256"] = digest("f")
        with self.assertRaisesRegex(gate.BehaviorGateError, "executable_closure_sha256 mismatch"):
            gate.validate_family(family)
        family = family_raw()
        family["candidates"][0]["executable_closure"]["complete"] = False
        with self.assertRaisesRegex(gate.BehaviorGateError, "complete must be exactly true"):
            gate.validate_family(family)

    def test_closure_rejects_unsafe_or_duplicate_member_paths(self) -> None:
        family = family_raw()
        member = family["candidates"][0]["executable_closure"]["members"][0]
        member["path"] = "../main.py"
        with self.assertRaisesRegex(gate.BehaviorGateError, "safe canonical relative path"):
            gate.validate_family(family)
        family = family_raw()
        closure = family["candidates"][0]["executable_closure"]
        closure["members"].append(copy.deepcopy(closure["members"][0]))
        with self.assertRaisesRegex(gate.BehaviorGateError, "duplicate executable closure member"):
            gate.validate_family(family)

    def test_entrypoint_must_be_inside_the_declared_closure(self) -> None:
        family = family_raw()
        family["candidates"][0]["entrypoint"] = "absent.py::agent"
        with self.assertRaisesRegex(gate.BehaviorGateError, "absent from executable closure"):
            gate.validate_family(family)

    def test_invocation_contract_is_part_of_exact_executable_identity(self) -> None:
        family = family_raw(closures=(digest("a"), digest("a")))
        family["candidates"][1]["invocation_sha256"] = digest("7")
        self.assertEqual("PASS", gate.preflight_family(family)["verdict"])

