# Funded seed: official cash representation

DELVE's consumer experiment over JUNIPER/CYPRESS's existing join exposed a
representation mismatch in CEDAR's existing funding certificate. The pinned
engine initializes farm money with `float(starting_money)`. The certificate's
integer-only cash check therefore rejected ordinary reached values such as
40319.0 and41478.0 before evaluating funding.

## Repair

The only production change is a monetary scalar helper plus its call site in
`../seed_funding.py`. Exactly integral floats are converted to their exact integer
value. Fractional, nonfinite, negative, boolean and string cash are not rounded
or coerced. Seed quantities, indices, costs, callback ordering and all other
integer-only checks remain unchanged. This changes no controller, route, seller,
funding model, default entrypoint or optional product-price bound.

The source is `7f59917f6c16a60a16921f161124b328fdb93fcf`, SHA256
`249ad9fd46625088bfb8e1ab977862701aabf7bbe48aa3fbc3e2f58e2c84fd85`.
The pre-repair certificate is blob`f6ec71cf7ae168e646c24d9cbee2a88343aedf94`.

## Executed comparison

Development9965001/9965019 were announced before execution after Slack and
retained-source collision searches; GitHub search was incomplete. Each cell uses
both the same integrated funding-off controller (SELL remains on) and the repaired
funding-on controller, plus a separately labeled original frozen-SELL benchmark.
The dependency closure is the unchanged PR9997 archive95c7bf10 plus exact
JUNIPER hook0336228e and entry32d74fe9. Later hot-path and product-bound changes
are not silently included.

| Seed | Position | Integrated control own/rival | Repaired funded own/rival | Own/rival change | Frozen SELL own/rival |
|---|---:|---:|---:|---:|---:|
|9965001|0|52731 /52446|52981 /52446|+250 /0|52356 /51768|
|9965001|1|52864 /52313|53104 /52313|+240 /0|52489 /51635|
|9965019|0|77678 /77208|77678 /77208|0 /0|77911 /77392|
|9965019|1|77678 /77208|77678 /77208|0 /0|77911 /77392|

At9965001, steps600/624 now certify the existing demand-valid proposals. Position0
saves160+90 and position1 saves150+90; these equal the respective terminal gains.
The original funded position0 diagnostic had two cash-type rejections and was
exactly action/trace/cash-identical to its control. At9965019 the callback is never
needed, and both off/on action sequences remain identical.

All three canonical arms are4W/0T/0L. Relative cash improves122.5 on average versus
the integrated off-arm, but the repaired integration is still53.5 worse on average
than frozen SELL. The incumbent is unchanged. These two development seeds, one
opponent lineage and mirrored positions do not establish a rating improvement.

Twelve canonical games completed, plus one extra original-funded diagnostic.
Two outer-harness-interrupted attempts are retained without assigned outcomes;
they are not policy errors, losses or completed games. First-seed off-arm results
were reused after the repair because that arm has no funding callback and never
executes the changed helper. No completed control was discarded or rerun to
choose a result. `RESULTS.json` records all13 complete trace hashes and counts.

The unchanged process-isolated cloud evaluator used fresh actors,1s RPC,10s
startup and120s game limits. Maximum observed candidate call was0.263553s;
maximum RPC was0.266046s, including telemetry. Hardware had4-CPU quota/4GiB,
not Kaggle-equivalent resources. No held panel, upload or selected-policy change
occurred.

## Tests and evidence

Eight portable methods pass; on the exact original source the same suite has five
assertion failures and zero execution errors. It exercises both official player
positions, whole float/integer parity, exact paired market state, underfunding,
invalid numbers, unchanged inputs and the separate product-bound behavior.
A second8-method packet checks the exact two reached observations and four full
paired market executions; it is retained in the full evidence package. These
are fixture/component checks, separate from the13 full games.

```sh
D=revenue/kaggriculture/cloud-integration-differentials/delve-evaluation
KAG_ENGINE_DIR=/path/to/existing/pinned/engine python "$D/test_cash_number.py" -v
```

The existing `cloud-eval/evaluate.py` and its existing loader are used offline.
`TITAN_FUNDING_FILE` and `TITAN_EVALUATOR_FILE` can identify exact source copies in
an isolated checkout. No new exporter, simulator or workflow is required.

The complete218-file source/evidence package is delivered in the owner's Library
as `TITAN-DELVE-funded-seed-evidence.zip`:6303320 bytes, SHA256
`aaa2d811a919b6b1c2219082753cfe476a0a0fac7567d3ad1d72c9f373a912f9`.
It retains full frame streams, telemetry, all incomplete attempts, original source
closure and licenses, both test packets, exact replay-hash readback and a
relocatable `reproduce.py`. All13 complete streams independently reconstruct the
unchanged evaluator's trace hashes, final rewards and720 frames. ZIP CRC and
all218 member digests were checked. Interrupted streams remain explicitly partial.

Preserve CEDAR's funding authorship, JUNIPER/CYPRESS's join, ALDER's demand logic,
Claude's producer and the existing projection/seller/evaluator contributors.
DELVE changes only cash representation and supplies this consumer evaluation.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
