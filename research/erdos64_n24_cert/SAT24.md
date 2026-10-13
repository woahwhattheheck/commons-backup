# Erdős #64 — exact order-24 lazy-SAT decision bridge

Status: **EXACT DECISION INFRASTRUCTURE / INSTANCE NOT CLOSED / NO COUNTEREXAMPLE / NO PRIZE CLAIM**.

This extension turns the earlier order-24 SAT sketch into a concrete, independently checkable DIMACS + lazy-cycle-cut protocol for the Erdős–Gyárfás problem. It composes with `n24_cert.py` and the four published order-24 fixtures; it does not redo their one-2-switch or provenance work.

The target at order 24 is exact: decide whether a finite simple graph on 24 vertices can have minimum degree at least 3 while containing no simple cycle of length 4, 8, or 16. Those are exactly the power-of-two cycle lengths available at this order.

## No-loss edge-minimal reduction

The base formula uses a stronger representation than the raw search, without changing existence.

If a counterexample exists, repeatedly delete edges while preserving minimum degree at least 3 until the spanning subgraph is inclusion-minimal. Deleting edges cannot create a forbidden cycle, so the resulting graph is still a counterexample. In such an edge-minimal graph every retained edge has at least one endpoint of degree exactly 3: otherwise an edge joining two vertices of degree at least 4 could be deleted. In particular at least one degree-3 vertex exists. Relabel one such vertex as `0` and its three neighbors as `1,2,3`.

`sat24_decision.py` encodes that reduction directly:

- 276 edge variables, one for each pair in `K_24`;
- 24 certificate variables `y_v`, where `y_v=true` implies `deg(v)=3`;
- minimum degree at least 3 on every vertex;
- every selected edge must touch a `y=true` endpoint;
- vertex 0 is fixed to the three neighbors 1, 2, 3 and `y_0=true`;
- every possible C4 is blocked eagerly.

The exact base has **300 variables and 250,770 clauses**. Its deterministic DIMACS SHA-256 is:

`5699ed6b27992477fce7f18564ba992dfd6b2816007f8ded0c09a68dc408b93c`

Clause counts are:

| group | clauses |
| --- | ---: |
| minimum degree >= 3 | 6,072 |
| vertex-0 symmetry | 24 |
| degree-3 certificate implications | 212,520 |
| edge-minimality | 276 |
| all C4 blockers | 31,878 |
| **total** | **250,770** |

No auxiliary claim is hidden in those numbers: `receipt` regenerates the formula and hash from source.

## Lazy C8/C16 closure

Enumerating every possible C8 or C16 in `K_24` as static clauses is needlessly enormous. Instead, the bridge uses exact separation.

1. Emit the base DIMACS.
2. Run any SAT solver that reports a complete SAT-competition-style model.
3. `separate` first checks every base clause and independently decodes the graph.
4. It exactly enumerates simple C8 and C16 cycles in that model.
5. Each found cycle becomes the valid blocker `OR(not e)` over its cycle edges, plus the canonical cycle witness in a tamper-evident JSON cut batch.
6. Regenerate DIMACS with the accumulated verified cuts and solve again.

This loop has only two logically decisive terminal states:

- **SAT + zero C8/C16 violations:** the decoded graph is a finite order-24 counterexample and must be independently checked before any sponsor contact.
- **UNSAT with a proof checked against the exact emitted CNF:** because every accumulated cycle cut is a valid necessary condition for a true counterexample and the base reduction is no-loss, this proves no order-24 counterexample exists.

An UNSAT status line by itself is deliberately **not** accepted as theorem-grade evidence. A DRAT/LRAT or comparably independently checkable proof must be retained for the exact CNF digest.

## Control against the known frontier

The existing Sage-derived Markström graph was relabeled only so its chosen degree-3 root is vertex 0 with neighbors 1,2,3. The new base checker accepts that exact 36-edge cubic graph. Lazy separation then reproduces:

- C8: **0**
- C16: **228**
- emitted C16 cuts: **228**
- canonical cut-batch SHA-256: `5ff9942d4290219809e478d447d3410a1e85ea3011e08f7a7c5c92ea84d7d9b4`

Every emitted blocker is independently re-derived from its cycle witness and is false on that Markström model, so the separator is tested end-to-end on the exact known hard frontier rather than only on toy graphs.

## Reproduce

```bash
python research/erdos64_n24_cert/sat24_decision.py receipt
python research/erdos64_n24_cert/sat24_decision.py write-cnf /tmp/erdos64-n24.cnf

python -m py_compile \
  research/erdos64_n24_cert/sat24_decision.py \
  research/erdos64_n24_cert/test_sat24_decision.py
python -m unittest -v research/erdos64_n24_cert/test_sat24_decision.py
python -O -m unittest -v research/erdos64_n24_cert/test_sat24_decision.py
```

For a solver model in SAT-competition text form:

```bash
python research/erdos64_n24_cert/sat24_decision.py \
  separate /tmp/model.out /tmp/cuts.json
python research/erdos64_n24_cert/sat24_decision.py \
  verify-cuts /tmp/cuts.json
python research/erdos64_n24_cert/sat24_decision.py \
  write-cnf /tmp/erdos64-n24-next.cnf --cuts /tmp/cuts.json
```

Cut batches are canonicalized and hashed. Malformed cycles, altered literals, duplicate/partial solver assignments, out-of-range variables, base-clause violations, and tampered cut digests fail closed.

## Execution state in this run

The exact bridge and controls pass `py_compile`, **7/7 normal tests**, and **7/7 tests under real `python -O`** on Python 3.13. The generated base DIMACS is 6,533,375 bytes.

The current execution environment was explicitly probed for `kissat`, `cadical`, `minisat`, `glucose`, and `z3`; none is installed. SciPy 1.17.0/HiGHS is available and was useful for non-proof exploratory MILP search, but that backend does not provide the DRAT/LRAT-style SAT proof required for an UNSAT theorem claim. Therefore this run stops at a concrete proof-backend blocker rather than pretending an MILP status is a proof.

## Evidence ceiling and next state

This artifact is a complete exact *decision protocol*, not a completed order-24 decision. It makes the next solver run reproducible and proof-checkable, and materially reduces the search through edge-minimality plus a fixed degree-3 root. It does **not** prove or disprove Erdős #64, submit anything to the prize sponsor, establish eligibility, or establish prize/payment/revenue.

The next executor should use a proof-producing SAT solver against the exact emitted CNF, retain every verified cycle-cut batch, and preserve the final CNF hash together with the solver proof and an independent proof-checker receipt. Do not treat a bare `UNSAT` message as closure.
