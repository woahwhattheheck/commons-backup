"""Strict input contract and hermetic bridge to the retained execution-truth classifier."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PRED = HERE.parent / "actions_execution_truth"


def _load_predecessor() -> tuple[Any, Any]:
    """Load predecessor modules without leaking generic names into sys.path/sys.modules."""
    schema_name = "_commons_actions_execution_truth_schema"
    truth_name = "_commons_actions_execution_truth_truth"

    schema_spec = importlib.util.spec_from_file_location(schema_name, PRED / "schema.py")
    if schema_spec is None or schema_spec.loader is None:
        raise ImportError("cannot load retained actions_execution_truth schema")
    schema_mod = importlib.util.module_from_spec(schema_spec)
    sys.modules[schema_name] = schema_mod
    schema_spec.loader.exec_module(schema_mod)

    missing = object()
    prior_schema = sys.modules.get("schema", missing)
    sys.modules["schema"] = schema_mod
    try:
        truth_spec = importlib.util.spec_from_file_location(truth_name, PRED / "truth.py")
        if truth_spec is None or truth_spec.loader is None:
            raise ImportError("cannot load retained actions_execution_truth truth module")
        truth_mod = importlib.util.module_from_spec(truth_spec)
        sys.modules[truth_name] = truth_mod
        truth_spec.loader.exec_module(truth_mod)
    finally:
        if prior_schema is missing:
            sys.modules.pop("schema", None)
        else:
            sys.modules["schema"] = prior_schema
    return schema_mod, truth_mod


_PRED_SCHEMA, _PRED_TRUTH = _load_predecessor()
EvidenceError = _PRED_SCHEMA.EvidenceError
canonical_bytes = _PRED_SCHEMA.canonical_bytes
digest = _PRED_SCHEMA.digest
loads_strict = _PRED_SCHEMA.loads_strict
classify_case = _PRED_TRUTH.classify_case

CAPTURE_SCHEMA = "commons-actions-merge-train-capture/v2"
WORKFLOW_OBSERVATION_SCHEMA = "commons-actions-workflow-observation/v1"
REVIEW_SCHEMA = "commons-source-review-capture/v1"
TOPOLOGY_SCHEMA = "commons-pr-topology-capture/v1"
RECEIPT_SCHEMA = "commons-actions-merge-train-receipt/v2"
VERIFY_SCHEMA = "commons-actions-merge-train-verification/v2"
MAX_CAPTURES = 64
MAX_WORKFLOWS = 64
MAX_CASES_PER_WORKFLOW = 32
MAX_WORKFLOW_NAME = 160
MAX_OBSERVATION_PAGES = 128
MAX_CURSOR = 1024

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REVIEW_STATES = {"GREEN", "RED", "ABSENT", "AMBIGUOUS"}
TOPOLOGY_STATES = {"CURRENT", "STALE", "ABSENT", "AMBIGUOUS"}


def exact(v: Any, keys: set[str], where: str) -> dict[str, Any]:
    if type(v) is not dict:
        raise EvidenceError(f"{where}: expected object")
    actual = set(v)
    if actual != keys:
        raise EvidenceError(
            f"{where}: schema mismatch missing={sorted(keys-actual)} extra={sorted(actual-keys)}"
        )
    return v


def text(v: Any, where: str, n: int = 512) -> str:
    if type(v) is not str or not v or len(v) > n:
        raise EvidenceError(f"{where}: expected non-empty string <= {n} characters")
    return v


def pos(v: Any, where: str) -> int:
    if type(v) is not int or v <= 0:
        raise EvidenceError(f"{where}: expected positive integer (bool is not int)")
    return v


def nonneg(v: Any, where: str) -> int:
    if type(v) is not int or v < 0:
        raise EvidenceError(f"{where}: expected non-negative integer (bool is not int)")
    return v


def strict_bool(v: Any, where: str) -> bool:
    if type(v) is not bool:
        raise EvidenceError(f"{where}: expected boolean")
    return v


def sha(v: Any, where: str) -> str:
    value = text(v, where, 40)
    if not SHA_RE.fullmatch(value):
        raise EvidenceError(f"{where}: expected lowercase 40-hex commit SHA")
    return value


def repo(v: Any, where: str) -> str:
    value = text(v, where)
    if not REPO_RE.fullmatch(value):
        raise EvidenceError(f"{where}: expected owner/name")
    return value


def opt_pos(v: Any, where: str) -> int | None:
    return None if v is None else pos(v, where)


def opt_sha(v: Any, where: str) -> str | None:
    return None if v is None else sha(v, where)


def normalize_review(raw: Any) -> dict[str, Any]:
    x = exact(raw, {"schema", "repository", "pr_number", "head_sha", "state", "review_id"}, "source_review")
    if x["schema"] != REVIEW_SCHEMA:
        raise EvidenceError("source_review: wrong schema")
    state = text(x["state"], "source_review.state", 16)
    if state not in REVIEW_STATES:
        raise EvidenceError(f"source_review.state: unexpected value {state!r}")
    rid = opt_pos(x["review_id"], "source_review.review_id")
    if state in {"GREEN", "RED"} and rid is None:
        raise EvidenceError("source_review: GREEN/RED requires review_id")
    if state == "ABSENT" and rid is not None:
        raise EvidenceError("source_review: ABSENT requires null review_id")
    return {
        "schema": REVIEW_SCHEMA,
        "repository": repo(x["repository"], "source_review.repository"),
        "pr_number": pos(x["pr_number"], "source_review.pr_number"),
        "head_sha": sha(x["head_sha"], "source_review.head_sha"),
        "state": state,
        "review_id": rid,
    }


def normalize_topology(raw: Any) -> dict[str, Any]:
    x = exact(
        raw,
        {"schema", "repository", "pr_number", "head_sha", "base_sha", "behind_by", "state", "required_workflows"},
        "topology",
    )
    if x["schema"] != TOPOLOGY_SCHEMA:
        raise EvidenceError("topology: wrong schema")
    state = text(x["state"], "topology.state", 16)
    if state not in TOPOLOGY_STATES:
        raise EvidenceError(f"topology.state: unexpected value {state!r}")
    base = opt_sha(x["base_sha"], "topology.base_sha")
    behind = None if x["behind_by"] is None else nonneg(x["behind_by"], "topology.behind_by")
    if state == "CURRENT" and (base is None or behind != 0):
        raise EvidenceError("topology: CURRENT requires base_sha and behind_by=0")
    if state == "ABSENT" and (base is not None or behind is not None):
        raise EvidenceError("topology: ABSENT requires null base_sha/behind_by")
    raw_names = x["required_workflows"]
    if type(raw_names) is not list or not raw_names or len(raw_names) > MAX_WORKFLOWS:
        raise EvidenceError(f"topology.required_workflows: expected 1..{MAX_WORKFLOWS} names")
    names = [text(n, "topology.required_workflows[]", MAX_WORKFLOW_NAME) for n in raw_names]
    if len(names) != len(set(names)):
        raise EvidenceError("topology.required_workflows: duplicate workflow name")
    return {
        "schema": TOPOLOGY_SCHEMA,
        "repository": repo(x["repository"], "topology.repository"),
        "pr_number": pos(x["pr_number"], "topology.pr_number"),
        "head_sha": sha(x["head_sha"], "topology.head_sha"),
        "base_sha": base,
        "behind_by": behind,
        "state": state,
        "required_workflows": sorted(names),
    }


def normalize_observation(
    raw: Any,
    *,
    repository: str,
    head_sha: str,
    workflow: str,
    case_count: int,
) -> dict[str, Any]:
    x = exact(
        raw,
        {
            "schema",
            "repository",
            "head_sha",
            "workflow",
            "observed_case_count",
            "pages_fetched",
            "pagination_exhausted",
            "next_cursor",
        },
        f"workflow {workflow}.observation",
    )
    if x["schema"] != WORKFLOW_OBSERVATION_SCHEMA:
        raise EvidenceError(f"workflow {workflow}.observation: wrong schema")
    observed_repository = repo(x["repository"], f"workflow {workflow}.observation.repository")
    observed_head = sha(x["head_sha"], f"workflow {workflow}.observation.head_sha")
    observed_workflow = text(x["workflow"], f"workflow {workflow}.observation.workflow", MAX_WORKFLOW_NAME)
    observed_count = nonneg(x["observed_case_count"], f"workflow {workflow}.observation.observed_case_count")
    pages = pos(x["pages_fetched"], f"workflow {workflow}.observation.pages_fetched")
    if pages > MAX_OBSERVATION_PAGES:
        raise EvidenceError(f"workflow {workflow}.observation.pages_fetched exceeds {MAX_OBSERVATION_PAGES}")
    exhausted = strict_bool(x["pagination_exhausted"], f"workflow {workflow}.observation.pagination_exhausted")
    cursor = x["next_cursor"]
    if cursor is not None:
        cursor = text(cursor, f"workflow {workflow}.observation.next_cursor", MAX_CURSOR)

    if (observed_repository, observed_head, observed_workflow) != (repository, head_sha, workflow):
        raise EvidenceError(f"workflow {workflow}.observation repository/head/workflow binding mismatch")
    if observed_count != case_count:
        raise EvidenceError(
            f"workflow {workflow}.observation count mismatch: observed={observed_count} cases={case_count}"
        )
    if exhausted and cursor is not None:
        raise EvidenceError(f"workflow {workflow}.observation exhausted pagination requires null next_cursor")
    if not exhausted and cursor is None:
        raise EvidenceError(f"workflow {workflow}.observation incomplete pagination requires next_cursor")
    return {
        "schema": WORKFLOW_OBSERVATION_SCHEMA,
        "repository": observed_repository,
        "head_sha": observed_head,
        "workflow": observed_workflow,
        "observed_case_count": observed_count,
        "pages_fetched": pages,
        "pagination_exhausted": exhausted,
        "next_cursor": cursor,
    }


def normalize_capture(raw: Any) -> dict[str, Any]:
    x = exact(raw, {"schema", "repository", "pr_number", "head_sha", "workflows", "source_review", "topology"}, "capture")
    if x["schema"] != CAPTURE_SCHEMA:
        raise EvidenceError("capture: wrong schema")
    repository = repo(x["repository"], "capture.repository")
    pr = pos(x["pr_number"], "capture.pr_number")
    head = sha(x["head_sha"], "capture.head_sha")
    review = normalize_review(x["source_review"])
    topology = normalize_topology(x["topology"])
    for label, evidence in (("source_review", review), ("topology", topology)):
        if (evidence["repository"], evidence["pr_number"], evidence["head_sha"]) != (repository, pr, head):
            raise EvidenceError(f"capture/{label} repository/pr/head binding mismatch")

    raw_workflows = x["workflows"]
    if type(raw_workflows) is not list or not raw_workflows or len(raw_workflows) > MAX_WORKFLOWS:
        raise EvidenceError(f"capture.workflows: expected 1..{MAX_WORKFLOWS} workflow groups")
    out: list[dict[str, Any]] = []
    names: list[str] = []
    for idx, wraw in enumerate(raw_workflows, 1):
        w = exact(wraw, {"name", "cases", "observation"}, f"workflow {idx}")
        name = text(w["name"], f"workflow {idx}.name", MAX_WORKFLOW_NAME)
        cases = w["cases"]
        if type(cases) is not list or len(cases) > MAX_CASES_PER_WORKFLOW:
            raise EvidenceError(f"workflow {name}.cases: expected list <= {MAX_CASES_PER_WORKFLOW}")
        pairs = []
        for case_idx, craw in enumerate(cases, 1):
            case_raw = exact(craw, {"run", "jobs"}, f"workflow {name} case {case_idx}")
            pairs.append({"run": case_raw["run"], "jobs": case_raw["jobs"]})
        observation = normalize_observation(
            w["observation"],
            repository=repository,
            head_sha=head,
            workflow=name,
            case_count=len(pairs),
        )
        out.append({"name": name, "cases": pairs, "observation": observation})
        names.append(name)

    if len(names) != len(set(names)):
        raise EvidenceError("capture.workflows: duplicate workflow name")
    if sorted(names) != topology["required_workflows"]:
        raise EvidenceError("capture.workflows do not exactly match topology.required_workflows")
    out.sort(key=lambda row: row["name"])
    return {
        "schema": CAPTURE_SCHEMA,
        "repository": repository,
        "pr_number": pr,
        "head_sha": head,
        "workflows": out,
        "source_review": review,
        "topology": topology,
    }
