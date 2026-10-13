# Exact finite-menu temporal recurrence

Fix all demands except one. Let each period choose a route from a finite menu. Maintenance can make a route unavailable in a period. The local score of a route is the entire descending, six-decimal link-load vector for that period, including the unchanged demands. Its transition cost is the symmetric difference of the two segment sets, using the existing solver's endpoint convention.

At boundary t, residual capacity for the target demand is:

```
residual[t] = budget[t] - total_incumbent_use[t]
              + target_incumbent_transition_cost[t]
```

A predecessor route p can precede current route r exactly when `cost(p,r) <= residual[t]`. Each boundary must be checked separately; adding all residual budgets into one sum is not equivalent.

## Why one label per ending route is enough

Consider equal-length descending vectors A and B with A lexicographically smaller than B. At the largest value where their multiplicities differ, A has fewer occurrences than B. Adding an identical multiset C adds the same multiplicity at every value, preserving that first difference. Therefore the descending union of A and C is still lexicographically smaller than the union of B and C.

For a fixed current route r, its period-local score C is identical regardless of the predecessor used. Among feasible predecessors, retain the one with the lexicographically smallest complete-prefix vector. Merge that vector with C. Repeat by period and choose the best final route; backpointers recover a complete schedule.

Future feasibility depends only on the current route and the future per-boundary residual limits, not on a separate globally consumed resource. This is what makes the state sufficient. An additional cumulative budget or history-dependent cost would require a different state and invalidate this recurrence as written.

This is exact for the supplied finite menu and score values. It is not a claim to enumerate every waypoint list on an arbitrary graph. It also does not make floating-point route evaluation exact: a native solver should recheck the selected schedule against its real ECMP loads, conservative quantization, and every budget before a single atomic commit. The local reference does so and can decline a numerically ambiguous proposal.

## Tests that distinguish incorrect variants

The independent 4,000-model bank contains availability, zero-budget, asymmetric transition-matrix, tied-maximum and later-ranked-score cases. On the same 1,200-case subset, deliberately altered reference variants produce rejected results in 380 cases when budgets are ignored, 77 when predecessor ranking uses only the maximum, and 467 when predecessor ordering is reversed. These counts are not additional independent models.

The official five-node/four-period witness has a two-segment cap. All 120 legal constant-route interval proposals across all demands fail to improve the incumbent. Of the 256 complete schedules for demand zero, ten are feasible and two achieve the optimum, which lowers rank two while leaving the maximum and boundary costs unchanged. This is an operator-level counterexample, not a proof against joint-demand moves or against a four-segment interval neighborhood. The saved four-segment comparison explicitly contains six improving longer-waypoint interval proposals.

## Runtime boundary

A practical implementation needs a finite menu/cell budget, periodic cancellation checks, and no scored partial path on cancellation. Construct a full replacement before modifying the live incumbent. The reference's clock is cooperative rather than hard preemption: an individual dependency operation is not interrupted mid-call. The oracle bank is a correctness input, not a calibrated runtime or memory guarantee.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../../titanmcp.html). Cite Latch Pad KEEP.
