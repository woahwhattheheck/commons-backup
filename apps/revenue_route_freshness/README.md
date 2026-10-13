# Revenue Route Freshness Proof Gate

`apps/revenue_route_freshness` is a **non-sending** revenue control. It compiles immutable route/provider/coordination receipts into one bounded decision before a seller asks Muse for an external-write lease.

It exists because a technically good buyer/offer match is still a bad outbound candidate when the route is stale, already bounced, the company was already touched, a hard DNR exists, or another single-writer lease is live.

## Decisions

The gate emits exactly one of:

- `READY_FOR_MUSE_CENSUS` — fresh first-party route and no evidence-backed blocker. **Not send permission.** A new exact Muse/collision census is the next step.
- `HOLD_STALE_ROUTE` — route source is non-first-party or older than the explicit evidence horizon.
- `HOLD_COMPANY_PRIOR_TOUCH` — the buyer has unresolved outbound history or a live Muse lease. A later genuine `HUMAN_REPLY` may release prior-touch history back to census; auto-acks never do.
- `HARD_DNR` — an active explicit DNR matches company, exact route, or buyer×offer×purpose.
- `DEAD_ROUTE` — the exact route has a permanent provider failure.

Every projection contains `"send_authorized": false`. This package has no network client and no send operation.

## Evidence contract

Input is `revenue-route-evidence/v1` JSON with a timezone-aware `as_of`; buyer/offer/purpose/seat keys; the proposed route and source observation; plus optional provider events, company-touch receipts, DNR receipts, and Muse leases.

Evidence is fail-closed:

- timestamps after `as_of`, naive timestamps, duplicate receipt IDs, malformed routes, invalid enums, and `bool` smuggled as an integer are rejected;
- freshness is calculated from timestamp evidence rather than trusting a caller's word `current`;
- permanent failure is scoped to the exact canonical route;
- company-level outbound history holds even when a different address is proposed;
- `AUTO_ACK` does not count as a human release;
- a live `CLEAR`/`SELECT` lease never becomes send authorization in this layer.

## CLI

```bash
PYTHONPATH=. python -m apps.revenue_route_freshness.gate \
  apps/revenue_route_freshness/fixtures/ready.json
```

Invalid evidence exits `2` and writes no projection to stdout.

## Validation

```bash
PYTHONPATH=. python -m unittest discover -s apps/revenue_route_freshness/tests -v
PYTHONPATH=. python -O -m unittest discover -s apps/revenue_route_freshness/tests -v
```

Both commands pass the same 27-case unit/hostile battery. A dedicated active workflow is intentionally **not** added: Commons currently uses the full 67/67 workflow-surface budget. This keeps the revenue gate from consuming a scarce shared CI slot while leaving exact reproducible proof in-tree; normal repository PR guards still apply. Identical evidence produces byte-stable semantic output.
