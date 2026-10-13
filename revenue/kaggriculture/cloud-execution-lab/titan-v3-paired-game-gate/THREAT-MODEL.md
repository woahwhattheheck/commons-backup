# Threat model

## Threats handled

- **Survivorship averages:** failed and timed-out rows cannot disappear before
  aggregation; any non-complete or missing cell invalidates the panel.
- **Grid substitution:** seeds, opponents, and both seats are predeclared and
  compared as an exact Cartesian product.
- **Duplicate weighting:** duplicate cell keys are rejected instead of counted
  twice.
- **Provenance substitution:** engine, runner, control archive, and candidate
  archive identities must match the frozen contract.
- **NaN/Infinity, overflow, and malformed numeric evidence:** non-finite JSON
  constants, booleans-as-numbers, integers that cannot convert to a finite
  float, and score vectors other than length two are rejected.
- **Mean-only selection:** result flips, pair balance, opponent strata, seat
  strata, median, and worst-cell behavior are explicit checks.
- **Policy drift:** every policy field is mandatory and embedded in the report.
- **Parser ambiguity:** duplicate JSON object keys, boolean schema versions, and
  unknown schema keys are rejected.
- **Hash/parse time-of-check-to-time-of-use:** every input is opened once with a
  no-follow regular-file check, copied into a private snapshot while hashing,
  and parsed only from that copy. The report records that digest and byte count.
  Source-path replacement after acquisition therefore cannot change evaluation.
- **Concurrent input mutation:** size and identity metadata are compared before
  and after snapshot construction. A post-evaluation digest check catches
  mutation of a private snapshot.
- **Torn reports:** reports are written and fsynced to a temporary file, then
  atomically replaced.

## Threats not handled

- A malicious evaluator that fabricates internally self-consistent rows.
- Incorrect engine/source hashes supplied identically to contract and evidence.
  Independent artifact construction and receipt review remain necessary.
- Hidden-state leakage or an invalid opponent implementation.
- In-process mutation of this program's own code or RAM during a run. Snapshot
  binding covers file bytes only; it is not a sandbox or a signature authority.
- Multiple-hypothesis bias, confidence intervals, or generalization beyond the
  declared seeds. Use a separately frozen development selector and disjoint
  holdout contract; generic statistical tooling may consume this gate's aligned
  cells afterward.
- Policy semantics that do not produce the intended action/state change. Each
  candidate still needs an official-engine transition oracle and action trace.
- Automatic production promotion. This tool never modifies a runtime, archive,
  release pointer, or provider state.

The gate proves that a declared paired panel is complete and that its observed
metrics satisfy a frozen decision contract. It does not prove why a candidate
won, that it will generalize, or that it is safe to deploy without review.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
