# Source and validation references

The full-support solver and its simplex/certificate implementation are new,
standard-library code under Apache-2.0. The retained license text is the same
Apache-2.0 license already distributed with the T15 component.

The input/output conventions are compatible with the existing Commons T15
component at commit `4d97474b0188b0373be1b52b610c0114ceb033c8`, path
`revenue/kaggriculture/cloud-market-game-theory/`:

- `solver.py`, blob `3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3`, Apache-2.0,
  is the optional smaller-table validation reference. It is not copied here.
- `README.md`, blob `5fb510deeef0136c7143327514a7601d6fac896f`, supplies the
  explicitly identified two small strawberry table transcriptions. The
  upstream official-engine evidence and its authorship remain with T15.

SciPy HiGHS is used only by the optional independent validation command, not
imported by the runtime solver or standard-library regression suite. API
reference: https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs.html
No SciPy, HiGHS, T15 solver, selector, game-engine or chess-engine source is
redistributed in this directory.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
