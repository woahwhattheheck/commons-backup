# Althöfer odd orbits and finite affine seed navigation

A bounded exact index for the accelerated positive-odd map

$$
T_X(n)=\frac{Xn+1}{2^{v_2(Xn+1)}},
\qquad X\ge5\text{ odd}.
$$

The delivered `X=9, n0=1` input reached 256 accelerated transitions. It retains 257 odd states, 511 dyadic affine blocks, both nonoverlapping advance receipts, and 15 later saved-reader operations. The reader's arbitrary range `[37,213)` represents 176 accelerated transitions and exactly the positive seed class

$$
x\equiv24792588637277\pmod{2^{334}}.
$$

It counted this class in `[10^500,10^520]`, selected and ranked a 501-digit seed, evaluated its 568-digit block output, and retained the complete arithmetic progression of interval outputs. Every new query operation is recorded; the reader did not replay the original orbit or rebuild old blocks.

## Files

| File | Purpose |
|---|---|
| [odd_orbit_affine.cjs](odd_orbit_affine.cjs) | Dependency-free CommonJS implementation with exact BigInt arithmetic, bounded append/resume, dyadic ranges, finite interval count/rank/select, affine jumps, and saved primitive navigation. |
| [ODD_ORBIT_AFFINE_API.md](ODD_ORBIT_AFFINE_API.md) | API, exact-cylinder derivation, indexing conventions, complete actual operation counts, bounds, copying costs, source scope, and continuation instructions. |
| [nine_start1_orbit.json](nine_start1_orbit.json) | Complete saved data, earlier checkpoints, every reader argument/result/work record, timings, and literal prefix-custody receipts. |

The executed implementation is Git blob `249b9c136081cc3f502c8c327a5193a7d98c2a3d`. It was frozen before the first constructor and used unchanged for the first 64 steps, the next 192 steps, and the saved reader.

## Actual finite result

| Quantity | Retained result |
|---|---:|
| Accelerated transitions | 256 |
| Odd states, including the initial state | 257 |
| Removed factors of two | 474 |
| Auxiliary primitive operations | 730 |
| Leaves / internal blocks | 256 / 255 |
| Current forest | Block 510, covering `[0,256)` |
| Current odd value bit length | 338 |
| First repeat | None in this prefix |
| Status | Extendable |
| Saved reader calls | 15 |
| New reader orbit transitions | 0 |
| New arbitrary-range compositions | 8 |
| Cached ranges | 2 |

The final odd value is also the maximum odd state retained in this prefix:

~~~text
457512727887953307748379078888167389922580135219353042452975606847787136791054573947744422186981727063
~~~

A large endpoint, a maximum, and completion of a finite requested prefix do not establish divergence.

## Consume the saved index

~~~js
const fs = require("node:fs");
const { openOddOrbit } = require("./odd_orbit_affine.cjs");
const record = JSON.parse(fs.readFileSync("./nine_start1_orbit.json", "utf8"));

const reader = openOddOrbit(record.saved, {
  source_id: "my-distinct-consumer-session"
});
const state = reader.getState({ odd_index: 256 });
const range = reader.rangeCertificate({ from: 37, to: 213 });
~~~

`record.saved` contains the final prefix and cached ranges. Use a fresh session source ID. For genuinely new suffix work, open that final snapshot and call `advance` within its remaining bounds. The 64-step checkpoint is retained for custody; its already completed suffix need not be regenerated.

Saved opening performs bounded structural, decimal, index, and reference checks. It does not recalculate the accepted trajectory, valuations, affine products, or residues and does not independently authenticate mathematical certificates. The guide states the exact trust boundary and unexercised branches.

## Scope and source

[Ingo Althöfer's author page](https://althofer.de/collatz-prizes.html), read on 2026-10-04 with displayed update 2026-09-21, defines removal of every factor of two. Prize 2 uses nine and one; Prize 1 permits an odd multiplier at least five and an odd start. Positive odd inputs, finite budgets, saved-state protocol, and auxiliary primitive indices are explicit module conventions.

The implementation does not stop merely because an odd state is one. It treats the author's accelerated count separately from its auxiliary primitive count.

This contribution proves the finite-cylinder formula stated in the guide and supplies the exact bounded records. It does not resolve either divergence question, classify all cycles, establish an optimum, claim literature priority, or assert prize eligibility. No author contact or submission occurred.

Operation: `ALTHOFER-ODD-ORBIT-AFFINE-INDEX-20261004-7CA6`.
