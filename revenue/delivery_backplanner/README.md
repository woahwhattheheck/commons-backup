# Delivery Backplanner

`delivery_backplanner` is a standard-library-only, pre-sale scheduling tool for testing whether a proposed delivery calendar is actually feasible **before** a team promises it to a buyer.

It models explicit business calendars/holidays, release and latest-finish windows, dependency lags, non-preemptive tasks, renewable shared-resource capacity, retained commitments, and a finite planning horizon. The deterministic bounded exhaustive solver returns exactly one of:

- `PLAN_FOUND` — a schedule that an independent validator re-checks;
- `NO_FEASIBLE_PLAN` — the bounded search space was exhausted with no valid schedule;
- `SEARCH_LIMIT` — the configured node budget was reached, so feasibility remains inconclusive.

It never turns technical fit into staffing or buyer authority. Inputs are owner-supplied planning assumptions. No buyer/vendor contact, staffing commitment, calendar booking, contract acceptance, provider mutation, spend, invoice/payment, or revenue authority is created.

## Input contract

See `example.json`. Weekdays use Python/ISO convention `0=Monday ... 6=Sunday`. A task consumes its resource demand on each of its consecutive eligible workdays. A dependency with `lag_workdays: 0` means the dependent may start on the next eligible workday in its own calendar; lag `N` leaves `N` additional eligible workdays between predecessor completion and dependent start.

The parser rejects duplicate JSON keys, non-finite numbers, unknown fields, unknown resources/calendars, duplicate IDs, orphan/self/cyclic dependencies, over-capacity demands/commitments, and horizons beyond 366 calendar days. Current v1 bounds are 24 tasks, 16 resources, 8 calendars, 256 retained commitments, and 2,000,000 search nodes.

## CLI

From repository root:

```bash
python -m revenue.delivery_backplanner solve revenue/delivery_backplanner/example.json /tmp/backplan
python -m revenue.delivery_backplanner verify revenue/delivery_backplanner/example.json /tmp/backplan/result.json
```

`solve` creates `result.json`, `timeline.md`, and `resource_load.csv` using create-exclusive writes and refuses to overwrite existing output files. If a later sibling write fails, rollback unlinks only the exact owned generation recorded at create time (device + inode); a renamed-aside file replaced by foreign bytes at the same pathname is left intact. Retry after a failed `solve` by choosing a new empty output directory or removing only files this process still owns. `verify` revalidates the schedule and recomputes the deterministic semantic result.

## Why this exists

Technical fit and calendar feasibility are separate questions. A proposal can be technically sound and still be a bad pursuit when paperwork lead time, holidays, dependency sequencing, retained commitments, or a shared reviewer/engineer bottleneck make the promised delivery window impossible. This tool makes that distinction explicit before a commercial commitment is made.
