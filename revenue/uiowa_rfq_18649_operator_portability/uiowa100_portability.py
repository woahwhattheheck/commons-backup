#!/usr/bin/env python3
"""Package and exercise the existing Iowa compiler/workbench without changing them.

All fixtures are synthetic. A verified package proves byte integrity, not source
independence, engagement acceptance, customer approval or current review authority.
Only this script's fixed rehearsal commands execute; manifests are data, not jobs.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys
import zipfile

SCHEMA = "uiowa.operator-portability.v1"
SELF = "revenue/uiowa_rfq_18649_operator_portability/uiowa100_portability.py"
WORKSHARE = "revenue/uiowa_rfq_18649_workshare"
WORKBENCH = "revenue/uiowa_rfq_18649_workbench"
MANIFEST = "PORTABLE-MANIFEST.json"
GUIDE = "START-HERE.md"
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 24 * 1024 * 1024
MAX_FILES = 256
SEEDS = (
    SELF,
    f"{WORKSHARE}/compiler.py",
    f"{WORKSHARE}/fixtures/synthetic_packet.json",
    f"{WORKSHARE}/fixtures/synthetic_authority.json",
    f"{WORKSHARE}/README.md",
    f"{WORKBENCH}/server.py",
    f"{WORKBENCH}/index.html",
    f"{WORKBENCH}/app.js",
    f"{WORKBENCH}/style.css",
    f"{WORKBENCH}/README.md",
)
PORTABLE_GUIDE = f"""# TJLabs — synthetic operator rehearsal\n\nThis is an offline preparation kit, not a University finding or accepted engagement.\nIt preserves the existing compiler and workbench; no replacement assessment model.\n\nUse Python 3.10 or newer in a Linux cloud environment. Native Windows has not been\nvalidated: the upstream compiler uses POSIX filesystem operations. No packages,\ncredentials, network connection or browser are needed for the CLI rehearsal.\n\nFrom this extracted directory, use a NEW output directory:\n\n```sh\npython3 {SELF} verify --root .\npython3 {SELF} rehearse --root . --out sample-run\n```\n\nRead `sample-run/REHEARSAL.md`, `report.json`, and `report.md`. The report must stay\n`UNTRUSTED_INSPECTION` / `HOLD_TRUSTED_AUTHORITY_REQUIRED`; a successful tool run\nis not a positive assessment. Missing/conflicting/stale evidence remains distinct.\n`sample-run/receipt.json` records source and output hashes and exact executed commands.\n\nFor an optional browser session, run:\n\n```sh\npython3 {WORKBENCH}/server.py --port 8765\n```\n\nOpen loopback http://127.0.0.1:8765/ on that same environment. Select the two JSON\nfixtures in `{WORKSHARE}/fixtures/`. Notes are draft-only and reset on new import.\nThe automated rehearsal exercises the real workbench adapter, not browser rendering.\nBrowser acceptance is explicitly NOT_RUN in its receipt.\n\n## Engagement navigation\n\n| Step | Available here | Inputs still required |\n|---|---|---|\n| Kickoff | This operating guide; parent workshare README | Agreed workshare, prime roles, scope and actual availability |\n| Evidence collection | Two clearly synthetic compiler fixture files and their source IDs | Authorized University records, exact versions/locators, interview evidence |\n| Analysis | Executed public compiler and 12-cell inspection | Evidence interpretation and independently established provenance |\n| Draft review | Existing workbench notes/dispositions and draft export | Reviewer comments and professional adjudication; no simulated reviewer approval |\n| Final delivery | Byte-bound report JSON, readable Markdown and reproducible kit | Accepted conclusions, finalized recommendations and prime-controlled delivery |\n| Optional readout | Report as technical support; not an executed presentation | Separately agreed readout, final deck, presenter and confirmed availability |\n\nThis portable runtime complements the UIOWA-100 operator guide and UIOWA-098\nintegration kit. It does not claim to implement their unfinished workflows.\nCopies retain original component authorship. Hashes establish consistency only;\nretain the package digest independently when transferring it. Never publish private\nUniversity evidence in the source repository. No customer contact, signing, payment,\nexternal submission, live infrastructure mutation or scheduling is performed.\n"""


class PortabilityError(ValueError):
    """An incomplete, inconsistent, or unsupported package/rehearsal."""


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw: bytes) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in items:
            if key in result:
                raise PortabilityError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def constant(value: str) -> None:
        raise PortabilityError(f"non-finite JSON value: {value}")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=constant)
    except (ValueError, UnicodeError) as exc:
        raise PortabilityError(f"invalid JSON: {exc}") from exc


def relative_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise PortabilityError(f"invalid relative path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ("", ".", "..") for p in name.split("/")):
        raise PortabilityError(f"unsafe relative path: {name!r}")
    if any(ord(c) < 32 for c in name):
        raise PortabilityError("control character in path")
    return name


def read_member(root: Path, name: str) -> bytes:
    path = root
    for part in relative_name(name).split("/"):
        path = path / part
        if path.is_symlink():
            raise PortabilityError(f"symlink is not a portable source file: {name}")
    if not path.is_file():
        raise PortabilityError(f"missing regular file: {name}")
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise PortabilityError(f"not a regular source: {name}")
        raw = handle.read(MAX_FILE + 1)
        after = os.fstat(handle.fileno())
    if len(raw) > MAX_FILE:
        raise PortabilityError(f"source exceeds size bound: {name}")
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if signature(before) != signature(after) or len(raw) != before.st_size:
        raise PortabilityError(f"source changed during read: {name}")
    return raw


def source_closure(root: Path, seeds: tuple[str, ...] = SEEDS) -> dict[str, bytes]:
    """Resolve the current flat local-module imports without executing source.

    The known workbench loads its compiler from a sibling directory, so both
    entrypoints are explicit seeds. Dynamic/relative local imports are not inferred.
    """
    result: dict[str, bytes] = {}
    todo = list(seeds)
    while todo:
        name = relative_name(todo.pop())
        if name in result:
            continue
        raw = read_member(root, name)
        result[name] = raw
        if len(result) > MAX_FILES or sum(map(len, result.values())) > MAX_TOTAL:
            raise PortabilityError("source closure exceeds package bounds")
        if not name.endswith(".py"):
            continue
        try:
            parsed = ast.parse(raw, filename=name)
        except (SyntaxError, UnicodeError) as exc:
            raise PortabilityError(f"cannot parse source {name}: {exc}") from exc
        modules: set[str] = set()
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    raise PortabilityError(f"relative import needs an explicit adapter: {name}")
                if node.module:
                    modules.add(node.module.split(".")[0])
        for module in sorted(modules):
            candidate = str(PurePosixPath(name).parent / (module + ".py"))
            if (root / candidate).exists() or (root / candidate).is_symlink():
                todo.append(candidate)
            elif module.startswith("workshare_"):
                raise PortabilityError(f"missing local import {module} required by {name}")
    return dict(sorted(result.items()))


def source_manifest(files: dict[str, bytes], revision: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise PortabilityError("source revision must be a complete Git commit SHA")
    return {
        "schema": SCHEMA, "source_revision": revision,
        "revision_binding": "operator-supplied commit label; file hashes identify actual bytes",
        "synthetic_only": True,
        "scope": "compiler/workbench public inspection runtime; not full engagement completion",
        "files": [{"path": name, "bytes": len(raw), "sha256": digest(raw),
                   "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}
                  for name, raw in sorted(files.items())],
    }


def pack(root: Path, output: Path, revision: str) -> dict:
    files = source_closure(root)
    files[GUIDE] = PORTABLE_GUIDE.encode("utf-8")
    manifest = source_manifest(files, revision)
    members = {**files, MANIFEST: canonical(manifest)}
    # Exclusive publication: callers choose a new output; existing files survive.
    with output.open("xb") as destination:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, raw in sorted(members.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, raw)
    return {"schema": SCHEMA, "files": len(files),
            "archive_sha256": digest(output.read_bytes()),
            "manifest_sha256": digest(members[MANIFEST])}


def validate_manifest(manifest: object) -> list[dict]:
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise PortabilityError("unsupported portable manifest")
    if manifest.get("synthetic_only") is not True:
        raise PortabilityError("this rehearsal requires an explicitly synthetic package")
    if not isinstance(manifest.get("source_revision"), str) or not re.fullmatch(r"[0-9a-f]{40}", manifest["source_revision"]):
        raise PortabilityError("invalid source revision label")
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_FILES:
        raise PortabilityError("invalid file inventory")
    seen: set[str] = set()
    total = 0
    for row in rows:
        if not isinstance(row, dict):
            raise PortabilityError("file inventory row is not an object")
        name = relative_name(row.get("path"))
        if name.casefold() in seen or name == MANIFEST:
            raise PortabilityError(f"duplicate/reserved member: {name}")
        seen.add(name.casefold())
        size = row.get("bytes")
        if type(size) is not int or not 0 <= size <= MAX_FILE:
            raise PortabilityError(f"invalid member size: {name}")
        if not isinstance(row.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise PortabilityError(f"invalid member digest: {name}")
        total += size
    if total > MAX_TOTAL:
        raise PortabilityError("package exceeds total size bound")
    if not set(SEEDS).issubset({row["path"] for row in rows}):
        raise PortabilityError("required runtime or synthetic fixtures absent from manifest")
    return rows


def verify(root: Path) -> dict:
    raw = read_member(root, MANIFEST)
    manifest = strict_json(raw)
    rows = validate_manifest(manifest)
    for row in rows:
        member = read_member(root, row["path"])
        if len(member) != row["bytes"] or digest(member) != row["sha256"]:
            raise PortabilityError(f"member integrity mismatch: {row['path']}")
    expected = set(source_closure(root)) | {GUIDE}
    if expected != {row["path"] for row in rows}:
        raise PortabilityError("manifest does not describe the complete runtime closure")
    return {"state": "BYTE_INTEGRITY_VERIFIED", "files": len(rows),
            "source_revision": manifest["source_revision"],
            "manifest_sha256": digest(raw), "source_authenticity_established": False}


def unpack(archive_path: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise PortabilityError("unpack destination must not exist")
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or len(names) > MAX_FILES + 1:
            raise PortabilityError("duplicate/oversized archive inventory")
        for info in archive.infolist():
            relative_name(info.filename)
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_ISLNK(mode) or info.file_size > MAX_FILE:
                raise PortabilityError("non-regular/oversized archive member")
        if MANIFEST not in names:
            raise PortabilityError("portable manifest missing")
        raw = archive.read(MANIFEST)
        rows = validate_manifest(strict_json(raw))
        if set(names) != {MANIFEST, *(r["path"] for r in rows)}:
            raise PortabilityError("archive and manifest inventories disagree")
        # Validate all bytes before creating the output tree.
        members = {MANIFEST: raw}
        for row in rows:
            data = archive.read(row["path"])
            if len(data) != row["bytes"] or digest(data) != row["sha256"]:
                raise PortabilityError(f"archive integrity mismatch: {row['path']}")
            members[row["path"]] = data
    output.mkdir(parents=False)
    for name, data in sorted(members.items()):
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(data)
    return verify(output)


def inspection_assertions(report: object) -> dict:
    if not isinstance(report, dict):
        raise PortabilityError("compiler report is not an object")
    if report.get("mode") != "UNTRUSTED_INSPECTION":
        raise PortabilityError("rehearsal must remain public untrusted inspection")
    if report.get("aggregate_state") != "HOLD_TRUSTED_AUTHORITY_REQUIRED":
        raise PortabilityError("untrusted inspection aggregate changed")
    trust = report.get("trust")
    if not isinstance(trust, dict):
        raise PortabilityError("inspection trust record is not an object")
    if any(trust.get(key) is not False for key in (
            "authority_root_supplied_out_of_band", "current_evidence_review_authority")):
        raise PortabilityError("inspection unexpectedly claims review authority")
    authority = report.get("external_authority")
    if not isinstance(authority, dict) or not authority or any(v is not False for v in authority.values()):
        raise PortabilityError("external authority fields must all remain false")
    matrix = report.get("assessment_matrix")
    if not isinstance(matrix, list) or len(matrix) != 12:
        raise PortabilityError("expected exactly twelve assessment cells")
    pairs: set[tuple[str, str]] = set()
    for cell in matrix:
        if not isinstance(cell, dict) or not all(isinstance(cell.get(k), str) for k in ("group", "dimension", "status")):
            raise PortabilityError("malformed assessment cell")
        pairs.add((cell["group"], cell["dimension"]))
        if cell.get("maturity") is not None or cell.get("confidence_bp") is not None:
            raise PortabilityError("public inspection must not carry authoritative ratings")
    groups = {p[0] for p in pairs}
    dimensions = {p[1] for p in pairs}
    if len(pairs) != 12 or len(groups) != 3 or len(dimensions) != 4:
        raise PortabilityError("assessment matrix is not a complete 3 x 4 product")
    return {"cells": len(matrix), "groups": sorted(groups),
            "dimensions": sorted(dimensions), "aggregate_state": report["aggregate_state"],
            "receipt_sha256": report.get("receipt_sha256")}


ADAPTER_CODE = '''import json, sys
from pathlib import Path
from server import CompilerAdapter
root = Path(sys.argv[1])
p = root / "revenue/uiowa_rfq_18649_workshare/fixtures"
report = CompilerAdapter().inspect(json.loads((p / "synthetic_packet.json").read_text()), json.loads((p / "synthetic_authority.json").read_text()))
print(json.dumps(report, sort_keys=True, ensure_ascii=False))
'''


def _run_recorded(argv: list[str], *, cwd: Path, environment: dict[str, str],
                  timeout_s: int, record: dict) -> subprocess.CompletedProcess:
    """Retain the attempt even when subprocess.run cannot return a process result.

    ATTEMPTED does not assert that the child started. None is an unknown exit code,
    never an invented successful exit. TimeoutExpired may contain bytes even with
    text=True; keep those exact bytes as hex alongside a readable UTF-8 rendering.
    """
    record.update({"state": "ATTEMPTED", "exit_code": None,
                   "stdout": "", "stderr": ""})

    def retain_streams(stdout: str | bytes | None, stderr: str | bytes | None) -> None:
        for name, value in (("stdout", stdout), ("stderr", stderr)):
            if isinstance(value, bytes):
                record[name + "_bytes_hex"] = value.hex()
                record[name] = value.decode("utf-8", errors="backslashreplace")
            else:
                record[name] = "" if value is None else value

    try:
        proc = subprocess.run(argv, cwd=cwd, env=environment, capture_output=True,
                              text=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired as exc:
        record.update({"state": "TIMED_OUT", "timeout_s": exc.timeout,
                       "error_type": type(exc).__name__, "error": str(exc)})
        retain_streams(exc.output, exc.stderr)
        raise
    except OSError as exc:
        record.update({"state": "LAUNCH_ERROR", "error_type": type(exc).__name__,
                       "error": str(exc)})
        raise
    except (ValueError, subprocess.SubprocessError) as exc:
        record.update({"state": "PROCESS_ERROR", "error_type": type(exc).__name__,
                       "error": str(exc)})
        raise
    record.update({"state": "EXITED", "exit_code": proc.returncode})
    retain_streams(proc.stdout, proc.stderr)
    return proc


def rehearse(root: Path, output: Path) -> dict:
    root = root.resolve()
    package = verify(root)
    output.mkdir(parents=False, exist_ok=False)
    output = output.resolve()
    python = [sys.executable] + (["-O"] if sys.flags.optimize else [])
    environment = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    commands: list[dict] = []

    def execute(label: str, argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
        shown = [part.replace(str(output), "{OUT}").replace(str(root), "{ROOT}")
                 for part in argv]
        record = {"step": label, "argv": ["python3"] + python[1:] + shown,
                  "cwd": "{ROOT}/" + str(cwd.relative_to(root))}
        commands.append(record)
        proc = _run_recorded(python + argv, cwd=cwd, environment=environment,
                             timeout_s=60, record=record)
        if proc.returncode:
            raise PortabilityError(f"{label} exited {proc.returncode}: {proc.stderr.strip()}")
        return proc

    receipt: dict = {"schema": SCHEMA, "synthetic_only": True, "state": "RUNNING",
                    "package": package, "environment": {"python": platform.python_version(),
                    "platform": platform.system(), "optimized": bool(sys.flags.optimize)},
                    "commands": commands, "browser_acceptance": "NOT_RUN",
                    "engagement_completion": "NOT_ESTABLISHED"}
    try:
        workshare = root / WORKSHARE
        execute("compiler_compile", ["compiler.py", "compile", "fixtures/synthetic_packet.json",
                "fixtures/synthetic_authority.json", str(output / "report.json")], workshare)
        check = execute("compiler_verify", ["compiler.py", "verify", str(output / "report.json")], workshare)
        if not check.stdout.startswith("UNTRUSTED_INTEGRITY_ONLY "):
            raise PortabilityError("verify did not report semantic integrity only")
        execute("compiler_render", ["compiler.py", "render", str(output / "report.json"),
                str(output / "report.md")], workshare)
        report = strict_json((output / "report.json").read_bytes())
        receipt["inspection"] = inspection_assertions(report)
        adapted = execute("real_workbench_adapter", ["-c", ADAPTER_CODE, str(root)], root / WORKBENCH)
        if strict_json(adapted.stdout.encode()) != report:
            raise PortabilityError("workbench adapter and public CLI reports disagree")
        # Re-check inputs/source after execution: a moving input cannot receive PASS.
        after = verify(root)
        if after != package:
            raise PortabilityError("package changed during rehearsal")
        receipt["outputs"] = [{"path": name, "sha256": digest((output / name).read_bytes()),
                               "bytes": (output / name).stat().st_size}
                              for name in ("report.json", "report.md")]
        receipt["state"] = "PASS_PORTABLE_SYNTHETIC_REHEARSAL"
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        receipt["state"] = "FAIL"
        receipt["error"] = str(exc)
        raise PortabilityError(str(exc)) from exc
    finally:
        with (output / "receipt.json").open("xb") as handle:
            handle.write(canonical(receipt))
        text = ("# Synthetic operator rehearsal\n\n" + receipt["state"] + "\n\n"
                "This is tool execution, not University findings or engagement approval.\n\n"
                + "\n".join(f"- {r['step']}: {r['state']}; "
                            + (f"exit {r['exit_code']}" if r['exit_code'] is not None
                               else "no exit code available") for r in commands)
                + "\n\nBrowser rendering: NOT_RUN. Actual compiler and adapter execution is recorded above.\n"
                + ("\nFailure: " + receipt["error"] + "\n" if "error" in receipt else ""))
        with (output / "REHEARSAL.md").open("x", encoding="utf-8") as handle:
            handle.write(text)
    return receipt


def acceptance(root: Path, output: Path, revision: str) -> dict:
    """Two independent unpack locations must produce identical report bytes.

    Failed attempts retain acceptance-failure.json; acceptance.json is success-only.
    The failure artifact is diagnostic evidence, not a partial acceptance certificate.
    """
    output.mkdir(parents=False, exist_ok=False)
    invocations: list[dict] = []
    failure = {"schema": SCHEMA, "state": "RUNNING", "synthetic_only": True,
               "source_revision": revision, "stage": "PACKAGING",
               "packaged_runner_invocations": invocations,
               "browser_acceptance": "NOT_RUN", "engagement_completion": "NOT_ESTABLISHED"}
    try:
        first = pack(root, output / "operator-kit.zip", revision)
        second = pack(root, output / "repeat-kit.zip", revision)
        if first != second:
            raise PortabilityError("repeat packaging was not byte-identical")
        failure["package"] = first
        results = []
        for name in ("operator-one", "operator-two"):
            failure["stage"] = "UNPACKING_" + name.upper().replace("-", "_")
            location = (output / name).resolve()
            run_output = (output / (name + "-run")).resolve()
            unpack(output / "operator-kit.zip", location)
            python = [sys.executable] + (["-O"] if sys.flags.optimize else [])
            argv = python + [str(location / SELF), "rehearse", "--root", str(location),
                             "--out", str(run_output)]
            environment = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            shown = [part.replace(str(run_output), "{OUT}").replace(str(location), "{ROOT}")
                     for part in argv[1:]]
            invocation = {"operator": name, "entrypoint": SELF,
                          "argv": ["python3"] + shown, "cwd": "{ROOT}",
                          "runner_sha256": digest(read_member(location, SELF))}
            invocations.append(invocation)
            failure["stage"] = "RUNNING_" + name.upper().replace("-", "_")
            proc = _run_recorded(argv, cwd=location, environment=environment,
                                 timeout_s=300, record=invocation)
            if proc.returncode:
                raise PortabilityError(f"packaged {name} runner exited {proc.returncode}: {proc.stderr.strip()}")
            result = strict_json(proc.stdout.encode("utf-8"))
            if not isinstance(result, dict) or result.get("state") != "PASS_PORTABLE_SYNTHETIC_REHEARSAL":
                raise PortabilityError(f"packaged {name} runner did not report rehearsal success")
            if strict_json((run_output / "receipt.json").read_bytes()) != result:
                raise PortabilityError(f"packaged {name} stdout and durable receipt disagree")
            results.append(result)
        failure["stage"] = "COMPARING_OUTPUTS"
        if results[0]["outputs"] != results[1]["outputs"]:
            raise PortabilityError("second operator reports were not byte-identical")
        receipt = {"schema": SCHEMA, "state": "PASS_TWO_OPERATOR_REPRODUCTION",
                   "package": first, "source_revision": revision,
                   "outputs": results[0]["outputs"], "inspection": results[0]["inspection"],
                   "commands_per_operator": len(results[0]["commands"]),
                   "packaged_runner_invocations": invocations,
                   "browser_acceptance": "NOT_RUN", "engagement_completion": "NOT_ESTABLISHED"}
        failure["stage"] = "PUBLISHING_SUCCESS_RECEIPT"
        with (output / "acceptance.json").open("xb") as handle:
            handle.write(canonical(receipt))
        return receipt
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        failure.update({"state": "FAIL", "error_type": type(exc).__name__, "error": str(exc)})
        with (output / "acceptance-failure.json").open("xb") as handle:
            handle.write(canonical(failure))
        raise PortabilityError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("pack", "verify", "rehearse", "acceptance"):
        part = sub.add_parser(command)
        part.add_argument("--root", type=Path, required=True)
        if command != "verify":
            part.add_argument("--out", type=Path, required=True)
        if command in ("pack", "acceptance"):
            part.add_argument("--revision", required=True)
    part = sub.add_parser("unpack")
    part.add_argument("--archive", type=Path, required=True)
    part.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if sys.version_info < (3, 10):
            raise PortabilityError("Python 3.10+ is required")
        if args.command == "unpack":
            result = unpack(args.archive, args.out)
        elif args.command == "pack":
            result = pack(args.root, args.out, args.revision)
        elif args.command == "verify":
            result = verify(args.root)
        elif args.command == "acceptance":
            result = acceptance(args.root, args.out, args.revision)
        else:
            result = rehearse(args.root, args.out)
        print(canonical(result).decode(), end="")
        return 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
