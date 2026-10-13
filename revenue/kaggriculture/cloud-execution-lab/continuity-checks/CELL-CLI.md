# Explicit retained-record selection

The checker now accepts a named retained SELL record through `--cell`, rather
than imposing a fixed parser menu. Omitting `--cell` still selects the same four
original cells in the same order. Repeated flags preserve the supplied order.
The source/archive hashes, record-existence checks, complete-SELL requirements,
frame/telemetry alignment, one-parent execution and output preservation are
unchanged. This does not enable a different TITAN runtime or a public variant.

Seven actual parser cases passed: defaults, each of the four original names,
an explicit additional record prefix, and two original names in reversed order.
The original parser rejects the additional prefix; the new parser accepts its
name, while actual data must still exist and satisfy the unchanged input code.
Both original and updated real `--help` subprocesses exited zero. All five
non-main function ASTs are identical, including `own_inputs` and `worker`.
No policy, engine, prefix, game or stored benchmark was rerun for this change.

Original checker blob `5e7782d495f40eeadd761e5aadd17370a927ea3c` remains in
PR10169 and the retained delivery archive. Updated checker blob is
`0fb1f8f804cebf04b1f712123e868cfa5413e43b`. The original 2,876-pair result
continues to identify its original runtime and execution; it is not relabelled
as a new run of this CLI. `SOURCE-PINS.json`, `CONTINUITY-RESULTS.json`, input
controls and all original evidence remain unchanged.

Hosted checks are recorded per commit in the pull request, separately from the
original parser and continuity measurements. This usage-note clarification
changes no executable source or workflow configuration.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
