# R04 postprocessor survivorship

This is one bounded, package-authoritative follow-up to the merged V5 production-recovery candidate. It does not create a second V5 release line and does not authorize games by itself.

## Why this arm exists

Exact submitted V3.1 archive `5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361` fast-returned through the R04 whole-route policy before constructing the canonical FrozenSelected/postprocessor path. Merged production recovery restores that exact R04 policy family inside the retained V4 runtime and adds the deliberate carrot/delivery composition. As a result, several config values that were already `true` in submitted V3.1 become executable around R04 in the V5 composition even though V3.1 never ran those stages on scored callbacks.

The baseline is the exact merged production-recovery archive:

- archive SHA256: `0aded66a2c393cc60f4f45d10f11c384a7e788182bf5430863829a02b66daf02`
- config SHA256: `ba18563683125fd89d5473ddb8a5c3e9431db1787a3046f618a9e03af2cb44af`

This treatment changes only `TITAN-CONFIG.json` and suppresses the canonical consumer/postprocessors as one aggregate survivorship test:

- `consumer: frozen -> parent`
- `seed: true -> false`
- `funding: true -> false`
- `redundant_hire: true -> false`
- `market_pressure: true -> false`
- `operating_stock: true -> false`
- `idle_fertilizer: true -> false`
- `crop_release: true -> false`
- `early_capital: true -> false`
- `town_procurement: true -> false`

Treatment config SHA256 is `f32890231e5ea0b082ffdb6e2e9dbf65450172488e023f51314fc1aff059ff2f`. Every other archive member must remain byte-identical, including the authenticated R04 donor closure and carrot/delivery code.

`consumer=parent` is intentional. In the authenticated `0aded...` topology, `FrozenSelected` inherits `SellScheduler`; that constructor creates `controller = parent.Agent()`, and `TitanAgent._initialize()` assigns that controller to `production`. The #13455 overlay makes `parent.Agent` the embedded R04 agent. Production therefore already calls R04 directly. The frozen scheduler runs later through `consumer.transform(...)`; parent mode makes `transform_selected()` take the selected-action deepcopy path instead. `seed`, `funding`, and `redundant_hire` are explicitly disabled because TitanRuntime can still apply those selected-action transforms in parent mode; the remaining false flags suppress the retained pressure/stock/spatial/capital/town stages. The deliberate carrot/delivery shell remains unchanged and continues to read the R04 controller tape.

That interpretation is machine-bound, not documentary only. Receipt schema v2 pins the exact baseline SHA256 of `main.py`, `titan_runtime.py`, `frozen_selected.py`, `scheduler.py`, and `r04_full_router.py`, and requires unique source anchors for the controller/production and parent-mode transform topology before any treatment is emitted. A later package cannot inherit this interpretation merely by updating the top-level archive constant.

## Publication custody

Both final destination paths are reserved create-exclusively before either payload is written. The materializer retains each process-owned file descriptor and its `(st_dev, st_ino)` identity, writes and fsyncs the archive and receipt only after both reservations succeed, and marks the pair committed only after both payloads complete. On reservation, write, or fsync failure, cleanup checks each pathname's current inode against its reservation before unlinking it. A pre-existing receipt survives untouched while the first reservation is removed; a replacement already visible at the identity check is also preserved.

This contract covers cooperating create-only writers. Reserved names must remain stable during cleanup: the identity check and unlink are separate filesystem operations, so an uncooperative writer replacing a path between them can race cleanup. The final existence checks likewise do not establish custody of a directory that another writer can arbitrarily mutate.

## Decision rule

This is an aggregate kill-or-localize arm, not a factorial. Do not run it while the SPARK native panel for exact `0aded66a...` is unresolved. If the baseline fails its native screen, stop. If the baseline remains viable, one matched treatment arm may reuse the same engine, opponents, seeds, seats, RNG, timeouts and exact controls. If the aggregate treatment is worse, close this lane. If it is materially better, only then localize the surviving canonical stages with the minimum additional arms.

No runtime/default/CURRENT/release/Kaggle activation is made here. `native_economics_status` remains `PENDING_BASE_PRODUCTION_PANEL` until real matched evidence exists.
