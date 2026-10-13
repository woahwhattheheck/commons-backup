"""Read-only AWS S3 manifest adapter for ProofCam.

The adapter constrains object identity and binds bytes before invoking the core.
It does not write to AWS and does not claim AWS execution merely because an
AWS-shaped event was supplied. A live deployment must retain provider evidence
separately.

Recovered from Z-Vectorforge-1545's ProofCam donor for Commons issue #15715;
canonical-path integration by ZZ–Keystone-43CF.
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable, Mapping

from packet_quality import (
    MAX_IMAGE_BYTES, MAX_JSON_BYTES, MAX_REQUIRED_SLOTS, ProofCamError,
    _freeze, _ident, _validate_packet, canonical_bytes, compile_triage, sha256,
    strict_json_bytes,
)

BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/+=,@-]{0,1023}$")
ETAG_RE = re.compile(r'^(?:"[0-9a-f]{32}(?:-\d+)?"|[0-9a-f]{32}(?:-\d+)?)$')


def _safe_key(value: Any, label: str) -> str:
    if type(value) is not str or not KEY_RE.fullmatch(value):
        raise ProofCamError(f"{label}: invalid S3 key")
    if value.startswith("/") or ".." in value.split("/") or "//" in value:
        raise ProofCamError(f"{label}: noncanonical S3 key")
    return value


def _bucket(value: Any) -> str:
    if type(value) is not str or not BUCKET_RE.fullmatch(value) or ".." in value:
        raise ProofCamError("invalid S3 bucket")
    return value


def _etag(value: Any, label: str) -> str:
    if type(value) is not str or not ETAG_RE.fullmatch(value):
        raise ProofCamError(f"{label}: canonical ETag required")
    return value.strip('"')


def compile_s3_manifest_event(event: Mapping[str, Any], s3_get: Callable[[str, str, str], bytes]) -> dict[str, Any]:
    if type(event) is not dict or set(event) != {"bucket", "manifest_key", "manifest_etag"}:
        raise ProofCamError("event must contain exactly bucket, manifest_key, manifest_etag")
    if not callable(s3_get):
        raise ProofCamError("s3_get must be callable")
    bucket = _bucket(event["bucket"])
    manifest_key = _safe_key(event["manifest_key"], "manifest_key")
    manifest_etag = _etag(event["manifest_etag"], "manifest_etag")
    manifest_bytes = s3_get(bucket, manifest_key, manifest_etag)
    if not isinstance(manifest_bytes, (bytes, bytearray)):
        raise ProofCamError("s3_get must return bytes")
    manifest = strict_json_bytes(bytes(manifest_bytes))
    if type(manifest) is not dict or set(manifest) != {"packet", "objects"}:
        raise ProofCamError("manifest must contain exactly packet and objects")
    packet = _freeze(manifest["packet"])
    _, images = _validate_packet(packet)
    if type(manifest["objects"]) is not list:
        raise ProofCamError("manifest.objects must be list")
    if len(manifest["objects"]) > MAX_REQUIRED_SLOTS:
        raise ProofCamError("manifest object count exceeds packet limit")
    bindings: dict[str, tuple[str, str, str]] = {}
    for i, row in enumerate(manifest["objects"]):
        if type(row) is not dict or set(row) != {"image_id", "key", "etag", "payload_sha256"}:
            raise ProofCamError(f"manifest.objects[{i}] shape invalid")
        image_id = _ident(row["image_id"], f"objects[{i}].image_id")
        if image_id in bindings:
            raise ProofCamError("duplicate/invalid manifest image_id")
        key = _safe_key(row["key"], f"objects[{i}].key")
        etag = _etag(row["etag"], f"objects[{i}].etag")
        payload_sha = row["payload_sha256"]
        if type(payload_sha) is not str or len(payload_sha) != 64 or any(c not in "0123456789abcdef" for c in payload_sha):
            raise ProofCamError("invalid manifest payload_sha256")
        bindings[image_id] = (key, etag, payload_sha)
    packet_ids = {row["image_id"] for row in images}
    if packet_ids != set(bindings):
        raise ProofCamError("manifest object set must exactly equal packet image ids")
    packet_digests = {row["image_id"]: row["payload_sha256"] for row in images}
    if any(bindings[image_id][2] != digest for image_id, digest in packet_digests.items()):
        raise ProofCamError("manifest and packet payload digests must agree")

    def loader(image_id: str) -> bytes:
        if image_id not in bindings:
            raise ProofCamError("unbound image id")
        key, etag, payload_sha = bindings[image_id]
        payload = s3_get(bucket, key, etag)
        if not isinstance(payload, (bytes, bytearray)):
            raise ProofCamError("s3_get must return bytes")
        data = bytes(payload)
        if sha256(data) != payload_sha:
            raise ProofCamError("S3 object digest mismatch")
        # Core reads each declared image once; do not retain all packet bytes.
        return data

    artifact = compile_triage(packet, loader)
    envelope = {
        "adapter": "aws-s3-manifest-readonly/v1",
        "bucket": bucket,
        "manifest_key": manifest_key,
        "manifest_etag": manifest_etag,
        "manifest_sha256": sha256(bytes(manifest_bytes)),
        "aws_execution_proven": False,
    }
    core = {
        "adapter_schema": "proofcam-aws-s3-adapter-artifact/v1",
        "core_artifact": artifact,
        "runtime_envelope": envelope,
    }
    return {**core, "adapter_receipt_sha256": sha256(core)}


def verify_s3_manifest_event(
    event: Mapping[str, Any],
    s3_get: Callable[[str, str, str], bytes],
    artifact: Mapping[str, Any],
) -> bool:
    """Verify an adapter artifact by exact deterministic recompile.

    This binds the outer runtime envelope as well as the inner ProofCam artifact.
    An envelope field cannot be changed while retaining a valid adapter receipt.
    """
    if type(artifact) is not dict:
        raise ProofCamError("adapter artifact must be plain object")
    expected = compile_s3_manifest_event(event, s3_get)
    try:
        actual_bytes = canonical_bytes(artifact)
        expected_bytes = canonical_bytes(expected)
    except (TypeError, ValueError) as exc:
        raise ProofCamError("adapter artifact must contain plain canonical JSON values") from exc
    if actual_bytes != expected_bytes:
        raise ProofCamError("adapter artifact does not exactly match deterministic recompile")
    receipt = artifact.get("adapter_receipt_sha256")
    if type(receipt) is not str or len(receipt) != 64 or any(c not in "0123456789abcdef" for c in receipt):
        raise ProofCamError("adapter receipt malformed")
    core = {
        "adapter_schema": artifact.get("adapter_schema"),
        "core_artifact": artifact.get("core_artifact"),
        "runtime_envelope": artifact.get("runtime_envelope"),
    }
    if sha256(core) != receipt:
        raise ProofCamError("adapter receipt mismatch")
    return True


def _read_provider_body(response: Mapping[str, Any], expected_etag: str,
                        max_bytes: int) -> bytes:
    """Consume a bounded provider stream through EOF, then close it.

    StreamingBody length checks and StreamingChecksumBody checksum checks happen
    at completion; one nonempty read(size) does not establish a complete object.
    """
    if type(response) is not dict:
        raise ProofCamError("provider response must be an object")
    body = response.get("Body")
    try:
        if type(max_bytes) is not int or not 0 < max_bytes <= MAX_IMAGE_BYTES:
            raise ProofCamError("provider byte limit must be a positive bounded integer")
        actual = str(response.get("ETag", "")).strip('"')
        if actual != expected_etag:
            raise ProofCamError("provider ETag mismatch")
        size = response.get("ContentLength")
        if size is not None and (type(size) is not int or not 0 <= size <= max_bytes):
            raise ProofCamError("provider object exceeds byte limit")
        if body is None or not callable(getattr(body, "read", None)):
            raise ProofCamError("provider body must be readable")
        chunks = []
        total = 0
        while True:
            chunk = body.read(min(64 * 1024, max_bytes + 1 - total))
            if not isinstance(chunk, bytes):
                raise ProofCamError("provider body must be bytes")
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ProofCamError("provider object exceeds byte limit")
            chunks.append(chunk)
        if size is not None and total != size:
            raise ProofCamError("provider body length does not match ContentLength")
        return b"".join(chunks)
    finally:
        if callable(getattr(body, "close", None)):
            body.close()


def lambda_handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """Optional deployment entry point; read-only S3 access, no writes.

    Competition deployment must run OpenCV 5. This function refuses to present
    itself as a competition-ready runtime on any other major version.
    """
    import cv2
    if not str(cv2.__version__).startswith("5."):
        raise ProofCamError("live competition adapter requires OpenCV 5.x")
    if not os.environ.get("AWS_EXECUTION_ENV"):
        raise ProofCamError("AWS execution environment evidence absent")
    import boto3
    client = boto3.client("s3")
    def s3_get(bucket: str, key: str, etag: str) -> bytes:
        limit = MAX_JSON_BYTES if key == event.get("manifest_key") else MAX_IMAGE_BYTES
        response = client.get_object(Bucket=bucket, Key=key, IfMatch=f'"{etag}"')
        return _read_provider_body(response, etag, limit)
    return compile_s3_manifest_event(event, s3_get)
