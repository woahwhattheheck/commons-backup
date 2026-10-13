#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exact submitted-V4 WHEAT feed-stock ablation helpers."""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

BASELINE_SHA256 = "4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b"
V4_RUNTIME_GIT_BLOB = "998bf5da08f61f82eafaf5750c8a86fc3adad7fb"
V4_OPERATING_STOCK_GIT_BLOB = "80b372bfd34d04a2c9e2376fa02917f21f659c41"
RUNTIME_MEMBER = "titan_runtime.py"
STOCK_MEMBER = "operating_stock.py"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_bytes(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def archive_members_bytes(raw: bytes) -> dict[str, bytes]:
    """Parse one already-captured archive buffer; never reopen caller paths."""
    if type(raw) is not bytes:
        raise TypeError("archive bytes must be bytes")
    data: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as archive:
        for member in archive:
            rel = PurePosixPath(member.name)
            if (not member.name or "\\" in member.name or rel.is_absolute()
                    or ".." in rel.parts or str(rel) != member.name.rstrip("/")):
                raise ValueError(f"Invalid archive path: {member.name}")
            if member.isdir():
                continue
            if not member.isfile() or member.name in data:
                raise ValueError(f"Non-file or duplicate member: {member.name}")
            if member.size > 100 * 1024**2:
                raise ValueError(f"Oversized member: {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Unreadable archive member: {member.name}")
            with stream:
                payload = stream.read()
            if len(payload) != member.size:
                raise ValueError(f"Truncated archive member: {member.name}")
            data[member.name] = payload
    if "main.py" not in data or "frozen_selected.py" not in data:
        raise ValueError("Expected canonical V4 flat archive layout")
    return data


def _rewrite_runtime(raw: bytes, expected_blob: str) -> bytes:
    """Replace only TitanAgent._feed_stock_selected with an identity method."""
    if type(raw) is not bytes:
        raise TypeError("runtime source must be bytes")
    actual = git_blob_bytes(raw)
    if actual != expected_blob:
        raise ValueError(f"runtime source drift: expected {expected_blob}, got {actual}")
    text = raw.decode("utf-8")
    tree = ast.parse(text)
    classes = [node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == "TitanAgent"]
    if len(classes) != 1:
        raise ValueError("Expected exactly one TitanAgent class")
    methods = [node for node in classes[0].body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == "_feed_stock_selected"]
    if len(methods) != 1 or not isinstance(methods[0], ast.FunctionDef):
        raise ValueError("Expected exactly one synchronous _feed_stock_selected method")
    method = methods[0]
    if method.col_offset != 4 or method.end_lineno is None or not method.body:
        raise ValueError("Unexpected _feed_stock_selected source shape")
    args = method.args
    if (args.vararg is not None or args.kwarg is not None or args.kwonlyargs
            or args.posonlyargs or [arg.arg for arg in args.args] !=
            ["self", "obs", "cfg", "selected"]):
        raise ValueError("Unexpected _feed_stock_selected signature")
    first_body = method.body[0].lineno
    if first_body <= method.lineno:
        raise ValueError("Unexpected method body span")
    lines = text.splitlines(keepends=True)
    indent = " " * 8
    replacement = lines[:first_body - 1] + [indent + "return selected\n"] + lines[method.end_lineno:]
    changed = "".join(replacement)
    ast.parse(changed)
    result = changed.encode("utf-8")
    if result == raw:
        raise AssertionError("feed-stock ablation did not change runtime")
    return result


def rewrite_feed_stock_identity(raw: bytes) -> bytes:
    return _rewrite_runtime(raw, V4_RUNTIME_GIT_BLOB)


def exact_v4_arms(baseline_raw: bytes) -> dict[str, dict[str, bytes]]:
    """Return exact control + one-member feed-stock-off treatment."""
    if type(baseline_raw) is not bytes:
        raise TypeError("baseline archive capture must be bytes")
    actual = sha256_bytes(baseline_raw)
    if actual != BASELINE_SHA256:
        raise ValueError(f"baseline is not exact submitted V4: {actual}")
    control = archive_members_bytes(baseline_raw)
    if git_blob_bytes(control.get(RUNTIME_MEMBER, b"")) != V4_RUNTIME_GIT_BLOB:
        raise ValueError("submitted V4 titan_runtime.py preimage mismatch")
    if git_blob_bytes(control.get(STOCK_MEMBER, b"")) != V4_OPERATING_STOCK_GIT_BLOB:
        raise ValueError("submitted V4 operating_stock.py preimage mismatch")
    treatment = dict(control)
    treatment[RUNTIME_MEMBER] = rewrite_feed_stock_identity(control[RUNTIME_MEMBER])
    if set(treatment) != set(control):
        raise AssertionError("treatment changed archive membership")
    changed = [name for name in control if control[name] != treatment[name]]
    if changed != [RUNTIME_MEMBER]:
        raise AssertionError(f"expected only {RUNTIME_MEMBER} to change; got {changed}")
    if treatment[STOCK_MEMBER] != control[STOCK_MEMBER]:
        raise AssertionError("fertilizer/feed helper source changed")
    return {"control": control, "feed_stock_off": treatment}


def extract_members(members: dict[str, bytes], directory: Path) -> None:
    """Materialize authenticated flat archive members without tar extraction."""
    directory = Path(directory)
    if directory.exists():
        raise FileExistsError(directory)
    directory.mkdir()
    for name, data in members.items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or "\\" in name or str(rel) != name:
            raise ValueError(f"unsafe member path: {name}")
        path = directory.joinpath(*rel.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def encoded(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def action_trace_sha256(actions: list[dict]) -> str:
    digest = hashlib.sha256()
    for step, action in enumerate(actions):
        digest.update(encoded({"step": step, "action": action}))
    return digest.hexdigest()


def first_action_divergence(control: list[dict], treatment: list[dict]):
    upto = min(len(control), len(treatment))
    for step in range(upto):
        if control[step] != treatment[step]:
            return {
                "step": step,
                "control": deepcopy(control[step]),
                "feed_stock_off": deepcopy(treatment[step]),
            }
    if len(control) != len(treatment):
        return {
            "step": upto,
            "control": deepcopy(control[upto]) if upto < len(control) else None,
            "feed_stock_off": deepcopy(treatment[upto]) if upto < len(treatment) else None,
        }
    return None


def play_with_candidate_trace(evaluator, *args, candidate_spec: str, **kwargs):
    """Observe candidate returned actions without modifying evaluator/agent bytes."""
    captured: list[dict] = []
    original = evaluator.Actor.act

    def traced(actor, observation, configuration, timeout):
        response = original(actor, observation, configuration, timeout)
        if actor.spec == candidate_spec and response.get("kind") == "action":
            captured.append(deepcopy(response["action"]))
        return response

    evaluator.Actor.act = traced
    try:
        game = evaluator.play(*args, **kwargs)
    finally:
        evaluator.Actor.act = original
    return game, captured


def game_scores(game: dict, seat: int):
    if game.get("status") != "complete" or game.get("steps") != 719:
        return None
    scores = game.get("scores")
    if not isinstance(scores, list) or len(scores) != 2:
        return None
    own, rival = scores[seat], scores[1 - seat]
    return {"own": own, "rival": rival, "margin": own - rival}
