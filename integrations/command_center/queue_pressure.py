"""Read-only GitHub Actions queue-pressure advisory for command-center work state.

This reducer consumes normalized work-source observations. It performs no provider
I/O and never treats queue health as evidence that an individual CI run passed.
"""
from __future__ import annotations

from datetime import datetime, timezone

SCHEMA = "commons-actions-queue-pressure/v1"
PRESSURED_QUEUED = 50
SATURATED_QUEUED = 200
PRESSURED_AGE_SECONDS = 15 * 60
SATURATED_AGE_SECONDS = 60 * 60
ACTIVE_STATUSES = {"queued", "in_progress"}


def _stamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _unknown(reason, *, repositories=None):
    return {
        "schema": SCHEMA,
        "state": "UNKNOWN",
        "warning": True,
        "reason": reason,
        "repositories": sorted(repositories or []),
        "queued": None,
        "in_progress": None,
        "active": None,
        "oldest_active_age_seconds": None,
        "thresholds": {
            "pressured_queued": PRESSURED_QUEUED,
            "saturated_queued": SATURATED_QUEUED,
            "pressured_age_seconds": PRESSURED_AGE_SECONDS,
            "saturated_age_seconds": SATURATED_AGE_SECONDS,
        },
        "ci_green_claim_allowed": False,
        "ci_green_note": (
            "Queue observations never establish an individual check conclusion; "
            "unknown/partial observations must not be represented as CI green."
        ),
        "read_only": True,
    }


def _active_coverage_complete(source):
    """Queue counts bind dedicated queued/in_progress coverage, not history caps."""
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    active = metadata.get("active_queue_coverage")
    if not isinstance(active, dict) or active.get("complete") is not True:
        return False
    queried = active.get("queried_statuses")
    return isinstance(queried, list) and set(queried) == ACTIVE_STATUSES


def queue_pressure(state, *, now=None):
    """Reduce complete GitHub Actions work sources into a bounded queue advisory.

    Product behavior is fail-open: malformed or incomplete queue observations
    produce UNKNOWN instead of raising. CI-green claims fail closed: this advisory
    never authorizes them, even when the provider queue is otherwise healthy.
    Active-queue authority is the dedicated queued/in_progress coverage generation.
    A capped recent-history slice may leave broad source coverage incomplete
    without invalidating fully observed active counts.
    """
    if not isinstance(state, dict):
        return _unknown("work_state_not_object")
    sources = state.get("sources")
    items = state.get("items")
    if not isinstance(sources, list) or not isinstance(items, list):
        return _unknown("work_state_shape")

    action_sources = [source for source in sources if isinstance(source, dict)
                      and str(source.get("id", "")).startswith("github:actions:")]
    if not action_sources:
        return _unknown("no_actions_sources")

    repositories = set()
    source_ids = set()
    for source in action_sources:
        source_id = source.get("id")
        scope = source.get("scope")
        repo = scope.get("repository") if isinstance(scope, dict) else None
        if isinstance(repo, str) and repo:
            repositories.add(repo)
        if not isinstance(source_id, str) or not source_id:
            return _unknown("invalid_actions_source", repositories=repositories)
        source_ids.add(source_id)
        if source.get("future_observation") is True or source.get("future_data") is True:
            return _unknown("actions_source_timestamp_unusable", repositories=repositories)
        if (source.get("error") or source.get("retained_last_good")
                or source.get("stale") is True or source.get("data_stale") is True):
            return _unknown("actions_coverage_incomplete", repositories=repositories)
        if not _active_coverage_complete(source):
            return _unknown("active_queue_coverage_incomplete", repositories=repositories)

    observed = now if isinstance(now, datetime) else datetime.now(timezone.utc)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    observed = observed.astimezone(timezone.utc)

    queued = in_progress = 0
    oldest_age = None
    malformed = False
    for item in items:
        if not isinstance(item, dict) or item.get("source_id") not in source_ids:
            continue
        refs = item.get("refs")
        status = refs.get("provider_status") if isinstance(refs, dict) else item.get("status")
        if status not in ("queued", "in_progress"):
            continue
        queued += status == "queued"
        in_progress += status == "in_progress"
        stamp = _stamp(item.get("created_at"))
        if stamp is None or stamp > observed:
            malformed = True
            continue
        age = max(0, int((observed - stamp).total_seconds()))
        oldest_age = age if oldest_age is None else max(oldest_age, age)

    if malformed:
        return _unknown("active_run_timestamp_unusable", repositories=repositories)

    active = queued + in_progress
    if queued >= SATURATED_QUEUED or (oldest_age is not None and oldest_age >= SATURATED_AGE_SECONDS):
        pressure = "SATURATED"
    elif queued >= PRESSURED_QUEUED or (oldest_age is not None and oldest_age >= PRESSURED_AGE_SECONDS):
        pressure = "PRESSURED"
    else:
        pressure = "NORMAL"

    return {
        "schema": SCHEMA,
        "state": pressure,
        "warning": pressure != "NORMAL",
        "reason": "threshold_crossed" if pressure != "NORMAL" else "within_thresholds",
        "repositories": sorted(repositories),
        "queued": queued,
        "in_progress": in_progress,
        "active": active,
        "oldest_active_age_seconds": oldest_age,
        "thresholds": {
            "pressured_queued": PRESSURED_QUEUED,
            "saturated_queued": SATURATED_QUEUED,
            "pressured_age_seconds": PRESSURED_AGE_SECONDS,
            "saturated_age_seconds": SATURATED_AGE_SECONDS,
        },
        "ci_green_claim_allowed": False,
        "ci_green_note": (
            "Queue health is diagnostic only; verify the exact run/check conclusion "
            "before describing CI as green."
        ),
        "read_only": True,
    }
