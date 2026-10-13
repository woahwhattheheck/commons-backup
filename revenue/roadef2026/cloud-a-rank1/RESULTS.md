# ROADEF targeted rank-one diversion — executed result

Exact PR source head `160bfecef362c3372bd52669ab661d147f532f48` completed dedicated workflow run `34202488794`. Artifact `10046558128` was independently downloaded and matched GitHub SHA-256 `e663be938802e283308f72d63ab44b2f5832719d3353b8b9a0dca415e88746ef` (390,514 bytes; 43 files). The generated opt-in candidate is 45,157 bytes, SHA-256 `038cffc7121f6447423d231c473af1f49e6f75d4d315bdc5c7fc2b2391f94306`.

| Instance | Named target | Continued target | First full-vector difference | Search | Result |
|---|---:|---:|---:|---:|---|
| A04 | 0.587276 | 0.587276 | — | 14,870 attempted / 0 accepted | unchanged |
| A14 | 0.533147 | 0.492132 | rank 1: 0.533147 → 0.517621 | 47,796 / 9 | strictly better |
| A16 | 0.079918 | 0.079918 | rank 539: 0.027868 → 0.027827 | 249,214 / 13 | strictly better below the bottleneck |

All three outputs pass the pinned official checker at both six and twelve decimals. A14 closes the named six-decimal peak gap: the resulting maximum is 0.517621, equal to the published reference peak scalar. The artifact does not contain the published reference's complete vector, so this is **not** a full-vector reference win or tie claim. A16 leaves its named maximum and leading ranks unchanged; its gain begins at rank 539. A04 terminates after one no-change pass with byte-identical output.

These are three warm-started public-development cases, not a qualification submission, hidden-instance result, set-wide superiority claim, or S139 status change. The full raw vectors, input identities, solutions, stats, reports, stdout/stderr, generated source, and test source remain in the workflow artifact.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
