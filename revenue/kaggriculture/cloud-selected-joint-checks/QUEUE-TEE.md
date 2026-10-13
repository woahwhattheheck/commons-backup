# Queue-copy persisted-output consistency

The selected-joint supplemental reader already validates the queue-copy JSON report, its embedded unittest transcript, source hashes, comparison counts, and the outer unittest footer. The current producer also prints a second persisted representation: the same unittest transcript followed by a one-line JSON summary. Before this change, those two stored outputs could disagree while the reader still returned `COMPLETE_PASS`.

## Change

For queue-copy reports carrying the producer's `python` identity, the helper now:

1. parses the final outer-log line with duplicate-key and non-finite-value rejection;
2. compares that object, type-sensitively, with the report excluding only `log` and optional `benchmark`;
3. compares the preceding outer unittest text with the report's embedded log; and
4. exposes `emitted_summary_bound=true` in the suite receipt after a successful comparison.

Older synthetic or legacy reports without the producer metadata field keep their established behavior. This preserves the existing helper's compatibility contract while binding the actual current producer output.

## Executed validation

- The exact current helper (`03e94ab3`) passes the existing 44 retained-artifact reader checks but fails 13 of 18 tee-consistency discriminators.
- The composed helper (`518b33c8`) passes all 44 retained-artifact checks, all 18 actual-artifact tee discriminators, and 12 standalone contract methods.
- The unchanged provider artifacts remain accepted at 95, 245, and 282 methods. The 282 artifact is SHA-256 `fe33a36cebf521ee4188609fc68a1739c68bbbb26e99f9ef87e3b7abbe91000b`.

The tests mutate detached evidence copies and recalculate only their enclosing fixture digests. No archived tests, engines, policies, games, workflows, or canonical release files are executed or changed.

## Commands

From `revenue/kaggriculture/cloud-selected-joint-checks/`:

```bash
python -B test_queue_tee_consistency.py
```

The retained-provider execution used the independent archive consumer preserved in the source-bound validation record. `QUEUE-TEE-VALIDATION.json` distinguishes the accepted reader fixture, exact current helper, candidate helper, artifacts, and before/after method counts.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
