from __future__ import annotations

from .core import INPUT_SCHEMA, compile_plan, render_markdown


def sample_packet() -> dict:
    return {
        "schema": INPUT_SCHEMA,
        "evaluation_utc": "2026-09-17T23:20:00Z",
        "request_budget": 2,
        "evidence_ttl_seconds": 900,
        "backoff_base_seconds": 2,
        "backoff_cap_seconds": 120,
        "surfaces": [
            {
                "surface_id": "coordination",
                "surface_class": "coordination",
                "snapshot_generation": "coord-42",
                "snapshot_observed_utc": "2026-09-17T23:19:58Z",
                "last_success_utc": "2026-09-17T23:19:00Z",
                "last_throttle_utc": None,
                "retry_after_seconds": 0,
                "consecutive_throttles": 0,
                "min_poll_interval_seconds": 5,
                "max_staleness_seconds": 30,
                "unread_estimate": 3,
                "backlog_estimate": 1,
                "covered_by_generation": None,
            },
            {
                "surface_id": "hot-leads",
                "surface_class": "hot_lead",
                "snapshot_generation": "leads-18",
                "snapshot_observed_utc": "2026-09-17T23:19:58Z",
                "last_success_utc": "2026-09-17T23:18:00Z",
                "last_throttle_utc": "2026-09-17T23:19:57Z",
                "retry_after_seconds": 8,
                "consecutive_throttles": 3,
                "min_poll_interval_seconds": 10,
                "max_staleness_seconds": 60,
                "unread_estimate": 1,
                "backlog_estimate": 4,
                "covered_by_generation": None,
            },
            {
                "surface_id": "awaiting-merge",
                "surface_class": "merge_queue",
                "snapshot_generation": "merge-7",
                "snapshot_observed_utc": "2026-09-17T23:19:58Z",
                "last_success_utc": "2026-09-17T23:10:00Z",
                "last_throttle_utc": None,
                "retry_after_seconds": 0,
                "consecutive_throttles": 0,
                "min_poll_interval_seconds": 30,
                "max_staleness_seconds": 300,
                "unread_estimate": 2,
                "backlog_estimate": 8,
                "covered_by_generation": None,
            },
        ],
    }


def main() -> int:
    print(render_markdown(compile_plan(sample_packet())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
