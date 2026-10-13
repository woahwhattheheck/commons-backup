#!/usr/bin/env python3
"""Fail-closed authority verifier for the frozen TITAN V5 D2 source archive.

The verifier never extracts archive members. It authenticates the raw gzip
tarball first, then inspects a safe in-memory member manifest and binds the
known D2 main/runtime/helper identities. It does not authorize gameplay,
promotion, submission, or provider mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import tarfile
from typing import Any, Iterable

SCHEMA = "titan-v5-d2-archive-authority-v1"
MANIFEST_SCHEMA = "titan-v5-d2-safe-member-manifest-v1"

D2_ARCHIVE_NAME = "titan-v5-runtime-one-timer-variant-d2-prewarmed.tar.gz"
D2_ARCHIVE_SHA256 = "3d250d7bd32bf51f26ec1f69c2c10bc3c914e7d0cf64a078ae5bac5832465bd8"
D2_ARCHIVE_BYTES = 424145
D2_MEMBER_COUNT = 94
D2_MAIN_SHA256 = "ae7032281ba680cc70fdfc333bb55cbd4aab7127c277c5150f18746c12f549d3"
D2_RUNTIME_MEMBER = "titan_runtime.py"
D2_RUNTIME_GIT_BLOB = "e0cdcf5a5dbe350d442d3b492795d37507449853"
D2_OPERATING_STOCK_GIT_BLOB = "80b372bfd34d04a2c9e2376fa02917f21f659c41"
OFFICIAL_ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
HARNESS_SHA256 = "853850d8673cff0b21fdfe783e2dfcd539b8b2707bfe2d36c2e60d8ec2e43ea4"


class AuthorityError(ValueError):
    """Archive or sidecar bytes fail the retained D2 authority contract."""


@dataclass(frozen=True)
class AuthorityRoot:
    archive_sha256: str
    archive_bytes: int
    member_count: int
    main_sha256: str
    runtime_member: str
    runtime_git_blob: str
    helper_git_blob: str

    def validate(self) -> None:
        for label, value, length in (
            ("archive_sha256", self.archive_sha256, 64),
            ("main_sha256", self.main_sha256, 64),
            ("runtime_git_blob", self.runtime_git_blob, 40),
            ("helper_git_blob", self.helper_git_blob, 40),
        ):
            if not isinstance(value, str) or len(value) != length:
                raise AuthorityError(f"invalid {label}")
            try:
                int(value, 16)
            except ValueError as exc:
                raise AuthorityError(f"invalid {label}") from exc
        if type(self.archive_bytes) is not int or self.archive_bytes <= 0:
            raise AuthorityError("archive_bytes must be a positive integer")
        if type(self.member_count) is not int or self.member_count <= 0:
            raise AuthorityError("member_count must be a positive integer")
        _safe_member_name(self.runtime_member)


D2_ROOT = AuthorityRoot(
    archive_sha256=D2_ARCHIVE_SHA256,
    archive_bytes=D2_ARCHIVE_BYTES,
    member_count=D2_MEMBER_COUNT,
    main_sha256=D2_MAIN_SHA256,
    runtime_member=D2_RUNTIME_MEMBER,
    runtime_git_blob=D2_RUNTIME_GIT_BLOB,
    helper_git_blob=D2_OPERATING_STOCK_GIT_BLOB,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob_id(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _safe_member_name(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise AuthorityError("archive contains an empty member name")
    if "\\" in name:
        raise AuthorityError(f"archive member uses backslash: {name!r}")
    if name.startswith("/"):
        raise AuthorityError(f"archive member is absolute: {name!r}")
    path = PurePosixPath(name)
    parts = path.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise AuthorityError(f"archive member is not canonical: {name!r}")
    if ":" in parts[0]:
        raise AuthorityError(f"archive member has drive-like prefix: {name!r}")
    normalized = path.as_posix()
    if normalized != name.rstrip("/"):
        raise AuthorityError(f"archive member normalization drift: {name!r}")
    return normalized


def _read_regular(tf: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    stream = tf.extractfile(member)
    if stream is None:
        raise AuthorityError(f"unable to read regular member: {member.name!r}")
    data = stream.read()
    if len(data) != member.size:
        raise AuthorityError(f"member size drift: {member.name!r}")
    return data


def _member_manifest(raw: bytes, expected_count: int) -> list[dict[str, Any]]:
    try:
        tf = tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz")
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise AuthorityError("archive is not a valid gzip tar stream") from exc

    with tf:
        members = tf.getmembers()
        if len(members) != expected_count:
            raise AuthorityError(
                f"archive member count mismatch: expected {expected_count}, got {len(members)}"
            )
        seen: set[str] = set()
        manifest: list[dict[str, Any]] = []
        for member in members:
            name = _safe_member_name(member.name)
            if name in seen:
                raise AuthorityError(f"duplicate archive member: {name!r}")
            seen.add(name)

            if member.type in (tarfile.REGTYPE, tarfile.AREGTYPE):
                data = _read_regular(tf, member)
                manifest.append(
                    {
                        "name": name,
                        "kind": "file",
                        "size": len(data),
                        "sha256": _sha256(data),
                        "git_blob": _git_blob_id(data),
                    }
                )
            elif member.type == tarfile.DIRTYPE:
                manifest.append(
                    {
                        "name": name,
                        "kind": "directory",
                        "size": 0,
                        "sha256": None,
                        "git_blob": None,
                    }
                )
            else:
                raise AuthorityError(
                    f"unsafe archive member type for {name!r}: "
                    "links/devices/fifos/sparse entries are forbidden"
                )
    return sorted(manifest, key=lambda row: row["name"])


def _exactly_one(rows: Iterable[dict[str, Any]], label: str) -> dict[str, Any]:
    values = list(rows)
    if len(values) != 1:
        raise AuthorityError(f"{label} must resolve to exactly one member; got {len(values)}")
    return values[0]


def audit_archive_bytes(raw: bytes, root: AuthorityRoot = D2_ROOT) -> dict[str, Any]:
    """Return an authority receipt only after every retained root predicate passes."""
    root.validate()
    if not isinstance(raw, (bytes, bytearray)):
        raise AuthorityError("archive input must be bytes")
    raw = bytes(raw)
    archive_sha = _sha256(raw)
    if len(raw) != root.archive_bytes:
        raise AuthorityError(
            f"archive byte-size mismatch: expected {root.archive_bytes}, got {len(raw)}"
        )
    if archive_sha != root.archive_sha256:
        raise AuthorityError("archive SHA-256 mismatch")

    members = _member_manifest(raw, root.member_count)
    files = [row for row in members if row["kind"] == "file"]

    main = _exactly_one(
        (row for row in files if PurePosixPath(row["name"]).name == "main.py"),
        "D2 main.py binding",
    )
    if main["sha256"] != root.main_sha256:
        raise AuthorityError("D2 main.py SHA-256 identity mismatch")
    runtime = _exactly_one(
        (row for row in files if row["name"] == root.runtime_member),
        "D2 runtime path binding",
    )
    if runtime["git_blob"] != root.runtime_git_blob:
        raise AuthorityError("D2 runtime Git-blob identity mismatch")

    helper = _exactly_one(
        (
            row
            for row in files
            if row["git_blob"] == root.helper_git_blob
            and PurePosixPath(row["name"]).name == "operating_stock.py"
        ),
        "D2 operating_stock.py Git-blob binding",
    )

    manifest_core = {
        "schema": MANIFEST_SCHEMA,
        "archive_sha256": archive_sha,
        "archive_bytes": len(raw),
        "member_count": len(members),
        "members": members,
    }
    manifest_sha = _sha256(_canonical_json(manifest_core))
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "D2_SOURCE_AUTHENTICATED",
        "source_authority_verified": True,
        "promotion_authorized": False,
        "candidate_build_authorized": False,
        "archive": {
            "name": D2_ARCHIVE_NAME,
            "sha256": archive_sha,
            "bytes": len(raw),
            "member_count": len(members),
        },
        "bindings": {
            "main": {
                "member": main["name"],
                "sha256": main["sha256"],
                "git_blob": main["git_blob"],
            },
            "runtime": {
                "member": runtime["name"],
                "sha256": runtime["sha256"],
                "git_blob": runtime["git_blob"],
            },
            "operating_stock": {
                "member": helper["name"],
                "sha256": helper["sha256"],
                "git_blob": helper["git_blob"],
            },
        },
        "safe_member_manifest": manifest_core,
        "safe_member_manifest_sha256": manifest_sha,
        "execution_sidecars": {
            "official_engine": {
                "required_sha256": OFFICIAL_ENGINE_SHA256,
                "provided": False,
                "verified": False,
            },
            "harness": {
                "required_sha256": HARNESS_SHA256,
                "provided": False,
                "verified": False,
            },
        },
        "execution_inputs_ready": False,
    }
    receipt["receipt_sha256"] = _sha256(
        _canonical_json({k: v for k, v in receipt.items() if k != "receipt_sha256"})
    )
    return receipt


def _verify_sidecar(path: Path | None, expected_sha256: str, label: str) -> dict[str, Any]:
    result = {
        "required_sha256": expected_sha256,
        "provided": path is not None,
        "verified": False,
    }
    if path is None:
        return result
    raw = Path(path).read_bytes()
    actual = _sha256(raw)
    if actual != expected_sha256:
        raise AuthorityError(f"{label} SHA-256 mismatch")
    result.update(
        verified=True,
        path_name=Path(path).name,
        sha256=actual,
        bytes=len(raw),
    )
    return result


def audit_archive_file(
    archive: Path,
    *,
    engine: Path | None = None,
    harness: Path | None = None,
) -> dict[str, Any]:
    receipt = audit_archive_bytes(Path(archive).read_bytes())
    engine_receipt = _verify_sidecar(engine, OFFICIAL_ENGINE_SHA256, "official engine")
    harness_receipt = _verify_sidecar(harness, HARNESS_SHA256, "harness")
    receipt["execution_sidecars"] = {
        "official_engine": engine_receipt,
        "harness": harness_receipt,
    }
    receipt["execution_inputs_ready"] = bool(
        engine_receipt["verified"] and harness_receipt["verified"]
    )
    receipt["receipt_sha256"] = _sha256(
        _canonical_json({k: v for k, v in receipt.items() if k != "receipt_sha256"})
    )
    return receipt


def blocked_receipt() -> dict[str, Any]:
    """Deterministic current-state receipt for environments without the D2 tarball."""
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "D2_SOURCE_BYTES_ABSENT",
        "source_authority_verified": False,
        "promotion_authorized": False,
        "candidate_build_authorized": False,
        "required_archive": {
            "name": D2_ARCHIVE_NAME,
            "sha256": D2_ARCHIVE_SHA256,
            "bytes": D2_ARCHIVE_BYTES,
            "member_count": D2_MEMBER_COUNT,
            "main_sha256": D2_MAIN_SHA256,
            "runtime_member": D2_RUNTIME_MEMBER,
            "runtime_git_blob": D2_RUNTIME_GIT_BLOB,
            "operating_stock_git_blob": D2_OPERATING_STOCK_GIT_BLOB,
        },
        "required_execution_sidecars": {
            "official_engine_sha256": OFFICIAL_ENGINE_SHA256,
            "harness_sha256": HARNESS_SHA256,
        },
        "next_step": (
            "provide exact D2 archive bytes to this verifier; run official-engine "
            "census/dev/holdout only after source_authority_verified=true"
        ),
    }
    receipt["receipt_sha256"] = _sha256(_canonical_json(receipt))
    return receipt


def _write_json(value: Any, output: Path | None) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if output is None:
        print(encoded, end="")
    else:
        Path(output).write_text(encoded, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path)
    parser.add_argument("--engine", type=Path)
    parser.add_argument("--harness", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.archive is None:
            receipt = blocked_receipt()
        else:
            receipt = audit_archive_file(
                args.archive,
                engine=args.engine,
                harness=args.harness,
            )
    except (AuthorityError, OSError) as exc:
        parser.error(str(exc))
    _write_json(receipt, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
