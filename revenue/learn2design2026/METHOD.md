# Method / ablation packet — vectorized successor

## Claim discipline

The v2 successor is a performance hypothesis grounded in the organizer-documented vectorized Objective API. Local fake-objective runs prove execution semantics only. No synthetic number may be described as Learn2Design competition performance. Official/public dfbench measurements require an exact environment and package receipt; hidden score/rank/prize claims require provider evidence.

## Algorithm hypothesis

The merged v1 candidate spends the objective loop on one trajectory at a time. On the H100-class evaluation target, the successor instead advances multiple independent Adam trajectories with one `vmap_value_and_grad` call per generation. The hypothesis has two parts:

- **throughput:** amortize objective/JAX dispatch and expose more parallel work to the accelerator;
- **search robustness:** keep independent moments/trust radii/historical anchors so extra lanes explore distinct basins rather than behaving like one oversized gradient vector.

The algorithm deliberately avoids an additional learned model. The weakest historical quarter is periodically recycled around historical elites, with moments reset only for recycled lanes. This converts persistent dead/non-finite/stalled lanes into bounded exploration while preserving strong lanes.

## Required real-data ablations

| ID | Candidate | Comparator | Promote only if |
|---|---|---|---|
| V1 | 16-lane vectorized v2 | serial merged v1 | equal wall budget shows repeatable best-feasible improvement or materially more useful evaluations without worse tail |
| V2 | 8 / 16 / 32 lanes | each other | throughput gain survives compile/memory cost and quality does not collapse |
| V3 | elite recycle on | recycle off | improves late best-feasible tail on held-out topology/seed cells |
| V4 | per-lane trust adaptation | fixed trust | repeated improvement across at least two held-out topology/seed groups |
| V5 | annealed lane noise | no noise | improves median/tail without more non-finite failures |

Record topology identifier, seed, dfbench/Learn2Design revision, package SHA-256, Python/JAX/CUDA versions, accelerator, batch size, pre-clock warmup, wall budget, evaluation count, best feasible loss, feasibility rate, non-finite rows, peak memory and termination reason.

## Failure modes to watch

- larger batches can lose wall time to compile/memory pressure even when per-call throughput improves;
- objective penalty semantics already encode constraints, so the optimizer must not invent a second unverified penalty;
- JAX host synchronization inside the inner loop can erase vectorization benefits; keep ranking/update state on device;
- recycled lanes need moment reset or stale optimizer state can bias the new basin;
- public-topology tuning can overfit; reserve topology/seed cells for promotion decisions;
- package readiness and competitive readiness remain separate states.

## Decision rule

Do not promote v2 merely because it is vectorized. Promote it over v1 only after matched public-dfbench evidence shows a repeatable wall-clock/quality advantage. If 16 lanes are too large, retain the architecture and tune population size rather than reverting to unmeasured claims.
