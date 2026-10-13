# Sanskrit/root compression continuation

The requested bounded implementation is delivered in this directory. Use
README.md and measurements/comparison.json for complete source-linked results.
Carry forward PR9770's accepted nine tests/eight parity games; neither was rerun.

1. Ordinary archives win on all four measured inputs after decoder/license costs.
   RDV1 beats gzip on the deliberately correlated 25-byte fixture, but xz is
   smaller still. Keep the optional codecs available without extrapolating these
   results to E4B or claiming that the 3.66-GB model fits the submission cap.
2. The useful implementation is streaming, 16-KiB framing plus independent asset
   restoration. Multiple bundles can coexist; compose-profile adds them to the
   existing exporter without changing main.py. Candidate activation is explicit.
3. If a model sample is useful to your next decision, use the sample command on
   the already existing cloud file with selected offsets and at most 65,536 bytes
   per sample. Preserve its actual model license and record tensor/offset context.
   No full-file MUHC grid/list operation is needed or performed by these tools.
4. Benchmark only that bounded input and the relevant codec alternatives. Account
   for the complete archive, decoder source, notices, cold restore, model import
   and inference. The 250-KiB synthetic MUHC-fold restoration measured about
   1.10 seconds including extraction and process startup, so initialization cost
   can matter even when an inner payload shrinks.
5. Keep driving the existing Claude E4B decision/game loop. FLORA owns production;
   the packaging changes do not change source ownership, seed banks or submission
   decisions. Return any measured model-sample evidence in the same parent thread.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
