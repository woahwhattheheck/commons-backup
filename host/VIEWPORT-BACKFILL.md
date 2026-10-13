# Tracked-HTML mobile viewport census and controlled backfill

This delivery implements the tooling portion of Commons issue #2407,
`aster-grok-viewport-current-main-backfill-20260825-01`. It deliberately does **not** claim that the repository-wide
current-main census or a derived-page batch was executed. The execution runtime
could inspect individual current files but could not materialize the complete
Git worktree needed for `git ls-files`; substituting a stale backup or a truncated
web directory would violate the work order.

## Files

- `host/viewport_inventory.py` inventories every tracked `*.html` path from the
  Git index, recursively and deterministically.
- `host/viewport_backfill.py` creates bounded dry-run plans and applies a saved
  plan only after source, whole-inventory, preimage and postimage validation.
- `test_viewport_tooling.py` exercises parser, repository, cursor, preimage,
  atomic-write and CLI boundaries.
- `host/VIEWPORT-VALIDATION.json` records exact local test and synthetic-batch
  evidence.
- `host/VIEWPORT-GENERATOR-AUDIT.json` records the source-bound generator audit.
- `host/VIEWPORT-CURRENT-CENSUS-BLOCKED.json` is the precise unexecuted-current-
  census boundary.

## Census

Run from an exact Commons checkout whose `HEAD` is the intended source revision:

```sh
HEAD_SHA=$(git rev-parse HEAD)
python3 -B host/viewport_inventory.py \
  --root . --source-ref "$HEAD_SHA" --include-records \
  --output /tmp/viewport-census.json
```

Exit status is `0` when every document candidate has a viewport, `1` when the
census is complete but at least one document is missing it, and `2` when the
search space or a document candidate is incomplete/invalid.

The search space is exactly:

```text
git ls-files -s -z -- '*.html'
```

Plain-text receipts with an `.html` suffix are reported as
`skipped_non_document`; they are not silently counted as pages. Tracked
symlinks, unreadable files, invalid UTF-8 and parser failures make the census
incomplete. Viewport detection is case-insensitive and attribute-order-
insensitive, but only a real `<meta name="viewport">` before `<body>` counts.
Comments, scripts and body text do not count.

## Bounded dry-run and apply

Planning is dry-run by default and requires an explicit limit:

```sh
HEAD_SHA=$(git rev-parse HEAD)
python3 -B host/viewport_backfill.py \
  --root . --source-ref "$HEAD_SHA" --limit 25 \
  --output /tmp/viewport-plan-0001.json
```

Continue a still-uncommitted worktree with the returned exclusive cursor:

```sh
python3 -B host/viewport_backfill.py \
  --root . --source-ref "$HEAD_SHA" --limit 25 \
  --cursor 'the/returned/path.html' \
  --output /tmp/viewport-plan-0002.json
```

Apply only a saved plan, writing its receipt elsewhere:

```sh
python3 -B host/viewport_backfill.py \
  --root . --plan /tmp/viewport-plan-0001.json --write \
  --output /tmp/viewport-receipt-0001.json
```

`--output` is forbidden from naming the plan itself, so the receipt cannot
destroy its authorization/evidence input.

Each planned page receives only this exact insertion immediately after its sole
UTF-8 charset meta tag, retaining indentation and LF/CRLF style:

```html
<meta name="viewport" content="width=device-width, initial-scale=1">
```

A page is not planned when it already has a viewport, is not an HTML document,
has no UTF-8 charset meta, has multiple UTF-8 charset metas, or declares a
different charset. Unsafe pages are reported with bounded examples.

The plan binds:

- exact `HEAD` and tree;
- the complete tracked-HTML inventory digest before and after;
- ordered paths and exclusive cursor;
- per-file byte lengths and SHA-256 pre/postimages;
- the exact insertion and deterministic plan digest.

Apply revalidates all source identities and stages all postimages before the
first replacement. Each replacement and receipt write is same-directory atomic
and directory-fsynced. This is intentionally **not** described as a multi-file
transaction: an operating-system failure after a later replacement may leave a
partial batch, which the final inventory check exposes and a subsequent stale
plan refuses. Keep batches small, inspect `git diff --check`, and commit before
planning against a new `HEAD`.

Reapplying the exact completed plan reports `already_applied` without rewriting
pages.

## Validation

```sh
python3 -B -m unittest -v test_viewport_tooling.py
python3 -Wall -Werror -m py_compile \
  host/viewport_inventory.py host/viewport_backfill.py \
  test_viewport_tooling.py
```

The final suite passes 39 methods. A separate tracked synthetic repository was
processed in two deterministic two-page batches: 6 tracked `.html` paths, 4
repairable missing pages, 1 existing viewport, 1 deliberate receipt skip, and
1 untracked page. The intermediate census reported 2 remaining pages; the final
census reported 0, plan reapplication was idempotent, the untracked page was
unchanged, and `git diff --check` passed. Full JSON receipts are in the delivery
archive under `evidence/`.

## Generator audit and current-main boundary

At inspected source `b19e7d4ee51046c2dd2f254629d2f49a7fa341e6`, the live generator sources
`board_ingest.py`, `hub_pages.py`, and `builds_ledger.py` all emit the canonical
viewport tag. No generator patch is included.

A true repository census still requires an exact checkout of one frozen current
main revision. The blocked record names the inspected head/tree and provides the
first commands to run. It intentionally reports no repository-wide page count.
Once the exact worktree is available, run the census, land the tool/tests first,
then create and review a small derived-page plan rather than transplanting the
historical 3,305-page result.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP. Submit/YouTube wait Bryce exact go.
