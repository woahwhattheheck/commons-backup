# Finite affine-interval cells

Exact rational geometry for all positive-scale affine copies of a finite increasing pattern inside a finite union of separated closed intervals, restricted to a declared parameter rectangle.

The retained thirteen-point input has **seven feasible cells**. Its scale projection is

~~~text
[1/66752,5/33376] ∪ [1/5440,3/8344] ∪ [11/13472,25/29248].
~~~

The largest scale is **25/29248**, with translation **0** only. Complete saved data includes all 86 accepted prefix nodes, 183 attempted branches, rejected-branch evidence, seven polygons and 32 reader outputs.

- [API, proof and source scope](AFFINE_INTERVAL_API.md)
- [Compiler and saved reader](affine_interval_cells.cjs)
- [Complete input and certificate](thirteen_pattern_interval_cells.json)

~~~js
const {openAffineIntervals} = require("./affine_interval_cells.cjs");
const record = JSON.parse(savedText);
const index = openAffineIntervals(record.snapshot);
index.translationFiber("25/29248");
index.areaThrough("1/3000");
index.cell(2);
~~~

The compiler ran once. The separate saved reader performed no assignment search or compiler replay; its 14 query clips and 104 affine-image evaluations are explicitly counted. Exact rational arithmetic retains zero-measure boundary fibers.

Finite-copy existence is already classical: Feng–Lai–Xiong's [author account](https://arxiv.org/pdf/2312.01319), §1.1, credits Steinhaus. The infinite Erdős similarity problem asks a different question about every infinite pattern and all nonzero scales. This package provides finite exact parameter navigation; it does not settle that conjecture, cover parameters outside the declared rectangle, or assert mathematical novelty.

Only the literal host values from released Commons #31551 are reused, shifted by −1. No prior subset-sum, field or B3 computation is repeated. Source, exact input and complete results were banked before publication.
