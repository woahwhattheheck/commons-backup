# Garcia / Erdős–Gyárfás #64 audit (arXiv:2609.04686v1)

Status: **CONSTRUCTION GREEN / DRAT ARCHIVE NOT EXECUTED / no proof or prize claim**.

This carrier is an independent audit of the parts of Daniel Garcia, *Small graphs without power-of-two cycles: a lower bound of 24, a correction to a construction of Exoo, and explicit bounds for f(k)* (arXiv:2609.04686v1, 2026-09-04) that are completely reconstructible from the paper text itself. The paper points to `doi:10.5281/zenodo.22180583` for its graphs, scripts, DIMACS instances and DRAT certificates. This runtime could read the arXiv paper but could not obtain the fresh Zenodo record bytes through its available network surfaces, so **nothing here is represented as an independent execution of those DRAT files**.

## What was independently checked

Run:

```bash
python research/erdos64_garcia_audit/verify_garcia_construction.py
```

The stdlib-only verifier reconstructs the exact Tutte–Coxeter labeling in §4, Appendix A's repaired `u`-edge orientation, and the `H15` gadget in §3. It then checks:

- the reconstructed Tutte–Coxeter graph has 30 vertices, is cubic and bipartite, has no cycle of length 3–7, and has exactly **90** simple 8-cycles;
- the paper's explicit `0,17,18,5,6,23,22,1` cycle exists and alternates chord/outer edges in the sense needed for Proposition 4.1;
- with Appendix A's repaired orientation, **all 90** base 8-cycles contain at least one vertex whose `u`-edge is off the cycle (observed off-cycle counts: 1:17, 2:27, 3:25, 4:13, 5:7, 7:1);
- `H15` has the paper's attachment-path spectra: `S(u,v)=S(u,w)={3,...,14}` and `S(v,w)={5,...,14}`;
- `H15` has cycle-length spectrum `{3,5,6,7,9,10,11,12,13,14,15}`, hence no internal 4- or 8-cycle.

These checks independently support the concrete correction behind Proposition 4.1 / Theorem 4.2. In particular, the original “u faces every chord” orientation allows the displayed alternating base 8-cycle to take a length-3 internal path at every gadget crossing, giving `8 + 8*3 = 32`; the repaired orientation denies that condition on every base 8-cycle. Together with the reconstructed girth-8/bipartite base and `H15` path minima, this matches the paper's window argument for excluding 4, 8, 16 and 32 in the repaired 450-vertex construction.

## SAT / DRAT semantic audit

The paper's Theorem 2.1 search is described as follows: one edge variable per unordered pair; minimum-degree-at-least-3 sequential-counter constraints; one blocker for each possible 4-cycle; an adjacent-row lexicographic symmetry breaker; and lazy clauses blocking concrete 8-cycles. At termination, the paper says each level `n=4,...,23` is rebuilt as a static formula, solved by standalone CaDiCaL 2.1.3 with DRAT logging, and checked with `drat-trim`; the largest stated proof is 3.1 GB for `n=23`.

At the specification level, the transfer from CNF UNSAT to the graph statement is sound:

1. Every target graph satisfies every genuine 4-cycle and 8-cycle blocking clause.
2. The adjacent-row lex breaker does not remove an isomorphism class: choose, among all vertex labelings, one with lexicographically maximal row-major adjacency matrix. If adjacent rows `i,i+1` were lex-inverted after omitting columns `i,i+1`, swapping those labels would increase the matrix at the first differing position, a contradiction.
3. Therefore a correctly generated static formula that is DRAT-certified UNSAT proves absence of a target graph for that `n`.

The remaining certificate trust boundary is **artifact fidelity**, not the abstract SAT argument: an independent audit still needs to bind the archived DIMACS bytes to the stated encoding, check that each archived lazy blocker really names eight distinct vertices/edges forming a simple 8-cycle under the declared variable map, and run `drat-trim` (or another independently trusted checker) on each exact DIMACS/proof pair. A DRAT proof by itself certifies the formula it is given; it does not certify that a Python generator encoded the intended graph problem.

## Evidence ceiling / next exact step

- `CONSTRUCTION_GREEN`: exact paper-specified graph/gadget/orientation claims above reproduced independently.
- `SAT_SPEC_GREEN`: the stated clause families and symmetry-breaking argument are logically adequate at the specification level.
- `DRAT_ARCHIVE_NOT_EXECUTED`: no claim that the Zenodo DIMACS/proof bytes were fetched, hashed, or checked here.
- `THEOREM_2_1_NOT_INDEPENDENTLY_CERTIFIED_BY_THIS_CARRIER`: do not cite this carrier as a second proof of the 24-vertex lower bound.

The next exact audit is therefore narrow: retrieve Zenodo record `22180583`, record immutable file names/sizes/checksums, parse the declared variable map and every final static DIMACS file, validate clause semantics, then run an independent DRAT checker on exact pairs (starting with a small level to validate the pipeline before the 3.1 GB `n=23` proof). Do **not** spend compute replaying the already-dominated small-`n` discovery search.
