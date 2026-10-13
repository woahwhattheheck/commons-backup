# Erdős 604: finite Cartesian pinned-distance profiles

This directory provides an exact public index for all pinned-distance profiles of a finite Cartesian product of integer coordinate sets. Equal one-dimensional coefficient profiles share convolution work, while complete target references remain available for circle-point queries.

The new input is \(\{0,\ldots,16\}\times\{0,\ldots,28\}\), with **493 points**. Its unique center has **87 distinct distances including zero**; exactly the four corners attain the maximum **293**. Positive-distance counts are 86 and 292. A direct support-inclusion proof in the guide identifies every maximizing corner and minimizing central pin for any full rectangular integer grid.

The complete data retains 542 axis-pair witnesses, 1,130 target references, 24 distinct axis profiles, 135 profile-pair convolutions, 23,764 coefficient rows and all 38,610 convolution term records. The saved-reader consumer returns all 16 center-circle points and all four corner-circle points at squared radius 65, a center disk count of 213, and exact rank/select and page results without recomputing distances or convolutions.

| File | Purpose |
| --- | --- |
| [cartesian_distance_index.cjs](cartesian_distance_index.cjs) | Dependency-free compiler and saved-reader API |
| [CARTESIAN_DISTANCE_API.md](CARTESIAN_DISTANCE_API.md) | Derivation, rectangular extrema proof, public contract, sources and execution limits |
| [grid17x29_pinned_distances.json](grid17x29_pinned_distances.json) | Complete new input, saved index, witnesses, query responses and work records |

```js
const { openRetainedCartesianDistanceIndex } =
  require("./cartesian_distance_index.cjs");
const data = require("./grid17x29_pinned_distances.json");
const index = openRetainedCartesianDistanceIndex(data.construction.snapshot);

index.pinSummary([8, 14]);
index.selectDistance([8, 14], "43", { include_zero: false });
index.pagePointsAtDistance([8, 14], "65", "0", 128);
```

Pins are indices into the sorted coordinate axes. Distances are exact integer **squared** distances, and ranks are zero-based. The loader checks structure and consumes the saved mathematical premise; it does not authenticate arbitrary input or repeat the geometry.

The zero convention follows [Passant's 2021 author presentation](https://vlasiuk.com/PDseminar/pdf/passant.pdf). Because the general extremal function minimizes over all point sets, this configuration supplies \(f_{\mathrm{pin}}(493)\le293\), **not** a universal lower bound or a global optimum. The guide distinguishes this finite result from the full real-plane problem and from dated published bounds. No earlier rich-line configuration or accepted enumeration was replayed.
