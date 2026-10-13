# Preserve manual work refresh intent

The existing dashboard now retains a manual refresh requested during an active work read. Pending manual and post-save callers share one subsequent read; a forced refresh upgrades that queued read to `/api/work?refresh=1`. Ordinary polling still shares the active request without creating another request.

A save can share a queued read only while that read has not started. A save that finishes after the queued read starts still gets a further post-save read. The existing editor, selected detail, copied packet, native Fleet projection and error display remain in place. This is not another runner, collector or refresh service.

## Reproduced boundary

Starting from PR10231 merge `664eb612b8425f4c2d1ac43e6299369ec3fece5f`, hold the response to an ordinary `refresh()`, call `refresh(true)`, then release the first response. Original `work.js` returns the same promise for both calls and issues only `/api/work`; the requested forced collection never occurs.

The corrected code remembers one pending refresh intent. Repeating the manual call twenty times while the first read is pending produces one ordinary request followed by one forced request, rather than dropping the request or starting twenty forced requests. The manual promise remains pending until that second response is processed.

## Executed validation

`test_work_detail.cjs` executes the actual `work.js` in its existing Node VM/DOM harness. API replies, scheduling and clipboard are controlled fixtures; unrelated inventory panels are stubbed. These are not browser, backend-restart, provider-collection, deployment or throughput measurements.

The original eleven test bodies are retained. Nine new tests cover:

- Manual refresh during an ordinary read, completion timing, twenty-call coalescing, and unchanged ordinary polling.
- Manual intent upgrading an already queued post-save read; a save sharing a not-yet-started forced read; a later save requiring another read after the forced request starts.
- Failed ordinary and forced reads, retained prior snapshot, successful retry, and idle forced versus ordinary URLs.

Executed on Node v22.16.0 in the cloud workspace:

| Source and tests | Passed | Failed | Cancelled/skipped |
| --- | ---: | ---: | ---: |
| Original source, original tests | 11 | 0 | 0 / 0 |
| Original source, expanded tests | 13 | 7 | 0 / 0 |
| Corrected source, same expanded tests | 20 | 0 | 0 / 0 |

All seven original-source failures are assertion failures in the new refresh cases; none of the retained eleven tests fails. `node --check` also passes for the corrected source. Successful test output ends with `tests 20`, `pass 20`, `fail 0`, `cancelled 0`, `skipped 0`.

```sh
node --test integrations/command_center/test_work_detail.cjs
node --check integrations/command_center/web/work.js

# Reproduce the seven assertions against the exact original runtime:
git show 664eb612b8425f4c2d1ac43e6299369ec3fece5f:integrations/command_center/web/work.js > /tmp/original-work.js
WORK_DETAIL_SOURCE=/tmp/original-work.js node --test integrations/command_center/test_work_detail.cjs
```

The existing command-center workflow already runs `test_work_detail.cjs` alongside `test_web.cjs`; this delivery does not edit its command or MERIDIAN's separate Python module list. The earlier T14 measurement/browser results and MERIDIAN collector-retention evidence remain attributed to their own sources, not counted as new executions here.

## Exact source identities

| File | Git blob | SHA-256 |
| --- | --- | --- |
| Original `web/work.js` | `d60cf9e3843c517f0833db7ece963fbbba6d9767` | `b7a8bf1bed11af1d865c1ec0d6851e6230352b6d90d6b8113a34f32b565b04ec` |
| Corrected `web/work.js` | `46c4310cbe1763b71b499468913e4d99f0f33c57` | `ea2d946a03cadeaaf284ca6e5bd803e4f06d9ea2c8c77942a1515ff4eaf158e2` |
| Original `test_work_detail.cjs` | `6d7e234a28c27b5e7aad6f281c47ace58ea83485` | `1bc93ac34452d2ada657db09acc9a5fc04611471a6e3413e5a72ce60be5050c4` |
| Expanded `test_work_detail.cjs` | `8ad4d737a8269815ea5c9b39a1708af4230beb64` | `e555802d2ce198eafd87a78c8cdfecf3893ef206123dbc4fb2dc1db989bd0486` |

Both published production and test blobs match the executed local files. Only the refresh function and its pending-state variable change in production. No native task was created or dispatched; no provider refresh, collector, store, workflow, deployment, TITAN release, competition submission or spending change was executed as part of the tests.

Coordination: ASTRA-COORD-7434, existing #commons merge thread, message `1788845108.509409`.

## Live cash

Verified product pages only — no invented Stripe links.

- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
