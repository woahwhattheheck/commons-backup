#!/usr/bin/env python3
"""Bind a newly published TITAN V3 packet to its own external claim profile.

The retained audit in ``audit_transport.py`` intentionally defaults to one historical
Slack object.  This adapter changes those expectations only inside a guarded process-
local context, calls the same raw parser, and restores every historical constant.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from typing import Any, Iterator, Mapping

import audit_transport as core

CLAIM_SCHEMA = "titan.v3-one-tree-publication-claim.v1"
_REQUIRED_TOP = {"schema", "file_id", "transport", "package", "publication_claim", "claim_sha256"}
_HEX64 = core._HEX64


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise core.AuditError(
            f"{label}: key set mismatch missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )


def _integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise core.AuditError(f"{label}: expected nonnegative integer")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise core.AuditError(f"{label}: expected nonempty string")
    return value


def claim_body(profile: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(profile)
    body.pop("claim_sha256", None)
    return body


def claim_digest(profile: Mapping[str, Any]) -> str:
    return hashlib.sha256(core.canonical_bytes(claim_body(profile))).hexdigest()


def validate_claim(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise core.AuditError("claim profile: expected object")
    _exact_keys(value, _REQUIRED_TOP, "claim profile")
    if value["schema"] != CLAIM_SCHEMA:
        raise core.AuditError("claim profile: wrong schema")
    supplied_digest = _text(value["claim_sha256"], "claim profile.claim_sha256")
    if not _HEX64.fullmatch(supplied_digest) or supplied_digest != claim_digest(value):
        raise core.AuditError("claim profile: seal mismatch")

    file_id = _text(value["file_id"], "claim profile.file_id")
    if not file_id.startswith("F"):
        raise core.AuditError("claim profile.file_id: expected Slack file id")

    transport = value["transport"]
    package = value["package"]
    publication = value["publication_claim"]
    if not isinstance(transport, Mapping) or not isinstance(package, Mapping) or not isinstance(publication, Mapping):
        raise core.AuditError("claim profile: transport/package/publication_claim must be objects")
    _exact_keys(transport, {"sha256", "bytes", "regular_files"}, "claim profile.transport")
    _exact_keys(package, {"base", "archive"}, "claim profile.package")
    _exact_keys(publication, {"channel_id", "thread_ts", "message_ts"}, "claim profile.publication_claim")

    transport_sha = _text(transport["sha256"], "claim profile.transport.sha256")
    if not _HEX64.fullmatch(transport_sha):
        raise core.AuditError("claim profile.transport.sha256: expected lowercase SHA-256")
    normalized_transport = {
        "sha256": transport_sha,
        "bytes": _integer(transport["bytes"], "claim profile.transport.bytes"),
        "regular_files": _integer(transport["regular_files"], "claim profile.transport.regular_files"),
    }
    if not isinstance(package["base"], Mapping) or not isinstance(package["archive"], Mapping):
        raise core.AuditError("claim profile.package: base/archive must be objects")
    normalized_package = {
        "base": core._validate_pin(package["base"], "claim profile.package.base"),
        "archive": core._validate_pin(package["archive"], "claim profile.package.archive"),
    }
    normalized_publication = {
        name: _text(publication[name], f"claim profile.publication_claim.{name}")
        for name in ("channel_id", "thread_ts", "message_ts")
    }
    return {
        "schema": CLAIM_SCHEMA,
        "file_id": file_id,
        "transport": normalized_transport,
        "package": normalized_package,
        "publication_claim": normalized_publication,
        "claim_sha256": supplied_digest,
    }


@contextmanager
def _bound_core(profile: Mapping[str, Any]) -> Iterator[None]:
    names = (
        "EXPECTED_FILE_ID",
        "EXPECTED_TRANSPORT_SHA256",
        "EXPECTED_TRANSPORT_BYTES",
        "EXPECTED_TRANSPORT_FILES",
        "PUBLICATION_CLAIM",
    )
    old = {name: getattr(core, name) for name in names}
    try:
        setattr(core, "EXPECTED_FILE_ID", profile["file_id"])
        setattr(core, "EXPECTED_TRANSPORT_SHA256", profile["transport"]["sha256"])
        setattr(core, "EXPECTED_TRANSPORT_BYTES", profile["transport"]["bytes"])
        setattr(core, "EXPECTED_TRANSPORT_FILES", profile["transport"]["regular_files"])
        setattr(core, "PUBLICATION_CLAIM", dict(profile["publication_claim"]))
        yield
    finally:
        for name, value in old.items():
            setattr(core, name, value)


def audit_successor(blob: bytes, profile: Mapping[str, Any], *, observed_file_id: str | None = None) -> dict[str, Any]:
    normalized = validate_claim(profile)
    file_id = observed_file_id or normalized["file_id"]
    with _bound_core(normalized):
        report = core.audit(blob, file_id=file_id, expected=normalized["package"])
    report["external_claim_sha256"] = normalized["claim_sha256"]
    # Re-seal after adding the externally authenticated claim identity.
    report.pop("report_sha256", None)
    return core.seal(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", required=True)
    parser.add_argument("--claim-profile", required=True)
    parser.add_argument("--file-id")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        with open(args.claim_profile, "rb") as handle:
            profile = validate_claim(core.strict_json(handle.read(), "claim profile"))
        with open(args.packet, "rb") as handle:
            blob = handle.read(core._MAX_PACKET_BYTES + 1)
        report = audit_successor(blob, profile, observed_file_id=args.file_id)
        if args.output:
            core.write_report(args.output, report)
        print(
            f"{report['verdict']} file={report['file_id']} "
            f"transport={report['transport']['sha256']} claim={profile['claim_sha256']}"
        )
        return 0 if report["verdict"] == "PASS" else 3
    except (core.AuditError, OSError) as exc:
        print(f"INVALID: {exc}", file=core.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
