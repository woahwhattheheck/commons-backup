#!/usr/bin/env python3
"""CCC vault harvest / snapshot toolchain — Class D dead-end boxes.

Stdlib-only CLI. Gold copies OUT only. Never writes the source. Never
copies live ~/.claude or real CCC / secret bytes. Repo tests use wholly
synthetic fixtures.

  python3 host/ccc_snapshot_toolchain.py plan --source <root>
  python3 host/ccc_snapshot_toolchain.py snapshot --source <root> --dest <empty>
  python3 host/ccc_snapshot_toolchain.py verify --source <root> --dest <box>
  python3 host/ccc_snapshot_toolchain.py self-test

Leftover: ccc-snapshot-toolchain-working-20260901-01
Prior false-complete card (do not remint): ship-ccc-vault-harvest-toolchain-20260901-01
Issue: #7238
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable


SCHEMA = "commons-ccc-snapshot-protocol/v1"
LEFTOVER_ID = "ccc-snapshot-toolchain-working-20260901-01"
PRIOR_FALSE_COMPLETE_ID = "ship-ccc-vault-harvest-toolchain-20260901-01"
ISSUE = 7238
PROTOCOL_CLASS = "D"
BOX_KIND = "DEAD_END"
DIRECTION = "GOLD_OUT_ONLY"
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
PROMPT_LEAK_MARKER = "CCC_PROMPT_LEAK"
DATA_LEAK_MARKER = "CCC_DATA_LEAK"
FORBIDDEN_COMPONENTS = frozenset({".claude"})
RECEIPT_NAMES = (
    "source_before.json",
    "source_after.json",
    "destination.json",
    "isolation.json",
    "equality.json",
    "result.json",
)

# Tests may install a hook that runs after the first gold file is copied.
_mutation_hook: Callable[[], None] | None = None


class ToolchainError(Exception):
    """Fail-closed harvest error with one precise repair."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        repair: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.repair = repair or f"fix {code}: {message}"
        self.evidence = evidence or {}

    def as_result(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "id": LEFTOVER_ID,
            "ok": False,
            "state": "FAIL",
            "code": self.code,
            "message": self.message,
            "repair": self.repair,
            "evidence": self.evidence,
        }


def canonical_json(payload: dict[str, Any] | list[Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    fd = os.open(str(path), os.O_RDONLY)
    try:
        with os.fdopen(fd, "rb", closefd=True) as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    return digest.hexdigest()


def tree_hash(entries: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(str(entry["rel"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(int(entry["size"])).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(entry["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def split_rel(rel: str) -> tuple[str, ...]:
    parts: list[str] = []
    for chunk in str(rel).replace("\\", "/").split("/"):
        if chunk in ("", "."):
            continue
        if chunk == "..":
            raise ToolchainError(
                "LINK_ESCAPE",
                "relative path escapes the vault root",
                repair="remove .. components and retry with a path inside the root",
                evidence={"rel": rel},
            )
        parts.append(chunk)
    if not parts:
        raise ToolchainError("LINK_ESCAPE", "empty relative path", evidence={"rel": rel})
    return tuple(parts)


def windows_rel(rel: str) -> str:
    return str(rel).replace("/", "\\")


def posix_rel(rel: str) -> str:
    return str(rel).replace("\\", "/")


def display_path(path: Path) -> str:
    return path.resolve().as_posix() if path.exists() else path.absolute().as_posix()


def protocol_pins() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "id": LEFTOVER_ID,
        "issue": ISSUE,
        "prior_false_complete_id": PRIOR_FALSE_COMPLETE_ID,
        "class": PROTOCOL_CLASS,
        "box_kind": BOX_KIND,
        "direction": DIRECTION,
        "write_back": False,
        "peer_read": False,
        "egress": False,
        "shared_claude": False,
        "claude_on_laptop": False,
        "owner_disk_writeback": False,
        "peer_remint_secrets": False,
        "real_ccc_bytes": False,
        "stdlib_only": True,
    }


def _is_reparse(path: Path, st: os.stat_result | None = None) -> bool:
    if path.is_symlink():
        return True
    info = st or path.lstat()
    attrs = int(getattr(info, "st_file_attributes", 0) or 0)
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def _parts_have_claude(path: Path) -> bool:
    raw = posix_rel(str(path))
    bits = [bit for bit in raw.split("/") if bit]
    if any(bit in FORBIDDEN_COMPONENTS for bit in bits):
        return True
    try:
        return any(part in FORBIDDEN_COMPONENTS for part in path.parts)
    except Exception:
        return ".claude" in raw


def refuse_shared_claude(path: Path, *, role: str) -> None:
    home_claude = Path.home() / ".claude"
    raw = posix_rel(str(path))
    if _parts_have_claude(path):
        raise ToolchainError(
            "SHARED_CLAUDE",
            f"{role} path names a shared .claude store",
            repair="use a synthetic or operator vault that is not ~/.claude",
            evidence={"role": role, "path": raw},
        )
    try:
        resolved = path.resolve() if path.exists() else path.expanduser().absolute()
    except OSError:
        resolved = path.expanduser().absolute()
    if resolved == home_claude or home_claude in resolved.parents:
        raise ToolchainError(
            "SHARED_CLAUDE",
            f"{role} resolves to the live home .claude store",
            repair="do not read or write ~/.claude; harvest synthetic gold only in-repo",
            evidence={"role": role, "path": display_path(resolved)},
        )


def refuse_home_writeback(dest: Path) -> None:
    home = Path.home().resolve()
    try:
        target = dest.resolve() if dest.exists() else dest.expanduser().absolute()
    except OSError:
        target = dest.expanduser().absolute()
    if target == home:
        raise ToolchainError(
            "WRITE_BACK",
            "destination is the home directory",
            repair="choose an empty dead-end box outside home",
            evidence={"dest": display_path(target)},
        )


def same_or_nested(left: Path, right: Path) -> bool:
    try:
        left_r = left.resolve() if left.exists() else left.absolute()
        right_r = right.resolve() if right.exists() else right.absolute()
    except OSError:
        left_r, right_r = left.absolute(), right.absolute()
    if left_r == right_r:
        return True
    try:
        right_r.relative_to(left_r)
        return True
    except ValueError:
        pass
    try:
        left_r.relative_to(right_r)
        return True
    except ValueError:
        return False


def refuse_alias(source: Path, dest: Path) -> None:
    if same_or_nested(source, dest):
        raise ToolchainError(
            "ALIAS",
            "source and destination alias or nest",
            repair="choose a dest that is a separate empty directory",
            evidence={
                "source": display_path(source),
                "dest": display_path(dest),
            },
        )
    if source.exists() and dest.exists():
        try:
            if os.path.samestat(source.stat(), dest.stat()):
                raise ToolchainError(
                    "ALIAS",
                    "source and destination are the same inode",
                    repair="choose a dest that is a separate empty directory",
                )
        except OSError:
            pass


def dest_must_be_absent_or_empty(dest: Path) -> None:
    if not dest.exists():
        return
    if not dest.is_dir() or dest.is_symlink() or _is_reparse(dest):
        raise ToolchainError(
            "DEST_REUSE",
            "destination exists and is not an empty directory",
            repair="supply a missing path or a truly empty directory",
            evidence={"dest": display_path(dest)},
        )
    try:
        next(dest.iterdir())
    except StopIteration:
        return
    raise ToolchainError(
        "DEST_REUSE",
        "destination already has contents",
        repair="use a fresh empty dead-end box; never reuse a box",
        evidence={"dest": display_path(dest)},
    )


def apply_dead_end_mode(path: Path) -> int:
    try:
        os.chmod(path, 0o700)
    except OSError as error:
        raise ToolchainError(
            "UNVERIFIABLE_ISOLATION",
            f"cannot set dead-end mode on {path}: {error}",
            repair="place the box on a filesystem that can hold 0700 and retry",
            evidence={"path": display_path(path)},
        ) from error
    mode = path.stat().st_mode & 0o777
    if os.name != "nt" and mode & 0o077:
        raise ToolchainError(
            "UNVERIFIABLE_ISOLATION",
            f"dead-end mode still peer-readable: {oct(mode)}",
            repair="chmod 0700 the destination and retry",
            evidence={"path": display_path(path), "mode": oct(mode)},
        )
    return mode


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ToolchainError(
            "MANIFEST_MISMATCH",
            f"cannot read {path.name}: {error}",
            repair=f"restore {path.name} from the capture evidence",
            evidence={"path": display_path(path)},
        ) from error
    if not isinstance(data, dict):
        raise ToolchainError(
            "MANIFEST_MISMATCH",
            f"{path.name} is not an object",
            repair=f"replace {path.name} with the canonical capture object",
        )
    return data


def write_exclusive_json(path: Path, payload: dict[str, Any]) -> None:
    text = canonical_json(payload)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(path), flags, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def copy_file_readonly_source(src: Path, dst: Path) -> None:
    if src.is_symlink() or _is_reparse(src):
        raise ToolchainError(
            "LINK_ESCAPE",
            f"refusing to follow link at {src}",
            repair="replace links with regular gold files inside the vault",
            evidence={"src": display_path(src)},
        )
    src_fd = os.open(str(src), os.O_RDONLY)
    try:
        with os.fdopen(src_fd, "rb", closefd=True) as handle:
            data = handle.read()
    except Exception:
        try:
            os.close(src_fd)
        except OSError:
            pass
        raise
    dst_fd = os.open(str(dst), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(dst_fd, data)
        os.fsync(dst_fd)
    finally:
        os.close(dst_fd)


def inventory(root: Path, *, role: str = "source") -> dict[str, Any]:
    refuse_shared_claude(root, role=role)
    if not root.exists() or not root.is_dir():
        raise ToolchainError(
            "UNVERIFIABLE_ISOLATION",
            f"{role} root is not a directory",
            repair=f"create the {role} directory first",
            evidence={"role": role, "path": str(root)},
        )
    if root.is_symlink() or _is_reparse(root):
        raise ToolchainError(
            "LINK_ESCAPE",
            f"{role} root is a symlink or reparse point",
            repair=f"use a real directory for {role}",
            evidence={"role": role, "path": display_path(root)},
        )
    entries: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        if current != root and (current.is_symlink() or _is_reparse(current)):
            raise ToolchainError(
                "LINK_ESCAPE",
                f"directory link escapes or aliases at {current}",
                repair="remove symlink/reparse directories from the vault",
                evidence={"path": display_path(current), "role": role},
            )
        if any(part in FORBIDDEN_COMPONENTS for part in current.relative_to(root).parts):
            raise ToolchainError(
                "SHARED_CLAUDE",
                "vault contains a .claude path",
                repair="remove .claude from the vault; never harvest live Claude state",
                evidence={"path": display_path(current)},
            )
        dirnames.sort()
        filenames.sort()
        for name in filenames:
            path = current / name
            rel = posix_rel(path.relative_to(root).as_posix())
            if name in FORBIDDEN_COMPONENTS or ".claude" in split_rel(rel):
                raise ToolchainError(
                    "SHARED_CLAUDE",
                    f"refusing {rel}",
                    repair="remove .claude files; they are not gold",
                    evidence={"rel": rel},
                )
            info = path.lstat()
            if _is_reparse(path, info) or stat.S_ISLNK(info.st_mode):
                raise ToolchainError(
                    "LINK_ESCAPE",
                    f"symlink or reparse at {rel}",
                    repair="replace links with regular files inside the vault",
                    evidence={"rel": rel, "role": role},
                )
            if not stat.S_ISREG(info.st_mode):
                continue
            entries.append(
                {
                    "rel": rel,
                    "rel_windows": windows_rel(rel),
                    "size": int(info.st_size),
                    "sha256": sha256_file(path),
                    "mode": int(info.st_mode & 0o777),
                }
            )
    entries.sort(key=lambda row: row["rel"])
    return {
        "root": display_path(root),
        "file_count": len(entries),
        "byte_count": sum(int(row["size"]) for row in entries),
        "sha256_tree": tree_hash(entries),
        "entries": entries,
    }


def _scan_json_flags(root: Path) -> dict[str, bool]:
    flags = {"write_back": False, "peer_read": False, "egress": False}
    names = (
        "isolation.json",
        "protocol.json",
        "egress.json",
        "write_back.json",
        "peer_read.json",
    )
    for name in names:
        path = root / name
        if not path.is_file():
            continue
        data = _read_json(path)
        if data.get("write_back") is True:
            flags["write_back"] = True
        if data.get("peer_read") is True:
            flags["peer_read"] = True
        if data.get("egress") is True or data.get("egress_enabled") is True:
            flags["egress"] = True
    return flags


def _leakage_present(root: Path) -> list[str]:
    found: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            if not path.is_file() or path.is_symlink():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if PROMPT_LEAK_MARKER in text:
                found.append("prompt")
            if DATA_LEAK_MARKER in text:
                found.append("data")
    return sorted(set(found))


def measure_isolation(dest: Path, *, gold_root: Path | None = None) -> dict[str, Any]:
    refuse_shared_claude(dest, role="dest")
    refuse_home_writeback(dest)
    if dest.is_symlink() or _is_reparse(dest):
        raise ToolchainError(
            "LINK_ESCAPE",
            "destination root is a symlink or reparse point",
            repair="use a real empty directory as the dead-end box",
        )
    mode = dest.stat().st_mode & 0o777
    peer_bits = bool(mode & 0o077) if os.name != "nt" else False
    flags = _scan_json_flags(dest)
    receipts = dest / "receipts"
    if receipts.is_dir():
        flags_receipts = _scan_json_flags(receipts)
        flags = {key: flags[key] or flags_receipts[key] for key in flags}
    gold = gold_root or (dest / "gold")
    leaks = _leakage_present(gold) if gold.exists() else []
    if gold.exists():
        for dirpath, dirnames, filenames in os.walk(gold, followlinks=False):
            current = Path(dirpath)
            if current != gold and (current.is_symlink() or _is_reparse(current)):
                raise ToolchainError(
                    "CAGE_CROSSTALK",
                    f"gold directory link at {current}",
                    repair="keep every gold file as a regular file inside this box",
                    evidence={"path": display_path(current)},
                )
            for name in dirnames + filenames:
                path = current / name
                if path.is_symlink() or _is_reparse(path):
                    raise ToolchainError(
                        "CAGE_CROSSTALK",
                        f"gold link at {path}",
                        repair="remove cross-box links; each cage is opaque",
                        evidence={"path": display_path(path)},
                    )
    contract = {
        "schema": SCHEMA,
        "class": PROTOCOL_CLASS,
        "box_kind": BOX_KIND,
        "direction": DIRECTION,
        "write_back": False,
        "peer_read": False,
        "egress": False,
        "shared_claude": False,
        "mode": mode,
        "peer_bits": peer_bits,
        "leakage_markers": leaks,
        "ok": True,
    }
    if flags["write_back"]:
        raise ToolchainError(
            "WRITE_BACK",
            "destination declares write-back",
            repair="delete write-back config; gold copies OUT only",
            evidence={"dest": display_path(dest)},
        )
    if flags["egress"]:
        raise ToolchainError(
            "EGRESS",
            "destination declares egress",
            repair="remove egress.json / egress pins; a dead-end box has no egress",
            evidence={"dest": display_path(dest)},
        )
    if flags["peer_read"] or peer_bits:
        raise ToolchainError(
            "PEER_READ",
            "destination is peer-readable or declares peer_read",
            repair="chmod 0700 and set peer_read=false",
            evidence={"dest": display_path(dest), "mode": oct(mode)},
        )
    if leaks:
        raise ToolchainError(
            "LEAKAGE",
            "prompt/data leakage markers present in the box",
            repair="strip synthetic leak markers; never harvest live prompts or secrets",
            evidence={"markers": leaks},
        )
    return contract


def plan(source: str | Path) -> dict[str, Any]:
    root = Path(source)
    refuse_shared_claude(root, role="source")
    inv = inventory(root, role="source")
    return {
        "schema": SCHEMA,
        "id": LEFTOVER_ID,
        "command": "plan",
        "ok": True,
        "state": "PLANNED",
        "class": PROTOCOL_CLASS,
        "box_kind": BOX_KIND,
        "direction": DIRECTION,
        "writes_source": False,
        "writes_home_claude": False,
        "source": inv,
        "protocol": protocol_pins(),
    }


def _receipt_dir(dest: Path) -> Path:
    path = dest / "receipts"
    path.mkdir(parents=True, exist_ok=True)
    apply_dead_end_mode(path)
    return path


def snapshot(source: str | Path, dest: str | Path) -> dict[str, Any]:
    src = Path(source)
    box = Path(dest)
    refuse_shared_claude(src, role="source")
    refuse_shared_claude(box, role="dest")
    refuse_home_writeback(box)
    refuse_alias(src, box)
    dest_must_be_absent_or_empty(box)
    source_before = inventory(src, role="source")
    box.mkdir(parents=True, exist_ok=True)
    apply_dead_end_mode(box)
    gold = box / "gold"
    gold.mkdir()
    apply_dead_end_mode(gold)
    copied = 0
    for entry in source_before["entries"]:
        rel_parts = split_rel(entry["rel"])
        src_file = src.joinpath(*rel_parts)
        dst_file = gold.joinpath(*rel_parts)
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        if dst_file.parent != gold:
            apply_dead_end_mode(dst_file.parent)
        copy_file_readonly_source(src_file, dst_file)
        dest_hash = sha256_file(dst_file)
        dest_size = dst_file.stat().st_size
        if dest_hash != entry["sha256"] or dest_size != entry["size"]:
            try:
                source_now = sha256_file(src_file)
            except OSError:
                source_now = ""
            if source_now != entry["sha256"]:
                raise ToolchainError(
                    "SOURCE_MUTATION",
                    f"source drifted while copying {entry['rel']}",
                    repair="freeze the source, keep the evidence, and re-run snapshot",
                    evidence={"rel": entry["rel"], "before": entry["sha256"], "source_now": source_now},
                )
            raise ToolchainError(
                "HASH_MISMATCH",
                f"copied bytes differ for {entry['rel']}",
                repair="delete the dest box and re-run snapshot",
                evidence={"rel": entry["rel"]},
            )
        copied += 1
        if copied == 1 and _mutation_hook is not None:
            _mutation_hook()
    source_after = inventory(src, role="source")
    if source_after["sha256_tree"] != source_before["sha256_tree"]:
        raise ToolchainError(
            "SOURCE_MUTATION",
            "source changed during capture",
            repair="freeze the source, keep the evidence, and re-run snapshot",
            evidence={
                "before": source_before["sha256_tree"],
                "after": source_after["sha256_tree"],
            },
        )
    dest_inv = inventory(gold, role="dest")
    if dest_inv["sha256_tree"] != source_before["sha256_tree"]:
        raise ToolchainError(
            "EQUALITY_MISMATCH",
            "destination gold does not equal source",
            repair="delete the dest box and re-run snapshot from a frozen source",
            evidence={
                "source": source_before["sha256_tree"],
                "dest": dest_inv["sha256_tree"],
            },
        )
    isolation = measure_isolation(box, gold_root=gold)
    equality = {
        "schema": SCHEMA,
        "source_unchanged": True,
        "destination_equals_source": True,
        "source_before_tree": source_before["sha256_tree"],
        "source_after_tree": source_after["sha256_tree"],
        "destination_tree": dest_inv["sha256_tree"],
        "file_count": source_before["file_count"],
        "byte_count": source_before["byte_count"],
    }
    result = {
        "schema": SCHEMA,
        "id": LEFTOVER_ID,
        "command": "snapshot",
        "ok": True,
        "state": "PASS",
        "class": PROTOCOL_CLASS,
        "box_kind": BOX_KIND,
        "direction": DIRECTION,
        "token_burn": False,
        "meter_burn": False,
        "copied": copied,
        "source": display_path(src),
        "dest": display_path(box),
        "protocol": protocol_pins(),
    }
    receipts = _receipt_dir(box)
    write_exclusive_json(receipts / "source_before.json", source_before)
    write_exclusive_json(receipts / "source_after.json", source_after)
    write_exclusive_json(receipts / "destination.json", dest_inv)
    write_exclusive_json(receipts / "isolation.json", isolation)
    write_exclusive_json(receipts / "equality.json", equality)
    write_exclusive_json(receipts / "result.json", result)
    write_exclusive_json(box / "protocol.json", protocol_pins())
    write_exclusive_json(box / "isolation.json", isolation)
    result["receipts"] = [f"receipts/{name}" for name in RECEIPT_NAMES]
    result["equality"] = equality
    result["isolation"] = isolation
    return result


def verify(source: str | Path, dest: str | Path) -> dict[str, Any]:
    src = Path(source)
    box = Path(dest)
    refuse_shared_claude(src, role="source")
    refuse_shared_claude(box, role="dest")
    refuse_alias(src, box)
    receipts = box / "receipts"
    if not receipts.is_dir():
        raise ToolchainError(
            "FALSE_COMPLETION",
            "destination has no receipts",
            repair="run snapshot into an empty dead-end box; token burn is not a receipt",
            evidence={"dest": display_path(box)},
        )
    stored_result = _read_json(receipts / "result.json")
    if stored_result.get("token_burn") or stored_result.get("meter_burn"):
        raise ToolchainError(
            "FALSE_COMPLETION",
            "receipt claims completion from token or meter burn",
            repair="discard the fake PASS; run snapshot and keep equality receipts",
            evidence={"result": stored_result},
        )
    if stored_result.get("state") == "PASS" and not (box / "receipts" / "equality.json").is_file():
        raise ToolchainError(
            "FALSE_COMPLETION",
            "PASS without an equality receipt",
            repair="re-run snapshot; PASS requires source-unchanged and dest-equals-source",
        )
    source_now = inventory(src, role="source")
    gold = box / "gold"
    dest_now = inventory(gold, role="dest")
    source_before = _read_json(receipts / "source_before.json")
    source_after = _read_json(receipts / "source_after.json")
    dest_stored = _read_json(receipts / "destination.json")
    equality = _read_json(receipts / "equality.json")
    if source_now["sha256_tree"] != source_before["sha256_tree"]:
        raise ToolchainError(
            "SOURCE_MUTATION",
            "source no longer matches the capture",
            repair="do not mutate the source after harvest; keep the before-receipt",
            evidence={
                "now": source_now["sha256_tree"],
                "before": source_before["sha256_tree"],
            },
        )
    if source_after["sha256_tree"] != source_before["sha256_tree"]:
        raise ToolchainError(
            "SOURCE_MUTATION",
            "stored source-after does not match source-before",
            repair="treat the capture as failed and re-run snapshot",
        )
    if dest_now["sha256_tree"] != dest_stored["sha256_tree"]:
        raise ToolchainError(
            "MANIFEST_MISMATCH",
            "destination gold drifted from the capture manifest",
            repair="do not edit the box after harvest; restore from gold copies or re-snapshot",
            evidence={
                "now": dest_now["sha256_tree"],
                "stored": dest_stored["sha256_tree"],
            },
        )
    if dest_now["sha256_tree"] != source_now["sha256_tree"]:
        raise ToolchainError(
            "EQUALITY_MISMATCH",
            "destination gold does not equal current source",
            repair="re-run snapshot into a fresh empty box",
        )
    if not equality.get("source_unchanged") or not equality.get("destination_equals_source"):
        raise ToolchainError(
            "FALSE_COMPLETION",
            "equality receipt is not a real proof",
            repair="re-run snapshot; do not mint PASS by editing receipts",
        )
    isolation = measure_isolation(box, gold_root=gold)
    return {
        "schema": SCHEMA,
        "id": LEFTOVER_ID,
        "command": "verify",
        "ok": True,
        "state": "PASS",
        "source_unchanged": True,
        "destination_equals_source": True,
        "file_count": source_now["file_count"],
        "byte_count": source_now["byte_count"],
        "sha256_tree": source_now["sha256_tree"],
        "isolation": isolation,
        "protocol": protocol_pins(),
    }


def make_synthetic_vault(root: Path) -> Path:
    vault = root / "vault"
    (vault / "gold" / "nest").mkdir(parents=True)
    (vault / "gold" / "item-a.txt").write_text("synthetic gold a\n", encoding="utf-8")
    (vault / "gold" / "nest" / "item-b.bin").write_bytes(b"\x00\x01\x02CCC")
    write_exclusive_json(
        vault / "ccc_vault.json",
        {
            "schema": SCHEMA,
            "kind": "SYNTHETIC_VAULT",
            "class": PROTOCOL_CLASS,
            "secrets": False,
            "real_ccc": False,
            "claude": False,
            "note": "fixture only — not a real CCC vault",
        },
    )
    return vault


def _expect_fail(fn: Callable[[], Any], code: str) -> dict[str, Any]:
    try:
        fn()
    except ToolchainError as error:
        if error.code != code:
            raise ToolchainError(
                "SELF_TEST",
                f"expected {code}, got {error.code}: {error.message}",
                evidence={"expected": code, "got": error.code},
            ) from error
        return {"code": error.code, "repair": error.repair, "ok": False}
    raise ToolchainError("SELF_TEST", f"expected {code} but the call passed")


def self_test() -> dict[str, Any]:
    global _mutation_hook
    cases: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="ccc-snapshot-self-") as tmp:
        root = Path(tmp)
        vault = make_synthetic_vault(root)
        planned = plan(vault)
        box = root / "box"
        captured = snapshot(vault, box)
        checked = verify(vault, box)
        cases["happy_path"] = {
            "plan": planned["state"],
            "snapshot": captured["state"],
            "verify": checked["state"],
            "file_count": planned["source"]["file_count"],
            "byte_count": planned["source"]["byte_count"],
            "copied": captured["copied"],
        }

        def _mismatch() -> None:
            target = box / "gold" / "gold" / "item-a.txt"
            target.write_text("tampered\n", encoding="utf-8")
            verify(vault, box)

        cases["manifest_mismatch"] = _expect_fail(_mismatch, "MANIFEST_MISMATCH")

        link_src = root / "link-src"
        link_src.mkdir()
        (link_src / "ok.txt").write_text("ok\n", encoding="utf-8")
        outside = root / "outside.txt"
        outside.write_text("escape\n", encoding="utf-8")
        (link_src / "escape.txt").symlink_to(outside)

        def _link() -> None:
            plan(link_src)

        cases["link_escape"] = _expect_fail(_link, "LINK_ESCAPE")

        drift_src = make_synthetic_vault(root / "drift-src-root")
        drift_box = root / "drift-box"
        snapshot(drift_src, drift_box)
        os.chmod(drift_box, 0o777)

        def _drift() -> None:
            verify(drift_src, drift_box)

        cases["isolation_drift"] = _expect_fail(_drift, "PEER_READ")

        mutate_src = make_synthetic_vault(root / "mutate-src-root")
        mutate_box = root / "mutate-box"

        def _hook() -> None:
            path = mutate_src / "ccc_vault.json"
            path.write_text("mutated during capture\n", encoding="utf-8")

        _mutation_hook = _hook
        try:
            cases["source_mutation"] = _expect_fail(
                lambda: snapshot(mutate_src, mutate_box),
                "SOURCE_MUTATION",
            )
        finally:
            _mutation_hook = None

        wb_src = make_synthetic_vault(root / "wb-src-root")
        wb_box = root / "wb-box"
        snapshot(wb_src, wb_box)
        write_exclusive_json(wb_box / "write_back.json", {"write_back": True})

        def _wb() -> None:
            verify(wb_src, wb_box)

        cases["write_back"] = _expect_fail(_wb, "WRITE_BACK")

        peer_src = make_synthetic_vault(root / "peer-src-root")
        peer_box = root / "peer-box"
        snapshot(peer_src, peer_box)
        write_exclusive_json(peer_box / "peer_read.json", {"peer_read": True})

        def _peer() -> None:
            verify(peer_src, peer_box)

        cases["peer_read"] = _expect_fail(_peer, "PEER_READ")

        eg_src = make_synthetic_vault(root / "eg-src-root")
        eg_box = root / "eg-box"
        snapshot(eg_src, eg_box)
        write_exclusive_json(eg_box / "egress.json", {"egress": True})

        def _eg() -> None:
            verify(eg_src, eg_box)

        cases["egress"] = _expect_fail(_eg, "EGRESS")

        leak_src = make_synthetic_vault(root / "leak-src-root")
        (leak_src / "gold" / "leak.txt").write_text(
            f"{PROMPT_LEAK_MARKER} {DATA_LEAK_MARKER}\n",
            encoding="utf-8",
        )
        leak_box = root / "leak-box"

        def _leak() -> None:
            snapshot(leak_src, leak_box)

        cases["leakage_markers"] = _expect_fail(_leak, "LEAKAGE")

        talk_src = make_synthetic_vault(root / "talk-src-root")
        talk_box = root / "talk-box"
        snapshot(talk_src, talk_box)
        other = root / "other-cage"
        other.mkdir()
        (talk_box / "gold" / "cross").symlink_to(other)

        def _talk() -> None:
            verify(talk_src, talk_box)

        cases["cage_crosstalk"] = _expect_fail(_talk, "CAGE_CROSSTALK")

        fake = root / "fake-box"
        fake.mkdir()
        apply_dead_end_mode(fake)
        (fake / "gold").mkdir()
        apply_dead_end_mode(fake / "gold")
        receipts = fake / "receipts"
        receipts.mkdir()
        write_exclusive_json(
            receipts / "result.json",
            {"state": "PASS", "token_burn": True, "meter_burn": True},
        )

        def _fake() -> None:
            verify(vault, fake)

        cases["false_completion_token_burn"] = _expect_fail(_fake, "FALSE_COMPLETION")

        claude = root / ".claude"
        claude.mkdir()
        (claude / "notes.txt").write_text("not gold\n", encoding="utf-8")

        def _claude() -> None:
            plan(claude)

        cases["shared_claude"] = _expect_fail(_claude, "SHARED_CLAUDE")

        reuse_src = make_synthetic_vault(root / "reuse-src-root")
        reuse_box = root / "reuse-box"
        snapshot(reuse_src, reuse_box)

        def _reuse() -> None:
            snapshot(reuse_src, reuse_box)

        cases["dest_reuse"] = _expect_fail(_reuse, "DEST_REUSE")

        alias_src = make_synthetic_vault(root / "alias-src-root")

        def _alias() -> None:
            snapshot(alias_src, alias_src)

        cases["source_dest_alias"] = _expect_fail(_alias, "ALIAS")

        bad_iso_src = make_synthetic_vault(root / "bad-iso-src-root")
        bad_iso = root / "bad-iso"
        bad_iso.write_text("not a dead-end directory\n", encoding="utf-8")

        def _iso() -> None:
            snapshot(bad_iso_src, bad_iso)

        cases["unverified_isolation"] = _expect_fail(_iso, "DEST_REUSE")

        fail_closed = [name for name, row in cases.items() if name != "happy_path"]
        return {
            "schema": SCHEMA,
            "id": LEFTOVER_ID,
            "command": "self-test",
            "ok": True,
            "state": "PASS",
            "happy_path": cases["happy_path"],
            "adversarial_fail_closed": len(fail_closed),
            "adversarial_codes": {name: cases[name]["code"] for name in fail_closed},
            "protocol": protocol_pins(),
            "cash_usd": 0,
        }


def _emit(payload: dict[str, Any], *, ok: bool) -> int:
    sys.stdout.write(canonical_json(payload))
    return 0 if ok else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ccc_snapshot_toolchain",
        description="Class D CCC vault harvest: gold copies OUT into a dead-end box.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan", help="inventory a vault without writing")
    p_plan.add_argument("--source", required=True)
    p_snap = sub.add_parser("snapshot", help="copy gold into an empty dead-end box")
    p_snap.add_argument("--source", required=True)
    p_snap.add_argument("--dest", required=True)
    p_ver = sub.add_parser("verify", help="prove source unchanged and dest equality")
    p_ver.add_argument("--source", required=True)
    p_ver.add_argument("--dest", required=True)
    sub.add_parser("self-test", help="synthetic happy path plus adversarial fail-closed")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            return _emit(plan(args.source), ok=True)
        if args.command == "snapshot":
            return _emit(snapshot(args.source, args.dest), ok=True)
        if args.command == "verify":
            return _emit(verify(args.source, args.dest), ok=True)
        if args.command == "self-test":
            return _emit(self_test(), ok=True)
        raise ToolchainError("USAGE", f"unknown command {args.command}")
    except ToolchainError as error:
        return _emit(error.as_result(), ok=False)


if __name__ == "__main__":
    sys.exit(main())
