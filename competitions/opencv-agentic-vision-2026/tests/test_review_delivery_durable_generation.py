import copy
import json
import pathlib
import sys
import unittest

from botocore.exceptions import ClientError

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aws_agent import _canonical_storage_json, _deliver_review
from prooflens import ALGORITHM, decide, sha256_json


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


def stored_row(*, evidence=None, receipt=None, delivery="RECORDED"):
    evidence = evidence or valid_evidence()
    receipt = receipt or decide(evidence).to_dict()
    return {
        "event_id": {"S": evidence["event_id"]},
        "evidence_json": {"S": _canonical_storage_json(evidence)},
        "receipt_json": {"S": _canonical_storage_json(receipt)},
        "delivery": {"S": delivery},
    }


def conditional_failure(message="condition failed"):
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": message}},
        "UpdateItem",
    )


class RecordingSqs:
    def __init__(self):
        self.messages = []

    def send_message(self, **kwargs):
        self.messages.append(copy.deepcopy(kwargs))
        return {"MessageId": "fixture-message"}


class FailingSqs:
    def send_message(self, **kwargs):
        raise RuntimeError("fixture SQS unavailable")


class DurableDdb:
    """Small exact-row fake for the delivery reservation/readback contract."""

    def __init__(self, row, *, after_reserve=None):
        self.row = copy.deepcopy(row)
        self.after_reserve = after_reserve
        self.updates = 0
        self.reads = 0

    def get_item(self, **kwargs):
        self.reads += 1
        if self.row is None:
            return {}
        return {"Item": copy.deepcopy(self.row)}

    def update_item(self, **kwargs):
        self.updates += 1
        if self.row is None:
            raise conditional_failure("missing row")
        values = kwargs["ExpressionAttributeValues"]
        if self.row["evidence_json"] != values[":evidence"]:
            raise conditional_failure("evidence changed")
        if self.row["receipt_json"] != values[":receipt"]:
            raise conditional_failure("receipt changed")
        if self.row["delivery"] != values[":recorded"]:
            raise conditional_failure("not recorded")
        self.row["delivery"] = copy.deepcopy(values[":queued"])
        if self.after_reserve is not None:
            self.after_reserve(self)
        return {}


class ReviewDeliveryDurableGenerationTests(unittest.TestCase):
    def packet(self):
        evidence = valid_evidence()
        receipt = decide(evidence).to_dict()
        self.assertEqual(receipt["decision"], "REQUEST_HUMAN_REVIEW")
        return evidence, receipt, stored_row(evidence=evidence, receipt=receipt)

    def deliver(self, sqs, ddb, evidence, receipt):
        return _deliver_review(
            sqs,
            ddb,
            queue_url="https://sqs.example/review.fifo",
            table="prooflens-events",
            evidence=evidence,
            receipt=receipt,
        )

    def test_matching_current_row_is_reserved_then_sent(self):
        evidence, receipt, row = self.packet()
        sqs = RecordingSqs()
        ddb = DurableDdb(row)
        self.deliver(sqs, ddb, evidence, receipt)
        self.assertEqual(ddb.row["delivery"]["S"], "REVIEW_QUEUED")
        self.assertEqual(len(sqs.messages), 1)
        self.assertEqual(sqs.messages[0]["MessageDeduplicationId"], evidence["event_id"])
        self.assertGreaterEqual(ddb.reads, 1)

    def test_direct_delivery_without_durable_row_sends_nothing(self):
        evidence, receipt, _ = self.packet()
        sqs = RecordingSqs()
        ddb = DurableDdb(None)
        with self.assertRaisesRegex(RuntimeError, "durable review row changed"):
            self.deliver(sqs, ddb, evidence, receipt)
        self.assertEqual(sqs.messages, [])

    def test_deleted_after_reservation_sends_nothing(self):
        evidence, receipt, row = self.packet()
        sqs = RecordingSqs()
        ddb = DurableDdb(row, after_reserve=lambda client: setattr(client, "row", None))
        with self.assertRaisesRegex(RuntimeError, "disappeared"):
            self.deliver(sqs, ddb, evidence, receipt)
        self.assertEqual(sqs.messages, [])

    def test_replaced_after_reservation_sends_nothing(self):
        evidence, receipt, row = self.packet()

        def replace(client):
            poisoned = copy.deepcopy(row)
            altered = json.loads(poisoned["evidence_json"]["S"])
            altered["source_ref"] = "s3://attacker/replacement"
            poisoned["evidence_json"]["S"] = _canonical_storage_json(altered)
            poisoned["delivery"] = {"S": "REVIEW_QUEUED"}
            client.row = poisoned

        sqs = RecordingSqs()
        ddb = DurableDdb(row, after_reserve=replace)
        with self.assertRaises(RuntimeError):
            self.deliver(sqs, ddb, evidence, receipt)
        self.assertEqual(sqs.messages, [])

    def test_exact_already_queued_row_is_reissued(self):
        evidence, receipt, row = self.packet()
        row["delivery"] = {"S": "REVIEW_QUEUED"}
        sqs = RecordingSqs()
        ddb = DurableDdb(row)
        self.deliver(sqs, ddb, evidence, receipt)
        self.assertEqual(len(sqs.messages), 1)
        self.assertEqual(ddb.row["delivery"]["S"], "REVIEW_QUEUED")

    def test_failed_sqs_does_not_make_queued_marker_delivery_proof(self):
        evidence, receipt, row = self.packet()
        ddb = DurableDdb(row)
        with self.assertRaisesRegex(RuntimeError, "SQS unavailable"):
            self.deliver(FailingSqs(), ddb, evidence, receipt)
        self.assertEqual(ddb.row["delivery"]["S"], "REVIEW_QUEUED")

        recovery = RecordingSqs()
        self.deliver(recovery, ddb, evidence, receipt)
        self.assertEqual(len(recovery.messages), 1)
        self.assertEqual(recovery.messages[0]["MessageDeduplicationId"], evidence["event_id"])


if __name__ == "__main__":
    unittest.main()
