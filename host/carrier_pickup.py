#!/usr/bin/env python3
"""host/carrier_pickup.py — formal CARRIER_ONLY→main lane lander and verifier.

A credentialed seat takes offered bytes from an uncredentialed peer (via Slack file,
issue body, action-pad payload, or carrier file) and lands them verbatim to target paths.

Guarantees & Invariants:
1. Byte-identity verification: The offered payload bytes (or hex SHA256) are verified
   against the written / target contents.
2. Fails closed: Any byte mismatch, path traversal attempt, invalid format, or missing
   declared path fails closed BEFORE any write or landing modification occurs.
3. Post-write readback: Landed blob readback from disk/target strictly equals the offered SHA256.
4. Attribution receipt: Emits a deterministic attribution receipt tracking the peer offer,
   landing seat, timestamps, source paths, blob SHA256 hashes, and verification status.
5. No gate: No authorization or identity gate on who may offer bytes.

Stdlib only. Zero credential requirement for offering peers.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union


INPUT_SCHEMA = "commons-carrier-pickup-input/v1"
RECEIPT_SCHEMA = "commons-carrier-pickup-receipt/v1"


class CarrierPickupError(Exception):
    """Base error for carrier pickup failures."""


class VerificationMismatchError(CarrierPickupError):
    """Raised when offered payload sha256 or bytes do not match expected/computed hash."""


class PathSecurityError(CarrierPickupError):
    """Raised when declared paths attempt directory traversal or invalid characters."""


def compute_sha256(data: Union[bytes, str]) -> str:
    """Compute hex sha256 of bytes or utf-8 encoded string."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_json(data: Any) -> bytes:
    """Deterministic JSON serialization."""
    return (json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def normalize_target_path(path_str: str, root_dir: Path) -> Path:
    """Safely normalize and validate that the target path resides strictly inside root_dir."""
    clean = str(path_str or "").strip().replace("\\", "/")
    if not clean:
        raise PathSecurityError("Declared path cannot be empty")
    if clean.startswith("/") or clean.startswith("../") or "/../" in clean or clean == "..":
        raise PathSecurityError(f"Path traversal or absolute path rejected: {clean!r}")
    
    root_resolved = root_dir.resolve()
    target_resolved = (root_dir / clean).resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError:
        raise PathSecurityError(f"Path escapes root directory: {clean!r}")
    return target_resolved


def parse_offered_item(raw_item: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
    """Validate and extract an offered file/blob item.
    
    Item schema supports:
      - path: relative target path (str, required)
      - content: text content (str) OR
      - content_base64: base64 encoded binary content (str) OR
      - raw_bytes: raw bytes (bytes)
      - sha256: expected sha256 hex digest (str, optional; verified if provided)
    """
    if not isinstance(raw_item, dict):
        raise CarrierPickupError(f"Offered item [{index}] must be a JSON object")

    path = str(raw_item.get("path") or "").strip()
    if not path:
        raise CarrierPickupError(f"Offered item [{index}] missing required 'path'")

    content_str = raw_item.get("content")
    content_b64 = raw_item.get("content_base64")
    raw_bytes = raw_item.get("raw_bytes")

    count_payloads = sum(x is not None for x in (content_str, content_b64, raw_bytes))
    if count_payloads == 0:
        raise CarrierPickupError(f"Offered item [{index}] for path '{path}' missing payload ('content', 'content_base64', or 'raw_bytes')")
    if count_payloads > 1:
        raise CarrierPickupError(f"Offered item [{index}] has multiple payload representations specified")

    if content_str is not None:
        if not isinstance(content_str, str):
            raise CarrierPickupError(f"Offered item [{index}] 'content' must be a string")
        payload_bytes = content_str.encode("utf-8")
    elif content_b64 is not None:
        if not isinstance(content_b64, str):
            raise CarrierPickupError(f"Offered item [{index}] 'content_base64' must be a string")
        try:
            payload_bytes = base64.b64decode(content_b64.encode("ascii"), validate=True)
        except Exception as exc:
            raise CarrierPickupError(f"Offered item [{index}] invalid base64 content: {exc}") from exc
    else:
        if not isinstance(raw_bytes, (bytes, bytearray)):
            raise CarrierPickupError(f"Offered item [{index}] 'raw_bytes' must be bytes")
        payload_bytes = bytes(raw_bytes)

    actual_sha256 = compute_sha256(payload_bytes)

    declared_sha256 = raw_item.get("sha256")
    if declared_sha256:
        declared_clean = str(declared_sha256).strip().lower()
        if declared_clean != actual_sha256:
            raise VerificationMismatchError(
                f"Offered item [{index}] sha256 mismatch for path '{path}': "
                f"declared '{declared_clean}' != computed '{actual_sha256}'"
            )

    return {
        "path": path,
        "bytes": payload_bytes,
        "size": len(payload_bytes),
        "sha256": actual_sha256,
    }


def parse_carrier_payload(payload: Union[Dict[str, Any], str, bytes]) -> Dict[str, Any]:
    """Parse a carrier payload input into a structured offer dict.
    
    Can accept:
      - Dictionary adhering to INPUT_SCHEMA or loose carrier payload structure
      - JSON string or bytes
    """
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise CarrierPickupError(f"Payload bytes could not be decoded as JSON: {exc}") from exc
    elif isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception as exc:
            raise CarrierPickupError(f"Payload string could not be decoded as JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise CarrierPickupError("Carrier payload must be a JSON object / dict")

    offered_by = payload.get("offered_by") or payload.get("peer") or payload.get("author") or "anonymous_carrier_peer"
    carrier_source = payload.get("carrier_source") or payload.get("source") or "carrier"
    source_ref = payload.get("source_ref") or payload.get("ref") or payload.get("id") or ""
    
    items_raw = payload.get("items") or payload.get("files")
    if items_raw is None:
        # Check single file shortcut: {"path": "...", "content": "..."}
        if "path" in payload and any(k in payload for k in ("content", "content_base64", "raw_bytes")):
            items_raw = [{
                "path": payload["path"],
                "content": payload.get("content"),
                "content_base64": payload.get("content_base64"),
                "raw_bytes": payload.get("raw_bytes"),
                "sha256": payload.get("sha256"),
            }]
        else:
            raise CarrierPickupError("Carrier payload contains no declared paths or items")

    if not isinstance(items_raw, list) or not items_raw:
        raise CarrierPickupError("Carrier payload 'items' / 'files' must be a nonempty list")

    parsed_items = []
    seen_paths = set()
    for idx, item in enumerate(items_raw):
        parsed = parse_offered_item(item, idx)
        norm_key = parsed["path"].replace("\\", "/")
        if norm_key in seen_paths:
            raise CarrierPickupError(f"Duplicate path offered in payload: '{parsed['path']}'")
        seen_paths.add(norm_key)
        parsed_items.append(parsed)

    return {
        "offered_by": str(offered_by),
        "carrier_source": str(carrier_source),
        "source_ref": str(source_ref),
        "items": parsed_items,
    }


def verify_and_land(
    payload: Union[Dict[str, Any], str, bytes],
    root_dir: Union[str, Path] = ".",
    landing_seat: str = "credentialed_seat",
    write_files: bool = True,
    observed_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify offered bytes and land them verbatim to target paths.
    
    Fails closed:
      - Validates all input data and offered sha256 checksums BEFORE writing any file.
      - Normalizes paths and ensures safety against directory traversal.
      - After writing each file (if write_files=True), reads back the exact blob from disk
        and asserts its sha256 and byte-identity equals the offered data.
      - Generates an immutable, deterministic attribution receipt.
    """
    root_path = Path(root_dir).resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise CarrierPickupError(f"Root directory does not exist or is not a directory: {root_dir}")

    offer = parse_carrier_payload(payload)
    items = offer["items"]

    # Phase 1: Pre-validation of all target paths before writing anything
    target_mappings: List[Tuple[Dict[str, Any], Path]] = []
    for item in items:
        target_path = normalize_target_path(item["path"], root_path)
        target_mappings.append((item, target_path))

    if observed_at is None:
        observed_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    landed_entries = []

    # Phase 2: Land verbatim & verify readback
    for item, target_file in target_mappings:
        offered_bytes = item["bytes"]
        offered_sha = item["sha256"]
        target_rel = str(target_file.relative_to(root_path)).replace("\\", "/")

        if write_files:
            # Ensure parent directory exists
            target_file.parent.mkdir(parents=True, exist_ok=True)
            # Write verbatim bytes
            target_file.write_bytes(offered_bytes)

            # Phase 3: Immediate readback verification from disk
            readback_bytes = target_file.read_bytes()
            readback_sha = compute_sha256(readback_bytes)

            if readback_sha != offered_sha or readback_bytes != offered_bytes:
                raise VerificationMismatchError(
                    f"Readback verification failed for landed blob '{target_rel}': "
                    f"readback sha256 '{readback_sha}' != offered sha256 '{offered_sha}'"
                )

        landed_entries.append({
            "path": target_rel,
            "bytes": len(offered_bytes),
            "sha256": offered_sha,
            "status": "LANDED_VERBATIM" if write_files else "VERIFIED_DRY",
            "readback_verified": write_files,
        })

    # Phase 4: Construct attribution receipt
    attribution_line = (
        f"Landed verbatim by {landing_seat} on behalf of {offer['offered_by']} "
        f"via {offer['carrier_source']} at {observed_at}"
    )

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "PASS",
        "landing_seat": landing_seat,
        "offered_by": offer["offered_by"],
        "carrier_source": offer["carrier_source"],
        "source_ref": offer["source_ref"],
        "observed_at": observed_at,
        "attribution_line": attribution_line,
        "files_count": len(landed_entries),
        "files": landed_entries,
    }
    return receipt


def verify_landed_tree(
    expected_items: List[Dict[str, Any]],
    root_dir: Union[str, Path] = ".",
) -> Dict[str, Any]:
    """Verify that existing files in root_dir match the expected paths and hashes."""
    root_path = Path(root_dir).resolve()
    results = []
    all_match = True

    for item in expected_items:
        path_str = item.get("path")
        if not path_str:
            raise CarrierPickupError("Expected item missing 'path'")
        expected_sha = item.get("sha256")

        try:
            target_path = normalize_target_path(path_str, root_path)
        except Exception as exc:
            results.append({"path": path_str, "status": "PATH_ERROR", "error": str(exc)})
            all_match = False
            continue

        if not target_path.exists():
            results.append({"path": path_str, "status": "MISSING_ON_DISK"})
            all_match = False
            continue

        disk_bytes = target_path.read_bytes()
        disk_sha = compute_sha256(disk_bytes)
        if expected_sha and disk_sha.lower() != expected_sha.lower():
            results.append({
                "path": path_str,
                "status": "HASH_MISMATCH",
                "disk_sha256": disk_sha,
                "expected_sha256": expected_sha,
            })
            all_match = False
        else:
            results.append({
                "path": path_str,
                "status": "MATCH",
                "bytes": len(disk_bytes),
                "sha256": disk_sha,
            })

    return {
        "status": "PASS" if all_match else "FAIL",
        "results": results,
    }


def self_test() -> Dict[str, Any]:
    """Run an in-memory / temporary self test verifying match, mismatch, and error handling."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        test_payload = {
            "schema": INPUT_SCHEMA,
            "offered_by": "peer-self-test",
            "carrier_source": "slack-file",
            "source_ref": "F12345678",
            "items": [
                {
                    "path": "test_dir/hello.txt",
                    "content": "Hello Commons Carrier Pickup!",
                    "sha256": hashlib.sha256(b"Hello Commons Carrier Pickup!").hexdigest(),
                },
                {
                    "path": "binary.dat",
                    "content_base64": base64.b64encode(b"\x00\x01\x02\x03\xff").decode("ascii"),
                }
            ]
        }

        receipt = verify_and_land(test_payload, root_dir=root, landing_seat="test-seat")
        if receipt["status"] != "PASS" or receipt["files_count"] != 2:
            raise AssertionError("Self-test landing failed")
        if not receipt["attribution_line"].startswith("Landed verbatim by test-seat on behalf of peer-self-test"):
            raise AssertionError("Self-test attribution line invalid")

        # Verify readback from disk
        check = verify_landed_tree([
            {"path": "test_dir/hello.txt", "sha256": hashlib.sha256(b"Hello Commons Carrier Pickup!").hexdigest()},
            {"path": "binary.dat", "sha256": hashlib.sha256(b"\x00\x01\x02\x03\xff").hexdigest()},
        ], root_dir=root)
        if check["status"] != "PASS":
            raise AssertionError("Self-test disk verification failed")

        # Verify mismatch failure
        mismatch_payload = {
            "items": [{
                "path": "bad.txt",
                "content": "Real content",
                "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            }]
        }
        try:
            verify_and_land(mismatch_payload, root_dir=root)
            raise AssertionError("Expected VerificationMismatchError was not raised")
        except VerificationMismatchError:
            pass

    return {"status": "PASS", "checks": 4}


def main() -> int:
    parser = argparse.ArgumentParser(description="Land uncredentialed peer carrier bytes verbatim.")
    parser.add_argument("--input", "-i", type=str, help="Path to input carrier JSON file (or stdin if omitted)")
    parser.add_argument("--root", "-r", type=str, default=".", help="Root repository / destination directory")
    parser.add_argument("--seat", "-s", type=str, default=os.getenv("CARRIER_LANDING_SEAT", "credentialed-seat"), help="Landing credentialed seat identifier")
    parser.add_argument("--dry-run", action="store_true", help="Verify hashes and paths without writing files to disk")
    parser.add_argument("--self-test", action="store_true", help="Execute self-test battery and exit")
    args = parser.parse_args()

    if args.self_test:
        res = self_test()
        sys.stdout.buffer.write(canonical_json(res))
        return 0

    if args.input:
        with open(args.input, "rb") as f:
            raw_input = f.read()
    else:
        raw_input = sys.stdin.buffer.read()

    if not raw_input.strip():
        sys.stderr.write("Error: No carrier payload provided on stdin or --input\n")
        return 1

    try:
        receipt = verify_and_land(
            payload=raw_input,
            root_dir=args.root,
            landing_seat=args.seat,
            write_files=not args.dry_run,
        )
        sys.stdout.buffer.write(canonical_json(receipt))
        return 0
    except CarrierPickupError as exc:
        err_out = {
            "schema": RECEIPT_SCHEMA,
            "status": "FAIL",
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
        }
        sys.stderr.buffer.write(canonical_json(err_out))
        return 2


if __name__ == "__main__":
    sys.exit(main())
