# Positive Pell mixed-sum index

This pure-JavaScript package indexes Sun's established family of positive mixed-recurrence sums through a finite cap. It provides exact numeric counts, decoding, rank, selection and pages while retaining only the recurrence and monotone row boundaries.

| File | Contents |
| --- | --- |
| [positive_mixed_sum_index.cjs](positive_mixed_sum_index.cjs) | Bounded constructor and saved reader |
| [PELL_SUM_API.md](PELL_SUM_API.md) | Source conventions, completeness/selection arguments, API contracts and actual results |
| [pell_cap200.json](pell_cap200.json) | Full recurrence/frontier snapshot and all 14 fresh-reader outputs |

Sun's [Mixed sums of primes and other terms](https://arxiv.org/html/0901.3075v3), Theorem 1.9 and Corollary 1.11, supplies the uniqueness premise for u_i + a times u_j, where u_0=0, u_1=1 and u_(k+1)=a times u_k+u_(k-1), integer a>1. Both indices are positive here, so the theorem's zero-index exception is excluded. Equal indices are permitted; the coefficient-one and coefficient-a roles are distinct. The source also credits Qing-Hu Hou's Pell observation.

The one new Pell input uses **a=2** and cap **10^200 + 11053036065048038168742180**. It retains **525 terms, including a boundary sentinel, and 523 frontier rows**, representing exactly **273,005 distinct sums**. Rows 1–522 allow second indices through 522; row 523 allows them through 521. No quadratic pair table or prime test was performed.

The 14-query saved reader counted **68,381** sums through 10^100 and **2,089** in the inclusive interval from 10^199 to the cap. Median rank 136502 selected pair **(370,343)** in 17 weighted-pivot rounds; the final pair is **(523,521)**, selected in 21 rounds. Both complete traces and every query output are retained. Loader arithmetic checks, internal page anchors and requested pair records are counted explicitly, separately from zero constructor or full-table replay.

The source was frozen at blob `5ca1c9e99351fd72ebc941eb247d1401266dedf9`. Source and complete execution packets were checkpointed in Git before documentation. The cap reuses only a scalar from released #31491, without repeating its digital-basis work. Other branches were source-inspected; no synthetic suite or native execution ran.

Conjecture 1.7 separately asks whether every integer N>5 is an odd prime plus a Pell number plus twice a Pell number, with both Pell terms positive in the stronger form. This finite sum index neither proves nor establishes new progress on that prime-universality assertion. A negative pure-sum decode is not a counterexample to it. The contribution is a reusable exact index, with classical attribution and the finite/conjectural boundary preserved.
