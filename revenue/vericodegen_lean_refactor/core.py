"""Offline evidence harness for the VeriCodeGen Lean Refactor Arena.

This module does not call an LLM or submit to the competition.  It assembles
candidate proofs under an immutable theorem/preamble, runs configured local
compiler commands, enforces a Track-1 cost ledger, and produces a deterministic
evidence package for later reproduction.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import resource
import statistics
import subprocess
import tempfile
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

RUN_SCHEMA = "vericodegen.refactor-run/v1"
TASK_SCHEMA = "vericodegen.refactor-task/v1"
RESULT_SCHEMA = "vericodegen.refactor-result/v1"
TRACK1_LIMIT_MICROUSD = 3_000_000
MAX_SAFE_INT = 9_007_199_254_740_991
MAX_CANDIDATES = 64
MAX_PROOF_BYTES = 256_000
MAX_CONTEXT_BYTES = 512_000
MAX_OUTPUT_BYTES = 65_536
MAX_ARGV = 32
MAX_REPETITIONS = 7
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,191}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_']*|\d+(?:\.\d+)?|:=|=>|->|←|→|≠|≤|≥|∧|∨|[^\s]", re.UNICODE)

RUN_KEYS = frozenset({"schema", "task", "toolchains"})
TASK_KEYS = frozenset({
    "schema", "task_id", "origin_ref", "origin_digest", "preamble",
    "declaration", "baseline_proof", "candidates",
})
CANDIDATE_KEYS = frozenset({
    "candidate_id", "proof", "model", "api_cost_microusd", "attempt", "seed",
    "request_digest", "response_digest",
})
TOOLCHAIN_KEYS = frozenset({
    "label", "role", "argv", "timeout_seconds", "repetitions",
})
BUDGET_KEYS = frozenset({"track", "limit_microusd_per_problem", "used_microusd", "remaining_microusd", "used_by_model_microusd", "spend_semantics"})
RECEIPT_KEYS = frozenset({"input_digest", "task_digest", "toolchain_digest", "baseline_source_digest", "selected_source_digest"})
METRIC_NOTICE = "LOCAL_TRIAGE_ONLY_NOT_ORGANIZER_SCORE; elapsed_ns is repeated local wall time, token_count is a stable lexical approximation"

RESULT_KEYS = frozenset({
    "schema", "input", "budget", "observations", "pareto_ids", "selected_id",
    "receipt", "authorities", "metric_notice", "package_digest",
})
OBS_KEYS = frozenset({
    "candidate_id", "kind", "proof_digest", "source_digest", "token_count",
    "byte_count", "line_count", "api_cost_microusd", "model",
    "toolchains", "target_pass", "transfer_passes", "target_median_elapsed_ns",
})
TC_OBS_KEYS = frozenset({"label", "role", "passes", "runs", "median_elapsed_ns"})
RUN_OBS_KEYS = frozenset({"exit_code", "elapsed_ns", "stdout_digest", "stderr_digest", "stdout_bytes", "stderr_bytes"})

AUTHORITIES = {
    "llm_or_api_call": False,
    "competition_registration": False,
    "terms_acceptance": False,
    "competition_submission": False,
    "organizer_contact": False,
    "spend_or_purchase": False,
    "leaderboard_or_prize_claim": False,
    "official_metric_claim": False,
}

class RefactorError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise RefactorError(f"non-finite JSON number {value!r} is not allowed")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RefactorError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def load_json_bytes(raw: bytes, label: str = "input") -> Any:
    if not isinstance(raw, (bytes, bytearray)):
        raise RefactorError(f"{label} must be bytes")
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RefactorError(f"{label} must be UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except RefactorError:
        raise
    except json.JSONDecodeError as exc:
        raise RefactorError(f"{label} is invalid JSON") from exc


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _exact(value: Any, keys: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RefactorError(f"{label} must be an object")
    actual = frozenset(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise RefactorError(f"{label} fields invalid: missing={missing} extra={extra}")
    return value


def _integer(value: Any, label: str, low: int = 0, high: int = MAX_SAFE_INT) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RefactorError(f"{label} must be an integer")
    if value < low or value > high:
        raise RefactorError(f"{label} outside allowed bounds")
    return value


def _text(value: Any, label: str, max_bytes: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise RefactorError(f"{label} must be text")
    if "\x00" in value or "\r" in value:
        raise RefactorError(f"{label} contains forbidden control/newline encoding")
    raw = value.encode("utf-8")
    if (not allow_empty and not value.strip()) or len(raw) > max_bytes:
        raise RefactorError(f"{label} is empty or too large")
    return value


def _ref(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        raise RefactorError(f"{label} must be a bounded opaque reference")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise RefactorError(f"{label} must be a lowercase SHA-256 digest")
    return value


def proof_token_count(proof: str) -> int:
    """Stable local lexical approximation; explicitly not an organizer metric."""
    return len(_TOKEN.findall(proof))


def assemble_source(task: dict[str, Any], proof: str) -> str:
    """Assemble only the proof body beneath the frozen declaration."""
    proof = _text(proof, "proof", MAX_PROOF_BYTES)
    lines = proof.split("\n")
    indented = "\n".join("  " + line for line in lines)
    return f"{task['preamble'].rstrip()}\n\n{task['declaration'].rstrip()} := by\n{indented}\n"


def _normalize_candidate(raw: Any, index: int) -> dict[str, Any]:
    c = _exact(raw, CANDIDATE_KEYS, f"candidates[{index}]")
    return {
        "candidate_id": _ref(c["candidate_id"], f"candidates[{index}].candidate_id"),
        "proof": _text(c["proof"], f"candidates[{index}].proof", MAX_PROOF_BYTES),
        "model": _ref(c["model"], f"candidates[{index}].model"),
        "api_cost_microusd": _integer(c["api_cost_microusd"], f"candidates[{index}].api_cost_microusd", 0, TRACK1_LIMIT_MICROUSD),
        "attempt": _integer(c["attempt"], f"candidates[{index}].attempt", 1, 1_000_000),
        "seed": _integer(c["seed"], f"candidates[{index}].seed", 0, MAX_SAFE_INT),
        "request_digest": _digest(c["request_digest"], f"candidates[{index}].request_digest"),
        "response_digest": _digest(c["response_digest"], f"candidates[{index}].response_digest"),
    }


def _normalize_task(raw: Any) -> dict[str, Any]:
    task = _exact(raw, TASK_KEYS, "task")
    if task["schema"] != TASK_SCHEMA:
        raise RefactorError("unsupported task schema")
    preamble = _text(task["preamble"], "task.preamble", MAX_CONTEXT_BYTES, allow_empty=True)
    declaration = _text(task["declaration"], "task.declaration", MAX_CONTEXT_BYTES)
    if ":=" in declaration or re.search(r"\bwhere\b", declaration):
        raise RefactorError("task.declaration must contain the declaration only, not a proof/body")
    first = declaration.lstrip().split(None, 1)[0] if declaration.lstrip() else ""
    if first not in {"theorem", "lemma", "example"}:
        raise RefactorError("task.declaration must begin with theorem, lemma, or example")
    baseline = _text(task["baseline_proof"], "task.baseline_proof", MAX_PROOF_BYTES)
    raw_candidates = task["candidates"]
    if not isinstance(raw_candidates, list) or not raw_candidates or len(raw_candidates) > MAX_CANDIDATES:
        raise RefactorError(f"task.candidates must contain 1..{MAX_CANDIDATES} entries")
    candidates = [_normalize_candidate(x, i) for i, x in enumerate(raw_candidates)]
    ids = [c["candidate_id"] for c in candidates]
    if len(ids) != len(set(ids)):
        raise RefactorError("duplicate candidate_id")
    proof_digests = [sha256(c["proof"].encode("utf-8")) for c in candidates]
    if len(proof_digests) != len(set(proof_digests)):
        raise RefactorError("duplicate candidate proof payload")
    total = sum(c["api_cost_microusd"] for c in candidates)
    if total > TRACK1_LIMIT_MICROUSD:
        raise RefactorError("Track-1 candidate ledger exceeds US$3/problem")
    out = {
        "schema": TASK_SCHEMA,
        "task_id": _ref(task["task_id"], "task.task_id"),
        "origin_ref": _ref(task["origin_ref"], "task.origin_ref"),
        "origin_digest": _digest(task["origin_digest"], "task.origin_digest"),
        "preamble": preamble,
        "declaration": declaration,
        "baseline_proof": baseline,
        "candidates": sorted(candidates, key=lambda c: c["candidate_id"]),
    }
    # Bound the complete assembled source, not just individual pieces.
    for label, proof in [("baseline", baseline)] + [(c["candidate_id"], c["proof"]) for c in candidates]:
        if len(assemble_source(out, proof).encode("utf-8")) > MAX_CONTEXT_BYTES + MAX_PROOF_BYTES + 4096:
            raise RefactorError(f"assembled source too large for {label}")
    return out


def _normalize_toolchain(raw: Any, index: int) -> dict[str, Any]:
    t = _exact(raw, TOOLCHAIN_KEYS, f"toolchains[{index}]")
    label = _ref(t["label"], f"toolchains[{index}].label")
    role = t["role"]
    if role not in {"target", "transfer"}:
        raise RefactorError(f"toolchains[{index}].role must be target or transfer")
    argv = t["argv"]
    if not isinstance(argv, list) or not argv or len(argv) > MAX_ARGV:
        raise RefactorError(f"toolchains[{index}].argv must be a bounded token array")
    norm_argv = []
    placeholder_count = 0
    for j, item in enumerate(argv):
        item = _text(item, f"toolchains[{index}].argv[{j}]", 2048)
        placeholder_count += item.count("{file}")
        norm_argv.append(item)
    if placeholder_count != 1:
        raise RefactorError(f"toolchains[{index}].argv must contain exactly one {{file}} placeholder")
    return {
        "label": label,
        "role": role,
        "argv": norm_argv,
        "timeout_seconds": _integer(t["timeout_seconds"], f"toolchains[{index}].timeout_seconds", 1, 300),
        "repetitions": _integer(t["repetitions"], f"toolchains[{index}].repetitions", 1, MAX_REPETITIONS),
    }


def normalize_run(raw: Any) -> dict[str, Any]:
    run = _exact(raw, RUN_KEYS, "run")
    if run["schema"] != RUN_SCHEMA:
        raise RefactorError("unsupported run schema")
    task = _normalize_task(run["task"])
    raw_toolchains = run["toolchains"]
    if not isinstance(raw_toolchains, list) or not raw_toolchains or len(raw_toolchains) > 8:
        raise RefactorError("toolchains must be a bounded non-empty array")
    toolchains = [_normalize_toolchain(x, i) for i, x in enumerate(raw_toolchains)]
    labels = [t["label"] for t in toolchains]
    if len(labels) != len(set(labels)):
        raise RefactorError("duplicate toolchain label")
    if sum(t["role"] == "target" for t in toolchains) != 1:
        raise RefactorError("exactly one target toolchain is required")
    return {"schema": RUN_SCHEMA, "task": task, "toolchains": sorted(toolchains, key=lambda t: (t["role"] != "target", t["label"]))}


def _limits(timeout_seconds: int):
    def apply() -> None:
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds + 1, timeout_seconds + 1))
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
            if hasattr(resource, "RLIMIT_NPROC"):
                resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except (ValueError, OSError):
            pass
    return apply


def _run_once(source: str, toolchain: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="vericodegen-refactor-") as td:
        src = Path(td) / "Main.lean"
        src.write_text(source, encoding="utf-8", newline="\n")
        argv = [token.replace("{file}", str(src)) for token in toolchain["argv"]]
        env = {"PATH": os.environ.get("PATH", ""), "HOME": td, "LANG": "C", "LC_ALL": "C", "TMPDIR": td}
        started = time.perf_counter_ns()
        try:
            cp = subprocess.run(
                argv, cwd=td, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=toolchain["timeout_seconds"], check=False,
                preexec_fn=_limits(toolchain["timeout_seconds"]) if os.name == "posix" else None,
            )
            elapsed = time.perf_counter_ns() - started
            stdout = cp.stdout[:MAX_OUTPUT_BYTES]
            stderr = cp.stderr[:MAX_OUTPUT_BYTES]
            return {
                "exit_code": cp.returncode if cp.returncode >= 0 else 128 + min(-cp.returncode, 127),
                "elapsed_ns": elapsed,
                "stdout_digest": sha256(stdout),
                "stderr_digest": sha256(stderr),
                "stdout_bytes": min(len(cp.stdout), MAX_OUTPUT_BYTES),
                "stderr_bytes": min(len(cp.stderr), MAX_OUTPUT_BYTES),
            }
        except subprocess.TimeoutExpired as exc:
            elapsed = time.perf_counter_ns() - started
            stdout = (exc.stdout or b"")[:MAX_OUTPUT_BYTES]
            stderr = (exc.stderr or b"")[:MAX_OUTPUT_BYTES]
            return {
                "exit_code": 124,
                "elapsed_ns": elapsed,
                "stdout_digest": sha256(stdout),
                "stderr_digest": sha256(stderr),
                "stdout_bytes": len(stdout),
                "stderr_bytes": len(stderr),
            }
        except OSError as exc:
            elapsed = time.perf_counter_ns() - started
            payload = str(exc).encode("utf-8")[:MAX_OUTPUT_BYTES]
            return {
                "exit_code": 127,
                "elapsed_ns": elapsed,
                "stdout_digest": sha256(b""),
                "stderr_digest": sha256(payload),
                "stdout_bytes": 0,
                "stderr_bytes": len(payload),
            }


def _run_toolchain(source: str, toolchain: dict[str, Any]) -> dict[str, Any]:
    runs = [_run_once(source, toolchain) for _ in range(toolchain["repetitions"])]
    passes = all(r["exit_code"] == 0 for r in runs)
    med = int(statistics.median(r["elapsed_ns"] for r in runs))
    return {"label": toolchain["label"], "role": toolchain["role"], "passes": passes, "runs": runs, "median_elapsed_ns": med}


def _observe(run: dict[str, Any], candidate_id: str, proof: str, kind: str, model: str, cost: int) -> dict[str, Any]:
    source = assemble_source(run["task"], proof)
    tool_obs = [_run_toolchain(source, tc) for tc in run["toolchains"]]
    target = next(x for x in tool_obs if x["role"] == "target")
    transfers = [x for x in tool_obs if x["role"] == "transfer"]
    return {
        "candidate_id": candidate_id,
        "kind": kind,
        "proof_digest": sha256(proof.encode("utf-8")),
        "source_digest": sha256(source.encode("utf-8")),
        "token_count": proof_token_count(proof),
        "byte_count": len(proof.encode("utf-8")),
        "line_count": len(proof.splitlines()),
        "api_cost_microusd": cost,
        "model": model,
        "toolchains": tool_obs,
        "target_pass": target["passes"],
        "transfer_passes": sum(x["passes"] for x in transfers),
        "target_median_elapsed_ns": target["median_elapsed_ns"],
    }


def _dominates(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if not a["target_pass"]:
        return False
    if not b["target_pass"]:
        return True
    no_worse = (
        a["token_count"] <= b["token_count"]
        and a["target_median_elapsed_ns"] <= b["target_median_elapsed_ns"]
        and a["transfer_passes"] >= b["transfer_passes"]
    )
    strict = (
        a["token_count"] < b["token_count"]
        or a["target_median_elapsed_ns"] < b["target_median_elapsed_ns"]
        or a["transfer_passes"] > b["transfer_passes"]
    )
    return no_worse and strict


def pareto_ids(observations: list[dict[str, Any]]) -> list[str]:
    eligible = [x for x in observations if x["target_pass"]]
    return sorted(
        x["candidate_id"] for x in eligible
        if not any(y is not x and _dominates(y, x) for y in eligible)
    )


def _select(observations: list[dict[str, Any]], front: list[str]) -> str:
    if not front:
        return "NONE"
    lookup = {x["candidate_id"]: x for x in observations}
    # Conservative deterministic local selector: maximize transfer first, then
    # minimize proof size, then local repeated wall time.  Not organizer score.
    return min(front, key=lambda cid: (
        -lookup[cid]["transfer_passes"], lookup[cid]["token_count"],
        lookup[cid]["target_median_elapsed_ns"], cid,
    ))


def compile_run(raw: Any) -> dict[str, Any]:
    run = normalize_run(raw)
    task = run["task"]
    observations = [_observe(run, "BASELINE", task["baseline_proof"], "baseline", "REFERENCE", 0)]
    for c in task["candidates"]:
        observations.append(_observe(run, c["candidate_id"], c["proof"], "candidate", c["model"], c["api_cost_microusd"]))
    observations.sort(key=lambda x: (x["candidate_id"] != "BASELINE", x["candidate_id"]))
    if not observations[0]["target_pass"]:
        raise RefactorError("baseline proof does not compile on the target toolchain")
    front = pareto_ids(observations)
    selected = _select(observations, front)
    used = sum(c["api_cost_microusd"] for c in task["candidates"])
    by_model: dict[str, int] = {}
    for c in task["candidates"]:
        by_model[c["model"]] = by_model.get(c["model"], 0) + c["api_cost_microusd"]
    budget = {
        "track": "closed-source-llm",
        "limit_microusd_per_problem": TRACK1_LIMIT_MICROUSD,
        "used_microusd": used,
        "remaining_microusd": TRACK1_LIMIT_MICROUSD - used,
        "used_by_model_microusd": {k: by_model[k] for k in sorted(by_model)},
        "spend_semantics": "DECLARED_GENERATION_LEDGER_ONLY_HARNESS_DOES_NOT_CALL_MODELS_OR_SPEND",
    }
    receipt = {
        "input_digest": sha256(canonical_bytes(run)),
        "task_digest": sha256(canonical_bytes(task)),
        "toolchain_digest": sha256(canonical_bytes(run["toolchains"])),
        "baseline_source_digest": observations[0]["source_digest"],
        "selected_source_digest": next((x["source_digest"] for x in observations if x["candidate_id"] == selected), "NONE"),
    }
    core = {
        "schema": RESULT_SCHEMA,
        "input": run,
        "budget": budget,
        "observations": observations,
        "pareto_ids": front,
        "selected_id": selected,
        "receipt": receipt,
        "authorities": dict(AUTHORITIES),
        "metric_notice": METRIC_NOTICE,
    }
    return {**core, "package_digest": sha256(canonical_bytes(core))}


def _validate_run_observation(run: Any, label: str) -> dict[str, Any]:
    x = _exact(run, RUN_OBS_KEYS, label)
    return {
        "exit_code": _integer(x["exit_code"], f"{label}.exit_code", 0, 255),
        "elapsed_ns": _integer(x["elapsed_ns"], f"{label}.elapsed_ns", 0, MAX_SAFE_INT),
        "stdout_digest": _digest(x["stdout_digest"], f"{label}.stdout_digest"),
        "stderr_digest": _digest(x["stderr_digest"], f"{label}.stderr_digest"),
        "stdout_bytes": _integer(x["stdout_bytes"], f"{label}.stdout_bytes", 0, MAX_OUTPUT_BYTES),
        "stderr_bytes": _integer(x["stderr_bytes"], f"{label}.stderr_bytes", 0, MAX_OUTPUT_BYTES),
    }


def _validate_observation(raw: Any, index: int, toolchains: list[dict[str, Any]]) -> dict[str, Any]:
    x = _exact(raw, OBS_KEYS, f"observations[{index}]")
    tc_raw = x["toolchains"]
    if not isinstance(tc_raw, list) or len(tc_raw) != len(toolchains):
        raise RefactorError("observation toolchain vector length mismatch")
    tc_out = []
    expected = {(t["label"], t["role"], t["repetitions"]) for t in toolchains}
    seen = set()
    for j, tc in enumerate(tc_raw):
        tc = _exact(tc, TC_OBS_KEYS, f"observations[{index}].toolchains[{j}]")
        label = _ref(tc["label"], "toolchain observation label")
        role = tc["role"]
        if role not in {"target", "transfer"}:
            raise RefactorError("invalid observed toolchain role")
        runs_raw = tc["runs"]
        spec = next((t for t in toolchains if t["label"] == label and t["role"] == role), None)
        if spec is None or not isinstance(runs_raw, list) or len(runs_raw) != spec["repetitions"]:
            raise RefactorError("observed toolchain does not match configured repetitions")
        runs = [_validate_run_observation(r, f"observations[{index}].toolchains[{j}].runs[{k}]") for k, r in enumerate(runs_raw)]
        passes = tc["passes"]
        if not isinstance(passes, bool) or passes != all(r["exit_code"] == 0 for r in runs):
            raise RefactorError("observed toolchain pass bit is inconsistent")
        med = _integer(tc["median_elapsed_ns"], "median_elapsed_ns", 0, MAX_SAFE_INT)
        if med != int(statistics.median(r["elapsed_ns"] for r in runs)):
            raise RefactorError("observed toolchain median is inconsistent")
        tc_out.append({"label": label, "role": role, "passes": passes, "runs": runs, "median_elapsed_ns": med})
        seen.add((label, role, spec["repetitions"]))
    if seen != expected:
        raise RefactorError("observed toolchain set mismatch")
    target = next(t for t in tc_out if t["role"] == "target")
    transfers = [t for t in tc_out if t["role"] == "transfer"]
    out = deepcopy(x)
    out["toolchains"] = tc_out
    if not isinstance(x["target_pass"], bool) or x["target_pass"] != target["passes"]:
        raise RefactorError("target_pass inconsistent")
    if _integer(x["transfer_passes"], "transfer_passes", 0, len(transfers)) != sum(t["passes"] for t in transfers):
        raise RefactorError("transfer_passes inconsistent")
    if _integer(x["target_median_elapsed_ns"], "target_median_elapsed_ns", 0, MAX_SAFE_INT) != target["median_elapsed_ns"]:
        raise RefactorError("target median inconsistent")
    _digest(x["proof_digest"], "proof_digest"); _digest(x["source_digest"], "source_digest")
    _integer(x["token_count"], "token_count", 0, MAX_SAFE_INT)
    _integer(x["byte_count"], "byte_count", 0, MAX_PROOF_BYTES)
    _integer(x["line_count"], "line_count", 1, MAX_PROOF_BYTES)
    _integer(x["api_cost_microusd"], "api_cost_microusd", 0, TRACK1_LIMIT_MICROUSD)
    _ref(x["candidate_id"], "candidate_id"); _ref(x["model"], "model")
    if x["kind"] not in {"baseline", "candidate"}:
        raise RefactorError("invalid observation kind")
    return out


def verify_result(package: Any, *, expected_package_digest: str | None = None, rerun_compilers: bool = False) -> dict[str, Any]:
    package = _exact(package, RESULT_KEYS, "result")
    if package["schema"] != RESULT_SCHEMA:
        raise RefactorError("unsupported result schema")
    _digest(package["package_digest"], "package_digest")
    core = {k: package[k] for k in RESULT_KEYS if k != "package_digest"}
    actual = sha256(canonical_bytes(core))
    if actual != package["package_digest"]:
        raise RefactorError("package digest mismatch")
    if expected_package_digest is not None:
        _digest(expected_package_digest, "expected_package_digest")
        if actual != expected_package_digest:
            raise RefactorError("external package commitment mismatch")
    run = normalize_run(package["input"])
    obs_raw = package["observations"]
    if not isinstance(obs_raw, list) or len(obs_raw) != 1 + len(run["task"]["candidates"]):
        raise RefactorError("observation count mismatch")
    observations = [_validate_observation(x, i, run["toolchains"]) for i, x in enumerate(obs_raw)]
    if [x["candidate_id"] for x in observations] != ["BASELINE"] + [c["candidate_id"] for c in run["task"]["candidates"]]:
        raise RefactorError("observation candidate ordering mismatch")
    proofs = {"BASELINE": run["task"]["baseline_proof"], **{c["candidate_id"]: c["proof"] for c in run["task"]["candidates"]}}
    costs = {"BASELINE": 0, **{c["candidate_id"]: c["api_cost_microusd"] for c in run["task"]["candidates"]}}
    models = {"BASELINE": "REFERENCE", **{c["candidate_id"]: c["model"] for c in run["task"]["candidates"]}}
    for ob in observations:
        proof = proofs[ob["candidate_id"]]
        source = assemble_source(run["task"], proof)
        if ob["proof_digest"] != sha256(proof.encode("utf-8")) or ob["source_digest"] != sha256(source.encode("utf-8")):
            raise RefactorError("proof/source commitment mismatch")
        if ob["token_count"] != proof_token_count(proof) or ob["byte_count"] != len(proof.encode("utf-8")) or ob["line_count"] != len(proof.splitlines()):
            raise RefactorError("local size metric mismatch")
        expected_kind = "baseline" if ob["candidate_id"] == "BASELINE" else "candidate"
        if ob["kind"] != expected_kind:
            raise RefactorError("candidate observation kind mismatch")
        if ob["api_cost_microusd"] != costs[ob["candidate_id"]] or ob["model"] != models[ob["candidate_id"]]:
            raise RefactorError("candidate ledger/model mismatch")
    expected_front = pareto_ids(observations)
    if package["pareto_ids"] != expected_front or package["selected_id"] != _select(observations, expected_front):
        raise RefactorError("Pareto/selection decision mismatch")
    used = sum(c["api_cost_microusd"] for c in run["task"]["candidates"])
    budget = _exact(package["budget"], BUDGET_KEYS, "budget")
    expected_by_model: dict[str, int] = {}
    for c in run["task"]["candidates"]:
        expected_by_model[c["model"]] = expected_by_model.get(c["model"], 0) + c["api_cost_microusd"]
    expected_by_model = {k: expected_by_model[k] for k in sorted(expected_by_model)}
    if (budget["track"] != "closed-source-llm"
            or budget["limit_microusd_per_problem"] != TRACK1_LIMIT_MICROUSD
            or budget["used_microusd"] != used
            or budget["remaining_microusd"] != TRACK1_LIMIT_MICROUSD - used
            or budget["used_by_model_microusd"] != expected_by_model
            or budget["spend_semantics"] != "DECLARED_GENERATION_LEDGER_ONLY_HARNESS_DOES_NOT_CALL_MODELS_OR_SPEND"):
        raise RefactorError("budget summary mismatch")
    receipt = _exact(package["receipt"], RECEIPT_KEYS, "receipt")
    by_id = {x["candidate_id"]: x for x in observations}
    selected_source = by_id[package["selected_id"]]["source_digest"] if package["selected_id"] in by_id else "NONE"
    if (receipt["input_digest"] != sha256(canonical_bytes(run))
            or receipt["task_digest"] != sha256(canonical_bytes(run["task"]))
            or receipt["toolchain_digest"] != sha256(canonical_bytes(run["toolchains"]))
            or receipt["baseline_source_digest"] != by_id["BASELINE"]["source_digest"]
            or receipt["selected_source_digest"] != selected_source):
        raise RefactorError("receipt commitment mismatch")
    if package["metric_notice"] != METRIC_NOTICE:
        raise RefactorError("metric notice mismatch")
    if package["authorities"] != AUTHORITIES or any(package["authorities"].values()):
        raise RefactorError("authority ceiling mismatch")
    rerun_match = None
    if rerun_compilers:
        fresh = compile_run(run)
        fresh_by_id = {x["candidate_id"]: x for x in fresh["observations"]}
        rerun_match = True
        for old in observations:
            new = fresh_by_id[old["candidate_id"]]
            if old["target_pass"] != new["target_pass"] or old["transfer_passes"] != new["transfer_passes"]:
                rerun_match = False
                break
    return {
        "valid": True,
        "package_digest": actual,
        "task_id": run["task"]["task_id"],
        "selected_id": package["selected_id"],
        "pareto_ids": package["pareto_ids"],
        "used_microusd": used,
        "externally_committed": expected_package_digest is not None,
        "compiler_pass_vector_rerun_match": rerun_match,
    }


def result_bytes(package: dict[str, Any]) -> bytes:
    return canonical_bytes(package) + b"\n"


def write_exclusive(path: str | os.PathLike[str], data: bytes) -> None:
    target = os.fspath(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags, 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(fd, data[offset:])
        os.fsync(fd)
    except Exception:
        os.close(fd)
        try:
            os.unlink(target)
        except FileNotFoundError:
            pass
        raise
    else:
        os.close(fd)


__all__ = [
    "AUTHORITIES", "RefactorError", "RUN_SCHEMA", "TASK_SCHEMA", "RESULT_SCHEMA",
    "TRACK1_LIMIT_MICROUSD", "assemble_source", "canonical_bytes", "compile_run",
    "load_json_bytes", "normalize_run", "pareto_ids", "proof_token_count",
    "result_bytes", "sha256", "verify_result", "write_exclusive",
]
