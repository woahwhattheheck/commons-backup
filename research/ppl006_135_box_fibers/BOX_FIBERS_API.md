# Finite 1–3–5 box fibers

This package gives complete representation counts and tuple navigation for the declared box
`0 <= x,y,z,w <= 31`, with `x+3*y+5*z=t*t` for a nonnegative integer `t`.
The target is `n=x*x+y*y+z*z+w*w`. Coordinates keep their names and order.
The result represents **48,352 labelled quadruples**, organized by **1,511 triple skeletons** and **13,478 joint (n,t) fibers**. There are **2,885 distinct target values** in this finite image.

These are complete fixed-box counts. They do not verify or extend an interval of unrestricted existence, prove Sun's conjecture, or establish a new record. A target absent from this box can have representations outside it. In particular, the saved empty n=2000 condition is a box result, not a counterexample.

## Source and conventions

Zhi-Wei Sun, *Refining Lagrange's four-square theorem*, https://arxiv.org/abs/1604.06723 , v14 revised 16 January 2017, Journal of Number Theory 175 (2017), 167–190, supplies the conjectural statement in its author abstract. It defines the natural numbers to include zero and asks for nonnegative x,y,z,w with the stated position-sensitive linear combination a square. The PPL006 card https://prizeproblems.org/problems/006/ binds this intake. The abstract and card are dated source statements; current award eligibility and the current proof frontier were not assessed.

The author abstract was read for definitions only. No computational report, published example, table, verification range or proof was imported or repeated. Protected A308734 and PPL021 four-square work remains separate. Exact Sun Cover.pdf and Prime-AP.pdf failures were not retried. See SOURCE_QUALIFICATION.md for the bounded current-carrier checks.

Writing the square as t² with t nonnegative makes t unique. There is no imposed coordinate order, distinctness condition or permutation quotient. Each genuinely different ordered tuple is counted if it satisfies the fixed coefficients. Swapping equal values creates no additional tuple.

## Exhaustion and uniqueness

For any tuple in the box,
`0 <= x+3*y+5*z <= 9*31 = 279`.
Thus its unique nonnegative t belongs to the finite loop `t*t <= 279`.
The constructor chooses y,z in the box, chooses each such t, and recovers
`x=t*t-3*y-5*z`. It keeps exactly the recovered x in the box.

Every admissible (x,y,z) appears, and none appears twice: y,z and the unique t determine x. Each saved triple then combines with every w in 0..31. This independent w range is exact because w has coefficient zero in the linear constraint. No explicit quadruple table is needed.

The skeleton row is `[x,y,z,t,s]`, where `s=x*x+y*y+z*z`.
Rows are sorted lexicographically by x,y,z, and their array positions are stable triple IDs. The complete tuple order is x,y,z,w, so its zero-based unconditioned rank is
`tripleId*32+w`.
Within a filter, the original tuple order is preserved. This order is not increasing n or t.

For every skeleton and w, the constructor increments the joint coefficient at
`(s+w*w,t)` and the corresponding n and t marginals. Coefficients count tuples, while the number of occupied n keys counts distinct targets. These quantities must not be conflated.

## Saved certificate

`certificate.json` is the complete constructor output, 204,591 UTF-8 bytes, Git blob
`69f2b1ed81d85ca2f095f84131020e0e735d79a9`.

| Field | Meaning |
| --- | --- |
| input | Fixed box and named-coordinate contract |
| squares | Saved values w² for w=0..31 |
| triples | All 1,511 lex-sorted [x,y,z,t,s] rows |
| joint | All 13,478 occupied [n,t,count] cells sorted by n then t |
| nProfile | All 2,885 occupied [n,count] cells, numeric n order |
| tProfile | All occupied [t,count] cells, numeric t order |
| summary | Family size, distinct image size and extrema |
| constructionWork | Counters from the one construction |

The smallest represented target is 0 and the largest is 3551. Every square root from 0 through 16 appears. These are extrema and support statements for this box.

The one constructor recorded 17,408 candidate (y,z,t) triples, 1,511 accepted triples and 48,352 joint-coefficient increments. Its squareProducts counter is 49 retained square values across the coordinate and root tables; it is not a count of every JavaScript multiplication or loop-bound expression. The explicitQuadrupleRows counter is zero. The counters describe this execution, not a complexity benchmark.

## Reader API

Load the unchanged CommonJS source and parsed certificate:

```javascript
const fs = require("node:fs");
const {createReader} = require("./box_fibers.cjs");
const saved = JSON.parse(fs.readFileSync("./certificate.json", "utf8"));
const r = createReader(saved);
const filter = {n:[100,400], t:[4,8]};
const condition = r.condition(filter);
const first = r.select(filter, 0);
const inverse = r.rank(filter, first.tuple);
```

No constructor call is needed for saved navigation. The code example is usage guidance; it is not an additional executed example.

Filters are objects containing any of x,y,z,w,n,t, each an inclusive two-element safe-integer range. Omitted fields use the physical box limits. Bounds are intersected with those limits. Reversed or disjoint bounds give an empty family. Unknown fields and malformed or nonintegral bounds are rejected.

For each saved triple that satisfies x,y,z,t bounds, let s be its saved square sum. The target restriction is
`nLo-s <= w*w <= nHi-s`.
Because the saved nonnegative square table is strictly increasing, two binary searches recover exactly one w interval. Intersect it with the w filter. Every nonempty block stores
`[tripleId,wLo,wHi,prefixCount]`.
The sum of interval lengths is the exact filtered count; no square test or triple candidate generation is repeated.

| Method | Result |
| --- | --- |
| summary() | Saved construction summary and counters |
| profiles() | Complete saved joint, n and t profiles |
| condition(filter) | Normalized key, count, block count, n extrema and t marginal |
| blocks(filter) | Complete cached blocks and condition metadata |
| count(filter) | Exact filtered tuple count |
| select(filter,rank) | Zero-based tuple-lex selection, n,t,triple ID and unconditioned globalRank |
| rank(filter,tuple) | Inverse filtered rank for an included ordered tuple |
| page(filter,start,limit) | At most 1,000 selected tuples; start may equal the count |
| fiber(n,t) | Saved global joint coefficient, zero for an absent key |
| image(filter) | Distinct numeric target image and tuple multiplicity at each target |
| work(), caches() | Actual new reader counters and complete memo state |

Rank/select use weighted prefix counts on ordered blocks. Selection finds the block containing rank, then computes w by its offset. Ranking finds the tuple's triple ID, confirms w lies in its surviving interval, and adds its interval offset to the prefix count. Both refer to the same partition into disjoint consecutive tuple blocks, so they are inverses. Invalid ranks, absent triples and excluded tuples are rejected.

The conditional image method deliberately performs new query work: it visits the surviving skeleton/w pairs and collects target multiplicities. It does not assert that taking independent marginals recovers joint fibers. Repeated identical image queries reuse the complete cached image. The saved global profiles are obtained directly without rebuilding them.

The reader checks the schema tag and its query contracts; it trusts the identified certificate. It is not an adversarial certificate verifier. Lookup-table reconstruction from saved rows is reported separately from mathematical construction. All values under the implemented construction cap 63 are exact safe integers. This package's actual input remains cap 31.

## Actual reader use

The banked reader plan selected fourteen explicit filters before execution. Each condition, count and complete block list was retained. For every nonempty condition, distinct first, middle and last ranks were selected and inverted; their global fibers and final five tuple rows were also read. Three conditional images were built, and one was requested again from cache.

| Condition | Tuple count |
| --- | ---: |
| Full box | 48,352 |
| x=0 | 1,600 |
| z=0 | 2,496 |
| w=0 | 1,511 |
| All coordinates positive | 41,230 |
| n=500 | 17 |
| n=1000 | 16 |
| n=2000 | 0 |
| 100<=n<=400 and 4<=t<=8 | 2,628 |
| t=16 | 800 |
| 8<=y<=15,16<=z<=23,3<=w<=9 | 588 |
| Reversed x range [20,10] | 0 |
| n range [4000,5000] outside the physical domain | 0 |
| x range [-10,0], w range [-5,5] after clipping | 300 |

The w=0 image has 877 distinct targets from 1,511 tuples. The n/t rectangle image has 299 distinct targets from 2,628 tuples. The empty reversed-range image is empty.

All **163 responses** are in `saved_reader.json`, including **33 matching inverse ranks**, fourteen complete conditions and every current cache. There was no failed reader call or lost response. This file is 411,175 UTF-8 bytes, Git blob
`cf7e403b30fad0e29dc493b3bed8798b6f7e13a3`.

The reader recorded 14,989 lookup rows, 14 condition builds, 178 condition hits, 18,132 triple checks, 116,986 saved square lookups, 606 selection-block reads, 229 ranking-block reads, 121 tuple materializations, 38 global fiber reads, 16,380 saved profile cells read, three image builds, one image hit and 4,139 conditional-image tuple visits. New triple candidates and new base coefficients were both zero. These are query-work counts, not zero-work or performance claims.

## Custody and publication

The source, exact input, construction plan and qualification were acknowledged as native Git blobs before construction. The complete certificate was acknowledged before the saved reader. The reader plan was acknowledged before its first use, and each request/response plus the latest caches and work was retained immediately. The complete reader was acknowledged before documentation and publication.

`public_checkpoints.json` gives the public recovery manifests and exact acknowledged artifact identities. These are native acknowledgements, not merely locally computed hashes and not a promise of indefinite Git retention. It contains no private provider or Slack raw records. The frozen full publication spec is separately checkpointed before its guarded writer; that locator is retained in the release receipt to avoid circularly embedding the spec's own identity in itself.

The publication uses the already-read guarded publisher with exact expected file pins and complete immutable content checks. A named-main alias is allowed only after an independent equality observation binds main to that verified merge; otherwise complete observed-main content reads are required. No earlier calculation, proof, source example or accepted range was rerun for publication.
