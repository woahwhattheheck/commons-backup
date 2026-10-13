from __future__ import annotations

import argparse
import ast
import json
import stat
import sys
import zipfile
from hashlib import sha256
from pathlib import Path, PurePosixPath

from core import TRACKS, canonical_json

REQUIRED = ("main.py", "core.py", "profiles.json", "runtime_contract.json", "model_config.json")
FORBIDDEN_IMPORTS = {"requests", "urllib", "httpx", "aiohttp", "socket", "ftplib", "paramiko"}
FORBIDDEN_TEXT = ("http://", "https://", "AKIA", "BEGIN PRIVATE KEY", "xoxb-")
FIXED_DT = (2026, 1, 1, 0, 0, 0)
DEFAULT_MAX_BUNDLE_BYTES = 14_000_000_000
DEFAULT_MAX_EXPANDED_BYTES = 14_000_000_000
DEFAULT_MAX_MEMBERS = 100_000
PROOF_TYPE = "lit-all3-bundle-verification/v2"


class VerificationError(ValueError):
    pass


def _sha256_path(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _scan_python_text(text: str, label: str) -> list[str]:
    failures: list[str] = []
    for token in FORBIDDEN_TEXT:
        if token in text:
            failures.append(f"{label}: forbidden literal {token}")
    try:
        tree = ast.parse(text, filename=label)
    except (SyntaxError, ValueError) as exc:
        return failures + [f"{label}: invalid Python: {exc}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]
        else:
            continue
        for name in names:
            if name in FORBIDDEN_IMPORTS:
                failures.append(f"{label}: forbidden import {name}")
    return failures


def _scan_python(path: Path) -> list[str]:
    return _scan_python_text(path.read_text(encoding="utf-8"), path.name)


def _safe_member_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise VerificationError(f"unsafe archive member name: {name!r}")
    if name.startswith("/") or name.endswith("/"):
        raise VerificationError(f"archive member must be a relative file: {name!r}")
    p = PurePosixPath(name)
    if p.is_absolute() or any(part in {"", ".", ".."} for part in p.parts):
        raise VerificationError(f"unsafe archive member path: {name!r}")
    normalized = p.as_posix()
    if normalized != name:
        raise VerificationError(f"non-canonical archive member path: {name!r}")
    return normalized


def _manifest_sha(files: list[dict]) -> str:
    return sha256(canonical_json(files).encode("utf-8")).hexdigest()


def _proof_sha(payload: dict) -> str:
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _runtime_contract_bytes(runtime: dict) -> bytes:
    return canonical_json(runtime).encode("utf-8")


def build(
    source: Path,
    track: str,
    output_zip: Path,
    receipt_path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BUNDLE_BYTES,
) -> dict:
    if track not in TRACKS:
        raise ValueError("unsupported track")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be > 0")
    missing = [x for x in REQUIRED if not (source / x).is_file()]
    if missing:
        raise ValueError(f"missing required files: {missing}")
    failures: list[str] = []
    files: list[tuple[str, Path, str, int]] = []
    for p in sorted(source.rglob("*")):
        if not p.is_file():
            continue
        rel = _safe_member_name(p.relative_to(source).as_posix())
        if p.is_symlink():
            failures.append(f"symlink forbidden: {rel}")
            continue
        if p.suffix == ".py":
            failures.extend(_scan_python(p))
        if p.stat().st_mode & (stat.S_ISUID | stat.S_ISGID):
            failures.append(f"privileged mode: {rel}")
        files.append((rel, p, _sha256_path(p), p.stat().st_size))
    if failures:
        raise ValueError("; ".join(failures))

    runtime = json.loads((source / "runtime_contract.json").read_text(encoding="utf-8"))
    if runtime.get("internet_at_execution") is not False:
        raise ValueError("runtime must be offline")
    model_config = json.loads((source / "model_config.json").read_text(encoding="utf-8"))
    if model_config.get("track") != track:
        raise ValueError("model_config track mismatch")

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel, p, _, _ in files:
            info = zipfile.ZipInfo(rel, FIXED_DT)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with p.open("rb") as src, z.open(info, "w", force_zip64=True) as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
    size = output_zip.stat().st_size
    if size > max_bytes:
        raise ValueError(f"bundle exceeds max_bytes: {size}>{max_bytes}")

    manifest = [{"path": r, "sha256": h, "bytes": n} for r, _, h, n in files]
    runtime_raw = (source / "runtime_contract.json").read_bytes()
    receipt = {
        "schema_version": 2,
        "receipt_type": "lit-all3-build-receipt/v2",
        "track": track,
        "accepted": True,
        "runtime_commit": runtime["upstream_commit"],
        "runtime_contract_sha256": sha256(runtime_raw).hexdigest(),
        "internet_at_execution": False,
        "bundle_sha256": _sha256_path(output_zip),
        "bundle_bytes": size,
        "manifest_sha256": _manifest_sha(manifest),
        "files": manifest,
    }
    receipt_path.write_text(canonical_json(receipt), encoding="utf-8")
    return receipt


def _validate_build_receipt(receipt: dict) -> tuple[str, list[dict]]:
    if not isinstance(receipt, dict):
        raise VerificationError("build receipt must be an object")
    if receipt.get("accepted") is not True:
        raise VerificationError("build receipt is not accepted")
    track = receipt.get("track")
    if track not in TRACKS:
        raise VerificationError("unsupported receipt track")
    files = receipt.get("files")
    if not isinstance(files, list) or not files:
        raise VerificationError("build receipt must contain a non-empty manifest")
    seen: set[str] = set()
    normalized: list[dict] = []
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"}:
            raise VerificationError("invalid manifest row shape")
        path = _safe_member_name(item["path"])
        if path in seen:
            raise VerificationError(f"duplicate manifest row: {path}")
        seen.add(path)
        digest = item["sha256"]
        size = item["bytes"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise VerificationError(f"invalid manifest digest: {path}")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise VerificationError(f"invalid manifest size: {path}")
        normalized.append({"path": path, "sha256": digest, "bytes": size})
    normalized.sort(key=lambda x: x["path"])
    if receipt.get("manifest_sha256") is not None and receipt.get("manifest_sha256") != _manifest_sha(normalized):
        raise VerificationError("manifest_sha256 mismatch")
    return track, normalized


def verify_bundle(
    zip_path: Path,
    receipt_path: Path,
    *,
    max_bundle_bytes: int = DEFAULT_MAX_BUNDLE_BYTES,
    max_expanded_bytes: int = DEFAULT_MAX_EXPANDED_BYTES,
    max_members: int = DEFAULT_MAX_MEMBERS,
) -> dict:
    if min(max_bundle_bytes, max_expanded_bytes, max_members) <= 0:
        raise ValueError("verification ceilings must be > 0")
    bundle_size = zip_path.stat().st_size
    if bundle_size > max_bundle_bytes:
        raise VerificationError("bundle byte ceiling exceeded")
    bundle_sha256 = _sha256_path(zip_path)
    receipt_raw = receipt_path.read_bytes()
    try:
        receipt = json.loads(receipt_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid build receipt JSON: {exc}") from exc
    track, manifest = _validate_build_receipt(receipt)
    if receipt.get("bundle_sha256") != bundle_sha256:
        raise VerificationError("bundle_sha256 mismatch")
    if receipt.get("bundle_bytes") != bundle_size:
        raise VerificationError("bundle_bytes mismatch")
    if receipt.get("internet_at_execution") is not False:
        raise VerificationError("build receipt does not prove offline runtime")

    archive_rows: list[dict] = []
    extracted: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(zip_path) as z:
            infos = z.infolist()
            if len(infos) > max_members:
                raise VerificationError("archive member ceiling exceeded")
            names = [i.filename for i in infos]
            if len(names) != len(set(names)):
                raise VerificationError("duplicate archive member name")
            total_expanded = 0
            for info in infos:
                name = _safe_member_name(info.filename)
                if info.is_dir():
                    raise VerificationError(f"directory entries forbidden: {name}")
                mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if file_type not in (0, stat.S_IFREG):
                    raise VerificationError(f"special archive member forbidden: {name}")
                if info.flag_bits & 0x1:
                    raise VerificationError(f"encrypted archive member forbidden: {name}")
                if info.file_size < 0:
                    raise VerificationError(f"invalid expanded size: {name}")
                total_expanded += info.file_size
                if total_expanded > max_expanded_bytes:
                    raise VerificationError("archive expanded-byte ceiling exceeded")
                h = sha256()
                captured = bytearray() if (name.endswith(".py") or name in {"runtime_contract.json", "model_config.json"}) else None
                read_bytes = 0
                with z.open(info, "r") as member:
                    while True:
                        chunk = member.read(1024 * 1024)
                        if not chunk:
                            break
                        read_bytes += len(chunk)
                        h.update(chunk)
                        if captured is not None:
                            captured.extend(chunk)
                if read_bytes != info.file_size:
                    raise VerificationError(f"archive size/read mismatch: {name}")
                if captured is not None:
                    extracted[name] = bytes(captured)
                archive_rows.append({"path": name, "sha256": h.hexdigest(), "bytes": read_bytes})
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise VerificationError(f"invalid archive: {exc}") from exc

    archive_rows.sort(key=lambda x: x["path"])
    archive_name_set = {row["path"] for row in archive_rows}
    if set(REQUIRED) - archive_name_set:
        raise VerificationError(f"missing required files: {sorted(set(REQUIRED) - archive_name_set)}")
    if archive_rows != manifest:
        receipt_names = {row["path"] for row in manifest}
        archive_names = {row["path"] for row in archive_rows}
        extra = sorted(archive_names - receipt_names)
        missing = sorted(receipt_names - archive_names)
        if extra:
            raise VerificationError(f"unmanifested archive members: {extra}")
        if missing:
            raise VerificationError(f"manifest members missing from archive: {missing}")
        raise VerificationError("archive member bytes differ from build manifest")

    py_failures: list[str] = []
    for name, data in extracted.items():
        if name.endswith(".py"):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise VerificationError(f"Python source is not UTF-8: {name}") from exc
            py_failures.extend(_scan_python_text(text, name))
    if py_failures:
        raise VerificationError("; ".join(py_failures))

    try:
        runtime = json.loads(extracted["runtime_contract.json"].decode("utf-8"))
        model_config = json.loads(extracted["model_config.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid bundled JSON contract: {exc}") from exc
    if runtime.get("internet_at_execution") is not False:
        raise VerificationError("bundled runtime must be offline")
    if model_config.get("track") != track:
        raise VerificationError("bundled model_config track mismatch")
    runtime_commit = runtime.get("upstream_commit")
    if not isinstance(runtime_commit, str) or not runtime_commit:
        raise VerificationError("bundled runtime missing upstream_commit")
    if receipt.get("runtime_commit") != runtime_commit:
        raise VerificationError("runtime_commit mismatch")
    runtime_sha = sha256(extracted["runtime_contract.json"]).hexdigest()
    if receipt.get("runtime_contract_sha256") is not None and receipt.get("runtime_contract_sha256") != runtime_sha:
        raise VerificationError("runtime_contract_sha256 mismatch")

    payload = {
        "schema_version": 2,
        "proof_type": PROOF_TYPE,
        "accepted": True,
        "track": track,
        "bundle_sha256": bundle_sha256,
        "bundle_bytes": bundle_size,
        "build_receipt_sha256": sha256(receipt_raw).hexdigest(),
        "runtime_commit": runtime_commit,
        "runtime_contract_sha256": runtime_sha,
        "internet_at_execution": False,
        "member_count": len(archive_rows),
        "expanded_bytes": sum(row["bytes"] for row in archive_rows),
        "manifest_sha256": _manifest_sha(archive_rows),
        "files": archive_rows,
    }
    return {**payload, "proof_sha256": _proof_sha(payload)}


def write_verification_proof(
    zip_path: Path,
    receipt_path: Path,
    proof_path: Path,
    *,
    max_bundle_bytes: int = DEFAULT_MAX_BUNDLE_BYTES,
    max_expanded_bytes: int = DEFAULT_MAX_EXPANDED_BYTES,
    max_members: int = DEFAULT_MAX_MEMBERS,
) -> dict:
    proof = verify_bundle(
        zip_path,
        receipt_path,
        max_bundle_bytes=max_bundle_bytes,
        max_expanded_bytes=max_expanded_bytes,
        max_members=max_members,
    )
    proof_path.write_text(canonical_json(proof), encoding="utf-8")
    return proof


def verify(zip_path: Path, receipt_path: Path) -> bool:
    """Compatibility bool verifier. Strict v2 semantics; no proof persistence."""
    try:
        verify_bundle(zip_path, receipt_path)
        return True
    except (VerificationError, OSError, ValueError):
        return False


def _build_cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("track", choices=sorted(TRACKS))
    ap.add_argument("output_zip", type=Path)
    ap.add_argument("receipt", type=Path)
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BUNDLE_BYTES)
    a = ap.parse_args(argv)
    build(a.source, a.track, a.output_zip, a.receipt, max_bytes=a.max_bytes)
    return 0


def _verify_cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("build_receipt", type=Path)
    ap.add_argument("proof", type=Path)
    ap.add_argument("--max-bundle-bytes", type=int, default=DEFAULT_MAX_BUNDLE_BYTES)
    ap.add_argument("--max-expanded-bytes", type=int, default=DEFAULT_MAX_EXPANDED_BYTES)
    ap.add_argument("--max-members", type=int, default=DEFAULT_MAX_MEMBERS)
    a = ap.parse_args(argv)
    write_verification_proof(
        a.bundle,
        a.build_receipt,
        a.proof,
        max_bundle_bytes=a.max_bundle_bytes,
        max_expanded_bytes=a.max_expanded_bytes,
        max_members=a.max_members,
    )
    return 0


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "verify":
        raise SystemExit(_verify_cli(argv[1:]))
    raise SystemExit(_build_cli(argv))


if __name__ == "__main__":
    main()
