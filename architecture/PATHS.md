# Commons path and subsystem map

`path-manifest.json` is the shared descriptive map for canonical records,
generated projections, executable source, public surfaces, commercial and
orchestration catalogs, evidence, and the large Muhlnickel corpus.

It has no participation effect. It never decides whether a post, Action Pad
request, job, or adapter invocation lands. It exists so generators, tests, CI,
builders, sparse-context workers, and future mirrors can describe the same path
with the same classification.

Run the deterministic diagnostic:

```bash
python3 host/path_manifest.py
python3 host/path_manifest.py --report /tmp/commons-path-report.json
```

The report reads `git ls-files`, applies first-match rules, inventories root and
nested tests, and extracts declared path contracts such as
`board_ingest.py:ASSET_PATHS` through Python's AST. `ASSET_PATHS` is a mixed
staging/generator contract: it includes canonical input trees, derived output
trees, and individual generated or staged files. The diagnostic therefore
classifies tracked directory declarations through an actual tracked descendant,
classifies missing file declarations as their literal path, and separately
lists missing and unmapped staging/generator targets. It does not claim that
every listed path is a generated output.

First-match order preserves exact canonical and derived rules, then gives CI,
tests, executable code, and public surfaces precedence over broad subsystem
prefixes. For example, an orchestration JSON catalog remains a catalog while an
orchestration Python probe is executable source and its HTML entrypoint is a
public surface. Paths that need a more precise mapping stay visible as
`UNMAPPED`; they do not stop existing roads.

The checked manifest is source. Reports are exact-tree observations and are not
committed as a second repository truth.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
