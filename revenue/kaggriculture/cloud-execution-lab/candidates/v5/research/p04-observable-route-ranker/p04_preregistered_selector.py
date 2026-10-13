#!/usr/bin/env python3
"""Pre-registered low-complexity selector fitter for the TITAN V5 P04 route matrix.

Discovery can nominate only a frozen, observation-only rule. The public fitting
surface consumes immutable route-matrix JSONL bytes from canonical-main history
and re-runs the merged P04 reducer; caller-authored reduced summaries are never
authority. Fresh held-out native cells remain required before any runtime
component or promotion decision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from p04_route_ranker import (
    ALL_PLANS,
    FINAL_PLAN_STEP,
    NATURAL_STEP144_PLANS,
    PRODUCTION_ARCHIVE_SHA256,
    ROUTER_SOURCE_SHA256,
    ROUTE_STEP,
    SCHEMA as RANKER_SCHEMA,
    SOURCE_CENSUS_COMMIT,
    canonical_public_snapshot,
    expected_incumbent_plan,
    public_feature_signature,
    reduce_matrix,
)

SCHEMA = "titan-v5-p04-preregistered-selector/v1"
EVIDENCE_SCHEMA = "titan-v5-p04-committed-row-evidence/v2"
EVIDENCE_PREFIX = "revenue/kaggriculture/cloud-execution-lab/candidates/v5/selective-carrot/route-matrix-native/"
TRUSTED_MAIN_REF = "refs/remotes/origin/main"
CANONICAL_ORIGIN_URLS = frozenset(
    {
        "https://github.com/woahwhattheheck/commons.git",
        "https://github.com/woahwhattheheck/commons",
        "git@github.com:woahwhattheheck/commons.git",
    }
)
ALLOWED_FEATURES = (
    "shop_pair",
    "first_two_yarn_count",
    "wool_vs_milk_price",
    "wool_vs_milk_inventory",
    "wheat_vs_carrot_price",
    "rival_livestock_leader",
    "rival_crop_leader",
)
OVERRIDE_PLANS = tuple(NATURAL_STEP144_PLANS)

SPEC = {
    "schema": "titan-v5-p04-selector-preregistration-spec/v1",
    "input": {
        "ranker_schema": RANKER_SCHEMA,
        "production_archive_sha256": PRODUCTION_ARCHIVE_SHA256,
        "router_source_sha256": ROUTER_SOURCE_SHA256,
        "route_step": ROUTE_STEP,
        "forced_terminal_plan_step": FINAL_PLAN_STEP,
        "allowed_features": list(ALLOWED_FEATURES),
        "forbidden_identifiers": ["seed", "opponent", "seat", "snapshot_sha256"],
    },
    "rule_class": {
        "fallback": "source_recomputed_incumbent_plan",
        "forms": [
            "always_override_with_one_natural_plan",
            "one_allowed_feature_equals_one_training_observed_value_then_override_with_one_natural_plan",
        ],
        "override_plans": list(OVERRIDE_PLANS),
        "max_predicates": 1,
        "plan_2_allowed": False,
    },
    "discovery_qualification": {
        "minimum_engaged_groups": 2,
        "require_two_distinct_seeds_when_available": True,
        "require_two_distinct_opponents_when_available": True,
        "require_both_seats_when_available": True,
        "failure_groups": 0,
        "minimum_delta_margin_vs_incumbent": 0.0,
        "minimum_delta_own_vs_incumbent": 0.0,
        "strictly_positive_total_margin_delta": True,
    },
    "selection_order": [
        "max_min_delta_margin",
        "max_min_delta_own",
        "max_mean_delta_margin",
        "max_mean_delta_own",
        "max_engaged_groups",
        "prefer_global_over_conditional",
        "lowest_lexicographic_predicate",
        "lowest_plan_id",
    ],
    "activation": {
        "discovery_can_only_nominate": True,
        "fresh_heldout_native_required": True,
        "heldout_rule_must_be_byte_identical": True,
        "default_off_until_separate_promotion": True,
    },
}

DISCOVERY_UNIVERSE = {
    "schema": "titan-v5-p04-discovery-universe/v1",
    "source": {
        "kind": "slack_preoutcome_route_board",
        "channel_id": "C0C0Z8AHGP2",
        "message_ts": "1789253666.394169",
    },
    "group_keys": [
        {"seed": 1209131101, "opponent": "apex_v7", "seat": 0},
        {"seed": 1209131101, "opponent": "apex_v7", "seat": 1},
        {"seed": 1209131101, "opponent": "arlene_v14", "seat": 0},
        {"seed": 1209131101, "opponent": "arlene_v14", "seat": 1},
        {"seed": 1209131102, "opponent": "apex_v7", "seat": 0},
        {"seed": 1209131102, "opponent": "apex_v7", "seat": 1},
        {"seed": 1209131102, "opponent": "arlene_v14", "seat": 0},
        {"seed": 1209131102, "opponent": "arlene_v14", "seat": 1},
    ],
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


PREREGISTERED_SPEC_SHA256 = "c0d57d3b20aba4ce8ecca7cc07ac3cf56bd7f7aeb9260efe1f6519d62aa8719e"
if _sha256(SPEC) != PREREGISTERED_SPEC_SHA256:
    raise RuntimeError("preregistered selector SPEC drift")
SPEC_SHA256 = PREREGISTERED_SPEC_SHA256

DISCOVERY_UNIVERSE_SHA256 = "3c393d57c4caae9c5ee3b4e6c1110220efbb556b48230ca209061b57a4119a66"
if _sha256(DISCOVERY_UNIVERSE) != DISCOVERY_UNIVERSE_SHA256:
    raise RuntimeError("pre-outcome discovery universe commitment drift")


def preregistration() -> dict[str, Any]:
    return {
        "spec": SPEC,
        "spec_sha256": SPEC_SHA256,
        "discovery_universe": DISCOVERY_UNIVERSE,
        "discovery_universe_sha256": DISCOVERY_UNIVERSE_SHA256,
        "accepted_evidence": {
            "schema": EVIDENCE_SCHEMA,
            "namespace": EVIDENCE_PREFIX,
            "canonical_origin_urls": sorted(CANONICAL_ORIGIN_URLS),
            "trusted_main_ref": TRUSTED_MAIN_REF,
            "trust": (
                "immutable JSONL bytes at a commit proven ancestor of canonical Commons origin/main; "
                "public repository root is derived from this module, reduced summaries rejected"
            ),
        },
    }


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{label} must be finite")
    return out


def _feature_value(value: Any, label: str) -> str | int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must not be bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value:
        return value
    raise ValueError(f"{label} must be a nonempty string or integer")


def _validate_authority(report: dict[str, Any]) -> None:
    if report.get("schema") != RANKER_SCHEMA:
        raise ValueError("route-ranker schema mismatch")
    expected = {
        "production_archive_sha256": PRODUCTION_ARCHIVE_SHA256,
        "router_source_sha256": ROUTER_SOURCE_SHA256,
        "source_census_commit": SOURCE_CENSUS_COMMIT,
        "route_step": ROUTE_STEP,
        "forced_terminal_plan_step": FINAL_PLAN_STEP,
    }
    if report.get("authority") != expected:
        raise ValueError("route-ranker authority mismatch")
    if report.get("policy_ready") is not False:
        raise ValueError("discovery report must remain policy_ready=false")


def _normalize_group(group: Any) -> dict[str, Any]:
    if not isinstance(group, dict):
        raise ValueError("route-ranker group must be an object")
    for name in ("seed", "opponent", "seat", "features", "incumbent_plan", "plans"):
        if name not in group:
            raise ValueError(f"route-ranker group missing {name}")
    seed, opponent, seat, incumbent = group["seed"], group["opponent"], group["seat"], group["incumbent_plan"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be integer")
    if not isinstance(opponent, str) or not opponent:
        raise ValueError("opponent must be nonempty string")
    if isinstance(seat, bool) or seat not in (0, 1):
        raise ValueError("seat must be 0 or 1")
    if isinstance(incumbent, bool) or incumbent not in ALL_PLANS:
        raise ValueError("incumbent_plan must be 0..12")

    features = group["features"]
    if not isinstance(features, dict) or set(features) != set(ALLOWED_FEATURES):
        raise ValueError("feature signature does not match preregistered public surface")
    clean_features = {name: _feature_value(features[name], f"features.{name}") for name in ALLOWED_FEATURES}

    plans = group["plans"]
    if not isinstance(plans, list) or len(plans) != len(ALL_PLANS):
        raise ValueError("each discovery group must contain exactly 13 plan rows")
    by_plan: dict[int, dict[str, Any]] = {}
    for row in plans:
        if not isinstance(row, dict):
            raise ValueError("plan row must be object")
        plan = row.get("plan")
        if isinstance(plan, bool) or plan not in ALL_PLANS or plan in by_plan:
            raise ValueError("plan rows must contain each plan exactly once")
        failures = row.get("failures", [])
        if not isinstance(failures, list) or not all(isinstance(x, str) for x in failures):
            raise ValueError("plan failures must be a list of strings")
        by_plan[plan] = {
            "plan": plan,
            "delta_margin_vs_incumbent": _finite(row.get("delta_margin_vs_incumbent"), "delta_margin_vs_incumbent"),
            "delta_own_vs_incumbent": _finite(row.get("delta_own_vs_incumbent"), "delta_own_vs_incumbent"),
            "failures": list(failures),
        }
    if set(by_plan) != set(ALL_PLANS):
        raise ValueError("plan rows do not cover 0..12")
    base = by_plan[incumbent]
    if base["delta_margin_vs_incumbent"] != 0 or base["delta_own_vs_incumbent"] != 0:
        raise ValueError("incumbent deltas must be zero")
    return {
        "seed": seed,
        "opponent": opponent,
        "seat": seat,
        "features": clean_features,
        "incumbent_plan": incumbent,
        "plans": by_plan,
    }


def _expected_discovery_keys() -> set[tuple[int, str, int]]:
    return {(row["seed"], row["opponent"], row["seat"]) for row in DISCOVERY_UNIVERSE["group_keys"]}


def validate_discovery_report(report: Any) -> list[dict[str, Any]]:
    """Validate reducer output. This is an internal seam, not evidence authority."""
    if not isinstance(report, dict):
        raise ValueError("discovery report must be an object")
    _validate_authority(report)
    groups_raw = report.get("groups")
    if not isinstance(groups_raw, list) or not groups_raw:
        raise ValueError("discovery report groups must be a nonempty list")
    groups = [_normalize_group(group) for group in groups_raw]
    keys = [(g["seed"], g["opponent"], g["seat"]) for g in groups]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate seed/opponent/seat discovery group")
    expected, actual = _expected_discovery_keys(), set(keys)
    if actual != expected:
        raise ValueError(f"discovery universe mismatch: missing={sorted(expected - actual)} extra={sorted(actual - expected)}")
    if report.get("complete_snapshot_groups") != len(groups):
        raise ValueError("complete_snapshot_groups mismatch")
    if len(groups) != len(expected):
        raise ValueError("complete_snapshot_groups does not match pre-outcome discovery universe")
    return groups


def _rule_key(rule: dict[str, Any]) -> tuple[Any, ...]:
    pred = rule.get("predicate")
    if pred is None:
        return (0, "", "", rule["override_plan"])
    return (1, pred["feature"], json.dumps(pred["value"], sort_keys=True), rule["override_plan"])


def enumerate_rules(groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = list(groups)
    values: dict[str, set[str | int]] = {name: set() for name in ALLOWED_FEATURES}
    for group in groups:
        for name in ALLOWED_FEATURES:
            values[name].add(group["features"][name])
    rules = [{"predicate": None, "override_plan": plan} for plan in OVERRIDE_PLANS]
    for feature in ALLOWED_FEATURES:
        for value in sorted(values[feature], key=lambda x: (type(x).__name__, repr(x))):
            rules.extend(
                {"predicate": {"feature": feature, "value": value}, "override_plan": plan}
                for plan in OVERRIDE_PLANS
            )
    return sorted(rules, key=_rule_key)


def selected_plan_for_features(features: dict[str, Any], incumbent_plan: int, rule: dict[str, Any]) -> int:
    plan = rule.get("override_plan")
    if isinstance(plan, bool) or plan not in OVERRIDE_PLANS:
        raise ValueError("override plan is outside preregistered natural-plan set")
    pred = rule.get("predicate")
    if pred is None:
        return plan
    if not isinstance(pred, dict) or set(pred) != {"feature", "value"}:
        raise ValueError("predicate must be null or one feature equality")
    feature = pred["feature"]
    if feature not in ALLOWED_FEATURES:
        raise ValueError("predicate uses non-preregistered feature")
    return plan if features[feature] == pred["value"] else incumbent_plan


def select_plan(snapshot: Any, rule: dict[str, Any]) -> int:
    canonical = canonical_public_snapshot(snapshot)
    incumbent = expected_incumbent_plan(canonical["first_two_shops"])
    if canonical["incumbent_plan"] != incumbent:
        raise ValueError("snapshot incumbent does not match source mapping")
    return selected_plan_for_features(public_feature_signature(canonical), incumbent, rule)


def _coverage_floor(total_distinct: int) -> int:
    return min(2, total_distinct)


def evaluate_rule(groups: Iterable[dict[str, Any]], rule: dict[str, Any]) -> dict[str, Any]:
    groups = list(groups)
    engaged = []
    for group in groups:
        selected = selected_plan_for_features(group["features"], group["incumbent_plan"], rule)
        if selected == group["incumbent_plan"]:
            continue
        candidate = group["plans"][selected]
        control = group["plans"][group["incumbent_plan"]]
        engaged.append({
            "seed": group["seed"],
            "opponent": group["opponent"],
            "seat": group["seat"],
            "delta_margin": candidate["delta_margin_vs_incumbent"],
            "delta_own": candidate["delta_own_vs_incumbent"],
            "candidate_failures": candidate["failures"],
            "incumbent_failures": control["failures"],
        })

    seeds = {g["seed"] for g in groups}
    opponents = {g["opponent"] for g in groups}
    seats = {g["seat"] for g in groups}
    engaged_seeds = {g["seed"] for g in engaged}
    engaged_opponents = {g["opponent"] for g in engaged}
    engaged_seats = {g["seat"] for g in engaged}
    dm = [g["delta_margin"] for g in engaged]
    do = [g["delta_own"] for g in engaged]
    candidate_failure_groups = sum(bool(g["candidate_failures"]) for g in engaged)
    incumbent_failure_groups = sum(bool(g["incumbent_failures"]) for g in engaged)
    comparison_failure_groups = sum(bool(g["candidate_failures"] or g["incumbent_failures"]) for g in engaged)
    qualified = bool(engaged)
    qualified = qualified and len(engaged) >= SPEC["discovery_qualification"]["minimum_engaged_groups"]
    qualified = qualified and len(engaged_seeds) >= _coverage_floor(len(seeds))
    qualified = qualified and len(engaged_opponents) >= _coverage_floor(len(opponents))
    qualified = qualified and len(engaged_seats) >= _coverage_floor(len(seats))
    qualified = qualified and comparison_failure_groups == 0
    qualified = qualified and min(dm, default=float("-inf")) >= 0
    qualified = qualified and min(do, default=float("-inf")) >= 0
    qualified = qualified and sum(dm) > 0
    return {
        "rule": rule,
        "qualified": qualified,
        "engaged_groups": len(engaged),
        "engaged_distinct_seeds": len(engaged_seeds),
        "engaged_distinct_opponents": len(engaged_opponents),
        "engaged_distinct_seats": len(engaged_seats),
        "failure_groups": comparison_failure_groups,
        "candidate_failure_groups": candidate_failure_groups,
        "incumbent_failure_groups": incumbent_failure_groups,
        "min_delta_margin": min(dm) if dm else None,
        "min_delta_own": min(do) if do else None,
        "mean_delta_margin": statistics.fmean(dm) if dm else None,
        "mean_delta_own": statistics.fmean(do) if do else None,
        "total_delta_margin": sum(dm),
        "total_delta_own": sum(do),
    }


def _selection_key(result: dict[str, Any]) -> tuple[Any, ...]:
    pred = result["rule"].get("predicate")
    return (
        -result["min_delta_margin"],
        -result["min_delta_own"],
        -result["mean_delta_margin"],
        -result["mean_delta_own"],
        -result["engaged_groups"],
        0 if pred is None else 1,
        "" if pred is None else pred["feature"],
        "" if pred is None else json.dumps(pred["value"], sort_keys=True),
        result["rule"]["override_plan"],
    )


def _fit_reduced_report(report: Any) -> dict[str, Any]:
    groups = validate_discovery_report(report)
    evaluated = [evaluate_rule(groups, rule) for rule in enumerate_rules(groups)]
    qualified = [item for item in evaluated if item["qualified"]]
    selected = min(qualified, key=_selection_key) if qualified else None
    return {
        "schema": SCHEMA,
        "preregistration_spec_sha256": SPEC_SHA256,
        "discovery_universe_sha256": DISCOVERY_UNIVERSE_SHA256,
        "discovery_report_sha256": _sha256(report),
        "authority": SPEC["input"],
        "discovery_groups": len(groups),
        "candidate_rules_evaluated": len(evaluated),
        "qualified_rules": len(qualified),
        "selected": selected,
        "policy_ready": False,
        "composer_ready": False,
        "heldout_required": selected is not None,
        "hold_reason": (
            "Discovery may nominate only the byte-frozen preregistered rule. Fresh held-out native games "
            "must validate that exact rule before any runtime component or promotion decision."
            if selected is not None
            else "No preregistered low-complexity rule met the discovery non-regression and coverage gate."
        ),
    }


def fit_selector(report: Any) -> dict[str, Any]:
    """Fail closed on the superseded caller-authored reduced-summary interface."""
    raise ValueError(
        "caller-authored reduced reports are not evidence authority; "
        "use fit_selector_from_committed_evidence()"
    )


def _git(
    repo_root: Path,
    *args: str,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    if env:
        clean_env.update(env)
    try:
        proc = subprocess.run(
            ["git", "--no-replace-objects", *args],
            cwd=repo_root,
            env=clean_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise ValueError(f"cannot execute git: {exc}") from exc
    if check and proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return proc


def _validate_canonical_checkout(repo_root: Path) -> str:
    remote_url = _git(repo_root, "remote", "get-url", "origin").stdout.decode("utf-8", errors="strict").strip()
    if remote_url not in CANONICAL_ORIGIN_URLS:
        raise ValueError("origin is not the canonical woahwhattheheck/commons repository")
    if _git(repo_root, "rev-parse", "--verify", "--quiet", TRUSTED_MAIN_REF, check=False).returncode != 0:
        raise ValueError("canonical origin/main ref is unavailable; fetch origin/main before fitting evidence")
    return TRUSTED_MAIN_REF


def _resolve_trusted_main_commit(
    repo_root: Path,
    trusted_main_commit: str | None = None,
) -> str:
    """Resolve and authenticate the trusted main commit tip.

    Authority requires an authenticated remote observation (e.g. via git ls-remote)
    or an explicit provider-supplied SHA. An attacker-mutable local ref alone
    cannot manufacture authority.
    """
    if trusted_main_commit is not None:
        if not isinstance(trusted_main_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", trusted_main_commit):
            raise ValueError("trusted_main_commit must be one full lowercase 40-hex commit SHA")
        resolved = _git(
            repo_root, "rev-parse", "--verify", "--quiet", f"{trusted_main_commit}^{{commit}}", check=False
        )
        if resolved.returncode != 0 or resolved.stdout.decode().strip() != trusted_main_commit:
            raise ValueError(f"trusted_main_commit {trusted_main_commit} does not resolve to a commit in repository")
        trusted_tip = trusted_main_commit
    else:
        ls_proc = _git(repo_root, "ls-remote", "--heads", "origin", "refs/heads/main", check=False)
        if ls_proc.returncode != 0:
            detail = ls_proc.stderr.decode("utf-8", errors="replace").strip()
            raise ValueError(
                f"cannot authenticate trusted main tip via origin ls-remote: {detail}; "
                "supply trusted_main_commit or connect to canonical remote"
            )
        stdout_text = ls_proc.stdout.decode("utf-8", errors="strict").strip()
        match = re.search(r"^([0-9a-f]{40})\s+refs/heads/main$", stdout_text, re.MULTILINE)
        if not match:
            raise ValueError("authenticated remote origin/main tip not found in ls-remote output")
        remote_tip = match.group(1)
        check_local = _git(repo_root, "rev-parse", "--verify", "--quiet", f"{remote_tip}^{{commit}}", check=False)
        if check_local.returncode != 0:
            raise ValueError(
                f"authenticated remote main tip {remote_tip} is not present in local repository; run git fetch origin"
            )
        trusted_tip = remote_tip

    local_origin_main = _git(repo_root, "rev-parse", "--verify", "--quiet", TRUSTED_MAIN_REF, check=False)
    if local_origin_main.returncode == 0:
        local_sha = local_origin_main.stdout.decode().strip()
        if local_sha != trusted_tip:
            if _git(repo_root, "merge-base", "--is-ancestor", local_sha, trusted_tip, check=False).returncode != 0:
                raise ValueError(
                    f"local {TRUSTED_MAIN_REF} ({local_sha}) is not an ancestor of authenticated main tip ({trusted_tip})"
                )

    return trusted_tip


def _canonical_repo_root() -> Path:
    module_dir = Path(__file__).resolve().parent
    root_text = _git(module_dir, "rev-parse", "--show-toplevel").stdout.decode("utf-8", errors="strict").strip()
    root = Path(root_text).resolve()
    if not root.is_dir():
        raise ValueError("canonical repository root is unavailable")
    _validate_canonical_checkout(root)
    return root


def _canonical_evidence_path(raw: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise ValueError("evidence path must be a nonempty repository-relative string")
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts or str(path) != raw:
        raise ValueError("evidence path must be canonical repository-relative POSIX syntax")
    if not raw.startswith(EVIDENCE_PREFIX) or not raw.endswith(".jsonl"):
        raise ValueError("evidence path must be canonical route-matrix-native JSONL")
    return raw


def load_committed_rows(
    repo_root: Path,
    evidence_commit: str,
    evidence_paths: Iterable[str],
    *,
    trusted_main_commit: str | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    repo_root = Path(repo_root).resolve()
    if not repo_root.is_dir():
        raise ValueError("repo_root must be an existing directory")
    trusted_ref = _validate_canonical_checkout(repo_root)
    trusted_commit = _resolve_trusted_main_commit(repo_root, trusted_main_commit=trusted_main_commit)
    if not isinstance(evidence_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", evidence_commit):
        raise ValueError("evidence_commit must be one full lowercase 40-hex commit SHA")
    resolved = _git(repo_root, "rev-parse", "--verify", f"{evidence_commit}^{{commit}}").stdout.decode().strip()
    if resolved != evidence_commit:
        raise ValueError("evidence_commit did not resolve to the exact requested commit")
    if _git(repo_root, "merge-base", "--is-ancestor", evidence_commit, trusted_commit, check=False).returncode != 0:
        raise ValueError(f"evidence commit is not an ancestor of canonical main tip {trusted_commit}")

    paths = [_canonical_evidence_path(path) for path in evidence_paths]
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("evidence_paths must be a nonempty duplicate-free list")

    rows: list[Any] = []
    members = []
    for path in sorted(paths):
        payload = _git(repo_root, "show", f"{evidence_commit}:{path}").stdout
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError(f"committed evidence path is not UTF-8 JSONL: {path}") from exc
        member_rows = []
        for lineno, raw_line in enumerate(text.splitlines(), 1):
            if not raw_line.strip():
                continue
            try:
                member_rows.append(json.loads(raw_line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid committed JSONL {path}:{lineno}: {exc}") from exc
        if not member_rows:
            raise ValueError(f"committed evidence path is empty: {path}")
        rows.extend(member_rows)
        members.append({
            "path": path,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "rows": len(member_rows),
        })

    return rows, {
        "schema": EVIDENCE_SCHEMA,
        "commit": evidence_commit,
        "trusted_main_ref": trusted_ref,
        "trusted_main_commit": trusted_commit,
        "members": members,
        "rows": len(rows),
    }


def _fit_selector_from_repo(
    repo_root: Path,
    evidence_commit: str,
    evidence_paths: Iterable[str],
    *,
    trusted_main_commit: str | None = None,
) -> dict[str, Any]:
    rows, evidence = load_committed_rows(
        repo_root,
        evidence_commit,
        evidence_paths,
        trusted_main_commit=trusted_main_commit,
    )
    report = reduce_matrix(rows)
    result = _fit_reduced_report(report)
    result["evidence"] = {**evidence, "reduced_report_sha256": _sha256(report)}
    return result


def fit_selector_from_committed_evidence(
    evidence_commit: str,
    evidence_paths: Iterable[str],
    *,
    trusted_main_commit: str | None = None,
) -> dict[str, Any]:
    """Fit only from committed evidence in the canonical checkout containing this module."""
    return _fit_selector_from_repo(
        _canonical_repo_root(),
        evidence_commit,
        evidence_paths,
        trusted_main_commit=trusted_main_commit,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-commit")
    parser.add_argument("--evidence-path", action="append", default=[])
    parser.add_argument("--trusted-main-commit")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-preregistration", action="store_true")
    args = parser.parse_args()
    if args.print_preregistration:
        payload = preregistration()
    else:
        if args.evidence_commit is None or not args.evidence_path:
            parser.error("--evidence-commit and at least one --evidence-path are required")
        payload = fit_selector_from_committed_evidence(
            args.evidence_commit,
            args.evidence_path,
            trusted_main_commit=args.trusted_main_commit,
        )
    encoded = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
