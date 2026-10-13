#!/usr/bin/env python3
"""ProofPatch hardened evidence core.

This module intentionally separates structural consistency from execution
provenance. A caller-authored receipt chain can be structurally valid without
proving that any command actually ran. Only verifier-selected executor replay
may emit EXECUTOR_REPLAY_VERIFIED, and even that state is relative to the
verifier's executor trust boundary.

Nothing in this module authorizes network access, cloud spend, repository
mutation, contest submission, prize, payment, or revenue claims.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import posixpath
import re
import sys
from urllib.parse import urlparse

SCHEMA = "proofpatch.bundle/v1"
TASK_SCHEMA = "proofpatch.task/v1"
SNAPSHOT_SCHEMA = "proofpatch.repo-snapshot/v1"
PATCH_SCHEMA = "proofpatch.patch/v1"
RECEIPT_SCHEMA = "proofpatch.tool-receipt/v1"
LIVE_SCHEMA = "proofpatch.nebius-runtime-receipt/v1"


class ProofError(ValueError):
    pass


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_./:=+,@%-]+$")
_FORBIDDEN = ("\x00", "\n", "\r", ";", "&&", "||", "`", "$(", ">", "<", "://")


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def freeze_plain_json(value):
    """Freeze one exact built-in JSON generation before any trust decision.

    Exact types are deliberate: dict/list/str/int/bool subclasses may expose
    stateful or side-effecting views across repeated reads. Floats are not part
    of any ProofPatch schema and are rejected rather than normalized.
    """
    if value is None:
        return None
    if type(value) is bool:
        return value
    if type(value) is int:
        return value
    if type(value) is str:
        return value
    if type(value) is list:
        return [freeze_plain_json(item) for item in value]
    if type(value) is dict:
        frozen = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ProofError("plain JSON object keys must be exact strings")
            frozen[key] = freeze_plain_json(item)
        return frozen
    raise ProofError("plain JSON built-in types required at verifier boundary")


def digest_text(text):
    if not isinstance(text, str):
        raise ProofError("digest input must be text")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest_json(value):
    return digest_text(canonical_json(value))


def exact_dict(value, keys, name):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ProofError(f"{name} keys mismatch")
    return value


def strict_int(value, name, low=0, high=2**31 - 1):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProofError(f"{name} must be integer")
    if value < low or value > high:
        raise ProofError(f"{name} out of range")
    return value


def strict_bool(value, name):
    if type(value) is not bool:
        raise ProofError(f"{name} must be boolean")
    return value


def valid_id(value, name):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ProofError(f"invalid {name}")
    return value


def valid_sha(value, name):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ProofError(f"{name} must be lowercase sha256")
    return value


def safe_relpath(value):
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ProofError("path must be non-empty bounded text")
    if value.startswith("/") or "\\" in value or "\x00" in value:
        raise ProofError("path must be POSIX relative")
    normalized = posixpath.normpath(value)
    if normalized != value or normalized in (".", "..") or normalized.startswith("../"):
        raise ProofError("path escape or alias rejected")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise ProofError("unsafe path component")
    return value


def validate_command(value):
    data = exact_dict(value, {"argv", "timeout_s"}, "command")
    argv = data["argv"]
    if not isinstance(argv, list) or not (1 <= len(argv) <= 16):
        raise ProofError("argv must be a bounded list")
    checked = []
    for token in argv:
        if not isinstance(token, str) or not token or len(token) > 300:
            raise ProofError("invalid argv token")
        if any(fragment in token for fragment in _FORBIDDEN) or not _TOKEN.fullmatch(token):
            raise ProofError("unsafe command token")
        checked.append(token)
    if checked[0] not in ("python", "python3"):
        raise ProofError("executable not allowlisted")
    if any(token in ("-c", "-i", "-I", "-E", "-s", "-S") for token in checked[1:]):
        raise ProofError("unsafe interpreter mode rejected")
    if len(checked) >= 3 and checked[1] == "-m" and checked[2] != "unittest":
        raise ProofError("module not allowlisted")
    for token in checked[1:]:
        if token.endswith(".py") or "/" in token:
            safe_relpath(token)
    timeout = strict_int(data["timeout_s"], "timeout_s", 1, 60)
    return {"argv": checked, "timeout_s": timeout}


def validate_result(value):
    data = exact_dict(value, {"exit_code", "stdout", "stderr", "timed_out"}, "tool result")
    code = strict_int(data["exit_code"], "exit_code", 0, 255)
    stdout, stderr = data["stdout"], data["stderr"]
    if not isinstance(stdout, str) or not isinstance(stderr, str):
        raise ProofError("stdout/stderr must be text")
    if len(stdout) > 1_000_000 or len(stderr) > 1_000_000:
        raise ProofError("tool output too large")
    return {"exit_code": code, "stdout": stdout, "stderr": stderr,
            "timed_out": strict_bool(data["timed_out"], "timed_out")}


def validate_task(value):
    data = exact_dict(value, {"schema", "task_id", "issue_ref", "allowed_paths", "reproduction", "regression"}, "task")
    if data["schema"] != TASK_SCHEMA:
        raise ProofError("task schema mismatch")
    task_id = valid_id(data["task_id"], "task_id")
    issue_ref = valid_id(data["issue_ref"], "issue_ref")
    paths = data["allowed_paths"]
    if not isinstance(paths, list) or not paths or len(paths) > 64:
        raise ProofError("allowed_paths invalid")
    paths = [safe_relpath(path) for path in paths]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ProofError("allowed_paths must be canonical unique order")
    return {
        "schema": TASK_SCHEMA,
        "task_id": task_id,
        "issue_ref": issue_ref,
        "allowed_paths": paths,
        "reproduction": validate_command(data["reproduction"]),
        "regression": validate_command(data["regression"]),
    }


def task_digest(task):
    return digest_json(validate_task(task))


def snapshot_from_files(files):
    if not isinstance(files, dict) or not files:
        raise ProofError("snapshot requires files")
    rows = []
    for path, content in files.items():
        path = safe_relpath(path)
        if not isinstance(content, str):
            raise ProofError("snapshot content must be text")
        rows.append({"path": path, "sha256": digest_text(content)})
    rows.sort(key=lambda row: row["path"])
    body = {"schema": SNAPSHOT_SCHEMA, "files": rows}
    return {**body, "digest": digest_json(body)}


def validate_snapshot(value):
    data = exact_dict(value, {"schema", "files", "digest"}, "snapshot")
    if data["schema"] != SNAPSHOT_SCHEMA or not isinstance(data["files"], list) or not data["files"]:
        raise ProofError("snapshot invalid")
    rows, seen = [], set()
    for raw in data["files"]:
        item = exact_dict(raw, {"path", "sha256"}, "snapshot file")
        path = safe_relpath(item["path"])
        if path in seen:
            raise ProofError("duplicate snapshot path")
        seen.add(path)
        rows.append({"path": path, "sha256": valid_sha(item["sha256"], "file sha")})
    if rows != sorted(rows, key=lambda row: row["path"]):
        raise ProofError("snapshot file order not canonical")
    body = {"schema": SNAPSHOT_SCHEMA, "files": rows}
    expected = digest_json(body)
    if valid_sha(data["digest"], "snapshot digest") != expected:
        raise ProofError("snapshot digest mismatch")
    return {**body, "digest": expected}


def snapshot_hashes(snapshot):
    checked = validate_snapshot(snapshot)
    return {row["path"]: row["sha256"] for row in checked["files"]}


def make_patch(baseline, patched, changes):
    base, post = validate_snapshot(baseline), validate_snapshot(patched)
    if base["digest"] == post["digest"]:
        raise ProofError("patch must change repository")
    if not isinstance(changes, list) or not changes:
        raise ProofError("changes required")
    rows = []
    for raw in changes:
        raw = exact_dict(raw, {"path", "before", "after"}, "change")
        path = safe_relpath(raw["path"])
        before, after = raw["before"], raw["after"]
        if not isinstance(before, str) or not isinstance(after, str) or before == after:
            raise ProofError("change bytes invalid")
        rows.append({"path": path, "before": before, "after": after})
    rows.sort(key=lambda row: row["path"])
    if len({row["path"] for row in rows}) != len(rows):
        raise ProofError("duplicate changed path")
    patch = {
        "schema": PATCH_SCHEMA,
        "base_repo_digest": base["digest"],
        "patched_repo_digest": post["digest"],
        "changes": rows,
    }
    patch["digest"] = digest_json(patch)
    validate_patch(patch, base, post)
    return patch


def validate_patch(value, baseline, patched):
    data = exact_dict(value, {"schema", "base_repo_digest", "patched_repo_digest", "changes", "digest"}, "patch")
    if data["schema"] != PATCH_SCHEMA:
        raise ProofError("patch schema mismatch")
    base, post = validate_snapshot(baseline), validate_snapshot(patched)
    if valid_sha(data["base_repo_digest"], "base_repo_digest") != base["digest"]:
        raise ProofError("patch baseline mismatch")
    if valid_sha(data["patched_repo_digest"], "patched_repo_digest") != post["digest"]:
        raise ProofError("patch generation mismatch")
    changes = data["changes"]
    if not isinstance(changes, list) or not changes:
        raise ProofError("patch changes invalid")
    base_hashes, post_hashes = snapshot_hashes(base), snapshot_hashes(post)
    if set(base_hashes) != set(post_hashes):
        raise ProofError("patch may not hide file additions/deletions")
    rows = []
    for raw in changes:
        raw = exact_dict(raw, {"path", "before", "after"}, "change")
        path = safe_relpath(raw["path"])
        before, after = raw["before"], raw["after"]
        if not isinstance(before, str) or not isinstance(after, str) or before == after:
            raise ProofError("patch changed bytes invalid")
        if path not in base_hashes:
            raise ProofError("patch path absent from repository roots")
        if digest_text(before) != base_hashes[path] or digest_text(after) != post_hashes[path]:
            raise ProofError("patch bytes do not bind repository roots")
        rows.append({"path": path, "before": before, "after": after})
    if rows != sorted(rows, key=lambda row: row["path"]) or len({row["path"] for row in rows}) != len(rows):
        raise ProofError("patch changes not canonical")
    actual = {path for path in base_hashes if base_hashes[path] != post_hashes[path]}
    declared = {row["path"] for row in rows}
    if actual != declared:
        raise ProofError("declared patch must enumerate every repository-root difference")
    body = {
        "schema": PATCH_SCHEMA,
        "base_repo_digest": base["digest"],
        "patched_repo_digest": post["digest"],
        "changes": rows,
    }
    expected = digest_json(body)
    if valid_sha(data["digest"], "patch digest") != expected:
        raise ProofError("patch digest mismatch")
    return {**body, "digest": expected}


def make_receipt(sequence, phase, task_sha, command, result, repo_before, repo_after, prev_digest):
    body = {
        "schema": RECEIPT_SCHEMA,
        "sequence": strict_int(sequence, "sequence", 0, 1000),
        "phase": valid_id(phase, "phase"),
        "task_digest": valid_sha(task_sha, "task_digest"),
        "command": validate_command(command),
        "result": validate_result(result),
        "repo_before": valid_sha(repo_before, "repo_before"),
        "repo_after": valid_sha(repo_after, "repo_after"),
        "prev_digest": valid_sha(prev_digest, "prev_digest"),
    }
    return {**body, "entry_digest": digest_json(body)}


def verify_receipts(receipts, task, baseline, patched):
    if not isinstance(receipts, list) or len(receipts) != 4:
        raise ProofError("exactly four proof receipts required")
    phases = ["REPRODUCTION", "FOCUSED_TEST", "REGRESSION_TEST", "REPLAY_TEST"]
    checked_task = validate_task(task)
    task_sha = digest_json(checked_task)
    base_sha = validate_snapshot(baseline)["digest"]
    post_sha = validate_snapshot(patched)["digest"]
    prev = "0" * 64
    out = []
    for index, raw in enumerate(receipts):
        keys = {"schema", "sequence", "phase", "task_digest", "command", "result", "repo_before", "repo_after", "prev_digest", "entry_digest"}
        data = exact_dict(raw, keys, "receipt")
        if data["schema"] != RECEIPT_SCHEMA or strict_int(data["sequence"], "sequence", 0, 3) != index:
            raise ProofError("receipt schema/sequence mismatch")
        if data["phase"] != phases[index] or valid_sha(data["task_digest"], "task_digest") != task_sha:
            raise ProofError("receipt phase or task binding mismatch")
        command, result = validate_command(data["command"]), validate_result(data["result"])
        before = valid_sha(data["repo_before"], "repo_before")
        after = valid_sha(data["repo_after"], "repo_after")
        if valid_sha(data["prev_digest"], "prev_digest") != prev:
            raise ProofError("receipt chain broken")
        body = {key: data[key] for key in data if key != "entry_digest"}
        expected_digest = digest_json(body)
        if valid_sha(data["entry_digest"], "entry_digest") != expected_digest:
            raise ProofError("receipt tamper")
        prev = expected_digest
        if result["timed_out"]:
            raise ProofError("timeout cannot advance proof")
        if index == 0:
            if command != checked_task["reproduction"] or result["exit_code"] == 0:
                raise ProofError("predecessor-discriminating reproduction must fail")
            if before != base_sha or after != base_sha:
                raise ProofError("reproduction mutated baseline")
        else:
            if before != post_sha or after != post_sha or result["exit_code"] != 0:
                raise ProofError("post-patch proof must be green on exact patched generation")
            if index == 1 and command != checked_task["reproduction"]:
                raise ProofError("focused test must rerun predecessor-discriminating reproduction")
            if index == 2 and command != checked_task["regression"]:
                raise ProofError("regression command mismatch")
            if index == 3 and command != checked_task["reproduction"]:
                raise ProofError("replay must rerun original reproduction")
        out.append(copy.deepcopy(data))
    return out


def validate_doc_evidence(value, task_sha):
    if not isinstance(value, list) or len(value) > 32:
        raise ProofError("doc evidence must be bounded list")
    out, last = [], None
    for raw in value:
        row = exact_dict(raw, {"url", "retrieved_text_sha256", "task_digest"}, "doc evidence")
        if not isinstance(row["url"], str) or not row["url"].startswith("https://") or len(row["url"]) > 1000:
            raise ProofError("doc evidence URL invalid")
        item = {
            "url": row["url"],
            "retrieved_text_sha256": valid_sha(row["retrieved_text_sha256"], "doc sha"),
            "task_digest": valid_sha(row["task_digest"], "doc task"),
        }
        if item["task_digest"] != task_sha:
            raise ProofError("cross-task documentation evidence")
        key = (item["url"], item["retrieved_text_sha256"])
        if last is not None and key <= last:
            raise ProofError("doc evidence order/uniqueness invalid")
        last = key
        out.append(item)
    return out


def validate_live_receipt(value, task_sha):
    if value is None:
        return None
    keys = {"schema", "provider", "model", "run_id", "task_digest", "request_sha256", "response_sha256", "receipt_sha256"}
    row = exact_dict(value, keys, "live runtime receipt")
    if row["schema"] != LIVE_SCHEMA or row["provider"] != "nebius-token-factory":
        raise ProofError("live provider schema mismatch")
    if not isinstance(row["model"], str) or not row["model"].lower().startswith("nvidia/"):
        raise ProofError("live model must be NVIDIA namespaced")
    valid_id(row["run_id"], "run_id")
    if valid_sha(row["task_digest"], "live task") != task_sha:
        raise ProofError("cross-task live receipt")
    valid_sha(row["request_sha256"], "request sha")
    valid_sha(row["response_sha256"], "response sha")
    body = {key: row[key] for key in row if key != "receipt_sha256"}
    if valid_sha(row["receipt_sha256"], "receipt sha") != digest_json(body):
        raise ProofError("live runtime receipt digest mismatch")
    return copy.deepcopy(row)


def build_bundle(task, baseline, patched, patch, receipts, doc_evidence=None, live_runtime_receipt=None):
    task = validate_task(task)
    task_sha = digest_json(task)
    baseline, patched = validate_snapshot(baseline), validate_snapshot(patched)
    patch = validate_patch(patch, baseline, patched)
    receipts = verify_receipts(list(receipts), task, baseline, patched)
    docs = validate_doc_evidence(list(doc_evidence or []), task_sha)
    live = validate_live_receipt(live_runtime_receipt, task_sha)
    body = {
        "schema": SCHEMA,
        "task": task,
        "baseline": baseline,
        "patched": patched,
        "patch": patch,
        "receipts": receipts,
        "doc_evidence": docs,
        "live_runtime_receipt": live,
        "authority": {
            "external_side_effects_authorized": False,
            "cloud_spend_authorized": False,
            "submission_authorized": False,
        },
    }
    bundle = {**body, "bundle_sha256": digest_json(body)}
    verify_bundle(bundle)
    return bundle


def verify_bundle(value):
    """Verify one frozen plain-JSON generation; never authenticate output provenance."""
    keys = {"schema", "task", "baseline", "patched", "patch", "receipts", "doc_evidence", "live_runtime_receipt", "authority", "bundle_sha256"}
    data = exact_dict(freeze_plain_json(value), keys, "bundle")
    if data["schema"] != SCHEMA:
        raise ProofError("bundle schema mismatch")
    task = validate_task(data["task"])
    task_sha = digest_json(task)
    baseline, patched = validate_snapshot(data["baseline"]), validate_snapshot(data["patched"])
    patch = validate_patch(data["patch"], baseline, patched)
    changed = {row["path"] for row in patch["changes"]}
    if not changed.issubset(set(task["allowed_paths"])):
        raise ProofError("patch exceeds task path authority")
    receipts = verify_receipts(data["receipts"], task, baseline, patched)
    docs = validate_doc_evidence(data["doc_evidence"], task_sha)
    live = validate_live_receipt(data["live_runtime_receipt"], task_sha)
    authority = exact_dict(data["authority"], {"external_side_effects_authorized", "cloud_spend_authorized", "submission_authorized"}, "authority")
    for name, raw in authority.items():
        if strict_bool(raw, name):
            raise ProofError("proof bundle cannot authorize external effects")
    body = {key: data[key] for key in data if key != "bundle_sha256"}
    expected = digest_json(body)
    if valid_sha(data["bundle_sha256"], "bundle sha") != expected:
        raise ProofError("bundle digest mismatch")
    return {
        "status": "STRUCTURAL_EVIDENCE_VERIFIED",
        "task_digest": task_sha,
        "bundle_sha256": expected,
        "receipt_chain_head": receipts[-1]["entry_digest"],
        "doc_evidence_count": len(docs),
        "live_runtime_evidence_present": live is not None,
        "receipt_provenance": "CALLER_AUTHORED_UNAUTHENTICATED",
        "executor_replay_verified": False,
        "replay_required": True,
        "competition_submission_ready": False,
        "external_side_effects_authorized": False,
        "cloud_spend_authorized": False,
        "submission_authorized": False,
    }


def verify_with_executor(value, executor, executor_id):
    snapshot = freeze_plain_json(value)
    structural = verify_bundle(snapshot)
    executor_id = valid_id(executor_id, "executor_id")
    if not hasattr(executor, "run") or not callable(executor.run):
        raise ProofError("executor must expose run(command, repo_digest)")
    for receipt in snapshot["receipts"]:
        actual = validate_result(executor.run(receipt["command"], receipt["repo_before"]))
        claimed = validate_result(receipt["result"])
        if actual != claimed:
            raise ProofError("executor replay disagrees with claimed receipt")
    out = dict(structural)
    out.update({
        "status": "EXECUTOR_REPLAY_VERIFIED",
        "executor_replay_verified": True,
        "replay_required": False,
        "executor_id": executor_id,
        "receipt_provenance": "REPLAYED_BY_VERIFIER_SELECTED_EXECUTOR",
    })
    return out


class HermeticFakeSandbox:
    """Exact command+repository keyed fake; never spawns subprocesses or uses network."""
    def __init__(self, outcomes):
        if not isinstance(outcomes, dict):
            raise ProofError("outcomes must be mapping")
        self.outcomes = copy.deepcopy(outcomes)

    @staticmethod
    def key(command, repo_digest):
        return digest_json({"command": validate_command(command), "repo_digest": valid_sha(repo_digest, "repo digest")})

    def run(self, command, repo_digest):
        key = self.key(command, repo_digest)
        if key not in self.outcomes:
            raise ProofError("no hermetic outcome for exact command/repository generation")
        return validate_result(self.outcomes[key])


class NebiusTokenFactoryAdapter:
    """Deterministic NVIDIA request issuer with explicit injected transport only."""
    ALLOWED_HOSTS = {"api.tokenfactory.nebius.com", "api.studio.nebius.ai"}

    def __init__(self, model, base_url="https://api.tokenfactory.nebius.com/v1/chat/completions", api_key_env="NEBIUS_API_KEY"):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or parsed.hostname not in self.ALLOWED_HOSTS:
            raise ProofError("Nebius endpoint not allowlisted")
        if not isinstance(model, str) or not model.lower().startswith("nvidia/"):
            raise ProofError("ProofPatch requires NVIDIA namespaced model")
        if not isinstance(api_key_env, str) or not api_key_env.isidentifier():
            raise ProofError("invalid credential environment name")
        self.model = model
        self.base_url = base_url
        self.api_key_env = api_key_env
        self._issued_request_sha256 = set()

    def build_request(self, task_sha, issue_text, repo_manifest):
        valid_sha(task_sha, "task digest")
        if not isinstance(issue_text, str) or not issue_text or len(issue_text) > 100_000:
            raise ProofError("issue text invalid")
        if not isinstance(repo_manifest, list) or len(repo_manifest) > 10_000:
            raise ProofError("repo manifest invalid")
        system = (
            "You are ProofPatch's planning model. Return JSON only. Propose bounded inspection/test/patch steps; "
            "never request network, credentials, package installation, git push, or shell strings. "
            "A failing predecessor-discriminating reproduction is mandatory before any fix."
        )
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": canonical_json({
                    "task_digest": task_sha,
                    "issue_text": issue_text,
                    "repo_manifest": repo_manifest,
                })},
            ],
        }
        request_sha = digest_json(body)
        self._issued_request_sha256.add(request_sha)
        return {"url": self.base_url, "model": self.model, "body": body, "request_sha256": request_sha}

    def execute(self, request, transport):
        # Freeze one exact request generation before any semantic request read.
        # This prevents stateful dict/list subclasses from passing validation or
        # digest checks as generation A and serializing generation B to transport.
        data = exact_dict(
            freeze_plain_json(request),
            {"url", "model", "body", "request_sha256"},
            "Nebius request",
        )
        if not callable(transport):
            raise ProofError("explicit transport required")
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ProofError(f"missing explicit credential environment: {self.api_key_env}")
        if data["url"] != self.base_url or data["model"] != self.model:
            raise ProofError("request/adapter generation mismatch")
        body = exact_dict(data["body"], {"model", "temperature", "messages"}, "Nebius request body")
        if body["model"] != self.model or body["temperature"] != 0:
            raise ProofError("request body escaped pinned model/generation policy")
        messages = body["messages"]
        if not isinstance(messages, list) or len(messages) != 2:
            raise ProofError("request messages generation mismatch")
        for index, message in enumerate(messages):
            checked = exact_dict(message, {"role", "content"}, "Nebius request message")
            expected_role = "system" if index == 0 else "user"
            if checked["role"] != expected_role or not isinstance(checked["content"], str):
                raise ProofError("request message schema mismatch")
        request_sha = valid_sha(data["request_sha256"], "request sha")
        if request_sha != digest_json(body):
            raise ProofError("request digest mismatch")
        if request_sha not in self._issued_request_sha256:
            raise ProofError("request was not issued by this adapter generation")
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        return transport(self.base_url, headers, canonical_json(body).encode("utf-8"))


class TavilyEvidenceBuilder:
    @staticmethod
    def retain(task_sha, url, retrieved_text):
        valid_sha(task_sha, "task digest")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ProofError("documentation URL must be https")
        if not isinstance(retrieved_text, str) or not retrieved_text:
            raise ProofError("retrieved text required")
        return {"url": url, "retrieved_text_sha256": digest_text(retrieved_text), "task_digest": task_sha}


BASE_CALC = "def ratio(a, b):\n    return a // b\n"
PATCHED_CALC = "def ratio(a, b):\n    return a / b\n"
TEST_CALC = "import unittest\nfrom calc import ratio\n\nclass RatioTest(unittest.TestCase):\n    def test_fraction(self):\n        self.assertEqual(ratio(5, 2), 2.5)\n"


def _demo_parts():
    baseline = snapshot_from_files({"calc.py": BASE_CALC, "test_calc.py": TEST_CALC})
    patched = snapshot_from_files({"calc.py": PATCHED_CALC, "test_calc.py": TEST_CALC})
    task = validate_task({
        "schema": TASK_SCHEMA,
        "task_id": "demo-ratio-floor-division",
        "issue_ref": "synthetic:ratio",
        "allowed_paths": ["calc.py"],
        "reproduction": {"argv": ["python", "-m", "unittest", "test_calc.py"], "timeout_s": 30},
        "regression": {"argv": ["python", "-m", "unittest", "discover"], "timeout_s": 30},
    })
    return task, baseline, patched


def demo_bundle():
    task, baseline, patched = _demo_parts()
    patch = make_patch(baseline, patched, [{"path": "calc.py", "before": BASE_CALC, "after": PATCHED_CALC}])
    task_sha, prev, receipts = digest_json(task), "0" * 64, []
    specs = [
        ("REPRODUCTION", task["reproduction"], {"exit_code": 1, "stdout": "", "stderr": "AssertionError: 2 != 2.5", "timed_out": False}, baseline["digest"], baseline["digest"]),
        ("FOCUSED_TEST", task["reproduction"], {"exit_code": 0, "stdout": "OK", "stderr": "", "timed_out": False}, patched["digest"], patched["digest"]),
        ("REGRESSION_TEST", task["regression"], {"exit_code": 0, "stdout": "OK", "stderr": "", "timed_out": False}, patched["digest"], patched["digest"]),
        ("REPLAY_TEST", task["reproduction"], {"exit_code": 0, "stdout": "OK", "stderr": "", "timed_out": False}, patched["digest"], patched["digest"]),
    ]
    for sequence, spec in enumerate(specs):
        receipt = make_receipt(sequence, spec[0], task_sha, spec[1], spec[2], spec[3], spec[4], prev)
        receipts.append(receipt)
        prev = receipt["entry_digest"]
    return build_bundle(task, baseline, patched, patch, receipts)


def demo_executor():
    task, baseline, patched = _demo_parts()
    outcomes = {
        HermeticFakeSandbox.key(task["reproduction"], baseline["digest"]):
            {"exit_code": 1, "stdout": "", "stderr": "AssertionError: 2 != 2.5", "timed_out": False},
        HermeticFakeSandbox.key(task["reproduction"], patched["digest"]):
            {"exit_code": 0, "stdout": "OK", "stderr": "", "timed_out": False},
        HermeticFakeSandbox.key(task["regression"], patched["digest"]):
            {"exit_code": 0, "stdout": "OK", "stderr": "", "timed_out": False},
    }
    return HermeticFakeSandbox(outcomes)


def verify_demo_bundle(value):
    return verify_with_executor(value, demo_executor(), "proofpatch-hermetic-demo-v1")


def _parser():
    parser = argparse.ArgumentParser(prog="proofpatch-core")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    sub.add_parser("demo-verify")
    verify = sub.add_parser("verify")
    verify.add_argument("bundle")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "demo":
            print(json.dumps(demo_bundle(), sort_keys=True, indent=2))
            return 0
        if args.command == "demo-verify":
            print(json.dumps(verify_demo_bundle(demo_bundle()), sort_keys=True, indent=2))
            return 0
        with open(args.bundle, "r", encoding="utf-8") as handle:
            bundle = json.load(handle)
        print(json.dumps(verify_bundle(bundle), sort_keys=True, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, ProofError) as exc:
        print("proofpatch-core: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
