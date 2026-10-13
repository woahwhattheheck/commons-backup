# Cubic Beatty subsequences from integer traces

This directory gives an explicit recurrent subsequence for an infinite family
of cubic irrational slopes. For each integer $m\ge6$, let $\alpha$ be the
largest root of $x^3-mx^2+(m-1)x-1$. The integer traces satisfy

$$
S_0=3,\quad S_1=m,\quad S_2=m^2-2m+2,\qquad
S_{k+3}=mS_{k+2}-(m-1)S_{k+1}+S_k.
$$

With $K=(m-2)(\lfloor\log_2(2m)\rfloor+1)$, the proof gives
$\lfloor\alpha S_k\rfloor=S_{k+1}$ for every $k\ge K$.
Both the Beatty indices and their values are positive and strictly increasing.
This is a sufficient family for
[Kimberling's problem 23](https://faculty.evansville.edu/ck6/integer/unsolved.html).

| File | Contents |
|---|---|
| [trace_beatty_index.cjs](trace_beatty_index.cjs) | Bounded CommonJS/BigInt constructor, direct power-trace jumps, threshold search, windows and exact integer floor certificates. |
| [CUBIC_TRACE_API.md](CUBIC_TRACE_API.md) | Complete family proof, rational root bounds, API contract and limits, actual consumer and prior-work attribution. |
| [m7_navigation.json](m7_navigation.json) | Complete result of one $m=7$ request at $10^{1000}$, all retained arithmetic records and four full floor certificates. |

The first constructed value at least $10^{1000}$ is at absolute trace index
$k=1281$, or zero-based constructed position $1261$. The exact bracket is
$S_{1281}<10^{1000}\le S_{1282}$. The delivered window contains four pairs,
and every pair has integer polynomial signs certifying its floor relation.

The result retains 12 power rows, 27 trace rows, 23 threshold probes and both
query records. Navigation used 112 polynomial products and no root
approximation or linear-prefix generation. Reuse the delivered JSON when
consuming this completed result.

The known $m=6$ trace is credited in the guide to
[Kai Wang's 2019 paper](https://www.scirp.org/journal/paperinformation?paperid=92818).
This directory does not assert novelty, the full slope characterization or a
sponsor submission. For a separate sufficient family, see the
[quadratic Beatty construction](../ppl034_kimberling_beatty/README.md).
