#!/usr/bin/env python3
"""Build and validate a public-safe, exact White Box archive inventory."""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Iterable


SCHEMA_VERSION = "commons-whitebox-archive-inventory/v1"
SCANNER_VERSION = "commons-high-confidence-byte-patterns/v1"
SCAN_WORKERS = 4
HASH_CHUNK_BYTES = 8 * 1024 * 1024
PATTERN_OVERLAP_BYTES = 512
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
LICENSE_NAME = re.compile(r"^(?:license|licence|copying|notice)(?:\..*)?$", re.I)

# High-confidence byte patterns only. Counts and affected-file counts are
# published; matched values never leave the scanner.
SENSITIVE_PATTERNS = {
    "AWS_ACCESS_KEY": re.compile(rb"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])"),
    "GITHUB_TOKEN": re.compile(rb"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}"),
    "GOOGLE_API_KEY": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "OPENAI_API_KEY": re.compile(rb"(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "PEM_PRIVATE_KEY": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
    "SLACK_TOKEN": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "STRIPE_LIVE_SECRET": re.compile(rb"(?:sk|rk)_live_[A-Za-z0-9]{16,}"),
    "POTENTIAL_EMAIL": re.compile(
        rb"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I
    ),
    "WINDOWS_USER_PATH": re.compile(rb"[A-Za-z]:\\Users\\[^\\\x00-\x1f]+", re.I),
}
COMBINED_SECRET_PATTERN = re.compile(
    rb"(?P<AWS_ACCESS_KEY>(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9]))"
    rb"|(?P<GITHUB_TOKEN>(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,})"
    rb"|(?P<GOOGLE_API_KEY>AIza[0-9A-Za-z_-]{35})"
    rb"|(?P<OPENAI_API_KEY>(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_-]{20,})"
    rb"|(?P<PEM_PRIVATE_KEY>-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----)"
    rb"|(?P<SLACK_TOKEN>xox[baprs]-[A-Za-z0-9-]{10,})"
    rb"|(?P<STRIPE_LIVE_SECRET>(?:sk|rk)_live_[A-Za-z0-9]{16,})"
)
COMBINED_PERSONAL_PATTERN = re.compile(
    rb"(?P<POTENTIAL_EMAIL>(?i:[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}))"
    rb"|(?P<WINDOWS_USER_PATH>(?i:[A-Za-z]:\\Users\\[^\\\x00-\x1f]+))"
)
SECRET_MARKERS = (
    b"AKIA",
    b"ghp_",
    b"gho_",
    b"ghu_",
    b"ghs_",
    b"ghr_",
    b"AIza",
    b"sk-",
    b"PRIVATE KEY-----",
    b"xox",
    b"sk_live_",
    b"rk_live_",
)
TEXT_LIKE_FORMATS = {".bat", ".cmd", ".json", ".md", ".py", ".sha256", ".txt"}
NUMERIC_PAYLOAD_FORMATS = {".f32", ".qbin"}
SECRET_CATEGORIES = {
    "AWS_ACCESS_KEY",
    "GITHUB_TOKEN",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "PEM_PRIVATE_KEY",
    "SLACK_TOKEN",
    "STRIPE_LIVE_SECRET",
}
PERSONAL_CATEGORIES = {"POTENTIAL_EMAIL", "WINDOWS_USER_PATH"}


class InventoryError(AssertionError):
    """The archive or frozen public inventory violates its contract."""


def _is_linklike(path: Path) -> bool:
    if path.is_symlink():
        return True
    checker = getattr(path, "is_junction", None)
    return bool(checker and checker())


def _canonical_file_line(entry: dict) -> bytes:
    return (
        "commons-whitebox-archive-file/v1\0%s\0%d\0%s\n"
        % (entry["path"], entry["size_bytes"], entry["sha256"])
    ).encode("utf-8")


def _digest_entries(entries: Iterable[dict]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(_canonical_file_line(entry))
    return digest.hexdigest()


def _format_for(relative_path: str) -> str:
    suffix = PurePosixPath(relative_path).suffix.lower()
    return suffix or "<none>"


def _group_for(relative_path: str) -> str:
    parts = PurePosixPath(relative_path).parts
    return parts[0] if len(parts) > 1 else "_ROOT"


def _hash_and_scan(
    path: Path, *, scan_secret: bool = True, scan_personal: bool = True
) -> tuple[str, int, dict[str, int]]:
    if not scan_secret and not scan_personal:
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256")
        return digest.hexdigest(), path.stat().st_size, {}
    digest = hashlib.sha256()
    offsets: dict[str, set[int]] = {name: set() for name in SENSITIVE_PATTERNS}
    tail = b""
    consumed = 0
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            window = tail + chunk
            base = consumed - len(tail)
            if scan_secret and any(marker in window for marker in SECRET_MARKERS):
                for match in COMBINED_SECRET_PATTERN.finditer(window):
                    absolute_offset = base + match.start()
                    if absolute_offset >= 0:
                        offsets[match.lastgroup].add(absolute_offset)
            if scan_personal and (
                b"@" in window or b":\\users\\" in window.lower()
            ):
                for match in COMBINED_PERSONAL_PATTERN.finditer(window):
                    absolute_offset = base + match.start()
                    if absolute_offset >= 0:
                        offsets[match.lastgroup].add(absolute_offset)
            consumed += len(chunk)
            tail = window[-PATTERN_OVERLAP_BYTES:]
    return digest.hexdigest(), total, {
        name: len(found) for name, found in offsets.items() if found
    }


def _walk(root: Path) -> tuple[list[Path], int]:
    if not root.is_dir():
        raise InventoryError("archive root is not a directory")
    if _is_linklike(root):
        raise InventoryError("archive root may not be a symlink or junction")

    files: list[Path] = []
    directory_count = 0
    for current_raw, directories, filenames in os.walk(root, followlinks=False):
        current = Path(current_raw)
        directories.sort()
        filenames.sort()
        for name in directories:
            child = current / name
            if _is_linklike(child):
                raise InventoryError("link-like directory is out of scan scope")
            directory_count += 1
        for name in filenames:
            child = current / name
            if _is_linklike(child):
                raise InventoryError("link-like file is out of scan scope")
            if not child.is_file():
                raise InventoryError("non-regular file is out of scan scope")
            files.append(child)
    files.sort(key=lambda item: item.relative_to(root).as_posix())
    return files, directory_count


def _summaries(entries: list[dict], key_fn) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        grouped[key_fn(entry["path"])].append(entry)
    result = []
    for name in sorted(grouped):
        children = grouped[name]
        result.append(
            {
                "name": name,
                "file_count": len(children),
                "total_bytes": sum(item["size_bytes"] for item in children),
                "tree_sha256": _digest_entries(children),
            }
        )
    return result


def _sensitivity_status(findings: list[dict]) -> str:
    hit_categories = {item["category"] for item in findings if item["matches"]}
    if hit_categories & SECRET_CATEGORIES:
        return "POTENTIAL_SECRET_REVIEW_REQUIRED"
    if hit_categories & PERSONAL_CATEGORIES:
        return "POTENTIAL_PERSONAL_DATA_REVIEW_REQUIRED"
    return "NO_HIGH_CONFIDENCE_PATTERN_MATCHES"


def scan_archive(
    root: Path,
    *,
    public_index: Path,
    inventory_date: str,
    index_blob_sha: str,
    readme_blob_sha: str,
) -> dict:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", inventory_date):
        raise InventoryError("inventory date must be YYYY-MM-DD")
    if not HEX_40.fullmatch(index_blob_sha) or not HEX_40.fullmatch(readme_blob_sha):
        raise InventoryError("public evidence blobs must be 40 lowercase hex characters")

    root = root.resolve(strict=True)
    expected_index = json.loads(public_index.read_text(encoding="utf-8"))
    if not isinstance(expected_index, dict) or not expected_index:
        raise InventoryError("public model index must be a nonempty object")

    source_files, directory_count = _walk(root)
    entries: list[dict] = []
    category_matches = defaultdict(int)
    category_files = defaultdict(int)
    license_like_files: list[str] = []
    personal_scanned_files = 0
    personal_scanned_bytes = 0
    secret_scanned_files = 0
    secret_scanned_bytes = 0

    def scan_one(source_path: Path):
        relative = source_path.relative_to(root).as_posix()
        if relative.startswith("/") or "\\" in relative or ":" in relative:
            raise InventoryError("relative path is not public-safe")
        file_format = _format_for(relative)
        scan_secret = file_format not in NUMERIC_PAYLOAD_FORMATS
        scan_personal = file_format in TEXT_LIKE_FORMATS
        digest, measured_size, hits = _hash_and_scan(
            source_path, scan_secret=scan_secret, scan_personal=scan_personal
        )
        stat_size = source_path.stat().st_size
        if measured_size != stat_size:
            raise InventoryError("file changed while scanning: %s" % relative)
        entry = {
            "path": relative,
            "size_bytes": measured_size,
            "sha256": digest,
            "format": file_format,
            "group": _group_for(relative),
        }
        return entry, hits, scan_secret, scan_personal, bool(
            LICENSE_NAME.fullmatch(PurePosixPath(relative).name)
        )

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
        scanned = executor.map(scan_one, source_files)
        for number, (entry, hits, scan_secret, scan_personal, is_license) in enumerate(
            scanned, start=1
        ):
            entries.append(entry)
            if scan_secret:
                secret_scanned_files += 1
                secret_scanned_bytes += entry["size_bytes"]
            if scan_personal:
                personal_scanned_files += 1
                personal_scanned_bytes += entry["size_bytes"]
            if is_license:
                license_like_files.append(entry["path"])
            for category, count in hits.items():
                category_matches[category] += count
                category_files[category] += 1
            if number % 250 == 0:
                print(
                    "hashed %d/%d files" % (number, len(source_files)),
                    file=sys.stderr,
                    flush=True,
                )

    findings = [
        {
            "category": category,
            "matches": category_matches[category],
            "affected_files": category_files[category],
        }
        for category in sorted(category_matches)
    ]
    groups = _summaries(entries, _group_for)
    formats = _summaries(entries, _format_for)
    observed_groups = sorted(
        item["name"] for item in groups if item["name"] not in {"_ROOT", "proof"}
    )
    public_index_model_ids = sorted(expected_index)
    expected_groups = sorted(
        model_id[:-5] if model_id.endswith(".gguf") else model_id
        for model_id in public_index_model_ids
    )
    license_status = (
        "FOUND_REVIEW_REQUIRED" if license_like_files else "NOT_LOCATED_REVIEW_REQUIRED"
    )
    sensitivity_status = _sensitivity_status(findings)
    total_bytes = sum(item["size_bytes"] for item in entries)

    inventory = {
        "schema_version": SCHEMA_VERSION,
        "inventory_date": inventory_date,
        "archive": {
            "public_label": "White Box Research Archive",
            "root_basename": root.name,
            "file_count": len(entries),
            "directory_count": directory_count,
            "total_bytes": total_bytes,
            "tree_sha256": _digest_entries(entries),
        },
        "scope": {
            "source_location_class": "OWNER_LOCAL_ARCHIVE",
            "source_absolute_path_published": False,
            "payload_files_published": False,
            "hash_algorithm": "SHA-256",
            "file_order": "POSIX_RELATIVE_PATH_CODEPOINT_ASCENDING",
            "leaf_encoding": "commons-whitebox-archive-file/v1\\0PATH\\0SIZE\\0SHA256\\n",
        },
        "public_evidence": {
            "index_path": "muhl/whitebox-data/_INDEX.json",
            "index_blob_sha": index_blob_sha,
            "readme_path": "muhl/whitebox-data/WhiteBox_Research_Archive_README.md",
            "readme_blob_sha": readme_blob_sha,
        },
        "provenance": {
            "status": "PARTIAL_OWNER_LOCAL_PLUS_PUBLIC_INDEX",
            "public_index_model_ids": public_index_model_ids,
            "expected_model_groups": expected_groups,
            "observed_model_groups": observed_groups,
            "model_groups_match_public_index": observed_groups == expected_groups,
            "source_model_download_receipts_verified": False,
        },
        "license": {
            "status": license_status,
            "license_like_files": sorted(license_like_files),
            "transfer_cleared": False,
        },
        "sensitive_data": {
            "status": sensitivity_status,
            "scanner_version": SCANNER_VERSION,
            "secret_patterns_scope": "NON_NUMERIC_ARTIFACT_BYTES",
            "scanned_files": len(entries),
            "scanned_bytes": total_bytes,
            "secret_patterns_scanned_files": secret_scanned_files,
            "secret_patterns_scanned_bytes": secret_scanned_bytes,
            "personal_patterns_scope": "TEXT_LIKE_FILE_BYTES",
            "personal_patterns_scanned_files": personal_scanned_files,
            "personal_patterns_scanned_bytes": personal_scanned_bytes,
            "findings": findings,
            "matched_values_published": False,
            "sampled_manual_review_completed": False,
            "public_sample_release_cleared": False,
            "absence_claimed": False,
        },
        "reproducibility": {
            "content_integrity": "EXACT_TREE_CHECKSUMMED",
            "generation_replay": "NOT_VERIFIED",
            "source_models_pinned": False,
        },
        "commercial_readiness": {
            "archive_license_offer_ready": False,
            "pricing_ready": False,
            "remaining_evidence": [
                "LICENSE_REVIEW",
                "SAMPLED_MANUAL_SENSITIVITY_REVIEW",
                "SOURCE_MODEL_PROVENANCE",
            ],
        },
        "groups": groups,
        "formats": formats,
        "files": entries,
    }
    validate_inventory(inventory)
    return inventory


def _validate_relative_path(raw: str) -> None:
    path = PurePosixPath(raw)
    if not raw or raw.startswith("/") or "\\" in raw or ":" in raw:
        raise InventoryError("inventory contains a non-relative or platform path")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise InventoryError("inventory contains an unsafe relative path")


def validate_inventory(inventory: dict) -> dict:
    if inventory.get("schema_version") != SCHEMA_VERSION:
        raise InventoryError("unexpected schema version")
    files = inventory.get("files")
    if not isinstance(files, list) or not files:
        raise InventoryError("inventory must contain files")
    paths = [item.get("path") for item in files]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise InventoryError("file paths must be sorted and unique")
    for entry in files:
        if set(entry) != {"path", "size_bytes", "sha256", "format", "group"}:
            raise InventoryError("file entry has unexpected keys")
        _validate_relative_path(entry["path"])
        if not isinstance(entry["size_bytes"], int) or entry["size_bytes"] < 0:
            raise InventoryError("invalid file size")
        if not HEX_64.fullmatch(entry["sha256"]):
            raise InventoryError("invalid file sha256")
        if entry["format"] != _format_for(entry["path"]):
            raise InventoryError("file format drift")
        if entry["group"] != _group_for(entry["path"]):
            raise InventoryError("file group drift")

    archive = inventory["archive"]
    total_bytes = sum(item["size_bytes"] for item in files)
    if archive["file_count"] != len(files):
        raise InventoryError("archive file count drift")
    if archive["total_bytes"] != total_bytes:
        raise InventoryError("archive byte count drift")
    if archive["tree_sha256"] != _digest_entries(files):
        raise InventoryError("archive tree digest drift")
    if inventory["groups"] != _summaries(files, _group_for):
        raise InventoryError("group summary drift")
    if inventory["formats"] != _summaries(files, _format_for):
        raise InventoryError("format summary drift")

    scope = inventory["scope"]
    if scope["source_absolute_path_published"] or scope["payload_files_published"]:
        raise InventoryError("public inventory may not publish local source or payload files")
    serialized = json.dumps(inventory, ensure_ascii=False).lower()
    if "c:\\\\users\\\\" in serialized or "c:/users/" in serialized:
        raise InventoryError("public inventory leaks an absolute Windows user path")

    evidence = inventory["public_evidence"]
    if not HEX_40.fullmatch(evidence["index_blob_sha"]):
        raise InventoryError("invalid index evidence blob")
    if not HEX_40.fullmatch(evidence["readme_blob_sha"]):
        raise InventoryError("invalid readme evidence blob")
    provenance = inventory["provenance"]
    normalized_public_ids = sorted(
        model_id[:-5] if model_id.endswith(".gguf") else model_id
        for model_id in provenance["public_index_model_ids"]
    )
    if normalized_public_ids != provenance["expected_model_groups"]:
        raise InventoryError("public model identifiers do not normalize to archive groups")
    if provenance["expected_model_groups"] != provenance["observed_model_groups"]:
        raise InventoryError("local model groups do not match public index")
    if not provenance["model_groups_match_public_index"]:
        raise InventoryError("public model-index match must be explicit")

    license_info = inventory["license"]
    if license_info["transfer_cleared"]:
        raise InventoryError("inventory does not establish transfer clearance")
    expected_license = (
        "FOUND_REVIEW_REQUIRED"
        if license_info["license_like_files"]
        else "NOT_LOCATED_REVIEW_REQUIRED"
    )
    if license_info["status"] != expected_license:
        raise InventoryError("license classification contradicts filename evidence")

    sensitive = inventory["sensitive_data"]
    if sensitive["scanned_files"] != len(files) or sensitive["scanned_bytes"] != total_bytes:
        raise InventoryError("sensitive-data scan coverage drift")
    text_entries = [item for item in files if item["format"] in TEXT_LIKE_FORMATS]
    secret_entries = [
        item for item in files if item["format"] not in NUMERIC_PAYLOAD_FORMATS
    ]
    if sensitive["secret_patterns_scope"] != "NON_NUMERIC_ARTIFACT_BYTES":
        raise InventoryError("secret-pattern scan scope drift")
    if sensitive["secret_patterns_scanned_files"] != len(secret_entries):
        raise InventoryError("secret-pattern file coverage drift")
    if sensitive["secret_patterns_scanned_bytes"] != sum(
        item["size_bytes"] for item in secret_entries
    ):
        raise InventoryError("secret-pattern byte coverage drift")
    if sensitive["personal_patterns_scope"] != "TEXT_LIKE_FILE_BYTES":
        raise InventoryError("personal-pattern scan scope drift")
    if sensitive["personal_patterns_scanned_files"] != len(text_entries):
        raise InventoryError("personal-pattern file coverage drift")
    if sensitive["personal_patterns_scanned_bytes"] != sum(
        item["size_bytes"] for item in text_entries
    ):
        raise InventoryError("personal-pattern byte coverage drift")
    if sensitive["matched_values_published"]:
        raise InventoryError("matched sensitive values may not be published")
    if sensitive["public_sample_release_cleared"]:
        raise InventoryError("inventory does not clear a public sample release")
    if sensitive["absence_claimed"]:
        raise InventoryError("pattern scan must not claim sensitive-data absence")
    if sensitive["status"] != _sensitivity_status(sensitive["findings"]):
        raise InventoryError("sensitive-data classification drift")

    readiness = inventory["commercial_readiness"]
    if readiness["archive_license_offer_ready"] or readiness["pricing_ready"]:
        raise InventoryError("commercial readiness exceeds collected evidence")
    if sorted(readiness["remaining_evidence"]) != sorted(
        [
            "LICENSE_REVIEW",
            "SAMPLED_MANUAL_SENSITIVITY_REVIEW",
            "SOURCE_MODEL_PROVENANCE",
        ]
    ):
        raise InventoryError("remaining evidence contract drift")

    return {
        "status": "VALID",
        "files": len(files),
        "directories": archive["directory_count"],
        "total_bytes": total_bytes,
        "tree_sha256": archive["tree_sha256"],
        "license_status": license_info["status"],
        "sensitive_data_status": sensitive["status"],
        "public_sample_release_cleared": False,
    }


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise InventoryError("inventory must be a JSON object")
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    path.write_text(encoded, encoding="utf-8", newline="\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="hash and classify a local archive")
    scan.add_argument("archive_root", type=Path)
    scan.add_argument("--public-index", type=Path, required=True)
    scan.add_argument("--inventory-date", required=True)
    scan.add_argument("--index-blob-sha", required=True)
    scan.add_argument("--readme-blob-sha", required=True)
    scan.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", help="validate a frozen inventory")
    validate.add_argument("inventory", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "scan":
        inventory = scan_archive(
            args.archive_root,
            public_index=args.public_index,
            inventory_date=args.inventory_date,
            index_blob_sha=args.index_blob_sha,
            readme_blob_sha=args.readme_blob_sha,
        )
        write_json(args.output, inventory)
        print(json.dumps(validate_inventory(inventory), sort_keys=True))
        return 0
    result = validate_inventory(read_json(args.inventory))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InventoryError as exc:
        print("INVALID: %s" % exc, file=sys.stderr)
        raise SystemExit(2)
