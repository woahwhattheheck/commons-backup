"""AWS orchestration for ProofLens.

An S3 ObjectCreated event for current/<name> invokes this Lambda. The event MUST
name the exact current-object version, and that object MUST carry user metadata
`baseline-version-id` naming the exact retained version of baseline/<name>.
The function emits only a metadata review request; it never performs a
high-authority external action.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

from opencv_perception import MAX_IMAGE_BYTES, analyze_pair
from prooflens import decide, validate_evidence, verify_receipt


STORED_ROW_KEYS = {"event_id", "evidence_json", "receipt_json", "delivery"}
DELIVERY_STATES = {"RECORDED", "REVIEW_QUEUED"}


class ContractError(ValueError):
    pass


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable {name}")
    return value


def _parse_s3_event(event: Any, allowed_bucket: str) -> tuple[str, str, str]:
    if type(event) is not dict or "Records" not in event:
        raise ContractError("expected S3 event object")
    records = event["Records"]
    if type(records) is not list or len(records) != 1 or type(records[0]) is not dict:
        raise ContractError("exactly one S3 record is required")
    record = records[0]
    if not str(record.get("eventName", "")).startswith("ObjectCreated:"):
        raise ContractError("only ObjectCreated events are accepted")
    try:
        bucket = record["s3"]["bucket"]["name"]
        obj = record["s3"]["object"]
        key = unquote_plus(obj["key"])
        version_id = obj["versionId"]
    except (KeyError, TypeError) as exc:
        raise ContractError("malformed S3 event; exact object versionId is required") from exc
    if bucket != allowed_bucket:
        raise ContractError("event bucket does not match configured bucket")
    if type(key) is not str or not key.startswith("current/") or len(key) <= len("current/"):
        raise ContractError("only current/<name> objects are accepted")
    if key.endswith("/") or "\x00" in key:
        raise ContractError("invalid current object key")
    if type(version_id) is not str or not version_id:
        raise ContractError("exact current object versionId is required")
    return bucket, key, version_id


def _read_object(s3: Any, *, bucket: str, key: str, version_id: str) -> dict[str, Any]:
    if type(version_id) is not str or not version_id:
        raise ContractError("exact object versionId is required")
    response = s3.get_object(Bucket=bucket, Key=key, VersionId=version_id)
    length = response.get("ContentLength")
    if type(length) is not int or length < 1 or length > MAX_IMAGE_BYTES:
        raise ContractError(f"{key} has invalid ContentLength")
    data = response["Body"].read(MAX_IMAGE_BYTES + 1)
    if type(data) is not bytes or len(data) != length or len(data) > MAX_IMAGE_BYTES:
        raise ContractError(f"{key} body length mismatch")
    resolved_version = response.get("VersionId")
    if resolved_version != version_id:
        raise ContractError("S3 response version does not match requested version")
    etag = response.get("ETag")
    if type(etag) is not str or not etag:
        raise ContractError("object ETag is required")
    metadata = response.get("Metadata") or {}
    if type(metadata) is not dict:
        raise ContractError("object metadata must be a mapping")
    return {
        "bytes": data,
        "version_id": resolved_version,
        "etag": etag.strip('"'),
        "metadata": metadata,
    }


def _source_ref(bucket: str, baseline_key: str, baseline: dict[str, Any], current_key: str, current: dict[str, Any]) -> str:
    return (
        f"s3://{bucket}/{baseline_key}?versionId={baseline['version_id']}&etag={baseline['etag']}"
        f"|s3://{bucket}/{current_key}?versionId={current['version_id']}&etag={current['etag']}"
    )


def _canonical_storage_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _ddb_string(item: dict[str, Any], name: str) -> str:
    attribute = item.get(name)
    if type(attribute) is not dict or set(attribute) != {"S"} or type(attribute.get("S")) is not str:
        raise RuntimeError(f"stored evidence row field {name} must be one DynamoDB string AttributeValue")
    return attribute["S"]


def _validate_stored_semantics(
    evidence: Any,
    receipt: Any,
    delivery: Any,
    *,
    expected_event_id: str,
) -> dict[str, Any]:
    if type(delivery) is not str or delivery not in DELIVERY_STATES:
        raise RuntimeError("stored evidence row has invalid delivery state")
    if type(evidence) is not dict or type(receipt) is not dict:
        raise RuntimeError("stored evidence row JSON payloads must be objects")
    try:
        validated = validate_evidence(evidence)
    except ValueError as exc:
        raise RuntimeError("stored evidence row has invalid evidence") from exc
    if validated["event_id"] != expected_event_id:
        raise RuntimeError("stored evidence event_id does not match queried DynamoDB key")
    if not verify_receipt(validated, receipt):
        raise RuntimeError("stored evidence row receipt does not recompile under current policy")
    expected_receipt = decide(validated).to_dict()
    if _canonical_storage_json(receipt) != _canonical_storage_json(expected_receipt):
        raise RuntimeError("stored evidence row receipt differs from exact writer form")
    if expected_receipt["event_id"] != expected_event_id:
        raise RuntimeError("stored receipt event_id does not match queried DynamoDB key")
    if expected_receipt["external_action_authorized"] is not False:
        raise RuntimeError("stored receipt attempted external-action authority")
    decision = expected_receipt["decision"]
    if delivery == "REVIEW_QUEUED" and decision != "REQUEST_HUMAN_REVIEW":
        raise RuntimeError("REVIEW_QUEUED requires REQUEST_HUMAN_REVIEW receipt")
    return {"evidence": validated, "receipt": expected_receipt, "delivery": delivery, "replay": True}


def _decode_stored(item: dict[str, Any], *, expected_event_id: str) -> dict[str, Any]:
    if type(item) is not dict or set(item) != STORED_ROW_KEYS:
        raise RuntimeError("stored evidence row keys are malformed")
    stored_event_id = _ddb_string(item, "event_id")
    if stored_event_id != expected_event_id:
        raise RuntimeError("stored DynamoDB partition key does not match queried event_id")
    evidence_text = _ddb_string(item, "evidence_json")
    receipt_text = _ddb_string(item, "receipt_json")
    delivery = _ddb_string(item, "delivery")
    try:
        evidence = json.loads(evidence_text)
        receipt = json.loads(receipt_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("stored evidence row JSON is malformed") from exc
    try:
        if _canonical_storage_json(evidence) != evidence_text or _canonical_storage_json(receipt) != receipt_text:
            raise RuntimeError("stored evidence row JSON is not canonical")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stored evidence row JSON cannot be canonicalized") from exc
    validated = _validate_stored_semantics(
        evidence,
        receipt,
        delivery,
        expected_event_id=expected_event_id,
    )
    if _canonical_storage_json(validated["evidence"]) != evidence_text:
        raise RuntimeError("stored evidence row differs from normalized writer form")
    if _canonical_storage_json(validated["receipt"]) != receipt_text:
        raise RuntimeError("stored receipt row differs from verified writer form")
    return validated


def _existing(ddb: Any, table: str, event_id: str) -> dict[str, Any] | None:
    result = ddb.get_item(TableName=table, Key={"event_id": {"S": event_id}}, ConsistentRead=True)
    item = result.get("Item")
    return _decode_stored(item, expected_event_id=event_id) if item else None


def _record_once(ddb: Any, table: str, evidence: dict[str, Any], receipt: dict[str, Any]) -> bool:
    validated = _validate_stored_semantics(
        evidence,
        receipt,
        "RECORDED",
        expected_event_id=evidence.get("event_id") if type(evidence) is dict else "",
    )
    canonical_evidence = validated["evidence"]
    canonical_receipt = validated["receipt"]
    try:
        ddb.put_item(
            TableName=table,
            Item={
                "event_id": {"S": canonical_evidence["event_id"]},
                "evidence_json": {"S": _canonical_storage_json(canonical_evidence)},
                "receipt_json": {"S": _canonical_storage_json(canonical_receipt)},
                "delivery": {"S": "RECORDED"},
            },
            ConditionExpression="attribute_not_exists(event_id)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def _review_body(evidence: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "prooflens-human-review/v1",
        "event_id": evidence["event_id"],
        "source_ref": evidence["source_ref"],
        "decision": receipt["decision"],
        "reason_codes": receipt["reason_codes"],
        "receipt_sha256": receipt["receipt_sha256"],
        "external_action_authorized": False,
    }


def _deliver_review(sqs: Any, ddb: Any, *, queue_url: str, table: str, evidence: dict[str, Any], receipt: dict[str, Any]) -> None:
    validated = _validate_stored_semantics(
        evidence,
        receipt,
        "RECORDED",
        expected_event_id=evidence.get("event_id") if type(evidence) is dict else "",
    )
    if validated["receipt"]["decision"] != "REQUEST_HUMAN_REVIEW":
        raise RuntimeError("only REQUEST_HUMAN_REVIEW receipts may be queued")
    evidence = validated["evidence"]
    receipt = validated["receipt"]
    event_id = evidence["event_id"]
    evidence_json = _canonical_storage_json(evidence)
    receipt_json = _canonical_storage_json(receipt)

    # Reserve queue progress only while the exact current durable evidence and
    # receipt generation are still present. REVIEW_QUEUED remains a progress
    # marker, not proof of SQS delivery; a later replay still reissues the same
    # event-id-deduplicated message.
    try:
        ddb.update_item(
            TableName=table,
            Key={"event_id": {"S": event_id}},
            UpdateExpression="SET #delivery = :queued",
            ConditionExpression=(
                "#evidence = :evidence AND #receipt = :receipt AND #delivery = :recorded"
            ),
            ExpressionAttributeNames={
                "#evidence": "evidence_json",
                "#receipt": "receipt_json",
                "#delivery": "delivery",
            },
            ExpressionAttributeValues={
                ":evidence": {"S": evidence_json},
                ":receipt": {"S": receipt_json},
                ":queued": {"S": "REVIEW_QUEUED"},
                ":recorded": {"S": "RECORDED"},
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        # A benign concurrent/replay path may already have advanced exactly
        # this row to REVIEW_QUEUED. Missing or changed rows are not equivalent
        # to that state and must fail closed before SQS.
        current = _existing(ddb, table, event_id)
        if (
            current is None
            or current["delivery"] != "REVIEW_QUEUED"
            or _canonical_storage_json(current["evidence"]) != evidence_json
            or _canonical_storage_json(current["receipt"]) != receipt_json
        ):
            raise RuntimeError("durable review row changed before queue delivery") from exc

    current = _existing(ddb, table, event_id)
    if current is None:
        raise RuntimeError("durable review row disappeared before queue delivery")
    if current["delivery"] != "REVIEW_QUEUED":
        raise RuntimeError("durable review row was not reserved for queue delivery")
    if (
        _canonical_storage_json(current["evidence"]) != evidence_json
        or _canonical_storage_json(current["receipt"]) != receipt_json
    ):
        raise RuntimeError("durable review row changed before queue delivery")

    body = _review_body(current["evidence"], current["receipt"])
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=_canonical_storage_json(body),
        MessageGroupId="prooflens-human-review",
        MessageDeduplicationId=event_id,
    )


def _recover_pending_review(
    prior: dict[str, Any],
    *,
    expected_event_id: str,
    sqs: Any,
    ddb: Any,
    queue_url: str,
    table: str,
) -> dict[str, Any]:
    if type(prior) is not dict or set(prior) != {"evidence", "receipt", "delivery", "replay"} or prior.get("replay") is not True:
        raise RuntimeError("pending replay row is malformed")
    prior = _validate_stored_semantics(
        prior["evidence"],
        prior["receipt"],
        prior["delivery"],
        expected_event_id=expected_event_id,
    )
    if prior["receipt"]["decision"] == "REQUEST_HUMAN_REVIEW":
        # `delivery` is only a progress marker, never proof that SQS accepted a
        # message. Reissue the same event_id FIFO message on every valid review
        # replay so a poisoned/stale REVIEW_QUEUED bit cannot suppress recovery.
        # Downstream consumers must preserve event_id idempotency beyond SQS's
        # finite deduplication window.
        _deliver_review(
            sqs,
            ddb,
            queue_url=queue_url,
            table=table,
            evidence=prior["evidence"],
            receipt=prior["receipt"],
        )
        refreshed = _existing(ddb, table, expected_event_id)
        if refreshed is None:
            raise RuntimeError("review delivery recovered but durable row disappeared")
        return refreshed
    return prior


def lambda_handler(event: Any, context: Any) -> dict[str, Any]:
    bucket = _required_env("PROOFLENS_BUCKET")
    table = _required_env("PROOFLENS_TABLE")
    queue_url = _required_env("PROOFLENS_REVIEW_QUEUE_URL")
    event_bucket, current_key, current_version = _parse_s3_event(event, bucket)

    s3 = boto3.client("s3")
    ddb = boto3.client("dynamodb")
    sqs = boto3.client("sqs")

    current = _read_object(s3, bucket=event_bucket, key=current_key, version_id=current_version)
    baseline_version = current["metadata"].get("baseline-version-id")
    if type(baseline_version) is not str or not baseline_version.strip() or len(baseline_version) > 1024:
        raise ContractError("current object must bind exact baseline-version-id metadata")
    suffix = current_key[len("current/"):]
    baseline_key = f"baseline/{suffix}"
    baseline = _read_object(s3, bucket=event_bucket, key=baseline_key, version_id=baseline_version)

    evidence = analyze_pair(
        baseline["bytes"],
        current["bytes"],
        source_ref=_source_ref(event_bucket, baseline_key, baseline, current_key, current),
    )
    event_id = evidence["event_id"]
    prior = _existing(ddb, table, event_id)
    if prior is not None:
        return _recover_pending_review(
            prior,
            expected_event_id=event_id,
            sqs=sqs,
            ddb=ddb,
            queue_url=queue_url,
            table=table,
        )

    receipt = decide(evidence).to_dict()
    created = _record_once(ddb, table, evidence, receipt)
    if not created:
        raced = _existing(ddb, table, event_id)
        if raced is None:
            raise RuntimeError("event race lost but durable row is unavailable")
        return _recover_pending_review(
            raced,
            expected_event_id=event_id,
            sqs=sqs,
            ddb=ddb,
            queue_url=queue_url,
            table=table,
        )

    delivery = "RECORDED"
    if receipt["decision"] == "REQUEST_HUMAN_REVIEW":
        _deliver_review(sqs, ddb, queue_url=queue_url, table=table, evidence=evidence, receipt=receipt)
        delivery = "REVIEW_QUEUED"

    return {"evidence": evidence, "receipt": receipt, "delivery": delivery, "replay": False}
