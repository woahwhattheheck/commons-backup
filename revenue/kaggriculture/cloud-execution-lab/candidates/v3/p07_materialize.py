# SPDX-License-Identifier: Apache-2.0
"""Materialize the P07 lane from one exact canonical TITAN archive.

Disabled mode is a byte-for-byte copy.  Enabled mode refuses an unexpected base,
adds the P07 module/check, wires one pre-consumer seam, updates package metadata, and
writes a deterministic archive plus a receipt.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
from typing import Any

BASE_MAIN = "2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb"
BASE_ARCHIVE_SHA256 = "5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1"
HERE = Path(__file__).resolve().parent
MODULE_SOURCE = HERE / "overlay" / "p07_joint_actor_assignment.py"
CHECK_SOURCE = HERE / "overlay" / "checks" / "test_p07_joint_actor_assignment.py"

FEATURE_FIELD = "    joint_actor_assignment: bool = False\n"
FEATURE_VALIDATION = (
    "        if self.joint_actor_assignment and (self.consumer != 'frozen' or self.terminal_route):\n"
    "            raise ValueError('joint_actor_assignment requires nonterminal frozen selection')\n"
)
INITIALIZER = (
    "        if f.joint_actor_assignment:\n"
    "            if self.joint_actor_assignment is None:\n"
    "                from p07_joint_actor_assignment import JointActorAssignment\n"
    "                self.joint_actor_assignment = JointActorAssignment(enabled=True)\n"
    "            else:\n"
    "                # Any ready=False reconstruction crossed an unconsumed action.\n"
    "                self.joint_actor_assignment.reset()\n"
)
RUNTIME_METHOD = r'''    def _joint_actor_selected(self, obs, cfg, selected):
        """Apply P07 after the single producer return, before any consumer snapshot."""
        if not self.features.joint_actor_assignment:
            return selected
        if self.joint_actor_assignment is None:
            self.diagnostics['joint_actor_assignment'] = {
                'enabled': True, 'changed': False, 'reason': 'module_not_initialized'}
            return selected
        try:
            result, report = self.joint_actor_assignment.apply(
                obs, cfg, selected,
                route=self.controller.R[self.controller.cur],
                route_id=self.controller.cur,
            )
        except Exception as error:
            self.joint_actor_assignment.reset()
            self.diagnostics['joint_actor_assignment'] = {
                'enabled': True, 'changed': False,
                'reason': 'P07_ERROR_' + type(error).__name__}
            return selected
        self.diagnostics['joint_actor_assignment'] = report
        return result

'''
RELEASE_NOTE = """

## P07 joint actor assignment candidate

`joint_actor_assignment` is an opt-in V3 key.  After the one existing producer call and
before FrozenSelected builds its post-unit snapshot, P07 joins the prior executable HIRE
prefix to the next public hand count.  On an observed underfill only, it preserves every
pre-existing actor lane and binds the completed new hands to the strongest represented
new-hand route suffix.  Farmer and market orders are unchanged.  Route switches, retries,
day resets, future HIRE boundaries, actor/cardinality drift and malformed inputs fail
closed.  No HIRE, cash, purchase or producer policy is added.
"""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def _read_archive(path: Path) -> tuple[dict[str, bytes], dict[str, int]]:
    files: dict[str, bytes] = {}
    modes: dict[str, int] = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            name = member.name
            pure = Path(name)
            if pure.is_absolute() or ".." in pure.parts or name in files:
                raise ValueError(f"unsafe or duplicate archive member: {name}")
            if member.isdir():
                continue
            if not member.isfile() or member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"unsupported archive member: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"unreadable archive member: {name}")
            files[name] = stream.read()
            modes[name] = member.mode or 0o644
    for required in ("main.py", "titan_runtime.py", "TITAN-CONFIG.json"):
        if required not in files:
            raise ValueError(f"canonical member missing: {required}")
    return files, modes


def _render_archive(files: dict[str, bytes], modes: dict[str, int]) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name in sorted(files):
                data = files[name]
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = modes.get(name, 0o644)
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def _patch_runtime(source: bytes) -> bytes:
    text = source.decode("utf-8")
    text = _replace_once(
        text,
        "    early_capital: bool = False\n",
        "    early_capital: bool = False\n" + FEATURE_FIELD,
        "Features field",
    )
    text = _replace_once(
        text,
        "        if not 0 <= self.reserve_seconds < self.budget_seconds <= 1:\n",
        FEATURE_VALIDATION + "        if not 0 <= self.reserve_seconds < self.budget_seconds <= 1:\n",
        "Features validation",
    )
    text = _replace_once(
        text,
        "        self.committed_seed_retry_module = None\n",
        "        self.committed_seed_retry_module = None\n        self.joint_actor_assignment = None\n",
        "agent state",
    )
    text = _replace_once(
        text,
        "        self._restore_seller_state()\n        self.ready = True\n",
        INITIALIZER + "        self._restore_seller_state()\n        self.ready = True\n",
        "module initialization",
    )
    text = _replace_once(
        text,
        "    def _selected_snapshot(self, obs, returned=None):\n",
        RUNTIME_METHOD + "    def _selected_snapshot(self, obs, returned=None):\n",
        "runtime method",
    )
    text = _replace_once(
        text,
        "                selected = self.production.act(obs)\n                self.selected = deepcopy(selected)\n",
        "                selected = self.production.act(obs)\n"
        "                selected = self._joint_actor_selected(obs, cfg, selected)\n"
        "                self.selected = deepcopy(selected)\n",
        "pre-consumer seam",
    )
    text = _replace_once(
        text,
        "            self.ready = False\n            # Retain only the route paired with a complete selected fallback.\n",
        "            self.ready = False\n"
        "            if self.joint_actor_assignment is not None:\n"
        "                self.joint_actor_assignment.reset()\n"
        "            # Retain only the route paired with a complete selected fallback.\n",
        "deadline reset",
    )
    return text.encode("utf-8")


def _update_source_manifest(files: dict[str, bytes]) -> None:
    if "SOURCE.json" not in files:
        return
    source = json.loads(files["SOURCE.json"].decode("utf-8"))
    source["default"] = json.loads(files["TITAN-CONFIG.json"].decode("utf-8"))
    runtime = source.setdefault("runtime", {})
    paths = {
        "titan_runtime.py": "titan_runtime.py",
        "TITAN-CONFIG.json": "TITAN-CONFIG.json",
        "TITAN-RELEASE.md": "TITAN-RELEASE.md",
        "p07_joint_actor_assignment.py": "candidates/v3/overlay/p07_joint_actor_assignment.py",
        "checks/test_p07_joint_actor_assignment.py": "candidates/v3/overlay/checks/test_p07_joint_actor_assignment.py",
    }
    for name, source_path in paths.items():
        if name not in files:
            continue
        data = files[name]
        runtime[name] = {"source_path": source_path, "sha256": _sha(data), "bytes": len(data)}
    source["p07_candidate"] = {
        "base_main": BASE_MAIN,
        "base_archive_sha256": BASE_ARCHIVE_SHA256,
        "key": "joint_actor_assignment",
        "enabled": True,
        "playing_strength": "not_measured_for_changed_bytes",
    }
    files["SOURCE.json"] = (json.dumps(source, indent=2, sort_keys=True) + "\n").encode("utf-8")


def materialize(
    base: Path,
    output: Path,
    *,
    enabled: bool,
    expected_sha256: str = BASE_ARCHIVE_SHA256,
    tree: Path | None = None,
) -> dict[str, Any]:
    base = Path(base)
    output = Path(output)
    raw = base.read_bytes()
    actual = _sha(raw)
    if actual != expected_sha256:
        raise ValueError(f"base archive SHA-256 mismatch: expected {expected_sha256}, got {actual}")

    output.parent.mkdir(parents=True, exist_ok=True)
    if not enabled:
        shutil.copyfile(base, output)
        built = raw
        files, _ = _read_archive(base) if tree is not None else ({}, {})
    else:
        files, modes = _read_archive(base)
        files["titan_runtime.py"] = _patch_runtime(files["titan_runtime.py"])
        config = json.loads(files["TITAN-CONFIG.json"].decode("utf-8"))
        if "joint_actor_assignment" in config:
            raise ValueError("joint_actor_assignment key already exists in base")
        config["joint_actor_assignment"] = True
        files["TITAN-CONFIG.json"] = (json.dumps(config, indent=2) + "\n").encode("utf-8")
        files["p07_joint_actor_assignment.py"] = MODULE_SOURCE.read_bytes()
        files["checks/test_p07_joint_actor_assignment.py"] = CHECK_SOURCE.read_bytes()
        if "TITAN-RELEASE.md" in files:
            files["TITAN-RELEASE.md"] += RELEASE_NOTE.encode("utf-8")
        _update_source_manifest(files)
        built = _render_archive(files, modes)
        output.write_bytes(built)

    if tree is not None:
        tree = Path(tree)
        if tree.exists():
            shutil.rmtree(tree)
        tree.mkdir(parents=True)
        if not files:
            files, _ = _read_archive(output)
        for name, data in files.items():
            target = tree / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    receipt = {
        "operation": "TITAN-V3-P07-JOINT-ACTOR-ASSIGNMENT-20260910-01",
        "base_main": BASE_MAIN,
        "base_archive_sha256": actual,
        "enabled": bool(enabled),
        "output": str(output),
        "output_sha256": _sha(built),
        "bytes": len(built),
        "default_off_byte_identity": (not enabled and built == raw),
        "playing_strength": "not_measured_for_changed_bytes",
    }
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--expected-sha256", default=BASE_ARCHIVE_SHA256)
    parser.add_argument("--tree", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = materialize(
        args.base,
        args.output,
        enabled=args.enabled,
        expected_sha256=args.expected_sha256,
        tree=args.tree,
    )
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
