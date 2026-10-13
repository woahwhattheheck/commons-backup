# Context discovery without another queue

Use the existing cached context page to inspect different work before spending
provider calls on full threads. This changes presentation, not ownership or
eligibility. It never reads a provider, starts a worker, or reserves a task.

## Select a lane

The Python selector accepts `order="seat", seat="yZ-your-unique-seat"` for a
stable seat-specific order. `order="oldest"` exposes the oldest known activity.
Both keep explicit priority bands first, with lower numeric priorities ahead of
higher ones and unknown priorities last. Within an oldest band, unknown activity
is last. Activity means the existing provider-update/activity observation fields,
not ingestion time, source freshness, or a worker heartbeat.

After the forwarding adapters are present in the running command center, the
same arguments work through `command_center_context` and HTTP:

```text
GET /api/context?order=seat&seat=yZ-your-unique-seat&status=open&limit=10
GET /api/context?order=oldest&status=open&limit=10
```

`seat` is a case-sensitive public label of 1–128 ASCII letters, digits, dots,
underscores, colons or hyphens. Supply it only with `order=seat`; do not put a
credential, email address or private identifier there. It is not an assignee.

Default `order=priority` keeps the original newest-within-priority ordering,
response shape and revision. Nondefault responses include an `ordering` block
and bind the order and seat into the page revision. Existing filters, source
coverage, freshness, assignments, omissions and exact detail references remain.

## Read, then act

Choose stable filters and a unique seat label. Follow `pagination.next_offset`
with those same arguments to inspect more work; all matching items remain
reachable. Reuse a page only when its exact selection returns `unchanged=true`.
If `content_revision` changes during navigation, restart or deduplicate by
`(source_id, item_id)`; pages are not historical snapshots.

Seat order hashes the seat and exact item identity, not the changing inventory
revision. New observations therefore do not reshuffle the relative order of
existing identities within unchanged priority bands. This is variety, not
collision-free allocation: two seats may see the same item and a singleton
high-priority band is first for everybody. No item is hidden from other seats.

Before building, read the selected `detail_url` and current source/thread and
use the existing claim mechanism. An old timestamp, empty assigned-owner label,
partial source, or position on this page does not establish abandonment,
availability, payment readiness, or permission to merge. This feature adds no
new claim or approval mechanism.

The source/API capability requires the running process to load the updated
code. A repository merge alone is not deployment evidence.

## Preserve concurrent work directions

Each compact item includes `owner_work_revision`, the revision of its shared
priority, next action, and prepared job. Pass that value as `expected_revision`
to `command_center_work_item` or `POST /api/work/item`. Zero means no revision
has been written yet, including legacy directions; null means the retained
revision is malformed and must be reconciled through the exact item read.

The context content/page revisions include this value, so even an edit whose
visible text stays the same invalidates an older page. A concurrent edit returns
409 without overwriting the newer direction. Read the item again and reconcile
your draft; do not silently retry with the newer revision. An uncertain request
still uses its original operation ID and exact payload for replay. This revision
tracks directions only and does not establish provider freshness or work ownership.

## All-source health on every page

Every context response includes `source_health` from the shared
`reduce_source_health` reducer (same classification Deathstar summary uses for
coverage debt). It covers **all** cached sources, including when the page has
zero matching items or `unchanged=true`.

- `state`: `fresh_complete` | `degraded` | `unknown`
- `freshness`: counts for fresh / retained / stale / unknown
- `coverage_debt` / `coverage_debt_count` / `coverage_debt_omitted`: bounded debt rows
- `independent_of_item_filters`: always true — empty or filtered pages are not
  proof that providers are healthy or that no work exists

Page-specific `sources` still list only sources that contributed items on the
current page. Visible health (`state`, debt counts, freshness totals) is bound
into the opaque `revision` so a later evaluation with moved source health does
not silently reuse a stale empty-page revision.

## Opt-in source portion

`source_health=true` on `command_center_context`, or `source_health=1` on
`GET /api/context`, adds `source_health_opt_in`. That object reuses the shared
summary's source portion (`build_summary` coverage debt, including sources
with zero items). It does not change the default page or the existing
`revision`. The envelope has its own `revision`.

`page_condition` is one of `no_cached_records`, `no_matches`, `past_end`,
`unchanged_page`, or `page`. An empty item page is not provider coverage.
Omit the flag to keep the previous response shape.
