#!/usr/bin/env python3
"""Cancel only GitHub Actions runs whose queued heads are provably stale.

This is the privileged companion to :mod:`host.actions_queue_triage`.  The
triager stays read-only.  This command is dry-run by default; ``--execute`` is
required before it sends a cancellation request.

Safety contract:

* default mode uses only ``CANDIDATE_CLASSES``; explicit targets require fresh
  proof that their workflow is retired or their named pull request is closed;
* every candidate run is fetched again by id before action;
* default mode refreshes complete branch/open-PR inventories twice per candidate;
* targeted mode refreshes its retirement or closed-PR evidence twice instead;
* the second evidence refresh happens immediately before the final run read;
* the run is fetched one final time immediately before the POST;
* any moved head, non-queued status, inventory/read error, or reclassification
  to a keep/unknown state fails closed without a POST;
* ``--max-cancels`` bounds cancellation POSTs, or candidate rechecks in dry-run;
* the JSON receipt records dry-run / accepted / held outcomes without secrets.

Typical dry run::

    python -m host.actions_queue_cancel --repo woahwhattheheck/commons

Execute a bounded drain after inspecting the dry-run receipt::

    python -m host.actions_queue_cancel --repo woahwhattheheck/commons \
      --execute --max-cancels 25 --out /tmp/actions-cancel-receipt.json

Restrict a pass to a removed workflow (dry-run first; add ``--execute`` to act)::

    python -m host.actions_queue_cancel --repo woahwhattheheck/commons \
      --retired-workflow .github/workflows/merged-branch-janitor.yml \
      --run-id 37108017263 --max-cancels 1

Or name one closed PR and the exact check workflow to drain::

    python -m host.actions_queue_cancel --repo woahwhattheheck/commons \
      --closed-pr 30520 --workflow .github/workflows/source-parses.yml

``--run-id`` and ``--workflow`` repeat and combine as an intersection. Workflow
selection always uses the repository-relative YAML path, never a display name.
Selecting alone does not make a run stale. Retired-workflow mode proves that
the file is absent from the current default branch; closed-PR mode requires an
exact same-repository PR head/branch match and preserves open-PR heads/branches.
`--require-closed-pr` can additionally require an exact closed PR for a retired
workflow. It resolves commit associations and preserves ambiguous associations,
open PR heads/branches and non-PR events. This mode bounds candidate rechecks as
well as cancellation POSTs, including during execution.
Explicit run IDs avoid a repository-wide queue scan. Otherwise ``--cap`` still
bounds the observed queue and the receipt reports incomplete coverage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Sequence

try:
    from host.actions_queue_triage import (
        CANDIDATE_CLASSES,
        GitHub,
        GitHubError,
        _discover_token,
        _http_error,
        classify_run,
        make_snapshot,
    )
except ModuleNotFoundError:  # direct ``python host/actions_queue_cancel.py``
    from actions_queue_triage import (  # type: ignore[no-redef]
        CANDIDATE_CLASSES,
        GitHub,
        GitHubError,
        _discover_token,
        _http_error,
        classify_run,
        make_snapshot,
    )

SCHEMA = "commons-actions-queue-cancel/v1"
DEFAULT_REPO = "woahwhattheheck/commons"
TARGET_CANDIDATE_CLASSES = {"RETIRED_WORKFLOW_CANDIDATE", "CLOSED_SELECTED_PR_CANDIDATE"}


def _workflow_path(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or str(path) != value or "\\" in value
            or path.parent != PurePosixPath(".github/workflows")
            or path.suffix not in {".yml", ".yaml"}):
        raise ValueError("workflow must be an exact .github/workflows/*.yml or *.yaml path")
    return value


def _matches_selection(run: dict[str, Any], run_ids: set[int], workflows: set[str]) -> bool:
    return ((not run_ids or _run_id(run) in run_ids)
            and (not workflows or run.get("path") in workflows))


def _target_context(github: GitHub, repo: str, *, closed_pr: int | None,
                    retired_workflow: str | None, require_closed_pr: bool = False,
                    run: dict[str, Any] | None = None) -> dict[str, Any]:
    if retired_workflow:
        metadata = github.get(f"/repos/{repo}")
        default = metadata.get("default_branch") if isinstance(metadata, dict) else None
        if not isinstance(default, str) or not default:
            raise GitHubError("repository response has no default branch")
        path = urllib.parse.quote(retired_workflow, safe="/")
        try:
            github.get(f"/repos/{repo}/contents/{path}", {"ref": default})
        except GitHubError as exc:
            if exc.status != 404:
                raise
            context: dict[str, Any] = {"kind": "retired", "path": retired_workflow, "retired": True}
            if require_closed_pr and run is not None:
                # pull_request_target records can have an empty pull_requests
                # list. Commit associations still identify the exact PR head.
                associated = github.paged(f"/repos/{repo}/commits/{_head_sha(run)}/pulls")
                matches = []
                for pr in associated:
                    head = pr.get("head") or {}
                    if (type(pr.get("number")) is int
                            and head.get("sha") == _head_sha(run)
                            and head.get("ref") == run.get("head_branch")
                            and (head.get("repo") or {}).get("full_name") == repo):
                        matches.append(pr["number"])
                context["closed_pr_context"] = None
                if len(set(matches)) == 1:
                    closed_context = _target_context(
                        github, repo, closed_pr=matches[0], retired_workflow=None,
                    )
                    closed_context["allow_pull_request_target"] = True
                    context["closed_pr_context"] = closed_context
            return context
        return {"kind": "retired", "path": retired_workflow, "retired": False}

    pr = github.get(f"/repos/{repo}/pulls/{closed_pr}")
    if not isinstance(pr, dict) or pr.get("number") != closed_pr:
        raise GitHubError("named pull request response is invalid")
    open_prs = github.paged(f"/repos/{repo}/pulls?state=open")
    heads = set()
    numbers = set()
    branches = set()
    for item in open_prs:
        head = item.get("head")
        sha = _head_sha({"head_sha": head.get("sha")}) if isinstance(head, dict) else None
        if sha is None or type(item.get("number")) is not int:
            raise GitHubError("open-PR inventory contains an invalid head or number")
        heads.add(sha)
        numbers.add(item["number"])
        head_repo = (head.get("repo") or {}).get("full_name")
        if isinstance(head_repo, str) and isinstance(head.get("ref"), str):
            branches.add((head_repo, head["ref"]))
    return {"kind": "closed_pr", "pr": pr, "open_heads": heads,
            "open_numbers": numbers, "open_branches": branches}


def _classify_target(run: dict[str, Any], context: dict[str, Any], repo: str) -> dict[str, Any]:
    base = {"run_id": _run_id(run), "name": run.get("name"), "path": run.get("path")}

    def result(label: str, reason: str, candidate: bool = False) -> dict[str, Any]:
        return {**base, "classification": label, "reason": reason, "cancel_candidate": candidate}

    if run.get("status") != "queued":
        return result("KEEP_NOT_QUEUED", "target is no longer queued")
    sha = _head_sha(run)
    if sha is None or (run.get("head_repository") or {}).get("full_name") != repo:
        return result("UNKNOWN_KEEP", "target needs an exact same-repository head")
    if context["kind"] == "retired":
        if run.get("path") != context["path"] or not context["retired"]:
            return result("KEEP_WORKFLOW_PRESENT", "selected workflow is not proven absent on default branch")
        if "closed_pr_context" in context:
            closed_context = context["closed_pr_context"]
            if closed_context is None:
                return result("UNKNOWN_KEEP", "commit associations do not identify one exact pull request")
            closed_state = _classify_target(run, closed_context, repo)
            if not closed_state.get("cancel_candidate"):
                return closed_state
        return result("RETIRED_WORKFLOW_CANDIDATE", "exact workflow file is absent on current default branch", True)

    pr = context["pr"]
    if pr.get("state") != "closed":
        return result("KEEP_PR_NOT_CLOSED", "named pull request is not closed")
    referenced = {item.get("number") for item in run.get("pull_requests") or [] if isinstance(item, dict)}
    if (sha in context["open_heads"] or referenced.intersection(context["open_numbers"])
            or (repo, run.get("head_branch")) in context["open_branches"]):
        return result("LIVE_PR_HEAD_KEEP", "run is still associated with an open pull request")
    head = pr.get("head") or {}
    events = {"pull_request", "pull_request_target"} if context.get("allow_pull_request_target") else {"pull_request"}
    if (run.get("event") not in events or head.get("sha") != sha
            or head.get("ref") != run.get("head_branch")
            or (head.get("repo") or {}).get("full_name") != repo):
        return result("UNKNOWN_KEEP", "run does not match the named closed PR's exact repository, branch and head")
    return result("CLOSED_SELECTED_PR_CANDIDATE", "selected check matches the exact head of the closed PR", True)


class CancelGitHub(GitHub):
    """GitHub reader plus the single mutation this command is allowed to make."""

    def cancel_run(self, run_id: int) -> int:
        if type(run_id) is not int or run_id <= 0:
            raise ValueError("run_id must be a positive integer")
        path = f"/repos/{self.repo}/actions/runs/{run_id}/cancel"
        request = urllib.request.Request(
            "https://api.github.com" + path,
            data=b"",
            method="POST",
        )
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("User-Agent", "commons-actions-queue-cancel")
        if self.token:
            request.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                # GitHub documents 202 Accepted for a successful cancellation.
                response.read()
                return int(response.status)
        except urllib.error.HTTPError as exc:
            raise _http_error("POST", path, exc) from exc
        except urllib.error.URLError as exc:
            raise GitHubError(f"POST {path} -> {exc}") from exc


def _fresh_snapshot(github: GitHub, repo: str):
    branches = github.paged(f"/repos/{repo}/branches")
    open_prs = github.paged(f"/repos/{repo}/pulls?state=open")
    return make_snapshot(branches, open_prs)


def _run_id(run: dict[str, Any]) -> int | None:
    value = run.get("id")
    return value if type(value) is int and value > 0 else None


def _head_sha(run: dict[str, Any]) -> str | None:
    value = run.get("head_sha")
    if not isinstance(value, str) or len(value) != 40:
        return None
    if not all(ch in "0123456789abcdefABCDEF" for ch in value):
        return None
    return value.lower()


def _parse_created_at(run: dict[str, Any]) -> dt.datetime | None:
    value = run.get("created_at")
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _candidate_age_seconds(run: dict[str, Any], now: dt.datetime) -> float | None:
    created = _parse_created_at(run)
    if created is None:
        return None
    return (now - created).total_seconds()


def _sorted_candidates(
    runs: list[dict[str, Any]], repo: str, snapshot,
    classifier: Callable[[dict[str, Any], Any, str], dict[str, Any]] = classify_run,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for run in runs:
        classification = classifier(run, snapshot, repo)
        if classification.get("cancel_candidate") is True:
            rows.append((run, classification))

    def key(item: tuple[dict[str, Any], dict[str, Any]]):
        run, _ = item
        created = _parse_created_at(run)
        stamp = created.timestamp() if created is not None else float("inf")
        return (stamp, _run_id(run) or 2**63)

    rows.sort(key=key)
    return rows


def drain_stale_runs(
    github: GitHub,
    repo: str,
    *,
    cap: int = 1000,
    max_cancels: int = 25,
    min_age_seconds: int = 60,
    execute: bool = False,
    now: dt.datetime | None = None,
    run_ids: Sequence[int] = (),
    workflows: Sequence[str] = (),
    closed_pr: int | None = None,
    retired_workflow: str | None = None,
    require_closed_pr: bool = False,
) -> dict[str, Any]:
    """Return a deterministic cancellation receipt; mutate only when execute=True."""
    if cap <= 0:
        raise ValueError("cap must be positive")
    if max_cancels <= 0:
        raise ValueError("max_cancels must be positive")
    if min_age_seconds < 0:
        raise ValueError("min_age_seconds must be non-negative")
    if any(type(value) is not int or value <= 0 for value in run_ids):
        raise ValueError("run IDs must be positive integers")
    selected_ids = set(run_ids)
    selected_workflows = {_workflow_path(value) for value in workflows}
    if len(selected_ids) > cap:
        raise ValueError("explicit run IDs exceed --cap")
    if closed_pr is not None and (type(closed_pr) is not int or closed_pr <= 0):
        raise ValueError("closed PR must be a positive integer")
    if closed_pr is not None and retired_workflow is not None:
        raise ValueError("choose a closed PR or retired workflow, not both")
    if retired_workflow is not None:
        retired_workflow = _workflow_path(retired_workflow)
        if selected_workflows and selected_workflows != {retired_workflow}:
            raise ValueError("workflow filters must match the retired workflow")
        selected_workflows = {retired_workflow}
    if closed_pr is not None and not (selected_ids or selected_workflows):
        raise ValueError("--closed-pr requires --run-id or --workflow to select the checks")
    if require_closed_pr and retired_workflow is None:
        raise ValueError("--require-closed-pr requires --retired-workflow")
    target_mode = closed_pr is not None or retired_workflow is not None
    selection_active = bool(selected_ids or selected_workflows or target_mode)
    candidate_classes = TARGET_CANDIDATE_CLASSES if target_mode else CANDIDATE_CLASSES
    classifier = _classify_target if target_mode else classify_run

    def refresh(run=None):
        if target_mode:
            return _target_context(
                github, repo, closed_pr=closed_pr, retired_workflow=retired_workflow,
                require_closed_pr=require_closed_pr, run=run,
            )
        return _fresh_snapshot(github, repo)
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(dt.timezone.utc)

    if selected_ids:
        runs = []
        for run_id in sorted(selected_ids):
            row = github.get(f"/repos/{repo}/actions/runs/{run_id}")
            if not isinstance(row, dict) or _run_id(row) != run_id:
                raise GitHubError("selected run response has a different or invalid run ID")
            runs.append(row)
        total = None
    else:
        runs, total = github.queued_runs(cap)
    selected = [row for row in runs if _matches_selection(row, selected_ids, selected_workflows)]
    # Empty queues need no branch/PR inventory, which can itself span thousands
    # of pages on a busy repository.
    initial_context = refresh() if selected else None
    candidates = _sorted_candidates(selected, repo, initial_context, classifier) if selected else []
    initial_states = [classifier(row, initial_context, repo) for row in selected] if selection_active else []

    results: list[dict[str, Any]] = []
    posts_attempted = 0
    candidates_rechecked = 0
    accepted = 0
    holds = 0
    rate_limit = None

    for original, initial_class in candidates:
        run_id = _run_id(original)
        initial_sha = _head_sha(original)
        base = {
            "run_id": run_id,
            "head_sha": initial_sha,
            "initial_classification": initial_class.get("classification"),
        }
        if run_id is None or initial_sha is None:
            holds += 1
            results.append({**base, "outcome": "HOLD_INVALID_INITIAL_RUN"})
            continue

        age = _candidate_age_seconds(original, now)
        if age is None:
            holds += 1
            results.append({**base, "outcome": "HOLD_INVALID_CREATED_AT"})
            continue
        if age < min_age_seconds:
            results.append(
                {
                    **base,
                    "age_seconds": round(age, 3),
                    "outcome": "KEEP_TOO_NEW",
                }
            )
            continue

        if posts_attempted >= max_cancels or ((not execute or require_closed_pr) and candidates_rechecked >= max_cancels):
            results.append({**base, "outcome": "KEEP_BATCH_LIMIT"})
            continue

        try:
            # Dry-run makes no POSTs. Count its expensive rechecks separately
            # so its batch bound still limits repeated full inventory reads.
            candidates_rechecked += 1
            live = github.get(f"/repos/{repo}/actions/runs/{run_id}")
            if not isinstance(live, dict):
                raise GitHubError("run re-read returned non-object")
            if live.get("status") != "queued":
                results.append(
                    {
                        **base,
                        "live_status": live.get("status"),
                        "outcome": "KEEP_NOT_QUEUED",
                    }
                )
                continue
            if _head_sha(live) != initial_sha:
                holds += 1
                results.append({**base, "outcome": "HOLD_HEAD_MOVED"})
                continue

            if not _matches_selection(live, selected_ids, selected_workflows):
                results.append({**base, "outcome": "KEEP_OUTSIDE_SELECTION"})
                continue
            live_snapshot = refresh(live)
            live_class = classifier(live, live_snapshot, repo)
            live_label = live_class.get("classification")
            if not (
                live_class.get("cancel_candidate") is True
                and live_label in candidate_classes
            ):
                results.append(
                    {
                        **base,
                        "live_classification": live_label,
                        "outcome": "KEEP_RECLASSIFIED",
                    }
                )
                continue

            # Refresh complete PR/branch authority one more time immediately
            # before the final run read. This narrows a reopened-PR / moved-ref
            # race without making the inventory the final read and thereby
            # widening the window in which a queued run could start executing.
            final_snapshot = refresh(live)
            final_class = classifier(live, final_snapshot, repo)
            final_label = final_class.get("classification")
            if not (
                final_class.get("cancel_candidate") is True
                and final_label in candidate_classes
            ):
                results.append(
                    {
                        **base,
                        "live_classification": live_label,
                        "final_classification": final_label,
                        "outcome": "KEEP_RECLASSIFIED_FINAL",
                    }
                )
                continue

            # Final exact-run re-read immediately before any mutation. A run
            # that started, completed, or otherwise changed while inventories
            # were being refreshed is preserved.
            final_run = github.get(f"/repos/{repo}/actions/runs/{run_id}")
            if not isinstance(final_run, dict):
                raise GitHubError("final run re-read returned non-object")
            if final_run.get("status") != "queued":
                results.append(
                    {
                        **base,
                        "live_classification": live_label,
                        "final_classification": final_label,
                        "final_status": final_run.get("status"),
                        "outcome": "KEEP_NOT_QUEUED_FINAL",
                    }
                )
                continue
            if _head_sha(final_run) != initial_sha:
                holds += 1
                results.append(
                    {
                        **base,
                        "live_classification": live_label,
                        "final_classification": final_label,
                        "outcome": "HOLD_HEAD_MOVED_FINAL",
                    }
                )
                continue

            if not _matches_selection(final_run, selected_ids, selected_workflows):
                results.append({**base, "outcome": "KEEP_OUTSIDE_SELECTION_FINAL"})
                continue
            if target_mode and not classifier(final_run, final_snapshot, repo).get("cancel_candidate"):
                results.append({**base, "outcome": "KEEP_RECLASSIFIED_FINAL_RUN"})
                continue

            if not execute:
                results.append(
                    {
                        **base,
                        "live_classification": live_label,
                        "final_classification": final_label,
                        "outcome": "WOULD_CANCEL",
                    }
                )
                continue

            posts_attempted += 1
            cancel = getattr(github, "cancel_run", None)
            if not callable(cancel):
                raise GitHubError("GitHub client has no cancel_run mutation")
            status = cancel(run_id)
            if status != 202:
                raise GitHubError(f"cancel returned unexpected HTTP {status}")
            accepted += 1
            results.append(
                {
                    **base,
                    "live_classification": live_label,
                    "final_classification": final_label,
                    "cancel_http_status": status,
                    "outcome": "CANCEL_ACCEPTED",
                }
            )
        except (GitHubError, OSError, ValueError) as exc:
            holds += 1
            results.append(
                {
                    **base,
                    "outcome": "ERROR_HOLD",
                    "error": str(exc)[:300],
                }
            )
            if isinstance(exc, GitHubError) and exc.rate_limited:
                rate_limit = {"http_status": exc.status, "retry_after": exc.retry_after}
                break

    receipt = {
        "schema": SCHEMA,
        "observed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": repo,
        "mode": "execute" if execute else "dry_run",
        "queued_total_reported": total,
        "queued_runs_observed": sum(row.get("status") == "queued" for row in runs) if selected_ids else len(runs),
        "queued_inventory_complete": isinstance(total, int) and total <= len(runs),
        "initial_cancel_candidates": len(candidates),
        "candidates_rechecked": candidates_rechecked,
        "candidates_unprocessed": len(candidates) - len(results),
        "max_cancels": max_cancels,
        "min_age_seconds": min_age_seconds,
        "cancel_posts_attempted": posts_attempted,
        "cancel_accepted": accepted,
        "holds": holds,
        "safety": {
            "mutates_github": execute,
            "dry_run_default": True,
            "requires_live_reclassification": True,
            "requires_final_inventory_reread": True,
            "requires_final_run_reread": True,
            "candidate_classes": sorted(candidate_classes),
        },
        "results": results,
    }
    if selection_active:
        receipt["selection"] = {
            "run_ids": sorted(selected_ids),
            "workflows": sorted(selected_workflows),
            "closed_pr": closed_pr,
            "retired_workflow": retired_workflow,
            "require_closed_pr": require_closed_pr,
            "inventory_scope": "explicit_run_ids" if selected_ids else "bounded_queued_runs",
            "observed_runs": len(runs),
            "observed_runs_in_scope": len(selected),
            "outside_selection_run_ids": [_run_id(row) for row in runs
                                          if not _matches_selection(row, selected_ids, selected_workflows)],
            "initial_states": initial_states,
        }
        if target_mode:
            receipt["safety"]["requires_final_inventory_reread"] = closed_pr is not None or require_closed_pr
            receipt["safety"]["requires_final_target_reread"] = True
    if rate_limit is not None:
        receipt.update(stop_reason="RATE_LIMITED", rate_limit=rate_limit)
    return receipt


def _write_receipt(receipt: dict[str, Any], out: Path | None) -> None:
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if out is None:
        sys.stdout.write(text)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        body = text.encode("utf-8")
        view = memoryview(body)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--cap", type=int, default=1000)
    parser.add_argument("--max-cancels", type=int, default=25,
                        help="maximum cancellation POSTs, or dry-run candidate rechecks (default: 25)")
    parser.add_argument("--min-age-seconds", type=int, default=60)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--out", type=Path, help="create-exclusive JSON receipt path")
    parser.add_argument("--run-id", type=int, action="append", default=[],
                        help="inspect only this exact run ID (repeatable)")
    parser.add_argument("--workflow", action="append", default=[],
                        help="select an exact .github/workflows/*.yml path (repeatable)")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--closed-pr", type=int,
                        help="require this PR to be closed; also name --run-id or --workflow")
    target.add_argument("--retired-workflow",
                        help="select one workflow path and require its file to be absent on current default branch")
    parser.add_argument("--require-closed-pr", action="store_true",
                        help="also require one exact closed PR for the retired workflow; preserve ambiguous associations")
    args = parser.parse_args(argv)

    if args.cap <= 0:
        parser.error("--cap must be positive")
    if args.max_cancels <= 0:
        parser.error("--max-cancels must be positive")
    if args.min_age_seconds < 0:
        parser.error("--min-age-seconds must be non-negative")

    token = _discover_token()
    if args.execute and not token:
        parser.error("--execute requires an available GitHub token")

    github = CancelGitHub(args.repo, token)
    try:
        receipt = drain_stale_runs(
            github,
            args.repo,
            cap=args.cap,
            max_cancels=args.max_cancels,
            min_age_seconds=args.min_age_seconds,
            execute=args.execute,
            run_ids=args.run_id,
            workflows=args.workflow,
            closed_pr=args.closed_pr,
            retired_workflow=args.retired_workflow,
            require_closed_pr=args.require_closed_pr,
        )
        _write_receipt(receipt, args.out)
    except (GitHubError, OSError, ValueError) as exc:
        parser.exit(2, f"actions_queue_cancel: {exc}\n")

    return 2 if receipt["holds"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
