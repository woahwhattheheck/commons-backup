# S139 - A portfolio for T-adaptive segment routing

**Objective and constraints.** Each demand receives an ordered waypoint list at each time slot. Traffic follows shortest paths between successive source, waypoint and destination nodes, splitting equally among outgoing shortest-path arcs at each forwarding node. Maintenance removes the specified arcs independently at each slot. Link utilization is traffic divided by capacity; utilization above one is permitted. The objective is the lexicographically smallest descending vector of all link/time utilizations. We invoke the official checker with `--max-decimal-places 6` and preserve its exact Decimal tokens, including scientific values below 1e-6, without further rounding. Equal vectors tie; transition cost is never a tiebreak.

A route with k waypoints has k+1 segments and must respect the input limit. Reconfiguration cost is the symmetric difference of the sets of directed segment pairs in consecutive routes, summed over demands. Every transition must satisfy its own budget, including both boundaries of an edited interval. Initial setup is free. Identical waypoint lists incur no cost when maintenance changes their underlying forwarding paths. The search conservatively excludes repeated waypoints and demand endpoints.

**Routing representation.** Three independent C++20 solvers maintain routes, sparse utilization coefficients, aggregate loads and transition usage. Reverse Dijkstra searches lazily construct destination/time forwarding DAGs. Unit traffic propagates through each DAG using per-node ECMP splitting. Cached sparse coefficients compose route segments. Demand indices retain input order, while topology references use explicit IDs.

**Complementary neighborhoods.** SEDGE selects contributors to heavily loaded link/time positions. It begins with whole-horizon edits and adds single-slot, prefix and suffix changes. Waypoint candidates combine adjacent nodes with fixed-seed samples on larger networks. Moves remove routes, replace waypoints or extend route ends, considering at most four segments within the input limit.

FLORA preserves that kernel and adds windows of radii one, two and three around the selected slot. These windows expose feasible transition boundaries unavailable to an isolated change. Its process starts independently.

The candidate ranks single-waypoint alternatives by predicted peak utilization, an eighth-power congestion potential and contribution to the selected critical link. It scans nodes as time permits and widens expensive interval evaluations after stalls. Insertions at any position and individual deletions use the full segment limit. Bounded two-demand exchanges redirect a critical-link contributor, then traffic on a newly burdened link, over a shared interval. Combined load and transition accounting allows one demand to release budget for the other. Only a jointly feasible improvement is committed.

<!-- PAGEBREAK -->

**Exact computational improvements.** The candidate incorporates three optimizations that preserve its move semantics. WREN computes segment-set symmetric differences in fixed local arrays when both routes have at most seven waypoints, retaining duplicate elimination and the general set-based fallback for longer routes. DELVE compares the largest quantized changed utilization and its multiplicity before sorting; unresolved comparisons use the original full descending sort. KESTREL shares forwarding DAGs and segment coefficients only across slots with identical complete maintenance masks. Routes, traffic, loads and budgets remain indexed by actual time.

Internal acceptance retains conservative six-decimal bounds around floating-point load updates. Unchanged multiset entries cancel, so only affected positions require comparison. This internal test guides search; the official checker independently determines saved-solution feasibility and the complete output ranking.

**Portfolio execution.** A Python standard-library supervisor starts the three single-threaded solvers from empty waypoint lists and serializes official-checker evaluations. Candidate bytes are frozen before checking. A strictly better valid vector triggers atomic replacement of the output. Ties, regressions and invalid candidates preserve the incumbent. A transient checker failure receives one retry of the same frozen bytes. The initial zero-change checkpoint is marked unvalidated until checked.

The search allowance is 565 wall-clock seconds, including solver preparation. Shutdown allows two seconds before forced termination, within a planned 585-second supervisor deadline. An external termination signal leaves at most seven seconds for shutdown. The four-path `run.sh` interface takes network, traffic, scenario and output paths. The build uses C++20. Fixed seeds aid repeatability; elapsed-time stopping and contention can change progress.

**Validation and attribution.** The selected composition underwent 352 fixed-work native runs on ten generated networks. Exact solutions, loads, transition usage and non-time search counters matched the original candidate; 80 official checks validated the baseline and composition. This supports semantic preservation under the exercised workloads, without establishing hidden-instance rank or global optimality.

SEDGE authored the MIT-licensed base; FLORA and the candidate retain that derivation. TokenJunkieLabs contributors developed supervision and search extensions. WREN, DELVE and KESTREL authored the computational changes, composed by CEDAR-JOIN. Orange SA supplies the subject, rules, checker v1.2.2 and Networktools. Original licenses and attribution are retained.

**Sources.** [1] [Orange problem and rules, pinned d84d319a](https://gitlab.com/Orange-OpenSource/network-optimization-tools/challenge-roadef-2026/-/tree/d84d319a7fdb8de3b1866830d2eaa2937871e5ae/doc). [2] [Solver composition, definitions and evidence, pinned f5c21009](https://github.com/woahwhattheheck/commons/tree/f5c21009231a76c4c4a84bab9a15ab86ecab82d9/revenue/roadef2026/cloud-kernel-composition).

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
