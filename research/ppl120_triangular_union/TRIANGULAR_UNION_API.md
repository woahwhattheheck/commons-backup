# Exact navigation in finite unions of shifted triangular sequences

This package counts distinct represented integers in two declared finite-offset families and navigates them in increasing numeric order. Indices are unbounded; offsets are fixed. It does not test Sun's unrestricted-prime conjecture, extend a reported verification range, or turn a missing restricted representation into a counterexample.

| Mode | Branch values | Allowed indices | Offset list, in bit order |
|---|---|---|---|
| triangular | p + k(k+1)/2 | k >= 0 | 0, 2, 3, 5, 7, 11, 13, 17, 19 |
| double_triangular | p + k(k+1) | k >= 1 | 3, 5, 7, 11, 13, 17, 19 |

The first mode includes the value zero. The second contains only odd values above 3. Offsets are an explicit input premise; the compiler performs no primality testing or sieve work. Labels identify offsets, but the union contains each integer once.

## Source convention and scope

[Sun, Mixed sums of primes and other terms](https://arxiv.org/abs/0901.3075), v3 dated January 29, 2009, printed page 1, defines triangular numbers with nonnegative indices. Its Conjecture 1.2 distinguishes a zero-or-prime summand in part (i) from a prime summand and positive index in part (ii). The [PPL120 card](https://prizeproblems.org/problems/120/) is the intake locator. SOURCE_QUALIFICATION.md records actual coverage, prior protected work, and bounded ownership checks.

The paper's historical computational ranges, known exceptional target and other recurrence examples are not recomputed. Its dated award language is not current eligibility evidence. No sponsor contact, prize submission, priority, novelty or general-resolution claim is made.

## Complete finite collision certificate

Write T_k=k(k+1)/2 and let c be the mode's factor, 1 or 2. Consider distinct offsets p<q. If

    p + c T_a = q + c T_b,

strict increase of T_k on k>=0 gives a>b. Put u=a-b and v=a+b+1. Then

    u v = 2(q-p)/c,
    a = (u+v-1)/2,
    b = (v-u-1)/2.

Both indices are integers exactly when u and v have opposite parity. They must also meet the mode's lower bound. Conversely every such factor pair gives an intersection. Positive u satisfies u<v, so the compiler checks the finite range u*u<2(q-p)/c, retains exact divisors, checks parity and both lower bounds, and saves every successful pair. Equality u=v cannot satisfy opposite parity. Each branch has no self-collision because its values strictly increase.

The saved pairs include those with no solution. Pair discoveries are grouped by represented integer and deduplicated by offset into a complete fiber. Every representation in a multiple fiber appears in at least one pair, so this grouping contains every branch present at that value. Three-way intersections are one fiber of size three, rather than three independent corrections.

| Saved quantity | triangular | double_triangular |
|---|---:|---:|
| Branches | 9 | 7 |
| Pair intersections | 62 | 21 |
| Distinct collision values | 41 | 15 |
| Total excess representations | 51 | 18 |
| Largest fiber size | 4 | 3 |
| Last collision value | 190 | 75 |

These are complete all-index collision results for the two fixed inputs. Beyond the stated last collision each represented value has a unique offset representation. This finite-palette statement makes no assertion about all prime offsets.

The one constructor visited 57 offset pairs, 157 trial factors and 119 exact divisors, retained 83 pair intersections, and inserted 125 distinct fiber representations. It scanned no target interval and enumerated no infinite branch prefix.

## Exact count, conditioning and numeric navigation

For bound X and offset p, let z=floor((X-p)/c). If X<p there are no branch terms. Otherwise the largest admissible triangular index is

    K = floor((floor(sqrt(1+8z))-1)/2).

The branch contributes max(0,K-kMin+1) values. Every integer calculation, square root and rank uses BigInt. Input integers may be BigInts, decimal strings or safe integer Numbers; noninteger and unsafe Number arguments are rejected.

For a selected offset mask S, a saved collision fiber F contributes

    max(0, |F intersect S|-1)

to the correction when its value is <=X. Thus

    distinct(S,X)
      = sum of selected branch prefix counts
        - sum of selected collision excesses at values <=X.

A fiber with no selected offset contributes zero, not minus one. A fiber with one selected offset requires no correction. The saved condition retains only fibers with at least two selected branches. Bit i selects offset i in the input list. Full masks are 511 and 127; mask 0 is the empty union.

Counts use inclusive upper bounds. Negative prefix bounds give zero. Windows are closed [L,R] with 0<=L<=R and use count(R)-count(L-1). Multiplicity profiles report positive multiplicities only; the number of missing target integers is not computed or classified.

rank returns the zero-based numeric rank of a member, or null for a nonmember. select takes a nonnegative rank and a nonempty palette. For its initial upper bound, one selected branch's term at index rank+kMin already guarantees rank+1 distinct union members at or below that bound. Binary search then finds the smallest X with count(X)>rank. This proves termination without an arbitrary fixed search ceiling. Selection order is numeric value order, not branch order.

representations checks every selected branch by an exact square discriminant and returns its offset and index. These membership operations are fresh query arithmetic and are reported separately from the saved pair construction.

## API

Load the saved certificate directly. The published demonstration reader never calls compile.

    const { createReader } = require("./triangular_union.cjs");
    const saved = require("./certificate.json");
    const reader = createReader(saved);
    const first = reader.select("triangular", "0");
    const huge = reader.count("triangular", "10000000000000000000000000000000000000000");
    const interval = reader.window("double_triangular", "1000", "2000", 65);

The snippet illustrates calls; only the requests in saved_reader.json are claimed as executed here. Optional mask defaults to the full palette.

| Method | Meaning |
|---|---|
| summary() | Copy saved mode summaries and constructor work |
| condition(mode,mask) | Selected branches and complete selected collision fibers |
| collisions(mode,mask?) | Complete selected collision list |
| count(mode,X,mask?) | Representation count, excess, distinct count through X |
| window(mode,L,R,mask?) | Distinct and representation counts on a closed interval |
| representations(mode,N,mask?) | Complete selected offset/index fiber |
| rank(mode,N,mask?) | Membership fiber plus zero-based rank, or null |
| select(mode,r,mask?) | Value and complete fiber at numeric rank r |
| profile(mode,X,mask?) | Count and positive-multiplicity histogram through X |
| work() | Current actual reader-work counters |
| caches() | Complete conditions and prefix-count cache |

Invalid mode, mask, integer, negative rank or reversed window is rejected; selecting an empty palette is rejected. Those rejection branches are stated from source and are not claimed as exercised by the successful reader run. Conditions and count caches are internal; callers should treat returned query data as read-only. compile is supplied for the declared mode shape but was invoked only once on the banked input.

## Actual saved reader

The banked reader plan and consumer produced 96 complete request/response pairs. Eleven palettes include full, empty, singleton and overlapping selections. Every nonempty palette has ranks 0, 10 and 10^24 selected and inversely ranked: all 27 pairs agree. The complete collision lists, negative-bound zero counts, last-collision multiplicity profiles, huge-bound counts and four closed windows are retained.

At X=10^40:

| Full palette | Representation count | Excess | Distinct represented values |
|---|---:|---:|---:|
| triangular | 1,272,792,206,135,785,543,920 | 51 | 1,272,792,206,135,785,543,869 |
| double_triangular | 699,999,999,999,999,999,993 | 18 | 699,999,999,999,999,999,975 |

Rank 10^24 selects 6172839506172839506173438271604938271604938303 in the first full union and 20408163265306122448980551020408163265306122477 in the second. Both inverse ranks were actually queried. These are exact restricted-union navigation results, not prime-existence verification.

The reader retains 11 condition caches and 1,526 prefix-count caches. Its fresh work is 321 saved-fiber scans, 717 saved-representation scans, 6,418 branch-count evaluations, 17,815 collision-count scans, 6,497 square-root calls with 37,796 Newton iterations, 228 representation-branch checks and 1,495 numeric-select iterations. It also reports 1,648 condition hits and 28 count hits. Constructor calls and new pair intersections are both zero.

Every request was retained before its call, and every complete response plus current caches/work immediately afterward. There was no failed reader call, reconstruction, or accepted computation replay. Rank inverses exercise the saved navigator; they are not an independent proof audit, benchmark, formal verification or exhaustive test of invalid-input branches.

## Files and recovery

certificate.json is the full 43,989-byte construction result, with exact Git blob identity 5e21448bc476ec69a0d54de489304ad997b2fae4. saved_reader.json is the full 722,021-byte response/cache/work package, blob 4bc7f2f1810973877252ea40f5e6df58bf2236b5.

The source/input/plan, complete construction, reader plan and complete reader were each banked as public native Git blobs before the next stage. public_checkpoints.json lists their acknowledged manifest locators and artifact identities. It contains no private provider envelopes or journal keys. A later full publication-spec checkpoint is named in the release receipt rather than made a self-referential package file. Native acknowledgement establishes the returned identity, not indefinite server retention.

The finite offset restriction remains essential for every count, profile, representation and absence result in this package.
