# Pierce remainder forests and terminal coefficients

The dependency-free [public module](pierce_remainder_forest.cjs) compiles all positive starts below one fixed denominator $a$, with $2\le a\le65536$. It retains first-zero lengths for $b_{i+1}=a\bmod b_i$, exact terminal-divisor identities $cb+ka=d$, and an interface for lookup, trace paging, length-based rank/select, and profiles of retained start lists.

The [complete denominator-2196 dataset](pierce_2196_forest_and_unit_profile.json) contains all 2,195 start records and their length groups. The maximum length is 10, attained exactly at 1247 and 1324. A fresh retained-data consumer uses the 720 units already recorded in [Commons #31280](https://github.com/woahwhattheheck/commons/pull/31280): 38 reach terminal one and 682 reach a larger proper divisor. All 720 profile records and eight complete example traces are included.

For the accepted unit 257, the chain is $257,140,96,84,12,0$ and the saved identity is $564\cdot257-66\cdot2196=12$. Initial coprimality therefore does not force the Pierce coefficient to be an inverse. The API returns a chain inverse only when $d=1$.

The [API and derivation guide](PIERCE_REMAINDER_API.md) states the fixed-denominator convention, proves the shared recurrence and terminal-cofactor formula, explains the gcd behavior, documents exact Number arithmetic under the cap, and gives the loader's structural-only trust boundary. Opening a saved index does not certify its provenance, recompute its mathematics, or establish unit membership.

The guide credits [Erdős and Shallit's 1991 paper](https://jtnb.centre-mersenne.org/articles/10.5802/jtnb.41/) and the stronger bounds in [Chase and Pandey's 2022 preprint](https://www.math.kent.edu/~zchase/pierce.pdf). This is a finite API and dataset contribution, with no asymptotic improvement, external-record or novelty claim. The accepted unit generation, field construction, triple property and affine-orbit search were not repeated.
