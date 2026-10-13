#!/usr/bin/env python3
"""Build a deterministic, synthetic file-backed INPRS handoff for demonstrations/tests only."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

_ACCEPT_PATH = Path(__file__).with_name("file_backed_acceptance.py")
_accept_spec = importlib.util.spec_from_file_location("inprs_file_backed_acceptance", _ACCEPT_PATH)
if _accept_spec is None or _accept_spec.loader is None:
    raise RuntimeError("unable to load sibling file_backed_acceptance.py")
_accept = importlib.util.module_from_spec(_accept_spec)
_accept_spec.loader.exec_module(_accept)
OPPORTUNITY_ID = _accept.OPPORTUNITY_ID
SOURCE_SYSTEM = _accept.SOURCE_SYSTEM
canonical_manifest_bytes = _accept.canonical_manifest_bytes
source_record_digest = _accept.source_record_digest


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(root: Path, rel: str, data: bytes) -> tuple[str, int]:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha(data), len(data)


def _search_terms(row: dict[str, Any]) -> list[str]:
    values = []
    for field in ("company_name", "service_type", "procurement_method", "rfp_number", "effective_date", "expiration_date"):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            values.append(value.strip().casefold())
    cents = row.get("contract_cost_cents")
    if isinstance(cents, int) and not isinstance(cents, bool) and cents >= 0:
        values.append(f"{cents // 100}.{cents % 100:02d}")
    return sorted(set(values))


def build(root: Path) -> tuple[Path, Path, str]:
    root.mkdir(parents=True, exist_ok=True)
    contracts: list[dict[str, Any]] = [
        {
            "legacy_id": "C-100", "kind": "master", "parent_legacy_id": None, "status": "active",
            "executed": True, "authorization_letter_attached": True, "company_name": "Synthetic Analytics",
            "contract_cost_cents": 12500000, "effective_date": "2025-01-01", "expiration_date": "2027-12-31",
            "procurement_method": "RFP", "rfp_number": "SYN-24-07", "service_type": "analytics services",
            "public_action": "publish_full", "withhold_reason": None,
        },
        {
            "legacy_id": "C-101", "kind": "amendment", "parent_legacy_id": "C-100", "status": "active",
            "executed": True, "authorization_letter_attached": True, "company_name": "Synthetic Analytics",
            "contract_cost_cents": 13500000, "effective_date": "2025-06-01", "expiration_date": "2027-12-31",
            "procurement_method": "RFP", "rfp_number": "SYN-24-07", "service_type": "analytics services",
            "public_action": "publish_redacted", "withhold_reason": None,
        },
        {
            "legacy_id": "C-200", "kind": "master", "parent_legacy_id": None, "status": "inactive",
            "executed": True, "authorization_letter_attached": False, "company_name": "Synthetic Legal",
            "contract_cost_cents": 8500000, "effective_date": "2023-02-15", "expiration_date": "2026-02-14",
            "procurement_method": "RFQ", "rfp_number": "SYN-23-11", "service_type": "legal services",
            "public_action": "withhold", "withhold_reason": "synthetic legal-review hold",
        },
    ]
    manifest_contracts: list[dict[str, Any]] = []
    public_records: list[dict[str, Any]] = []

    for contract in contracts:
        cid = contract["legacy_id"]
        source_data = f"SYNTHETIC SOURCE CONTRACT {cid}\n".encode()
        source_rel = f"source/contracts/{cid}.txt"
        target_rel = f"target/contracts/{cid}.txt"
        source_hash, source_size = _write(root, source_rel, source_data)
        target_hash, _ = _write(root, target_rel, source_data)
        prior_data = f"SYNTHETIC PRIOR REVISION {cid}\n".encode()
        v1_rel = f"target/versions/{cid}/1.txt"
        v2_rel = f"target/versions/{cid}/2.txt"
        v1_hash, _ = _write(root, v1_rel, prior_data)
        v2_hash, _ = _write(root, v2_rel, source_data)
        contract["source_sha256"] = source_hash
        contract["target_sha256"] = target_hash
        contract["version_history"] = [
            {"revision": 1, "sha256": v1_hash},
            {"revision": 2, "sha256": v2_hash},
        ]
        action = contract["public_action"]
        public_rel: str | None = None
        attestation_rel: str | None = None
        if action == "publish_full":
            public_rel = f"public/contracts/{cid}.txt"
            public_hash, _ = _write(root, public_rel, source_data)
            contract["public_document_sha256"] = public_hash
            contract["redaction_attestation_sha256"] = None
        elif action == "publish_redacted":
            public_rel = f"public/contracts/{cid}.txt"
            redacted = f"SYNTHETIC REDACTED CONTRACT {cid}\n".encode()
            public_hash, _ = _write(root, public_rel, redacted)
            attestation_rel = f"internal/redaction_attestations/{cid}.txt"
            attestation = f"SYNTHETIC REDACTION ATTESTATION {cid}\n".encode()
            attestation_hash, _ = _write(root, attestation_rel, attestation)
            contract["public_document_sha256"] = public_hash
            contract["redaction_attestation_sha256"] = attestation_hash
        else:
            contract["public_document_sha256"] = None
            contract["redaction_attestation_sha256"] = None
        manifest_contracts.append({
            "legacy_id": cid,
            "source_path": source_rel,
            "source_sha256": source_hash,
            "source_size_bytes": source_size,
            "source_record_sha256": source_record_digest(contract),
            "target_path": target_rel,
            "version_paths": [v1_rel, v2_rel],
            "public_action": action,
            "public_path": public_rel,
            "redaction_attestation_path": attestation_rel,
        })
        if action != "withhold":
            row = {
                key: contract[key]
                for key in ("legacy_id", "company_name", "service_type", "contract_cost_cents", "effective_date", "expiration_date", "procurement_method", "rfp_number")
            }
            row["document_sha256"] = contract["public_document_sha256"] if action == "publish_redacted" else contract["target_sha256"]
            row["redacted"] = action == "publish_redacted"
            row["redaction_attestation_sha256"] = contract["redaction_attestation_sha256"] if action == "publish_redacted" else None
            row["search_terms"] = _search_terms(row)
            public_records.append(row)

    vendor = {
        "document_id": "V-1", "document_type": "certificate_of_insurance", "company_name": "Synthetic Analytics", "access": "internal"
    }
    vendor_source = b"SYNTHETIC INTERNAL CERTIFICATE OF INSURANCE\n"
    vendor_source_rel = "source/vendor/V-1.txt"
    vendor_target_rel = "target/vendor/V-1.txt"
    vendor_hash, vendor_size = _write(root, vendor_source_rel, vendor_source)
    _write(root, vendor_target_rel, vendor_source)
    vendor["source_sha256"] = vendor_hash
    vendor["target_sha256"] = vendor_hash
    vendor_documents = [vendor]

    bundle = {
        "contracts": contracts,
        "expectations": {
            "active_count": 2,
            "amendment_count": 1,
            "inactive_count": 1,
            "master_count": 2,
            "public_record_count": 2,
            "source_contract_count": 3,
            "vendor_document_count": 1,
        },
        "public_records": public_records,
        "schema_version": 1,
        "source_system": SOURCE_SYSTEM,
        "vendor_documents": vendor_documents,
    }
    manifest = {
        "schema_version": 1,
        "opportunity_id": OPPORTUNITY_ID,
        "source_system": SOURCE_SYSTEM,
        "contracts": manifest_contracts,
        "vendor_documents": [{
            "document_id": vendor["document_id"],
            "source_path": vendor_source_rel,
            "source_sha256": vendor_hash,
            "source_size_bytes": vendor_size,
            "source_record_sha256": source_record_digest(vendor, vendor=True),
            "target_path": vendor_target_rel,
        }],
    }
    manifest_path = root / "source_manifest.json"
    bundle_path = root / "candidate_bundle.json"
    manifest_bytes = canonical_manifest_bytes(manifest)
    manifest_path.write_bytes(manifest_bytes)
    bundle_path.write_bytes(json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode())
    return manifest_path, bundle_path, _sha(manifest_bytes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    manifest, bundle, pin = build(args.output)
    print(json.dumps({"manifest": str(manifest), "bundle": str(bundle), "manifest_sha256": pin}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
