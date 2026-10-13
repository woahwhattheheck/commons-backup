"""Deterministic Learn2Design submission packager/verifier.

This tool is deliberately stricter than zipfile extraction defaults. It validates
source structure before packaging and re-derives every receipt field from archive
bytes during verification.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import PurePosixPath, Path
import re
import stat
import zipfile

SCHEMA = "tjlabs.learn2design2026/submission-receipt-v1"
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_MEMBERS = 64
REQUIRED = ("submission.py", "requirements.txt")
PEP508_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:\s*(?:===|==|~=|!=|<=|>=|<|>)\s*[^\s;]+)?(?:\s*;\s*.+)?$")


class PackageError(ValueError):
    pass


@dataclass(frozen=True)
class Member:
    name: str
    size: int
    sha256: str


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PackageError(f"cannot canonicalize: {exc}") from exc


def _safe_name(name: str) -> None:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise PackageError("unsafe archive member name")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PackageError(f"unsafe archive path: {name}")
    if len(name.encode("utf-8")) > 240:
        raise PackageError("archive member name too long")


def _validate_requirements(text: str) -> None:
    lines = text.splitlines()
    seen = set()
    meaningful = 0
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        meaningful += 1
        if line.startswith(("-", "http:", "https:", "git+", "/", ".")):
            raise PackageError("requirements must be PEP-508 package specifiers, not installer directives/URLs")
        if not PEP508_LINE.match(line):
            raise PackageError(f"invalid requirement line: {line}")
        key = re.split(r"[<>=!~\[;\s]", line, maxsplit=1)[0].lower().replace("_", "-")
        if key in seen:
            raise PackageError(f"duplicate requirement package: {key}")
        seen.add(key)
    if meaningful == 0:
        raise PackageError("requirements.txt must declare explicit dependencies")


def _validate_submission_source(text: str) -> str:
    try:
        tree = ast.parse(text, filename="submission.py")
    except SyntaxError as exc:
        raise PackageError(f"submission.py syntax error: {exc}") from exc
    subclasses: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                name = None
                if isinstance(base, ast.Name):
                    name = base.id
                elif isinstance(base, ast.Attribute):
                    name = base.attr
                if name == "OptimizationAlgorithm":
                    subclasses.append(node.name)
    if len(subclasses) != 1:
        raise PackageError(f"submission.py must define exactly one OptimizationAlgorithm subclass, got {subclasses}")
    return subclasses[0]


def validate_source_dir(source: Path) -> dict[str, object]:
    source = source.resolve()
    if not source.is_dir():
        raise PackageError("source must be a directory")
    entries: dict[str, bytes] = {}
    for child in sorted(source.iterdir(), key=lambda p: p.name.encode("utf-8")):
        if child.name.startswith(".") or child.name == "__pycache__":
            continue
        if child.is_symlink() or not child.is_file():
            raise PackageError(f"only ordinary root files allowed: {child.name}")
        _safe_name(child.name)
        mode = child.stat(follow_symlinks=False).st_mode
        if not stat.S_ISREG(mode):
            raise PackageError(f"not a regular file: {child.name}")
        data = child.read_bytes()
        if len(data) > MAX_MEMBER_BYTES:
            raise PackageError(f"member too large: {child.name}")
        entries[child.name] = data
    for required in REQUIRED:
        if required not in entries:
            raise PackageError(f"missing required member: {required}")
    if len(entries) > MAX_MEMBERS:
        raise PackageError("too many source members")
    try:
        submission = entries["submission.py"].decode("utf-8")
        requirements = entries["requirements.txt"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackageError("mandatory source files must be UTF-8") from exc
    class_name = _validate_submission_source(submission)
    _validate_requirements(requirements)
    return {"entries": entries, "className": class_name}


def build_archive(source: Path, output: Path) -> dict[str, object]:
    validated = validate_source_dir(source)
    entries: dict[str, bytes] = validated["entries"]  # type: ignore[assignment]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(entries, key=lambda n: n.encode("utf-8")):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            zf.writestr(info, entries[name])
    archive = buf.getvalue()
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise PackageError("archive too large")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(archive)
    return verify_archive_bytes(archive)


def verify_archive_bytes(archive: bytes) -> dict[str, object]:
    if not isinstance(archive, bytes) or not archive or len(archive) > MAX_ARCHIVE_BYTES:
        raise PackageError("invalid archive byte length")
    seen: set[str] = set()
    members: list[Member] = []
    sources: dict[str, bytes] = {}
    try:
        zf = zipfile.ZipFile(io.BytesIO(archive), "r")
    except zipfile.BadZipFile as exc:
        raise PackageError("invalid ZIP") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise PackageError("too many archive members")
        for info in infos:
            name = info.filename
            _safe_name(name)
            if name in seen:
                raise PackageError(f"duplicate archive member: {name}")
            seen.add(name)
            mode = (info.external_attr >> 16) & 0xFFFF
            kind = stat.S_IFMT(mode)
            if kind not in {0, stat.S_IFREG} or name.endswith("/"):
                raise PackageError(f"non-regular archive member: {name}")
            if info.file_size > MAX_MEMBER_BYTES or info.compress_size > MAX_MEMBER_BYTES:
                raise PackageError(f"member exceeds limit: {name}")
            data = zf.read(info)
            if len(data) != info.file_size:
                raise PackageError(f"member size mismatch: {name}")
            sources[name] = data
            members.append(Member(name, len(data), sha256(data)))
    for required in REQUIRED:
        if required not in sources:
            raise PackageError(f"missing required member: {required}")
    try:
        class_name = _validate_submission_source(sources["submission.py"].decode("utf-8"))
        _validate_requirements(sources["requirements.txt"].decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise PackageError("mandatory archive members must be UTF-8") from exc
    manifest = [m.__dict__ for m in sorted(members, key=lambda m: m.name.encode("utf-8"))]
    body: dict[str, object] = {
        "schema": SCHEMA,
        "archiveSha256": sha256(archive),
        "archiveBytes": len(archive),
        "optimizerClass": class_name,
        "memberCount": len(members),
        "members": manifest,
        "authority": {
            "officialSubmission": False,
            "officialScore": False,
            "prize": False,
            "payment": False,
        },
    }
    body["receiptSha256"] = sha256(canonical(body))
    return body


def verify_archive(path: Path) -> dict[str, object]:
    return verify_archive_bytes(path.read_bytes())
