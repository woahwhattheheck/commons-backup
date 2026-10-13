# V3.1 → V4 semantic-delta convergence map — 2026-09-12

This is an evidence/control-plane disposition for the **single production-v3 / V5 lineage**. It does not add a policy, change a runtime default, move `CURRENT`, publish a release, or authorize a Kaggle submission.

The root authority is the exact-submission package analysis in `COVERAGE.json` / `coverage.py`, not nearby Git history:

- submitted V3.1 `56172377`: SHA256 `5db3921f85efbc7596e5a1e7e198fc5f4644ceea43d8e8323c74ded7b4ba4361`, 148 members;
- submitted V4 `56182437`: SHA256 `4d9601552b5e25d02d8a33961c0bed54ed92d032dbcd4a72f6ab8e03515ed21b`, 75 members;
- observed canonical-main snapshot for this disposition: `0f715dcbb767d1b68574789123c020c0b4fbc8d7`.

## Causal center

Submitted V3.1 is **not** V4 with a few feature flags reversed. With `r04_sale_window=true`, exact V3.1 `TitanAgent.act()` returns through `TitanAgent._v3_r03_act()` **before canonical controller initialization**. That delegate imports `r04_full_router.install()`, whose factory returns standalone `v3_agent`. Submitted V4 removes the R04 package/config surface and executes the canonical runtime path.

Therefore the primary regression search is the boundary between the standalone R04 route program and V4's canonical runtime/postprocessing, not a blind rollback of every archived Python symbol that differs.

The exact config delta reinforces that rule: all 16 common keys are equal. V4 adds exactly one key, `town_procurement=true`; the many V3.1-only keys belong to the active V3/R04 package topology.

## What current V5 evidence already resolves

Canonical production-v3 archive `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239` restores the R04 producer while retaining selected V4 economics/finalizers. The retained native-9901 screen on seed `1209129901` completed 719 callbacks in every cell with no external failure:

| Arm | Apex own/rival | Apex margin | Arlene own/rival | Arlene margin |
|---|---:|---:|---:|---:|
| Submitted V3.1 | 74143 / 64333 | 9810 | 74260 / 68660 | 5600 |
| Submitted V4 | 70385 / 62323 | 8062 | 69847 / 68401 | 1446 |
| Production v3 | 73906 / 63838 | 10068 | 74592 / 68772 | 5820 |
| Town-off | 73904 / 63838 | 10066 | 74591 / 68772 | 5819 |
| Aggregate postprocessor bypass | 74143 / 64333 | 9810 | 74260 / 68660 | 5600 |

Consequences:

1. **The R04 restoration is real and useful.** Production-v3 beats submitted V4 by large margin and beats V3.1 margin on both opponents in this finite screen.
2. **`town_procurement` is not the missing V3.1 advantage.** Turning it off is slightly worse than full production-v3 here (Apex margin −2; Arlene margin −1).
3. **Blanket canonical-postprocessor removal is not the answer.** Aggregate bypass reproduces exact V3.1 terminal scores, while full production-v3 has better competitive margin. The remaining task is decomposition, not rollback.
4. **The V4 inner-deadline placement is not engaged on this authority.** Production-v3's maximum callback is `0.252s` with zero external failures. This is a native observation, not a hosted-runtime theorem, but it supplies no evidence for a timing repair now.
5. **There is still a narrow Apex own-score deficit.** Production-v3 is `−237` own score vs V3.1 on Apex even while its rival is `−495`, improving margin. This is the unresolved semantic frontier, not evidence for a wholesale V3.1 restore.

The matched consumer-boundary evidence is now canonical on main. Relative to its dependency-valid matched frozen control, the parent consumer bundle changes:

- Apex: own `+306`, rival `+441`, margin `−135`;
- Arlene: own `−302`, rival `−138`, margin `−164`.

So the whole consumer bundle is not promotable. It is also not a `FrozenSelected`-only result; the live decomposition lane must isolate the effective retained gates without invalid dependency combinations.

## Ownership / disposition

| Semantic seam | Evidence disposition | Single-V5 owner / action |
|---|---|---|
| Standalone R04 route topology removed in V4 | **ACTIVE CAUSAL CENTER**, already restored into production-v3 | Keep production-v3 as the common parent; do not create a sibling V3.1 tree |
| R04 route/plan choice | C00 controls are canonical on main; plan treatments need candidate-only comparisons | Existing shared route-matrix carrier; reuse C00, never rerun baselines |
| First returned-action divergence from V3.1 | Terminal scores cannot localize it | Existing immutable action-witness carrier (#13471); repair only from authenticated candidate-first evidence |
| `town_procurement=true` | Measured non-fix in native-9901 | Retain full production-v3; no town-off gameplay branch |
| Canonical postprocessor/finalizer bundle | Aggregate bypass exactly returns V3.1 but loses production-v3 margin | Existing consumer/postprocessor decomposition family; isolate only dependency-valid gates |
| Consumer boundary bundle | Conditional/non-winning: Apex own rises but both opponent margins fall | Decompose; no blanket consumer flip |
| Inner deadline around restored R04 producer | Non-engaged in retained native sample (`max_callback=0.252s`, failures `0`) | No repair from this lane; reopen only on concrete timeout/fallback evidence |
| Same-step R04 retry containment | Source closure already landed in canonical V5 lineage | Consume merged state-safe retry semantics; no sibling retry wrapper |
| SELL/funding/EOD/animal/fertilizer/capacity/economics hypotheses | Independently claimed source/evidence lanes | Preserve their ownership; winners export into the one staging/composer path |
| P05 weed-queue / same-day displacement | Earlier specific owner predates this global map | Handoff only; this lane makes **zero P05 source mutations** |
| V3.1/V4 raw leaf-symbol differences unreachable under active V3.1 R04 fast return | Not valid rollback evidence by themselves | Use only as V4 self-ablation diagnostics unless separate reachability proof exists |

## Convergence decision

**No new gameplay repair is justified by this global semantic-delta lane.** Every evidence-backed surviving seam is either:

- already restored in production-v3;
- experimentally negative/non-improving (`town_procurement` rollback, aggregate rollback as a promotion);
- currently non-engaged (native timing envelope); or
- actively owned by a narrower source/evidence lane (route, action witness, consumer decomposition, P05, P01/P02/P04, SELL/funding/EOD/animal/fertilizer/capacity).

Creating another policy branch from the global comparison would duplicate active work and make V5 less convergent. The correct output of this lane is this source-bound map plus handoffs. Any measured winner from narrower lanes must converge through the existing single staging/composer path against exact production-v3 rather than minting an independent V5 family.

## Durable evidence already on canonical main

- `regression-coverage/COVERAGE.json`: exact submitted-package inventory/config/symbol/reachability authority.
- `selective-carrot/native-9901/README.md`: production-v3 vs V3.1/V4 + town-off + aggregate-bypass native screen.
- `production-v3-postprocessor-attribution/native-9901/consumer-boundary/`: matched consumer pair.
- `selective-carrot/route-matrix-native/C00/`: shared V3.1 vs production-v3 route-matrix controls.

Do not rerun those controls merely to obtain another copy. New compute should buy information on an unresolved treatment.