#!/usr/bin/env python3
"""File-backed acceptance layer for the INPRS CLM migration evidence gate.

The existing bundle verifier validates a normalized evidence graph. This layer
binds that graph to an independently pinned source manifest and actual files.
It is read-only: it never mutates source, target, public, or provider state.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

SCHEMA_VERSION = 1
OPPORTUNITY_ID = "INPRS-RFP-26-04"
SOURCE_SYSTEM = "Conga Contracts"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_MANIFEST_BYTES = 1_000_000
MAX_BUNDLE_BYTES = 8_000_000
MAX_FILE_BYTES = 32_000_000
MAX_CONTRACTS = 20_000
MAX_VENDOR_DOCUMENTS = 20_000
MAX_VERSIONS_PER_CONTRACT = 256

_BASE_PATH = Path(__file__).with_name("verify_bundle.py")
_base_spec = importlib.util.spec_from_file_location("inprs_clm_verify_bundle", _BASE_PATH)
if _base_spec is None or _base_spec.loader is None:
    raise RuntimeError("unable to load sibling verify_bundle.py")
_base = importlib.util.module_from_spec(_base_spec)
_base_spec.loader.exec_module(_base)


class AcceptanceError(ValueError):
    pass


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def contract_source_semantics(row: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "legacy_id",
        "kind",
        "parent_legacy_id",
        "status",
        "executed",
        "authorization_letter_attached",
        "company_name",
        "contract_cost_cents",
        "effective_date",
        "expiration_date",
        "procurement_method",
        "rfp_number",
        "service_type",
        "public_action",
        "withhold_reason",
    )
    return {key: row.get(key) for key in fields}


def vendor_source_semantics(row: dict[str, Any]) -> dict[str, Any]:
    fields = ("document_id", "document_type", "company_name", "access")
    return {key: row.get(key) for key in fields}


def source_record_digest(row: dict[str, Any], *, vendor: bool = False) -> str:
    value = vendor_source_semantics(row) if vendor else contract_source_semantics(row)
    return _sha(_canon(value))


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return _canon(manifest)


def canonical_receipt_bytes(receipt: dict[str, Any]) -> bytes:
    return _canon(receipt) + b"\n"


def _load_canonical_json(path: Path, limit: int, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AcceptanceError(f"{label}_READ_FAILED:{exc.__class__.__name__}") from exc
    if len(raw) > limit:
        raise AcceptanceError(f"{label}_TOO_LARGE:{len(raw)}")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"{label}_JSON_INVALID:{exc.__class__.__name__}") from exc
    if not isinstance(value, dict):
        raise AcceptanceError(f"{label}_ROOT_INVALID")
    canonical = _canon(value)
    if label == "MANIFEST" and raw != canonical:
        raise AcceptanceError("MANIFEST_NOT_CANONICAL")
    return value, raw


def _strict_keys(value: Any, expected: set[str], label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label}_INVALID"]
    actual = set(value)
    if actual != expected:
        return [f"{label}_KEYS_INVALID:{','.join(sorted(actual ^ expected))}"]
    return []


def _relative_path(value: Any, prefix: str, label: str) -> tuple[str | None, list[str]]:
    if not isinstance(value, str) or not value or "\\" in value:
        return None, [f"PATH_INVALID:{label}"]
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None, [f"PATH_INVALID:{label}"]
    if not path.parts or path.parts[0] != prefix:
        return None, [f"PATH_PREFIX_INVALID:{label}:{prefix}"]
    return value, []


def _read_bound_file(root: Path, rel: str, label: str) -> tuple[bytes | None, list[str]]:
    root_abs = root.resolve()
    parts = PurePosixPath(rel).parts
    cursor = root_abs
    try:
        for part in parts:
            cursor = cursor / part
            mode = cursor.lstat().st_mode
            if stat.S_ISLNK(mode):
                return None, [f"PATH_SYMLINK_REJECTED:{label}:{rel}"]
        if not stat.S_ISREG(cursor.lstat().st_mode):
            return None, [f"FILE_NOT_REGULAR:{label}:{rel}"]
        resolved = cursor.resolve(strict=True)
        try:
            resolved.relative_to(root_abs)
        except ValueError:
            return None, [f"PATH_ESCAPE_REJECTED:{label}:{rel}"]
        size = resolved.stat().st_size
        if size > MAX_FILE_BYTES:
            return None, [f"FILE_TOO_LARGE:{label}:{size}"]
        return resolved.read_bytes(), []
    except FileNotFoundError:
        return None, [f"FILE_MISSING:{label}:{rel}"]
    except OSError as exc:
        return None, [f"FILE_READ_FAILED:{label}:{exc.__class__.__name__}"]


def _public_file_set(root: Path) -> tuple[set[str], list[str]]:
    public_root = root / "public"
    if not public_root.exists():
        return set(), []
    errors: list[str] = []
    paths: set[str] = set()
    try:
        for entry in public_root.rglob("*"):
            rel = entry.relative_to(root).as_posix()
            try:
                mode = entry.lstat().st_mode
            except OSError as exc:
                errors.append(f"PUBLIC_WALK_FAILED:{rel}:{exc.__class__.__name__}")
                continue
            if stat.S_ISLNK(mode):
                errors.append(f"PATH_SYMLINK_REJECTED:public:{rel}")
            elif stat.S_ISREG(mode):
                paths.add(rel)
            elif not stat.S_ISDIR(mode):
                errors.append(f"PUBLIC_SPECIAL_FILE_REJECTED:{rel}")
    except OSError as exc:
        errors.append(f"PUBLIC_WALK_FAILED:root:{exc.__class__.__name__}")
    return paths, errors


def _failure(errors: list[str], *, manifest_sha: str | None = None) -> dict[str, Any]:
    return {
        "accepted": False,
        "authority": {
            "buyer_contact_authorized": False,
            "contract_acceptance_authorized": False,
            "payment_authorized": False,
            "proposal_submission_authorized": False,
            "revenue_recognition_authorized": False,
        },
        "bundle_semantic_sha256": None,
        "contracts": 0,
        "errors": sorted(set(errors)),
        "manifest_sha256": manifest_sha,
        "opportunity_id": OPPORTUNITY_ID,
        "public_records": 0,
        "schema_version": SCHEMA_VERSION,
        "source_bytes_verified": 0,
        "target_bytes_verified": 0,
        "vendor_documents": 0,
    }


def verify_handoff(
    manifest_path: Path,
    expected_manifest_sha256: str,
    bundle_path: Path,
    root: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    if not _is_sha(expected_manifest_sha256):
        errors.append("MANIFEST_PIN_INVALID")

    try:
        manifest, manifest_raw = _load_canonical_json(manifest_path, MAX_MANIFEST_BYTES, label="MANIFEST")
    except AcceptanceError as exc:
        return _failure([str(exc)])
    manifest_sha = _sha(manifest_raw)
    if _is_sha(expected_manifest_sha256) and manifest_sha != expected_manifest_sha256:
        errors.append(f"MANIFEST_PIN_MISMATCH:{manifest_sha}")

    try:
        bundle, _ = _load_canonical_json(bundle_path, MAX_BUNDLE_BYTES, label="BUNDLE")
    except AcceptanceError as exc:
        return _failure(errors + [str(exc)], manifest_sha=manifest_sha)

    errors.extend(_strict_keys(
        manifest,
        {"schema_version", "opportunity_id", "source_system", "contracts", "vendor_documents"},
        "MANIFEST",
    ))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("MANIFEST_SCHEMA_INVALID")
    if manifest.get("opportunity_id") != OPPORTUNITY_ID:
        errors.append("OPPORTUNITY_ID_INVALID")
    if manifest.get("source_system") != SOURCE_SYSTEM:
        errors.append("MANIFEST_SOURCE_SYSTEM_INVALID")

    raw_contract_manifest = manifest.get("contracts")
    raw_vendor_manifest = manifest.get("vendor_documents")
    contract_manifest = raw_contract_manifest if isinstance(raw_contract_manifest, list) else []
    vendor_manifest = raw_vendor_manifest if isinstance(raw_vendor_manifest, list) else []
    if not isinstance(raw_contract_manifest, list):
        errors.append("MANIFEST_CONTRACTS_INVALID")
    if not isinstance(raw_vendor_manifest, list):
        errors.append("MANIFEST_VENDOR_DOCUMENTS_INVALID")
    if len(contract_manifest) > MAX_CONTRACTS:
        errors.append(f"MANIFEST_CONTRACTS_TOO_MANY:{len(contract_manifest)}")
    if len(vendor_manifest) > MAX_VENDOR_DOCUMENTS:
        errors.append(f"MANIFEST_VENDOR_DOCUMENTS_TOO_MANY:{len(vendor_manifest)}")

    base_report = _base.validate_bundle(bundle)
    if not base_report.get("ok"):
        for item in base_report.get("errors", []):
            errors.append(f"BASE_BUNDLE_INVALID:{item}")

    bundle_contract_rows = bundle.get("contracts") if isinstance(bundle.get("contracts"), list) else []
    bundle_contracts = {
        row.get("legacy_id"): row
        for row in bundle_contract_rows
        if isinstance(row, dict) and isinstance(row.get("legacy_id"), str)
    }
    bundle_vendor_rows = bundle.get("vendor_documents") if isinstance(bundle.get("vendor_documents"), list) else []
    bundle_vendors = {
        row.get("document_id"): row
        for row in bundle_vendor_rows
        if isinstance(row, dict) and isinstance(row.get("document_id"), str)
    }
    public_rows = bundle.get("public_records") if isinstance(bundle.get("public_records"), list) else []
    public_by_id = {
        row.get("legacy_id"): row
        for row in public_rows
        if isinstance(row, dict) and isinstance(row.get("legacy_id"), str)
    }

    manifest_contracts: dict[str, dict[str, Any]] = {}
    manifest_vendors: dict[str, dict[str, Any]] = {}
    all_paths: set[str] = set()
    expected_public_paths: set[str] = set()
    internal_hashes: set[str] = set()
    source_total = 0
    target_total = 0

    contract_keys = {
        "legacy_id", "source_path", "source_sha256", "source_size_bytes", "source_record_sha256",
        "target_path", "version_paths", "public_action", "public_path", "redaction_attestation_path",
    }
    for idx, row in enumerate(contract_manifest):
        label = f"contract-{idx}"
        errors.extend(_strict_keys(row, contract_keys, f"MANIFEST_CONTRACT:{label}"))
        if not isinstance(row, dict):
            continue
        cid = row.get("legacy_id")
        if not isinstance(cid, str) or not cid:
            errors.append(f"MANIFEST_CONTRACT_ID_INVALID:{label}")
            continue
        if cid in manifest_contracts:
            errors.append(f"MANIFEST_CONTRACT_DUPLICATE:{cid}")
            continue
        manifest_contracts[cid] = row
        source_path, path_errors = _relative_path(row.get("source_path"), "source", f"{cid}:source")
        errors.extend(path_errors)
        target_path, path_errors = _relative_path(row.get("target_path"), "target", f"{cid}:target")
        errors.extend(path_errors)
        versions = row.get("version_paths")
        if not isinstance(versions, list) or not versions or len(versions) > MAX_VERSIONS_PER_CONTRACT:
            errors.append(f"VERSION_PATHS_INVALID:{cid}")
            versions = []
        normalized_versions: list[str] = []
        for vidx, value in enumerate(versions, start=1):
            rel, path_errors = _relative_path(value, "target", f"{cid}:version:{vidx}")
            errors.extend(path_errors)
            if rel is not None:
                normalized_versions.append(rel)
        action = row.get("public_action")
        public_path = row.get("public_path")
        attestation_path = row.get("redaction_attestation_path")
        if action == "withhold":
            if public_path is not None or attestation_path is not None:
                errors.append(f"WITHHOLD_PATHS_PRESENT:{cid}")
        elif action == "publish_full":
            rel, path_errors = _relative_path(public_path, "public", f"{cid}:public")
            errors.extend(path_errors)
            if rel is not None:
                expected_public_paths.add(rel)
            if attestation_path is not None:
                errors.append(f"FULL_ATTESTATION_PATH_PRESENT:{cid}")
        elif action == "publish_redacted":
            rel, path_errors = _relative_path(public_path, "public", f"{cid}:public")
            errors.extend(path_errors)
            if rel is not None:
                expected_public_paths.add(rel)
            _, path_errors = _relative_path(attestation_path, "internal", f"{cid}:attestation")
            errors.extend(path_errors)
        else:
            errors.append(f"MANIFEST_PUBLIC_ACTION_INVALID:{cid}")

        for rel in [source_path, target_path, *normalized_versions, public_path, attestation_path]:
            if isinstance(rel, str):
                if rel in all_paths:
                    errors.append(f"MANIFEST_PATH_REUSED:{rel}")
                all_paths.add(rel)

        if not _is_sha(row.get("source_sha256")):
            errors.append(f"MANIFEST_SOURCE_HASH_INVALID:{cid}")
        if not _is_sha(row.get("source_record_sha256")):
            errors.append(f"MANIFEST_SOURCE_RECORD_HASH_INVALID:{cid}")
        size = row.get("source_size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0 or size > MAX_FILE_BYTES:
            errors.append(f"MANIFEST_SOURCE_SIZE_INVALID:{cid}")

        candidate = bundle_contracts.get(cid)
        if candidate is None:
            errors.append(f"BUNDLE_CONTRACT_MISSING:{cid}")
            continue
        if candidate.get("public_action") != action:
            errors.append(f"PUBLIC_ACTION_DRIFT:{cid}")
        if _is_sha(row.get("source_record_sha256")) and source_record_digest(candidate) != row.get("source_record_sha256"):
            errors.append(f"SOURCE_RECORD_DRIFT:{cid}")

        if source_path is not None:
            source_bytes, file_errors = _read_bound_file(root, source_path, f"{cid}:source")
            errors.extend(file_errors)
            if source_bytes is not None:
                source_total += len(source_bytes)
                actual = _sha(source_bytes)
                if actual != row.get("source_sha256"):
                    errors.append(f"SOURCE_HASH_MISMATCH:{cid}")
                if len(source_bytes) != row.get("source_size_bytes"):
                    errors.append(f"SOURCE_SIZE_MISMATCH:{cid}")
                if candidate.get("source_sha256") != actual:
                    errors.append(f"BUNDLE_SOURCE_HASH_MISMATCH:{cid}")
        if target_path is not None:
            target_bytes, file_errors = _read_bound_file(root, target_path, f"{cid}:target")
            errors.extend(file_errors)
            if target_bytes is not None:
                target_total += len(target_bytes)
                target_hash = _sha(target_bytes)
                if target_hash != row.get("source_sha256"):
                    errors.append(f"TARGET_SOURCE_DRIFT:{cid}")
                if candidate.get("target_sha256") != target_hash:
                    errors.append(f"BUNDLE_TARGET_HASH_MISMATCH:{cid}")

        history = candidate.get("version_history") if isinstance(candidate.get("version_history"), list) else []
        if len(history) != len(normalized_versions):
            errors.append(f"VERSION_PATH_COUNT_MISMATCH:{cid}")
        for vidx, rel in enumerate(normalized_versions):
            version_bytes, file_errors = _read_bound_file(root, rel, f"{cid}:version:{vidx + 1}")
            errors.extend(file_errors)
            if version_bytes is None or vidx >= len(history) or not isinstance(history[vidx], dict):
                continue
            if _sha(version_bytes) != history[vidx].get("sha256"):
                errors.append(f"VERSION_FILE_HASH_MISMATCH:{cid}:{vidx + 1}")

        if action in {"publish_full", "publish_redacted"} and isinstance(public_path, str):
            public_bytes, file_errors = _read_bound_file(root, public_path, f"{cid}:public")
            errors.extend(file_errors)
            if public_bytes is not None:
                public_hash = _sha(public_bytes)
                expected_hash = candidate.get("target_sha256") if action == "publish_full" else candidate.get("public_document_sha256")
                if public_hash != expected_hash:
                    errors.append(f"PUBLIC_FILE_HASH_MISMATCH:{cid}")
                public_row = public_by_id.get(cid)
                if public_row is None or public_row.get("document_sha256") != public_hash:
                    errors.append(f"PUBLIC_ROW_HASH_MISMATCH:{cid}")
                if public_hash in internal_hashes:
                    errors.append(f"PUBLIC_INTERNAL_HASH_EXPOSURE:{cid}")
        if action == "publish_redacted" and isinstance(attestation_path, str):
            attestation_bytes, file_errors = _read_bound_file(root, attestation_path, f"{cid}:attestation")
            errors.extend(file_errors)
            if attestation_bytes is not None:
                attestation_hash = _sha(attestation_bytes)
                internal_hashes.add(attestation_hash)
                if candidate.get("redaction_attestation_sha256") != attestation_hash:
                    errors.append(f"ATTESTATION_FILE_HASH_MISMATCH:{cid}")
                public_row = public_by_id.get(cid)
                if public_row is None or public_row.get("redaction_attestation_sha256") != attestation_hash:
                    errors.append(f"PUBLIC_ATTESTATION_HASH_MISMATCH:{cid}")

    vendor_keys = {
        "document_id", "source_path", "source_sha256", "source_size_bytes", "source_record_sha256", "target_path"
    }
    for idx, row in enumerate(vendor_manifest):
        label = f"vendor-{idx}"
        errors.extend(_strict_keys(row, vendor_keys, f"MANIFEST_VENDOR:{label}"))
        if not isinstance(row, dict):
            continue
        doc_id = row.get("document_id")
        if not isinstance(doc_id, str) or not doc_id:
            errors.append(f"MANIFEST_VENDOR_ID_INVALID:{label}")
            continue
        if doc_id in manifest_vendors:
            errors.append(f"MANIFEST_VENDOR_DUPLICATE:{doc_id}")
            continue
        manifest_vendors[doc_id] = row
        source_path, path_errors = _relative_path(row.get("source_path"), "source", f"{doc_id}:source")
        errors.extend(path_errors)
        target_path, path_errors = _relative_path(row.get("target_path"), "target", f"{doc_id}:target")
        errors.extend(path_errors)
        for rel in [source_path, target_path]:
            if isinstance(rel, str):
                if rel in all_paths:
                    errors.append(f"MANIFEST_PATH_REUSED:{rel}")
                all_paths.add(rel)
        if not _is_sha(row.get("source_sha256")):
            errors.append(f"MANIFEST_VENDOR_SOURCE_HASH_INVALID:{doc_id}")
        if not _is_sha(row.get("source_record_sha256")):
            errors.append(f"MANIFEST_VENDOR_SOURCE_RECORD_HASH_INVALID:{doc_id}")
        size = row.get("source_size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0 or size > MAX_FILE_BYTES:
            errors.append(f"MANIFEST_VENDOR_SOURCE_SIZE_INVALID:{doc_id}")
        candidate = bundle_vendors.get(doc_id)
        if candidate is None:
            errors.append(f"BUNDLE_VENDOR_MISSING:{doc_id}")
            continue
        if _is_sha(row.get("source_record_sha256")) and source_record_digest(candidate, vendor=True) != row.get("source_record_sha256"):
            errors.append(f"VENDOR_SOURCE_RECORD_DRIFT:{doc_id}")
        source_hash: str | None = None
        if source_path is not None:
            source_bytes, file_errors = _read_bound_file(root, source_path, f"{doc_id}:source")
            errors.extend(file_errors)
            if source_bytes is not None:
                source_total += len(source_bytes)
                source_hash = _sha(source_bytes)
                internal_hashes.add(source_hash)
                if source_hash != row.get("source_sha256"):
                    errors.append(f"VENDOR_SOURCE_HASH_MISMATCH:{doc_id}")
                if len(source_bytes) != row.get("source_size_bytes"):
                    errors.append(f"VENDOR_SOURCE_SIZE_MISMATCH:{doc_id}")
                if candidate.get("source_sha256") != source_hash:
                    errors.append(f"BUNDLE_VENDOR_SOURCE_HASH_MISMATCH:{doc_id}")
        if target_path is not None:
            target_bytes, file_errors = _read_bound_file(root, target_path, f"{doc_id}:target")
            errors.extend(file_errors)
            if target_bytes is not None:
                target_total += len(target_bytes)
                target_hash = _sha(target_bytes)
                if source_hash is not None and target_hash != source_hash:
                    errors.append(f"VENDOR_TARGET_SOURCE_DRIFT:{doc_id}")
                if candidate.get("target_sha256") != target_hash:
                    errors.append(f"BUNDLE_VENDOR_TARGET_HASH_MISMATCH:{doc_id}")

    if set(manifest_contracts) != set(bundle_contracts):
        errors.append("BUNDLE_CONTRACT_SET_MISMATCH")
    if set(manifest_vendors) != set(bundle_vendors):
        errors.append("BUNDLE_VENDOR_SET_MISMATCH")

    actual_public_paths, walk_errors = _public_file_set(root)
    errors.extend(walk_errors)
    if actual_public_paths != expected_public_paths:
        missing = sorted(expected_public_paths - actual_public_paths)
        extra = sorted(actual_public_paths - expected_public_paths)
        errors.append(f"PUBLIC_FILE_SET_MISMATCH:missing={','.join(missing)}:extra={','.join(extra)}")

    # Repeat after every internal hash is known so manifest row order cannot hide leakage.
    for cid, row in manifest_contracts.items():
        rel = row.get("public_path")
        if isinstance(rel, str):
            public_bytes, _ = _read_bound_file(root, rel, f"{cid}:public")
            if public_bytes is not None and _sha(public_bytes) in internal_hashes:
                errors.append(f"PUBLIC_INTERNAL_HASH_EXPOSURE:{cid}")

    return {
        "accepted": not errors,
        "authority": {
            "buyer_contact_authorized": False,
            "contract_acceptance_authorized": False,
            "payment_authorized": False,
            "proposal_submission_authorized": False,
            "revenue_recognition_authorized": False,
        },
        "bundle_semantic_sha256": _sha(_canon(bundle)),
        "contracts": len(bundle_contracts),
        "errors": sorted(set(errors)),
        "manifest_sha256": manifest_sha,
        "opportunity_id": OPPORTUNITY_ID,
        "public_records": len(public_by_id),
        "schema_version": SCHEMA_VERSION,
        "source_bytes_verified": source_total,
        "target_bytes_verified": target_total,
        "vendor_documents": len(bundle_vendors),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args(argv)
    receipt = verify_handoff(args.manifest, args.manifest_sha256, args.bundle, args.root)
    print(canonical_receipt_bytes(receipt).decode("utf-8"), end="")
    return 0 if receipt["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
