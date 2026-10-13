#!/usr/bin/env python3
"""Derive the one-factor TITAN terminal-deadline candidate from pinned sources.

This script never edits a repository checkout unless both canonical source blobs
match the exact reviewed preimages. It is intended for a disposable worktree;
the canonical archive, pointers, configuration, and provider state are outside
its scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Final

OPERATION: Final = "titan-v3-terminal-deadline-liquidation-preservation-20260909-01"
BASE_COMMIT: Final = "15d39ea7a9048c880b5185ed9797cd4af717b27f"
EXPECTED_BLOBS: Final = {
    "main.py": "4a8cf7bcda1f0fea231a144692cb84a779a9e73e",
    "titan_runtime.py": "b952c9c228ecbde592bf3d2df01638677abb0d24",
}

_MAIN_OLD: Final = '''def _entrypoint_fallback(instance, observation, configuration, deadline):
    """Return a completed current action, otherwise the visible-state fallback."""
    from copy import deepcopy
    selected = None if instance is None else getattr(instance, 'selected', None)
    if selected is not None:
        return deepcopy(selected)
    cfg = dict(configuration or {})
    obs = dict(observation)
    step = obs.get('step')
    if step is None:
        step = int(obs['day'])*int(cfg.get('turnsPerDay', 24))+int(obs['hour'])
    obs['step'] = int(step)
    last = int(cfg.get('episodeSteps', 720))-2
    return (deadline.terminal_liquidation_fallback(obs, cfg)
            if obs['step'] == last else deadline.legal_pass(obs))
'''

_MAIN_NEW: Final = '''def _entrypoint_fallback(instance, observation, configuration, deadline):
    """Keep terminal liquidation authoritative; otherwise reuse a selection."""
    from copy import deepcopy
    cfg = dict(configuration or {})
    obs = dict(observation)
    step = obs.get('step')
    if step is None:
        step = int(obs['day'])*int(cfg.get('turnsPerDay', 24))+int(obs['hour'])
    obs['step'] = int(step)
    last = int(cfg.get('episodeSteps', 720))-2
    if obs['step'] == last:
        return deadline.terminal_liquidation_fallback(obs, cfg)
    selected = None if instance is None else getattr(instance, 'selected', None)
    return deepcopy(selected) if selected is not None else deadline.legal_pass(obs)
'''

_RUNTIME_OLD: Final = '''                selected = self.production.act(obs)
                self.selected = deepcopy(selected)
                selected_checkpoint = (self.selected, self.controller.cur)
                fallback = selected_checkpoint[0]
                if self.quadrant is not None:
'''

_RUNTIME_NEW: Final = '''                selected = self.production.act(obs)
                self.selected = deepcopy(selected)
                selected_checkpoint = (self.selected, self.controller.cur)
                # At the final executable step, raw producer selection is not a
                # liquidation receipt. Preserve the visible-state fallback if
                # any downstream transform or finalizer exhausts the deadline.
                if obs['step'] != last:
                    fallback = selected_checkpoint[0]
                if self.quadrant is not None:
'''


class CandidateError(RuntimeError):
    """The candidate could not be derived exactly from the pinned source."""


def git_blob_sha(data: bytes) -> str:
    """Return the Git SHA-1 object id for exact blob bytes."""
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise CandidateError(f"{label}: expected one replacement site, found {count}")
    return text.replace(old, new, 1)


def patch_main(text: str) -> str:
    return _replace_exact(text, _MAIN_OLD, _MAIN_NEW, "main.py")


def patch_runtime(text: str) -> str:
    return _replace_exact(text, _RUNTIME_OLD, _RUNTIME_NEW, "titan_runtime.py")


def _read_exact(path: Path, expected_blob: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CandidateError(f"refusing non-regular source: {path}")
    data = path.read_bytes()
    actual = git_blob_sha(data)
    if actual != expected_blob:
        raise CandidateError(
            f"preimage mismatch for {path.name}: expected {expected_blob}, got {actual}"
        )
    return data


def _decode(data: bytes, name: str) -> str:
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CandidateError(f"{name}: source is not strict UTF-8") from exc


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.terminus.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def apply_candidate(lab: Path) -> dict[str, object]:
    """Patch both pinned sources and return a content-addressed receipt."""
    lab = lab.resolve(strict=True)
    if not lab.is_dir() or lab.is_symlink():
        raise CandidateError(f"refusing non-directory lab root: {lab}")

    before: dict[str, bytes] = {}
    for name, expected in EXPECTED_BLOBS.items():
        before[name] = _read_exact(lab / name, expected)

    # Render and encode the full two-file candidate before mutating either file.
    rendered = {
        "main.py": patch_main(_decode(before["main.py"], "main.py")).encode("utf-8"),
        "titan_runtime.py": patch_runtime(
            _decode(before["titan_runtime.py"], "titan_runtime.py")
        ).encode("utf-8"),
    }
    if any(rendered[name] == before[name] for name in rendered):
        raise CandidateError("candidate must change both claimed sources")

    for name in ("main.py", "titan_runtime.py"):
        _atomic_write(lab / name, rendered[name])

    receipt: dict[str, object] = {
        "operation": OPERATION,
        "base_commit": BASE_COMMIT,
        "changed_paths": ["main.py", "titan_runtime.py"],
        "before_git_blobs": {
            name: git_blob_sha(before[name]) for name in sorted(before)
        },
        "after_git_blobs": {
            name: git_blob_sha(rendered[name]) for name in sorted(rendered)
        },
        "semantic_delta": {
            "terminal_step": "visible-state liquidation remains fallback after selection",
            "nonterminal_steps": "completed producer selection remains fallback",
        },
        "canonical_runtime_mutated": False,
        "archive_or_pointer_mutated": False,
        "provider_or_submission_action": False,
        "score_or_promotion_claim": False,
    }
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lab", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    receipt = apply_candidate(args.lab)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
