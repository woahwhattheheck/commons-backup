# Work-feed poll planner

Offline compiler for bounded work-feed discovery.

It consumes retained surface snapshots, successful-read times, throttle timing, freshness limits, backlog estimates, and a request budget. It emits deterministic POLL_NOW, POLL_LATER, SKIP_REDUNDANT, or HOLD_THROTTLED decisions plus an overall coverage state and SHA-256 receipt.

It performs no provider reads. Run:

python -m tools.workfeed_poll_planner.demo

python -m tools.workfeed_poll_planner.core compile input.json plan.json

python -m tools.workfeed_poll_planner.core verify input.json plan.json

See Commons issue 15906 for the full contract and collision fence.
