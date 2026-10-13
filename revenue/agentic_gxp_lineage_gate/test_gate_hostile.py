from __future__ import annotations

import copy
import hashlib
import json
import random
import unittest
from datetime import datetime, timedelta, timezone

from .fixture import DEFECTS, EVALUATED_AT, build_acceptance_batch, build_case, build_policy
from .gate import AUTHORITY, GateInputError, digest, evaluate, verify


def _readdress(case):
    core = copy.deepcopy(case)
    core.pop("event_id", None)
    case["event_id"] = digest(core)
    return case

class AgenticGxpLineageHostileTests(unittest.TestCase):
    def setUp(self):
        self.policy = build_policy()
        self.batch = build_acceptance_batch()

    def test_case_event_id_must_content_address_case(self):
        case = build_case(3)
        case["artifact"]["artifact_id"] = "tampered-after-address"
        with self.assertRaisesRegex(GateInputError, "content address"):
            evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)

    def test_future_case_capture_rejected(self):
        case = build_case(3)
        case["captured_at"] = "2026-09-13T09:17:00Z"
        _readdress(case)
        with self.assertRaises(GateInputError):
            evaluate(self.policy, self._one(case, captured="2026-09-13T09:17:00Z"), evaluated_at=EVALUATED_AT)

    def test_source_after_case_rejected(self):
        case = build_case(3)
        case["source_snapshots"][0]["captured_at"] = "2026-09-13T09:15:30Z"
        _readdress(case)
        with self.assertRaises(GateInputError):
            evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)

    def test_execution_time_nonmonotonic_rejected(self):
        case = build_case(3)
        case["execution"]["started_at"] = case["captured_at"]
        case["execution"]["completed_at"] = "2026-09-13T09:00:00Z"
        _readdress(case)
        with self.assertRaises(GateInputError):
            evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)

    def test_approval_before_completion_rejected(self):
        case = build_case(3)
        case["human_approval"]["approved_at"] = case["execution"]["started_at"]
        _readdress(case)
        with self.assertRaises(GateInputError):
            evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)

    def test_change_approval_after_execution_start_rejected(self):
        case = build_case(3)
        case["change_control"]["approved_at"] = case["execution"]["completed_at"]
        _readdress(case)
        with self.assertRaises(GateInputError):
            evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)

    def test_duplicate_source_identity_rejected(self):
        case = build_case(3)
        case["source_snapshots"].append(copy.deepcopy(case["source_snapshots"][0]))
        _readdress(case)
        with self.assertRaisesRegex(GateInputError, "duplicate dataset/snapshot"):
            evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)

    def test_duplicate_tool_id_rejected(self):
        case = build_case(3)
        case["execution"]["tools"].append(copy.deepcopy(case["execution"]["tools"][0]))
        _readdress(case)
        with self.assertRaisesRegex(GateInputError, "duplicate tool"):
            evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)

    def test_uppercase_digest_rejected(self):
        case = build_case(3)
        case["artifact"]["sha256"] = case["artifact"]["sha256"].upper()
        _readdress(case)
        with self.assertRaisesRegex(GateInputError, "lowercase sha256"):
            evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)

    def test_unknown_case_field_rejected(self):
        case = build_case(3)
        case["release_batch"] = True
        _readdress(case)
        with self.assertRaisesRegex(GateInputError, "wrong fields"):
            evaluate(self.policy, self._one(case), evaluated_at=EVALUATED_AT)

    def test_bool_not_accepted_as_integer_policy_age(self):
        policy = build_policy()
        policy["max_evidence_age_seconds"] = True
        with self.assertRaises(GateInputError):
            evaluate(policy, self._one(build_case(3)), evaluated_at=EVALUATED_AT)

    def test_tampered_manifest_breaks_verification(self):
        result = evaluate(self.policy, self.batch, evaluated_at=EVALUATED_AT)
        result["manifest"]["rows"][0]["status"] = "BATCH_RELEASED"
        self.assertFalse(verify(result, policy=self.policy, batch=self.batch))

    def test_self_consistent_rehashed_forgery_is_rejected(self):
        result = evaluate(self.policy, self.batch, evaluated_at=EVALUATED_AT)
        result["manifest"]["rows"][0]["status"] = "BATCH_RELEASED"

        def h(value):
            raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
            return hashlib.sha256(raw).hexdigest()

        result["receipt"]["manifest_sha256"] = h(result["manifest"])
        core = dict(result["receipt"])
        core.pop("receipt_sha256")
        result["receipt"]["receipt_sha256"] = h(core)
        self.assertFalse(verify(result, policy=self.policy, batch=self.batch))

    def test_source_authenticity_escalation_breaks_verification(self):
        result = evaluate(self.policy, self.batch, evaluated_at=EVALUATED_AT)
        result["receipt"]["source_authenticity_verified"] = True
        self.assertFalse(verify(result, policy=self.policy, batch=self.batch))

    def test_authority_escalation_flag_breaks_verification(self):
        result = evaluate(self.policy, self.batch, evaluated_at=EVALUATED_AT)
        result["receipt"]["production_release_authorized"] = True
        self.assertFalse(verify(result, policy=self.policy, batch=self.batch))

    def test_wrong_policy_or_batch_breaks_verification(self):
        result = evaluate(self.policy, self.batch, evaluated_at=EVALUATED_AT)
        p2 = copy.deepcopy(self.policy)
        p2["max_evidence_age_seconds"] = 3599
        self.assertFalse(verify(result, policy=p2, batch=self.batch))
        b2 = copy.deepcopy(self.batch)
        b2["capture_complete"] = False
        self.assertFalse(verify(result, policy=self.policy, batch=b2))

    def test_extra_receipt_authority_field_breaks_verification(self):
        result = evaluate(self.policy, self.batch, evaluated_at=EVALUATED_AT)
        result["receipt"]["batch_release_authorized"] = True
        self.assertFalse(verify(result, policy=self.policy, batch=self.batch))

    def _one(self, case, captured="2026-09-13T09:15:00Z"):
        return {
            "schema": self.batch["schema"],
            "capture_complete": True,
            "captured_at": captured,
            "cases": [case],
        }


if __name__ == "__main__":
    unittest.main()
