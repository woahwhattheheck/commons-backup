# Binary AP-coloring decision diagram

Complete exact family of labelled binary colorings of [1,17] that avoid monochromatic four-term arithmetic progressions.

The saved index represents **1,850 colorings** through **2,331 residual states** and **16,748 coefficient cells**. Counts at weights 6 through 11 are 8, 180, 737, 737, 180 and 8. Fixing positions 1=0, 9=1, 17=0 and requiring eight ones leaves **132 completions**.

- [API, finite correctness argument and source scope](AP_COLORING_API.md)
- [Compiler and saved reader](ap_coloring_dag.cjs)
- [Core certificate and all 25 reader outputs](interval17_four_ap_colorings.json)
- [Nodes 0–1199](nodes_0000_1199.json)
- [Nodes 1200–2330](nodes_1200_2330.json)

Assemble the contiguous node shards according to the core manifest, then open the saved snapshot:

~~~js
const {openAPColorings} = require("./ap_coloring_dag.cjs");
const index = openAPColorings({...core.snapshot, nodes});
index.countFixed([[1,0],[9,1],[17,0]], 8);
index.selectFixed([[1,0],[9,1],[17,0]], 8, "66");
index.countPrefix("0000");
~~~

The constructor ran once and the complete result was banked immediately. Fresh queries created 1,079 conditioning memo states on the saved diagram, explicitly reported as query work. They generated no new AP constraints, residual states, subsumption comparisons or base coefficients.

This is finite completion and navigation, not a new van der Waerden threshold or asymptotic bound. The guide distinguishes the main root-limit and ratio questions from separately solved difference and normalized variants in the current formal source. The two colors and all positions remain labelled. No root three-term progression-free subset computation, known threshold coloring or external proof was replayed.
