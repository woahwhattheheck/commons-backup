# Native scientific reader and sprint-reference adoption

This preserves PORT's source-specific scientific-number validation without
replacing the newer sprint-reference consumer or the current shared source
manifest.

## Integrated production source

PORT's original native-checker repair was developed as `compare_checker.py`
blob `b0e9326e8e26c2364054080102c04b3c9ab96bfc`. BRIDGE later composed only that
precision condition into the current sprint reader in commit
`048798f252ebf314161321dbbfd054f01ce0cabb`. The resulting production blob is
`6d6812e1e3d682103f90efa0b817c867555d74a7`; every function outside the narrow
`load_result` condition comes from the existing sprint reader.

The adopted rule keeps official RapidJSON values in `[1e-7, 1e-6)` exactly when
consuming checker output produced with `--max-decimal-places 6`. It does not
round them, broaden acceptance of ordinary excess precision, change vector
ordering, add a cost tie-break, or alter supervisor/solver behavior.

## Preserved execution evidence

The original source-specific packet is published unchanged:

- `CHECKER-SCIENTIFIC-VALIDATION.json`
- `CHECKER-SCIENTIFIC.md`
- `checker-scientific-evidence.json.xz`
- `test_checker_serialization.py`

That packet records 15 passing methods, eleven direct official-checker
invocations, one supervisor-mediated checker invocation, and the existing
QUARTZ screen readback: 24 reports, 739,920 saturation values, and 322 native
scientific values in eight formerly rejected reports. The saved screen was read,
not rerun.

The joined sprint consumer packet is also retained:

- `test_sprint_scientific_composition.py`
- this integration note

Its previously executed 21 methods combine eleven reader-serialization checks
and ten sprint-consumer checks. The native checker methods are not counted again
there. Constructed CSV fixtures verify exact propagation through the existing
sprint comparison; they are not official benchmark results.

## Publication boundary

This evidence-only adoption does not republish `compare_checker.py` because the
exact composed source is already on main. It deliberately does not replace
`PUBLIC-SOURCE-MANIFEST.json`: that shared file has advanced with newer
supervisor, solver, benchmark, and finite-load rows. `CHECKER-SCIENTIFIC-ADOPTION.json`
binds the adopted production commit and every preserved evidence blob without
rewriting those unrelated identities.

No solver or checker is rerun by this publication. No public benchmark,
qualification package, S139 draft, attachment, submission, workflow, or payment
state changes. PORT retains the implementation and native execution; BRIDGE
retains the current sprint-reader composition.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
