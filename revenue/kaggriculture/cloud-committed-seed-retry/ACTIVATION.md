# Committed-seed retry activation result

The packaged retry is operational, but this evaluation does **not** support
enabling it by default.

The recovered actual turn-207 missed-seed input was passed through the real
`TitanAgent.act` path with only `committed_seed_retry=true`. The runtime called
the producer exactly once, called no second controller from the retry, and
returned the exact recovered funded action by appending
`BUY_SEED STRAWBERRY 1`. All worker actions and the next committed route were
unchanged, including its `SELL WHEAT 2`. The existing funding certificate
admitted the 100-cash purchase inside observed cash 258 and route reserve 0.
The same-turn-late input remained unchanged, as required.

Two official-engine panels then compared the exact `6c50cf60...` package with
the default false against a copy whose only configuration delta was true. Each
panel used 16 seeds, both seats, unchanged Arlene and the official starter, and
two concurrent cells. The initially executed 4101-4116 block is retained as
development/overlap after the later reservation correction. The prospective
5101-5116 block has its own immutable identities.

| panel | full games | complete | exact score/trace/trajectory pairs | enabled decisions | activations |
| --- | ---: | ---: | ---: | ---: | ---: |
| development/overlap 4101-4116 | 64 | 64 | 32/32 | 23,008 | 0 |
| prospective 5101-5116 | 64 | 64 | 32/32 | 23,008 | 0 |

The prospective enabled decisions ended unchanged for these reasons:
16,270 had no next-turn planting, 4,824 had no seed deficit, 1,024 were route
or day boundaries, 864 retained a dynamic product obligation, and 26 already
had a selected seed purchase. These are zero-activation cases, not strength
evidence. The 16W/0T/0L records against each opponent are shared by both arms
and therefore do not establish a retry gain.

The exact reached input proves the runtime seam is reachable and correct; the
fresh games simply did not produce a missed certified deficit. No new runtime
gap was identified, and no speculative relaxation of cash or route protections
was made. The default remains false. Raw trajectories and the private reached
observation are deliberately excluded; `ACTIVATION-RESULTS.json` retains only
aggregate outcomes and integrity hashes.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
