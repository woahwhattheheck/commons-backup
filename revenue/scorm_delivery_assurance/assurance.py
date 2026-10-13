from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import urllib.parse
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping
import xml.etree.ElementTree as ET

SCHEMA = "tjlabs.scorm-delivery-assurance/v1"
POLICY_SCHEMA = "tjlabs.scorm-delivery-assurance-policy/v1"
SIDECAR_SCHEMA = "tjlabs.scorm-course-evidence/v1"
READY = "READY_FOR_LMS_SANDBOX_REVIEW"
HOLD = "HOLD"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_XML_DECL_ENCODING = re.compile(
    r"^\s*<\?xml\b[^>]*\bencoding\s*=\s*(['\"])([^'\"]+)\1",
    re.IGNORECASE,
)
_FORBIDDEN_XML_DECL = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


class AssuranceError(ValueError):
    pass


def _pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise AssuranceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(raw: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                AssuranceError(f"non-finite JSON constant: {value}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise AssuranceError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _keys(obj: Mapping[str, Any], required: set[str]) -> None:
    if not isinstance(obj, Mapping):
        raise AssuranceError("expected object")
    missing = required - set(obj)
    unknown = set(obj) - required
    if missing:
        raise AssuranceError(f"missing keys: {sorted(missing)}")
    if unknown:
        raise AssuranceError(f"unknown keys: {sorted(unknown)}")


def _int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AssuranceError(f"{name} must be integer")
    if not low <= value <= high:
        raise AssuranceError(f"{name} out of range")
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise AssuranceError(f"{name} must be boolean")
    return value


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise AssuranceError(f"invalid {name}")
    return value


def _member(name: Any) -> str:
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise AssuranceError("unsafe ZIP member name")
    if name.startswith("/"):
        raise AssuranceError(f"absolute ZIP member path: {name}")
    path = PurePosixPath(name)
    if any(part in ("", ".", "..") for part in path.parts) or str(path) != name.rstrip("/"):
        raise AssuranceError(f"non-canonical ZIP member path: {name}")
    return name.rstrip("/")


def _href(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise AssuranceError("unsafe manifest href")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme or parsed.netloc:
        raise AssuranceError(f"external manifest href: {value}")
    path = urllib.parse.unquote(parsed.path)
    if not path or path.startswith("/"):
        raise AssuranceError(f"invalid manifest href: {value}")
    return _member(path)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(parent: ET.Element | None, name: str) -> str | None:
    if parent is None:
        return None
    for child in list(parent):
        if _local(child.tag) == name:
            return (child.text or "").strip()
    return None


def _unique_child_text(parent: ET.Element, name: str) -> str:
    children = [child for child in list(parent) if _local(child.tag) == name]
    if len(children) != 1:
        raise AssuranceError(f"manifest metadata must contain exactly one {name}")
    text = (children[0].text or "").strip()
    if not text:
        raise AssuranceError(f"manifest metadata {name} must be non-empty")
    return text


def _manifest_text(raw: bytes) -> str:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AssuranceError("imsmanifest.xml must be UTF-8") from exc
    if "\x00" in text:
        raise AssuranceError("imsmanifest.xml must be UTF-8 without NUL bytes")
    match = _XML_DECL_ENCODING.match(text)
    if match:
        encoding = re.sub(r"[-_]", "", match.group(2)).casefold()
        if encoding != "utf8":
            raise AssuranceError("imsmanifest.xml XML declaration must specify UTF-8")
    if _FORBIDDEN_XML_DECL.search(text):
        raise AssuranceError("manifest DTD/entity declarations are not accepted")
    return text


def default_policy() -> dict[str, Any]:
    return {
        "schema": POLICY_SCHEMA,
        "accepted_standards": ["SCORM_1_2", "SCORM_2004"],
        "max_files": 5000,
        "max_total_uncompressed_bytes": 500_000_000,
        "max_single_file_bytes": 100_000_000,
        "require_accessibility_evidence": True,
        "require_assessment_metadata": True,
        "require_source_revision_sha256": True,
    }


def validate_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    _keys(policy, {
        "schema", "accepted_standards", "max_files",
        "max_total_uncompressed_bytes", "max_single_file_bytes",
        "require_accessibility_evidence", "require_assessment_metadata",
        "require_source_revision_sha256",
    })
    if policy["schema"] != POLICY_SCHEMA:
        raise AssuranceError("unsupported policy schema")
    standards = policy["accepted_standards"]
    allowed = {"SCORM_1_2", "SCORM_2004"}
    if not isinstance(standards, list) or not standards or any(x not in allowed for x in standards):
        raise AssuranceError("invalid accepted_standards")
    if len(set(standards)) != len(standards):
        raise AssuranceError("duplicate accepted standard")
    return {
        "schema": POLICY_SCHEMA,
        "accepted_standards": sorted(standards),
        "max_files": _int(policy["max_files"], "max_files", 1, 100_000),
        "max_total_uncompressed_bytes": _int(
            policy["max_total_uncompressed_bytes"],
            "max_total_uncompressed_bytes", 1, 10_000_000_000,
        ),
        "max_single_file_bytes": _int(
            policy["max_single_file_bytes"],
            "max_single_file_bytes", 1, 2_000_000_000,
        ),
        "require_accessibility_evidence": _bool(
            policy["require_accessibility_evidence"], "require_accessibility_evidence"
        ),
        "require_assessment_metadata": _bool(
            policy["require_assessment_metadata"], "require_assessment_metadata"
        ),
        "require_source_revision_sha256": _bool(
            policy["require_source_revision_sha256"], "require_source_revision_sha256"
        ),
    }


def _standard(root: ET.Element) -> str:
    metadata_nodes = [child for child in list(root) if _local(child.tag) == "metadata"]
    if len(metadata_nodes) != 1:
        raise AssuranceError("manifest must contain exactly one root metadata element")
    metadata = metadata_nodes[0]
    schema = " ".join(_unique_child_text(metadata, "schema").split()).casefold()
    if schema != "adl scorm":
        raise AssuranceError("manifest metadata schema must be ADL SCORM")
    version = " ".join(_unique_child_text(metadata, "schemaversion").split()).casefold()
    if version == "1.2":
        return "SCORM_1_2"
    if version in {"1.3", "cam 1.3", "2004"} or re.fullmatch(
        r"2004(?: \d+(?:st|nd|rd|th) edition)?", version
    ):
        return "SCORM_2004"
    raise AssuranceError("unsupported SCORM schemaversion declaration")


def _sidecar(
    raw: bytes,
    members: set[str],
    resources: Mapping[str, str],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        obj = strict_json_loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise AssuranceError("sidecar must be UTF-8") from exc
    _keys(obj, {"schema", "course_id", "source_revision_sha256", "modules"})
    if obj["schema"] != SIDECAR_SCHEMA:
        raise AssuranceError("unsupported sidecar schema")
    course_id = _id(obj["course_id"], "course_id")
    revision = obj["source_revision_sha256"]
    if not isinstance(revision, str) or (
        policy["require_source_revision_sha256"] and not _SHA256.fullmatch(revision)
    ):
        raise AssuranceError("invalid source_revision_sha256")
    modules = obj["modules"]
    if not isinstance(modules, list) or not modules:
        raise AssuranceError("modules must be non-empty list")
    seen_ids: set[str] = set()
    seen_resources: set[str] = set()
    out: list[dict[str, Any]] = []
    for index, module in enumerate(modules):
        _keys(module, {"id", "resource_id", "title", "assessment", "completion", "accessibility"})
        module_id = _id(module["id"], f"modules[{index}].id")
        resource_id = _id(module["resource_id"], f"modules[{index}].resource_id")
        if module_id in seen_ids:
            raise AssuranceError(f"duplicate module id: {module_id}")
        if resource_id in seen_resources:
            raise AssuranceError(f"duplicate module resource_id: {resource_id}")
        if resource_id not in resources:
            raise AssuranceError(f"module references unknown resource: {resource_id}")
        seen_ids.add(module_id)
        seen_resources.add(resource_id)
        title = module["title"]
        if not isinstance(title, str) or not title.strip() or len(title) > 300:
            raise AssuranceError("invalid module title")

        assessment = module["assessment"]
        _keys(assessment, {"required", "passing_score"})
        assessment_required = _bool(assessment["required"], "assessment.required")
        passing = assessment["passing_score"]
        if assessment_required:
            passing = _int(passing, "assessment.passing_score", 0, 100)
        elif passing is not None:
            raise AssuranceError("passing_score must be null when assessment is not required")
        if policy["require_assessment_metadata"] and not assessment_required:
            raise AssuranceError("policy requires assessment metadata for every module")

        completion = module["completion"]
        _keys(completion, {"required"})
        completion_required = _bool(completion["required"], "completion.required")
        if not completion_required:
            raise AssuranceError("module completion tracking must be required")

        access = module["accessibility"]
        _keys(access, {"transcript", "captions"})
        transcript = _href(access["transcript"]) if access["transcript"] is not None else None
        captions_raw = access["captions"]
        if not isinstance(captions_raw, list):
            raise AssuranceError("accessibility.captions must be list")
        captions = [_href(x) for x in captions_raw]
        if len(set(captions)) != len(captions):
            raise AssuranceError("duplicate caption evidence path")
        if policy["require_accessibility_evidence"] and (not transcript or not captions):
            raise AssuranceError("policy requires transcript and caption evidence per module")
        evidence = ([transcript] if transcript else []) + captions
        missing = [path for path in evidence if path not in members]
        if missing:
            raise AssuranceError(f"missing accessibility evidence: {missing}")
        if any(not path.lower().endswith((".vtt", ".srt")) for path in captions):
            raise AssuranceError("caption evidence must use .vtt or .srt")

        out.append({
            "id": module_id,
            "resource_id": resource_id,
            "title": title.strip(),
            "launch": resources[resource_id],
            "assessment": {"required": assessment_required, "passing_score": passing},
            "completion": {"required": completion_required},
            "accessibility": {"transcript": transcript, "captions": sorted(captions)},
        })
    return {
        "schema": SIDECAR_SCHEMA,
        "course_id": course_id,
        "source_revision_sha256": revision,
        "modules": sorted(out, key=lambda x: x["id"]),
    }


def compile_assurance(
    package_bytes: bytes,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(package_bytes, (bytes, bytearray)):
        raise AssuranceError("package_bytes must be bytes")
    package_bytes = bytes(package_bytes)
    policy_norm = validate_policy(policy or default_policy())
    reasons: list[str] = []
    facts: dict[str, Any] = {
        "package_sha256": sha256(package_bytes),
        "policy_sha256": sha256(canonical_bytes(policy_norm)),
    }
    try:
        with zipfile.ZipFile(BytesIO(package_bytes), "r") as archive:
            infos = archive.infolist()
            if len(infos) > policy_norm["max_files"]:
                raise AssuranceError("package file count exceeds policy")
            exact: set[str] = set()
            folded: set[str] = set()
            files: list[zipfile.ZipInfo] = []
            total = 0
            for info in infos:
                name = _member(info.filename)
                if info.is_dir():
                    continue
                if name in exact:
                    raise AssuranceError(f"duplicate ZIP member: {name}")
                folded_name = name.casefold()
                if folded_name in folded:
                    raise AssuranceError(f"case-colliding ZIP member: {name}")
                mode = (info.external_attr >> 16) & 0xFFFF
                if mode and stat.S_IFMT(mode) == stat.S_IFLNK:
                    raise AssuranceError(f"symlink ZIP member: {name}")
                if info.file_size > policy_norm["max_single_file_bytes"]:
                    raise AssuranceError(f"member exceeds max size: {name}")
                total += info.file_size
                if total > policy_norm["max_total_uncompressed_bytes"]:
                    raise AssuranceError("package uncompressed size exceeds policy")
                exact.add(name)
                folded.add(folded_name)
                files.append(info)
            if "imsmanifest.xml" not in exact:
                raise AssuranceError("missing root imsmanifest.xml")
            if "course.assurance.json" not in exact:
                raise AssuranceError("missing course.assurance.json evidence sidecar")

            contents: dict[str, bytes] = {}
            inventory: list[dict[str, Any]] = []
            for info in sorted(files, key=lambda x: x.filename):
                data = archive.read(info)
                contents[info.filename] = data
                inventory.append({"path": info.filename, "bytes": len(data), "sha256": sha256(data)})

            manifest = contents["imsmanifest.xml"]
            text = _manifest_text(manifest)
            try:
                root = ET.fromstring(text)
            except ET.ParseError as exc:
                raise AssuranceError(f"invalid imsmanifest.xml: {exc}") from exc
            if _local(root.tag) != "manifest":
                raise AssuranceError("manifest root element must be manifest")
            standard = _standard(root)
            if standard not in policy_norm["accepted_standards"]:
                raise AssuranceError(f"SCORM standard not accepted by policy: {standard}")

            resources: dict[str, str] = {}
            declared = {"imsmanifest.xml", "course.assurance.json"}
            for element in root.iter():
                if _local(element.tag) != "resource":
                    continue
                resource_id = _id(element.attrib.get("identifier"), "resource identifier")
                if resource_id in resources:
                    raise AssuranceError(f"duplicate resource identifier: {resource_id}")
                launch = _href(element.attrib.get("href"))
                if launch not in exact:
                    raise AssuranceError(f"resource launch missing from package: {launch}")
                resources[resource_id] = launch
                declared.add(launch)
                for child in element.iter():
                    if _local(child.tag) == "file":
                        path = _href(child.attrib.get("href"))
                        if path not in exact:
                            raise AssuranceError(f"manifest-declared file missing: {path}")
                        declared.add(path)
            if not resources:
                raise AssuranceError("manifest declares no launch resources")

            referenced: set[str] = set()
            for element in root.iter():
                if _local(element.tag) == "item" and "identifierref" in element.attrib:
                    ref = _id(element.attrib["identifierref"], "item identifierref")
                    if ref not in resources:
                        raise AssuranceError(f"organization item references unknown resource: {ref}")
                    referenced.add(ref)
            if not referenced:
                raise AssuranceError("manifest organizations reference no resources")

            sidecar = _sidecar(contents["course.assurance.json"], exact, resources, policy_norm)
            sidecar_resources = {module["resource_id"] for module in sidecar["modules"]}
            if sidecar_resources != referenced:
                raise AssuranceError(
                    "sidecar module resource set must exactly match organization references"
                )
            for module in sidecar["modules"]:
                access = module["accessibility"]
                if access["transcript"]:
                    declared.add(access["transcript"])
                declared.update(access["captions"])

            facts.update({
                "standard": standard,
                "course_id": sidecar["course_id"],
                "source_revision_sha256": sidecar["source_revision_sha256"],
                "module_count": len(sidecar["modules"]),
                "resource_count": len(resources),
                "file_count": len(files),
                "total_uncompressed_bytes": total,
                "manifest_sha256": sha256(manifest),
                "sidecar_sha256": sha256(contents["course.assurance.json"]),
                "referenced_resource_ids": sorted(referenced),
                "undeclared_noncritical_paths": sorted(exact - declared),
                "modules": sidecar["modules"],
                "inventory": inventory,
            })
    except (zipfile.BadZipFile, RuntimeError, AssuranceError, KeyError, TypeError) as exc:
        reasons.append(str(exc))

    core = {
        "schema": SCHEMA,
        "status": HOLD if reasons else READY,
        "reasons": sorted(set(reasons)),
        "facts": facts,
        "authority": {
            "scorm_spec_certified": False,
            "accessibility_certified": False,
            "instructional_quality_approved": False,
            "lms_production_approved": False,
            "buyer_acceptance": False,
            "payment_or_revenue": False,
        },
    }
    return {**core, "receipt_sha256": sha256(canonical_bytes(core))}


def verify_assurance(
    package_bytes: bytes,
    report: Mapping[str, Any],
    policy: Mapping[str, Any] | None = None,
) -> bool:
    return canonical_bytes(compile_assurance(package_bytes, policy)) == canonical_bytes(report)


def _generation(st: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        st.st_dev,
        st.st_ino,
        st.st_mode,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
    )


def _read_regular(path: Path, limit: int) -> bytes:
    flags = os.O_RDONLY
    for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK", "O_BINARY"):
        flags |= int(getattr(os, name, 0))
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise AssuranceError(f"not a regular file: {path}")
        if before.st_size > limit:
            raise AssuranceError(f"input exceeds size limit: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > limit:
                raise AssuranceError(f"input exceeds size limit: {path}")
        after = os.fstat(fd)
        if _generation(before) != _generation(after) or after.st_size != total:
            raise AssuranceError(f"input changed during read: {path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_BINARY"):
        flags |= int(getattr(os, name, 0))
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise AssuranceError(f"refusing to overwrite output: {path}") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if fd >= 0:
            os.close(fd)
    # Deliberately do not unlink by pathname on late write/fsync failure. If another
    # actor replaces the directory entry, pathname cleanup could delete foreign bytes.
    # A partial file created by this invocation is safer to preserve for operator review.


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic SCORM delivery assurance")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("package")
    compile_p.add_argument("output")
    compile_p.add_argument("--policy")
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("package")
    verify_p.add_argument("report")
    verify_p.add_argument("--policy")
    args = parser.parse_args(argv)
    try:
        package = _read_regular(Path(args.package), 600_000_000)
        policy = None
        if args.policy:
            raw = _read_regular(Path(args.policy), 2_000_000).decode("utf-8")
            obj = strict_json_loads(raw)
            if not isinstance(obj, Mapping):
                raise AssuranceError("policy must be object")
            policy = validate_policy(obj)
        if args.command == "compile":
            report = compile_assurance(package, policy)
            _exclusive(Path(args.output), canonical_bytes(report) + b"\n")
            print(json.dumps({"status": report["status"], "receipt_sha256": report["receipt_sha256"]}, sort_keys=True))
            return 0 if report["status"] == READY else 2
        raw = _read_regular(Path(args.report), 2_000_000).decode("utf-8")
        report = strict_json_loads(raw)
        ok = verify_assurance(package, report, policy)
        print(json.dumps({"verified": ok}, sort_keys=True))
        return 0 if ok else 3
    except (AssuranceError, OSError, UnicodeDecodeError) as exc:
        print(json.dumps({"error": str(exc), "verified": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
