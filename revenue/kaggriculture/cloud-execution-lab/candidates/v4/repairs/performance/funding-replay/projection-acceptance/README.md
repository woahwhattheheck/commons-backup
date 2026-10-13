# Funding projection-copy acceptance

Recovered from the previously local-only executed packet and published additively under the existing V4 `funding-replay` family. This is not a successor V4, policy-key change, production-default change, release archive, or Kaggle submission.

## Scope

The complementary funding-only proposal replaces the two `copy.deepcopy` calls at `_funding_trace` with `clone_projection_state`. The default composer scope is `funding`; it leaves `represented_shed_event` and `early_capital._project_post_unit_private` untouched because those seams belonged to LIVEPATH when this packet was built. The `all` recipe in `edits.json` is diagnostic evidence only and must not be used to overwrite that ownership.

`compose_projection_clone.py` is fail-closed and method-pinned. It authenticates `edits.json` and the helper by SHA-256, writes only into a separate scratch runtime, preserves unrelated source bytes, rejects source drift and destination aliasing, and is idempotent on already-composed methods.

## Executed evidence recovered

`VALIDATION.json` is the original local execution receipt; its `status` field records the state at measurement time, before this recovery publication.

Funding-only results on the authenticated B567 fixture:

- normal Python: 8 complete games, identical action/state/score streams, aggregate native-agent elapsed reduction 12.73%.
- optimized Python: 8 complete games, identical action/state/score streams, aggregate native-agent elapsed reduction 12.62%.
- across the full final packet: 32 uninstrumented complete games, 23,008 native callbacks and 23,040 official-interpreter calls, with zero native fallbacks.
- 37 new tests per Python mode, 1,200 generated alias/cycle graphs per mode, 99 inherited tests per arm per mode, and nine deliberately broken variants assertion-rejected per mode.
- the withdrawn recursive-closure prototype retained 40 payload references after 40 discarded acyclic clones with cyclic GC paused; the final module-level walker retained zero in the same discriminator.

The diagnostic three-callsite arm measured roughly 16% aggregate local agent-call reduction in its four cells per mode, but it overlaps LIVEPATH and is not a competing implementation or activation recommendation.

## Limits

This evidence authenticates the historical B567 package and official starter controls. It is not a current combined-V4 gate, competitive EV/rating proof, hosted deadline guarantee, Python 3.11 result, or LIVEPATH-helper certification. Before any activation, bind the funding-only edit to the one canonical shared projection helper and rerun the same action/state/score and current-stack regression gates.

## Files

- `projection_state_clone.py`: exact built-in dict/list graph clone with whole-root `deepcopy` fallback and failed-partial cleanup.
- `compose_projection_clone.py`: authenticated method-local scratch composer.
- `edits.json`: source-pinned funding edit plus diagnostic-only peer seams.
- `test_projection_clone.py`: alias/cycle/fallback/lifetime/composer custody tests.
- `VALIDATION.json`: original execution receipt and limits.
- `SWARM-HANDOFF.md`: integration ownership handoff.

Raw large game traces and historical fixture bytes from the original local archive are intentionally not treated as a new release artifact here; the durable source, exact deltas, tests and receipt are sufficient for the existing native composer to consume and re-gate against current source.
