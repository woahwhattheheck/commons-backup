import copy
import json
import pathlib
import sys
import unittest

from botocore.exceptions import ClientError

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aws_agent import (
    ContractError,
    _canonical_storage_json,
    _decode_stored,
    _deliver_review,
    _existing,
    _parse_s3_event,
    _recover_pending_review,
    _review_body,
    _source_ref,
)
from prooflens import ALGORITHM, decide, sha256_json


def s3_event(*, bucket="prooflens", key="current/unit%201.png", version="v-current"):
    return {
        "Records": [
            {
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": key, "versionId": version},
                },
            }
        ]
    }


def valid_evidence(*, source_ref="s3://prooflens/baseline/x|s3://prooflens/current/x", changed=0.5):
    semantic = {
        "algorithm": ALGORITHM,
        "source_ref": source_ref,
        "baseline_sha256": "a" * 64,
        "current_sha256": "b" * 64,
        "width": 640,
        "height": 480,
        "changed_fraction": float(changed),
        "edge_delta": 0.2 if changed >= 0.025 else 0.0,
        "mean_delta": 20.0 if changed >= 0.025 else 0.0,
        "quality_score": 0.9,
        "alignment_confidence": 0.8,
        "opencv_version": "5.0.0",
    }
    return {**semantic, "event_id": sha256_json(semantic)}


def stored_row(*, evidence=None, receipt=None, delivery="RECORDED", event_key=None):
    evidence = evidence or valid_evidence()
    receipt = receipt or decide(evidence).to_dict()
    return {
        "event_id": {"S": event_key or evidence["event_id"]},
        "evidence_json": {"S": _canonical_storage_json(evidence)},
        "receipt_json": {"S": _canonical_storage_json(receipt)},
        "delivery": {"S": delivery},
    }


def reseal_receipt(receipt, **changes):
    forged = {**receipt, **changes}
    unsigned = {key: value for key, value in forged.items() if key != "receipt_sha256"}
    forged["receipt_sha256"] = sha256_json(unsigned)
    return forged


class Bomb:
    def __getattr__(self, name):
        raise AssertionError(f"unexpected external call: {name}")


class StaticDdb:
    def __init__(self, row):
        self.row = row

    def get_item(self, **kwargs):
        return {"Item": copy.deepcopy(self.row)}


class RecordingSqs:
    def __init__(self):
        self.messages = []

    def send_message(self, **kwargs):
        self.messages.append(copy.deepcopy(kwargs))
        return {"MessageId": "fixture-message"}


class AlreadyQueuedDdb(StaticDdb):
    def update_item(self, **kwargs):
        raise ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": "already queued"}},
            "UpdateItem",
        )


class AwsContractTests(unittest.TestCase):
    def test_event_binds_bucket_key_and_version(self):
        self.assertEqual(
            _parse_s3_event(s3_event(), "prooflens"),
            ("prooflens", "current/unit 1.png", "v-current"),
        )

    def test_wrong_bucket_rejected(self):
        with self.assertRaisesRegex(ContractError, "bucket"):
            _parse_s3_event(s3_event(bucket="other"), "prooflens")

    def test_non_current_prefix_rejected(self):
        with self.assertRaisesRegex(ContractError, "current"):
            _parse_s3_event(s3_event(key="baseline/unit.png"), "prooflens")

    def test_missing_current_version_rejected(self):
        event = s3_event()
        del event["Records"][0]["s3"]["object"]["versionId"]
        with self.assertRaisesRegex(ContractError, "versionId"):
            _parse_s3_event(event, "prooflens")

    def test_empty_current_version_rejected(self):
        with self.assertRaisesRegex(ContractError, "versionId"):
            _parse_s3_event(s3_event(version=""), "prooflens")

    def test_multiple_records_rejected(self):
        event = s3_event()
        event["Records"].append(event["Records"][0])
        with self.assertRaisesRegex(ContractError, "exactly one"):
            _parse_s3_event(event, "prooflens")

    def test_missing_records_rejected(self):
        with self.assertRaises(ContractError):
            _parse_s3_event({"unrelated": []}, "prooflens")

    def test_source_ref_preserves_exact_object_versions(self):
        baseline = {"version_id": "b-17", "etag": "beef"}
        current = {"version_id": "c-42", "etag": "cafe"}
        ref = _source_ref("bucket", "baseline/x.png", baseline, "current/x.png", current)
        self.assertIn("versionId=b-17", ref)
        self.assertIn("versionId=c-42", ref)
        self.assertIn("etag=beef", ref)
        self.assertIn("etag=cafe", ref)

    def test_review_message_cannot_authorize_external_action(self):
        evidence = {"event_id": "a" * 64, "source_ref": "s3://example"}
        receipt = {
            "decision": "REQUEST_HUMAN_REVIEW",
            "reason_codes": ["CHANGED_FRACTION_THRESHOLD"],
            "receipt_sha256": "b" * 64,
        }
        body = _review_body(evidence, receipt)
        self.assertIs(body["external_action_authorized"], False)
        self.assertEqual(body["event_id"], evidence["event_id"])

    def test_valid_stored_row_recompiles_before_replay(self):
        evidence = valid_evidence()
        row = stored_row(evidence=evidence)
        decoded = _decode_stored(row, expected_event_id=evidence["event_id"])
        self.assertEqual(decoded["evidence"], evidence)
        self.assertEqual(decoded["receipt"], decide(evidence).to_dict())
        self.assertEqual(decoded["delivery"], "RECORDED")
        self.assertIs(decoded["replay"], True)

    def test_stored_partition_key_must_match_query(self):
        evidence = valid_evidence()
        row = stored_row(evidence=evidence, event_key="c" * 64)
        with self.assertRaisesRegex(RuntimeError, "partition key"):
            _decode_stored(row, expected_event_id=evidence["event_id"])

    def test_stored_evidence_event_must_match_query(self):
        expected = valid_evidence(source_ref="s3://expected")
        other = valid_evidence(source_ref="s3://other")
        row = stored_row(evidence=other, event_key=expected["event_id"])
        with self.assertRaisesRegex(RuntimeError, "event_id"):
            _decode_stored(row, expected_event_id=expected["event_id"])

    def test_resealed_wrong_decision_is_rejected(self):
        evidence = valid_evidence()
        genuine = decide(evidence).to_dict()
        forged = reseal_receipt(genuine, decision="NO_ACTION", reason_codes=["BELOW_REVIEW_THRESHOLDS"])
        row = stored_row(evidence=evidence, receipt=forged)
        with self.assertRaisesRegex(RuntimeError, "does not recompile"):
            _decode_stored(row, expected_event_id=evidence["event_id"])

    def test_resealed_wrong_policy_is_rejected(self):
        evidence = valid_evidence()
        genuine = decide(evidence).to_dict()
        forged = reseal_receipt(genuine, policy_id="d" * 64)
        row = stored_row(evidence=evidence, receipt=forged)
        with self.assertRaisesRegex(RuntimeError, "does not recompile"):
            _decode_stored(row, expected_event_id=evidence["event_id"])

    def test_resealed_external_authority_is_rejected(self):
        evidence = valid_evidence()
        genuine = decide(evidence).to_dict()
        forged = reseal_receipt(genuine, external_action_authorized=True)
        row = stored_row(evidence=evidence, receipt=forged)
        with self.assertRaisesRegex(RuntimeError, "does not recompile"):
            _decode_stored(row, expected_event_id=evidence["event_id"])

    def test_corrupted_evidence_is_rejected(self):
        evidence = valid_evidence()
        corrupted = dict(evidence)
        corrupted["changed_fraction"] = 0.1
        row = stored_row(evidence=corrupted, receipt=decide(evidence).to_dict(), event_key=evidence["event_id"])
        with self.assertRaisesRegex(RuntimeError, "invalid evidence"):
            _decode_stored(row, expected_event_id=evidence["event_id"])

    def test_numeric_alias_cannot_claim_writer_canonical_evidence(self):
        evidence = valid_evidence(changed=0.0)
        row = stored_row(evidence=evidence)
        aliased = dict(evidence)
        aliased["changed_fraction"] = 0
        row["evidence_json"]["S"] = _canonical_storage_json(aliased)
        with self.assertRaisesRegex(RuntimeError, "normalized writer form"):
            _decode_stored(row, expected_event_id=evidence["event_id"])

    def test_unknown_row_field_is_rejected(self):
        evidence = valid_evidence()
        row = stored_row(evidence=evidence)
        row["unexpected"] = {"S": "x"}
        with self.assertRaisesRegex(RuntimeError, "keys"):
            _decode_stored(row, expected_event_id=evidence["event_id"])

    def test_non_string_attribute_value_is_rejected(self):
        evidence = valid_evidence()
        row = stored_row(evidence=evidence)
        row["delivery"] = {"N": "1"}
        with self.assertRaisesRegex(RuntimeError, "DynamoDB string"):
            _decode_stored(row, expected_event_id=evidence["event_id"])

    def test_noncanonical_stored_json_is_rejected(self):
        evidence = valid_evidence()
        row = stored_row(evidence=evidence)
        row["evidence_json"]["S"] = json.dumps(evidence, indent=2, sort_keys=True)
        with self.assertRaisesRegex(RuntimeError, "not canonical"):
            _decode_stored(row, expected_event_id=evidence["event_id"])

    def test_unknown_delivery_state_is_rejected(self):
        evidence = valid_evidence()
        row = stored_row(evidence=evidence, delivery="MAYBE_QUEUED")
        with self.assertRaisesRegex(RuntimeError, "delivery state"):
            _decode_stored(row, expected_event_id=evidence["event_id"])

    def test_review_queued_requires_review_receipt(self):
        evidence = valid_evidence(changed=0.0)
        self.assertEqual(decide(evidence).decision, "NO_ACTION")
        row = stored_row(evidence=evidence, delivery="REVIEW_QUEUED")
        with self.assertRaisesRegex(RuntimeError, "REVIEW_QUEUED"):
            _decode_stored(row, expected_event_id=evidence["event_id"])

    def test_existing_uses_query_event_as_independent_binding(self):
        evidence = valid_evidence()
        other = valid_evidence(source_ref="s3://other")
        poisoned = stored_row(evidence=other, event_key=evidence["event_id"])
        with self.assertRaisesRegex(RuntimeError, "event_id"):
            _existing(StaticDdb(poisoned), "table", evidence["event_id"])

    def test_pending_recovery_revalidates_before_any_queue_call(self):
        evidence = valid_evidence()
        forged = reseal_receipt(
            decide(evidence).to_dict(),
            decision="NO_ACTION",
            reason_codes=["BELOW_REVIEW_THRESHOLDS"],
        )
        prior = {"evidence": evidence, "receipt": forged, "delivery": "RECORDED", "replay": True}
        with self.assertRaisesRegex(RuntimeError, "does not recompile"):
            _recover_pending_review(
                prior,
                expected_event_id=evidence["event_id"],
                sqs=Bomb(),
                ddb=Bomb(),
                queue_url="queue",
                table="table",
            )

    def test_forged_review_queued_marker_cannot_suppress_recovery_send(self):
        evidence = valid_evidence()
        receipt = decide(evidence).to_dict()
        self.assertEqual(receipt["decision"], "REQUEST_HUMAN_REVIEW")
        row = stored_row(evidence=evidence, receipt=receipt, delivery="REVIEW_QUEUED")
        prior = _decode_stored(row, expected_event_id=evidence["event_id"])
        sqs = RecordingSqs()
        ddb = AlreadyQueuedDdb(row)
        recovered = _recover_pending_review(
            prior,
            expected_event_id=evidence["event_id"],
            sqs=sqs,
            ddb=ddb,
            queue_url="queue",
            table="table",
        )
        self.assertEqual(len(sqs.messages), 1)
        self.assertEqual(sqs.messages[0]["MessageDeduplicationId"], evidence["event_id"])
        self.assertEqual(recovered["delivery"], "REVIEW_QUEUED")
        self.assertIs(recovered["replay"], True)

    def test_delivery_refuses_semantically_valid_no_action_receipt(self):
        evidence = valid_evidence(changed=0.0)
        receipt = decide(evidence).to_dict()
        self.assertEqual(receipt["decision"], "NO_ACTION")
        with self.assertRaisesRegex(RuntimeError, "only REQUEST_HUMAN_REVIEW"):
            _deliver_review(Bomb(), Bomb(), queue_url="queue", table="table", evidence=evidence, receipt=receipt)


if __name__ == "__main__":
    unittest.main()
