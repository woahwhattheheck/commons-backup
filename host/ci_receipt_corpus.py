#!/usr/bin/env python3
"""Validate and summarize the Commons CI receipt corpus release candidate."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = Path("revenue/data/ci_receipt_corpus.json")
SCHEMA_PATH = Path("revenue/data/ci_receipt_corpus.schema.json")
ENTRY_IDS = (
    "codexsol-zero-auth-open-smoke-20260821-01",
    "codexsol-zero-auth-run-smoke-20260821-01",
    "codexsol-zero-auth-push-smoke-20260821-01",
    "codexsol-action-first-fire-20260821",
    "codexsol-action-second-fire-20260821",
    "commons-inventory-20260822-01",
    "codex-unblock-crawlers-20260823-01",
    "codexsol-common-resources-entry-20260821-01",
    "codexsol-common-resources-page-20260821-01",
)
SCAN_PATTERNS = {
    "PRIVATE_KEY": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GITHUB_TOKEN": re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "SLACK_TOKEN": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "AWS_KEY": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "STRIPE_SECRET": re.compile(rb"(?:sk|rk)_live_[A-Za-z0-9]{16,}"),
    "BEARER": re.compile(rb"Bearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE),
    "PASSWORD": re.compile(rb"(?:password|passwd|pwd)\s*[:=]\s*[^\s,;]{4,}", re.IGNORECASE),
    "EMAIL": re.compile(rb"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    "PHONE": re.compile(rb"(?<!\d)(?:\+?1[-. ]?)?\(?[2-9]\d{2}\)?[-. ]?\d{3}[-. ]?\d{4}(?!\d)"),
}
TRUTH_KEYS = {"buyer_interest_verified", "agreement_signed", "delivery_completed", "cash_received"}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class CorpusError(ValueError):
    """The corpus violates its source, scan, license, or release boundary."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CorpusError(message)


def _exact_keys(value: dict, required: set[str], at: str) -> None:
    _require(isinstance(value, dict), f"{at} must be an object")
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required)
    _require(not missing, f"{at} missing keys {missing!r}")
    _require(not extra, f"{at} has extra keys {extra!r}")


def _safe_path(value: str, at: str) -> str:
    _require(isinstance(value, str) and value and "\\" not in value, f"{at} path invalid")
    parsed = PurePosixPath(value)
    _require(not parsed.is_absolute() and ".." not in parsed.parts and str(parsed) == value, f"{at} path escapes root")
    return value


def _git(root: Path, *args: str, binary: bool = False):
    completed = subprocess.run(
        ["git", "-C", str(root), *args], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise CorpusError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def scan_bytes(raw: bytes) -> dict[str, int]:
    return {name: len(pattern.findall(raw)) for name, pattern in SCAN_PATTERNS.items()}


def load(root: Path = ROOT) -> tuple[dict, dict]:
    data = json.loads((root / CORPUS_PATH).read_text(encoding="utf-8"))
    schema = json.loads((root / SCHEMA_PATH).read_text(encoding="utf-8"))
    return data, schema


def _validate_license(root: Path, base: str, license_data: dict) -> None:
    _exact_keys(license_data, {"status", "root_license_files", "readme_license_statements", "reuse_rights_verified", "blocker"}, "license")
    root_names = _git(root, "ls-tree", "--name-only", base).splitlines()
    license_names = [name for name in root_names if re.match(r"^(LICENSE|COPYING|NOTICE)(\.|$)", name, re.IGNORECASE)]
    _require(len(license_names) == license_data["root_license_files"] == 0, "root license evidence drift")
    readme = _git(root, "cat-file", "blob", _git(root, "rev-parse", f"{base}:README.md"), binary=True)
    readme_hits = len(re.findall(rb"license|copyright", readme, re.IGNORECASE))
    _require(readme_hits == license_data["readme_license_statements"] == 0, "README license evidence drift")
    _require(license_data["status"] == "NOASSERTION" and license_data["reuse_rights_verified"] is False, "license must remain NOASSERTION")
    _require(isinstance(license_data["blocker"], str) and "rights-holder license decision" in license_data["blocker"], "license blocker missing")


def validate(root: Path, data: dict, schema: dict) -> dict:
    _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "schema draft mismatch")
    _require(schema.get("$id", "").endswith("/revenue/data/ci_receipt_corpus.schema.json"), "schema id mismatch")
    _require(schema.get("additionalProperties") is False, "schema root must be closed")
    _exact_keys(
        data,
        {
            "schema_version", "kind", "generated_at", "generated_from_main", "assessed_at", "scope", "source_pool",
            "selection_boundary", "payloads_duplicated", "scan", "manual_review", "license", "release", "truth", "entries",
        },
        "corpus",
    )
    _require(data["schema_version"] == "commons-ci-receipt-corpus/v1", "schema_version mismatch")
    _require(data["kind"] == "CI_RECEIPT_CORPUS", "kind mismatch")
    _require(bool(HEX40.fullmatch(data["generated_from_main"])), "generated_from_main invalid")
    _git(root, "cat-file", "-e", f"{data['generated_from_main']}^{{commit}}")
    _require(data["assessed_at"] == "2026-08-26", "assessed_at drift")
    _require(data["payloads_duplicated"] is False, "manifest may not duplicate source payloads")
    _exact_keys(data["source_pool"], {"path", "json_files_seen"}, "source_pool")
    _require(data["source_pool"] == {"path": "actions/results", "json_files_seen": 50}, "source pool drift")
    pool_paths = _git(root, "ls-tree", "-r", "--name-only", data["generated_from_main"], "actions/results").splitlines()
    _require(len([path for path in pool_paths if path.endswith(".json")]) == 50, "source pool count drift")
    _require("customer" in data["selection_boundary"].lower() and "outreach" in data["selection_boundary"].lower(), "selection exclusion boundary missing")

    scan = data["scan"]
    _exact_keys(scan, {"scanner_version", "rules", "files_scanned", "bytes_scanned", "hit_counts", "status"}, "scan")
    _require(scan["scanner_version"] == "commons-ci-receipt-scan/v1", "scanner version drift")
    _require(scan["rules"] == list(SCAN_PATTERNS), "scan rules/order drift")
    _exact_keys(scan["hit_counts"], set(SCAN_PATTERNS), "scan.hit_counts")
    _require(not any(scan["hit_counts"].values()), "recorded scan contains hits")
    _require(scan["status"] == "PASS_ZERO_HITS", "scan status drift")

    review = data["manual_review"]
    _exact_keys(review, {"status", "reviewed_at", "reviewer_seat", "files_reviewed", "criteria", "result"}, "manual_review")
    _require(review["status"] == "PASS" and review["files_reviewed"] == 9, "manual review incomplete")
    _require(review["reviewed_at"] == "2026-08-26" and review["reviewer_seat"], "manual review provenance missing")
    _require(
        review["criteria"]
        == "Inspect every selected JSON for credentials, personal contact data, customer or outreach material, private paths, and payload overcollection.",
        "manual review criteria drift",
    )
    _require(
        review["result"]
        == "Nine of nine selected receipts contain only technical repository-operation metadata; no customer, outreach, or private payload material was observed.",
        "manual review result drift",
    )

    entries = data["entries"]
    _require(isinstance(entries, list) and len(entries) == 9, "exactly nine entries required")
    _require([entry.get("receipt_id") for entry in entries] == list(ENTRY_IDS), "receipt order/set drift")
    entry_keys = {
        "receipt_id", "source_path", "source_blob_sha", "source_sha256", "source_bytes", "verb", "ok", "executed_at",
        "classification", "scan_status", "manual_review", "customer_material", "outreach_material",
    }
    total_bytes = 0
    actual_hits = Counter()
    paths = set()
    for index, entry in enumerate(entries):
        at = f"entries[{index}]"
        _exact_keys(entry, entry_keys, at)
        path = _safe_path(entry["source_path"], at)
        _require(path.startswith("actions/results/") and path.endswith(".json"), f"{at} source path out of pool")
        _require(path not in paths, f"{at} duplicate source path")
        paths.add(path)
        _require(bool(HEX40.fullmatch(entry["source_blob_sha"])), f"{at} blob invalid")
        actual_blob = _git(root, "rev-parse", f"{data['generated_from_main']}:{path}")
        _require(actual_blob == entry["source_blob_sha"], f"{at} source blob drift: {actual_blob}")
        raw = _git(root, "cat-file", "blob", actual_blob, binary=True)
        _require(len(raw) == entry["source_bytes"], f"{at} source byte count drift")
        _require(hashlib.sha256(raw).hexdigest() == entry["source_sha256"], f"{at} source SHA-256 drift")
        source = json.loads(raw)
        for key in ("id", "verb", "ok", "executed_at"):
            _require(source.get(key) == entry[{"id": "receipt_id"}.get(key, key)], f"{at} source {key} drift")
        hits = scan_bytes(raw)
        for name, count in hits.items():
            actual_hits[name] += count
        _require(not any(hits.values()) and entry["scan_status"] == "PASS_ZERO_HITS", f"{at} secret/PII scan failed")
        _require(entry["manual_review"] == "PASS", f"{at} manual review drift")
        _require(entry["classification"] == "PUBLIC_TECHNICAL_CI_RECEIPT", f"{at} classification drift")
        _require(entry["customer_material"] is False and entry["outreach_material"] is False, f"{at} excluded material present")
        total_bytes += len(raw)
    _require(total_bytes == scan["bytes_scanned"] == 3733, "scanned byte total drift")
    _require(len(entries) == scan["files_scanned"], "scanned file total drift")
    _require(dict(actual_hits) == scan["hit_counts"], "recorded scan counts drift")

    _validate_license(root, data["generated_from_main"], data["license"])
    release = data["release"]
    _exact_keys(release, {"state", "manifest_public", "payload_release_created", "transfer_ready", "price_known"}, "release")
    _require(release == {"state": "BLOCKED_LICENSE_REQUIRED", "manifest_public": True, "payload_release_created": False, "transfer_ready": False, "price_known": False}, "release must remain license-blocked")
    _exact_keys(data["truth"], TRUTH_KEYS, "truth")
    _require(not any(data["truth"].values()), "truth block may not invent commercial outcomes")
    return {
        "status": "VALID",
        "source_pool_json": data["source_pool"]["json_files_seen"],
        "curated_entries": len(entries),
        "curated_bytes": total_bytes,
        "scan_hits": sum(actual_hits.values()),
        "manual_reviewed": review["files_reviewed"],
        "release_state": release["state"],
        "cash_received": data["truth"]["cash_received"],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("validate", "summary"), default="validate")
    parser.add_argument("--root", default=str(ROOT), help="Commons repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        data, schema = load(root)
        result = validate(root, data, schema)
    except (CorpusError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CI RECEIPT CORPUS INVALID: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
