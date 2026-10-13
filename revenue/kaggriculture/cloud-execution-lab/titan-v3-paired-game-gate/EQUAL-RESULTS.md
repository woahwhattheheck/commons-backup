# Dual-predecessor closures, not score-file inequality

A finite game panel is an observation, not an executable closure. Two distinct
predecessor closures can legitimately produce the same normalized terminal rows
on every measured cell. Conversely, copying one panel and changing whitespace,
JSON key order, or row order changes the raw file digest without executing a
second predecessor.

The custody-bound gate therefore separates two statements:

1. **Execution closures:** predecessor names and both declared and observed
   closure-bundle SHA-256 values must be distinct; each strict receipt binds its
   closure to its contract, provenance evidence, engine, runner, baseline game
   bytes, and the shared candidate.
2. **Measured outcomes:** each baseline panel independently satisfies the
   inherited complete-grid and numeric-closure rules. Its bytes may equal the
   other predecessor panel when the measured outcomes are genuinely identical.

Reserialization remains an alias: when file bytes differ but the canonical
score matrix (including signed-zero normalization from #11760) matches, the
gate still returns `INVALID`. That preserves #11743. This change removes only
the raw outcome-byte inequality veto.

The candidate artifact and candidate panel remain shared exactly across both
comparisons. Candidate/predecessor artifact aliasing remains invalid. Closure,
receipt, grid, policy, candidate, and single-gate custody are unchanged.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
