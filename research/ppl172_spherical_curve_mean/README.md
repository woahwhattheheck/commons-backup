# Kimberling 10: spherical curve mean

This package constructs a simple closed eight-arc curve on the unit sphere with exact length \(4\pi\), and certifies its mean minimum spherical arclength distance under **normalized uniform surface area**. Kimberling's [section 10](https://faculty.evansville.edu/ck6/integer/unsolved.html) leaves the averaging measure implicit; the convention is declared here.

The actual curve's mean satisfies
\[
\frac{2912985\pi}{33554432}\le\mu(C_4)
\le\frac{3179225\pi}{33554432},
\]
with outward decimal enclosure **[0.272733338, 0.297660527] radians**. A separate swept-cap argument gives \(\mu(C)\ge\arctan(\pi/L)\) for every continuous rectifiable spherical path of length \(L\ge\pi\). Thus the infimum for the length-\(4\pi\) source problem is bracketed by **[atan(1/4), 3179225π/33554432]**, outward **[0.244978663, 0.297660527]**. No endpoint attainment or global minimizer is proved.

## Files

| File | Purpose |
| --- | --- |
| [spherical_curve_mean.cjs](spherical_curve_mean.cjs) | Pure CommonJS constructor and saved mean/sample/threshold index, using directed BigInt intervals. |
| [SPHERICAL_CURVE_MEAN_API.md](SPHERICAL_CURVE_MEAN_API.md) | Full curve, simplicity, length, symmetry, tube-bound, quadrature and interval derivations; API and trust boundaries. |
| [eight_arc_mean_grid256x64.json](eight_arc_mean_grid256x64.json) | Complete 16,384-sample/4,097-cosine snapshot, constructor record and all 16 fresh reader query responses. |

## Reuse the saved result

```js
const api = require("./spherical_curve_mean.cjs");
const data = require("./eight_arc_mean_grid256x64.json");
const index = api.openRetainedSphericalMean(data.snapshot);

index.meanDecimal(9);
index.infimumBracket(9);
index.thresholdCounts("1", "10");
index.pageThreshold("1", "10", "unresolved", 0, 32);
```

The module can also be loaded directly from its text in a connected JavaScript runtime, as shown in the guide. The saved reader checks complete record structure, angle-bin witnesses and mean aggregation without reconstructing trigonometric values or sample geometry.

At threshold \(\pi/10\), the retained samples have 9,523 certified `at_most`, 6,850 certified `greater` and 11 `unresolved` records. These are midpoint categories, not continuous surface-area proportions. Category count/rank/select/pages use row-major sample order.

## Construction and scope

For integer \(3\le m\le16\), vertices are
\[
v_j=(a\cos(j\pi/m),a\sin(j\pi/m),(-1)^j b),
\quad a^2=\frac1{1+\cos(\pi/m)},\quad b^2=1-a^2.
\]
Consecutive vertices are orthogonal; their minor quarter-circle arcs form a simple loop of length \(m\pi\). The sole actual constructor used \(m=4\), 256 height bands, 64 longitude bands, 4,096 angle bins and 48 fractional bits. The exact geometric quadrature error is \(\pi/256\).

The full executed source is Git blob **6044152becaa47a9763a441f3913a1e3f0551e24**. The complete data is **e4c40f0ec160b07f53f3d873ab20afc909d5a8b1**. The same frozen source served the constructor and the fresh reader. The latter made zero new series, cosine, radical, dot-product, arc-support or sample computations.

Loading retained records does not authenticate arbitrary mathematical provenance. The guide distinguishes those structural checks from the constructor's interval argument. Supported alternate parameter branches were source-inspected, not exercised as extra examples. This finite evaluation and universal lower bound do not resolve the author's minimization or arbitrary-length questions and make no novelty or external frontier claim.
