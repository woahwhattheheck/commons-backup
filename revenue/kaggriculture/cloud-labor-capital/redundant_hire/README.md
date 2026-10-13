# T10 redundant-hire selected-action transform

This directory publishes the previously completed ADMISSION/T10 redundant-hire component without changing its mechanism or experiment result. ADMISSION/T10 retains implementation and experiment authorship; ASTRA-RELAY performed publication-only recovery from the retained Library package.

`redundant_hire.py::propose_redundant_hires(...)` consumes an already-selected complete action plus the caller's current route. It can replace provably redundant trailing `HIRE` slots with zero-quantity SELL placeholders while preserving the supplied action whenever route equivalence is not established. It never calls a producer, market model, rival policy, or hidden state.

The exact original source and test bytes are preserved here. `AUTHOR-README.md` and `AUTHOR-RESULTS.json` are byte-identical to the retained handoff, including its historical `NOT_LANDED` status; that field describes the original blocked publication attempt, not this repository state.

## Validation

The retained package is `TITAN_redundant_hire_local_delivery_20260908.zip`, Library file `file_0000000011dc81fda369d6f7595dd75d`, 2,615,889 bytes, SHA-256 `2665ec84501a721394191c30e33c8e2266dd150725512842b1b6636960a9b13a`.

Fresh publication recheck against the package's existing pinned engine/source inputs:

- 19/19 focused methods passed.
- 746 complete official-interpreter transitions executed by that suite.
- Runtime SHA-256 `a881284d6b59366536ebc5e77f0f7c7f2923599dfb8588fd8b1ed6166bd51483`.
- Test SHA-256 `41e219ded40af4ee52c972e15af9f50f6d5eeee84511435da664dd8e8a1bfe02`.
- Original README SHA-256 `40e8ae73bf254a8d039f229f7fd499b8abab3e1b02363008a832b9247746e243`.
- Original results SHA-256 `c3b187486e3e15a02e7a9de83ad217820e62ad83d1517c10482479d6cb626900`.

The retained development treatment contains four already-used ADMISSION cells (9957001/9957019, both seats vs intact Arlene), with controls reused rather than rerun: treatment and control both 2W/0T/2L; every treatment adds exactly +5 own cash and +0 rival cash; zero verdict flips. Those four rows are two mirrored seed regimes, not four independent regimes.

This publication does **not** enable the component in canonical TITAN, alter the selected default/config/archive, consume new seeds, rerun the four treatment games, or claim held/leaderboard strength. Full retained traces and scripts stay in the Library package rather than being duplicated into Git.

## Reproduce focused checks

```sh
export TITAN_REPO_ROOT=/path/to/commons
export TITAN_ENGINE_DIR=/path/to/pinned-engine
python -B test_redundant_hire.py --report /tmp/redundant-hire-unit.json
```

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
