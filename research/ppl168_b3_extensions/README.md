# Finite B3 append extensions

Exact append classification and saved count/rank/select for a supplied nonempty B3 set. Repeated summands are allowed; equal sums identify multisets. The existing B3 property is an explicit input premise.

Files:

- [b3_append_index.cjs](b3_append_index.cjs): dependency-free CommonJS constructor and saved reader.
- [B3_APPEND_API.md](B3_APPEND_API.md): complete derivation, API, source lineage, limits and finite scope.
- [thirteen_seed_extensions.json](thirteen_seed_extensions.json): complete actual constructor snapshot and 22 fresh-reader outputs.

The actual thirteen-element seed comes from the released #31427 Bose–Chowla affine lift:
[1,13,32,66,169,174,396,416,756,858,915,1016,1044].
The accepted construction's field, cycle, orbit and decoder work is not repeated.

New production work forms its previously unenumerated 91 pairs and 455 triples, then classifies 47,320 candidate differences. The index retains all 1833 forbidden append values with explicit collision references and multiplicities. Every integer 1045 through 2196 is forbidden; the first admissible append is 2197. There are 253 admissible values through 3130, followed by the entire tail from 3131.

Each admissible value is a separate one-element extension of the same seed. The index does not certify simultaneous insertion of several listed values. It also does not authenticate a claimed seed's B3 property or arbitrary imported snapshot mathematics.

~~~js
const { openAppendIndex } = require("./b3_append_index.cjs");
const api = openAppendIndex(savedRecord.snapshot);
api.appendCertificate("2197");
api.forbiddenPage(0, 3);
api.page("0", 64);
~~~

The saved reader exported all 253 finite admissible values and selected rank 10^100 as 10^100+2878, with zero sum-row construction or candidate replay. The complete dataset retains every query and the source identities.

[Nathanson–O'Bryant (JIS 2024)](https://cs.uwaterloo.ca/journals/JIS/VOL27/OBryant2/obryant4.html) supplies the established repeated-summand/greedy convention. This seeded first append is distinct from the canonical sequence beginning with zero. [Erdős 41](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/41.lean) asks an infinite density-liminf question; the present result makes no claim to resolve it, improve an extremal record or establish mathematical novelty.
