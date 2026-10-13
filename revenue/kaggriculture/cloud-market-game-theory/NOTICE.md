# Source and licensing

T15 solver, selector, scanner, bridge and evaluator additions are Apache-2.0;
see LICENSE. The accepted frozen SELL scheduler and its mechanics/receipt
dependencies retain their existing Apache-2.0 provenance and source notices.
T12 policy/history/scorer and opponent perturbations are reused unchanged from
commons4d7fd6d4d4e1f71941f7fe76b8e10274f1bfc1a6 under their existing MIT and
vendored notices. Original Arlene/Apex implementations and every adjacent
license remain with the reused components; this work makes no authorship claim
over them. DEPENDENCIES.json records the exact source hashes.

The evaluator uses the unmodified official Kaggle engine at commit
28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c. Runtime strategies use normal observable
game actions only. Rival private inventories in engine fixtures are evaluator
inputs used to define hypothetical columns, never runtime policy inputs.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
