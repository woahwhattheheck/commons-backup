# Cyclic two-sum bases and periodic-lift navigation

This package retains the complete ordered residue and carry profiles of all 8,192 subsets of Z/13Z. It finds 5,097 bases, 689 inclusion-minimal bases, 39 bases of minimum size five, and 156 bases minimizing the largest ordered representation count. That last optimum is four.

The same saved residue fibers support exact representation counts and rank/select in the periodic nonnegative set B=A+13*N0. This is a declared periodic construction, whose representation counts grow with the target quotient. It is not a bounded-representation counterexample to the natural-number Erdős–Turán conjecture.

## Source conventions and status

Konyagin and Lev, [The Erdős–Turán problem in infinite groups](https://math.haifa.ac.il/seva/Papers/ErTur.pdf), define a basis of order two by representation of every ambient semigroup element and count ordered summand pairs. Equal summands are allowed. Specializing to the cyclic group makes zero an ordinary target and available element; there is no requirement that a chosen basis contain zero. Their introduction credits Ruzsa's 1990 result giving uniformly bounded representation functions for bases in finite cyclic groups. Thus the finite group problem is a separate model, not an unresolved equivalent of the nonnegative-integer question. The source was used for conventions and attribution, not proof replay.

The complete [FormalConjectures 28 source](https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/28.lean) was read and is included in the data package. It concerns A⊆N with cofinite A+A and an infinite limsup of the ordered convolution sumRep. Its annotation is research open and its local proof is a placeholder. No proof or comprehensive current-status survey was performed. The decoded text has independently computed Git-blob content identity 0ad5d5fb8fee38bf3630d851a73097421364552c, 1,233 bytes. The connector did not supply an immutable repository commit or blob pin; the content identity is not presented as one.

## Objects and exact finite coverage

For modulus m, a stored subset A⊆{0,...,m−1} has no repeated elements. Its ordered profile is

    r_A(t) = #{(a,b) in A x A : a+b = t modulo m}.

Every target t, including zero, must have r_A(t)>0 for A to be a cyclic basis. Diagonal pairs a=b are included. For an unordered modular profile, use canonical representatives a≤b and identify only their permutation. If d_A(t) counts diagonal pairs with 2a=t modulo m, then the unordered count is (r_A(t)+d_A(t))/2. The generic implementation does not assume that m is odd or prime.

The carry profile is

    c_A(t) = #{(a,b) in A x A : a+b = t+m}.

Canonical residues satisfy 0≤a,b<m, so each pair has carry zero or one. Both profiles are saved for every subset. The base pair catalog has all m² ordered pairs, with their residue, carry and support mask.

Subset masks use bit a for residue a. Numerical mask order is the API's family order; it is not lexicographic order of the varying-length element lists. All labelled subsets are retained. Translations, automorphisms and affine-equivalent subsets are not identified. Zero membership is not fixed.

A basis is inclusion-minimal when deleting any one element loses coverage. This is equivalent to having no proper basis subset because basis coverage is upward closed. It is different from minimum cardinality, and different again from minimizing the maximum representation count.

## Once-only construction

The sole actual input is m=13. No field or primality property is needed. This input is not a reconstruction of the earlier Singer, Bose–Chowla or digital-basis artifacts.

For each nonempty mask choose its least set bit x, with parent A without x. Copy the parent's ordered and carry vectors, then add:

- one diagonal pair (x,x), at residue 2x mod m and its corresponding carry;
- both ordered pairs (x,b) and (b,x) for each parent element b.

These pairs are exactly the new members of A×A, so this recurrence constructs the profiles without re-enumerating the full square for every mask. Coverage, minimum and maximum ordered counts and ordered energy sum_t r_A(t)^2 are retained. For each basis, saved immediate-child coverage determines its essential elements and inclusion minimality.

Every subset has one complete row:

    [size, covered_mask, minimum_ordered, maximum_ordered,
     ordered_energy, essential_mask, periodic_conductor,
     ordered_hex, carry_hex]

The two hexadecimal strings have two lowercase digits per residue in increasing residue order. A zero vector is explicitly retained for the empty subset. No row is represented by an omitted default.

The finite census is:

| Basis size | All bases | Inclusion-minimal bases |
|---:|---:|---:|
| 0–4 | 0 | 0 |
| 5 | 39 | 39 |
| 6 | 962 | 650 |
| 7 | 1,716 | 0 |
| 8 | 1,287 | 0 |
| 9 | 715 | 0 |
| 10 | 286 | 0 |
| 11 | 78 | 0 |
| 12 | 13 | 0 |
| 13 | 1 | 0 |
| Total | 5,097 | 689 |

The complete subset universe, rather than this summary table alone, certifies that the smallest size is five and exactly 39 sets attain it. Likewise, no basis has maximum ordered multiplicity at most three, while 156 attain four. These are optima only in the declared group Z/13Z. The data also retains 361 profile signatures, including the empty set's signature.

Construction accounting: 212,992 ordered/carry cells, 169 ordered base pairs, 212,966 copied parent cells, 8,191 diagonal updates, 45,057 off-diagonal two-orientation updates and 38,597 immediate deletion checks. The observed 77 ms is one runtime observation, not a benchmark. The constructor ran once and its entire output was banked in that producing call.

## Periodic lift and exact large-target formulas

For any saved subset A, define

    B = {a+m*k : a in A, k in N0}.

This is an infinite set of nonnegative integers, with its residues uniquely identifying the base element. Write target n=t+m*K with 0≤t<m and K≥0. For an ordered base pair a+b=t+m*c, where c is zero or one, representations of n using those residues correspond to nonnegative splits

    u+v = K−c,
    x=a+m*u, y=b+m*v.

They number K−c+1 when K≥c and zero otherwise. Because c≤1 and K≥0, that count equals K+1−c in either case. Summing over the saved residue fiber gives the exact formula

    R_B(t+m*K) = (K+1)*r_A(t) − c_A(t).

This identity is the package's elementary specialization, not attributed as a newly discovered theorem in the source paper.

If A is a cyclic basis, all targets n≥m are representable because K≥1 gives a positive contribution in each residue. The only possible omissions are t<m with r_A(t)=c_A(t). The exact conductor, meaning the least h≥0 such that every integer n≥h is in B+B, is one plus the largest such missing t, or zero if none is missing. If A is not a cyclic basis, a missing residue persists indefinitely and the conductor field is null.

For an unordered integer representation require x≤y in their actual integer values. It is not sufficient to require a≤b on residues, because the quotient parts can reverse that order. There is one diagonal representation precisely when n is even and n/2 belongs to B. Therefore

    unordered_B(n) = (R_B(n) + diagonal_B(n))/2.

All residue branches remain available for unordered navigation, but a branch a,b,c restricts its first quotient u to

    0 <= u <= min(K−c, floor((m*(K−c)+b−a)/(2m))).

A negative upper endpoint gives an empty branch. These branches are disjoint, cover exactly x≤y, and include an integer diagonal only once.

Both ordered and unordered lift rank/select use increasing base-residue pair (a,b), then increasing u. This is a documented representation order, not global increasing x. The API supplies the branch and quotient split with every selected pair.

The selected saved minimax example is mask 183:

    A = {0,1,2,4,5,7}.

It is an inclusion-minimal six-element cyclic basis with ordered profile

    [1,3,3,2,3,4,4,4,3,4,1,2,2]

and carry profile

    [0,1,0,0,0,0,0,0,0,0,0,0,0].

Its periodic conductor is zero. For n=13*10^500+5, it has exactly 4*(10^500+1) ordered and 2*(10^500+1) unordered representations. Complete selected pairs, branch data and inverse ranks are saved. A separate even target 2*(13*10^400) retains the diagonal case. This periodic basis satisfies the expected growth; finite cyclic bounded counts have not been transferred unchanged to an infinite natural-number basis.

## API

The dependency-free CommonJS module exports VERSION, compileCyclicBases and openCyclicBases:

    const { compileCyclicBases, openCyclicBases } =
      require("./cyclic_two_sum_bases.cjs");

compileCyclicBases({modulus:m}) accepts safe integer m from 2 through 16 and returns {snapshot,summary}. The public bound limits the exhaustive subset universe to 65,536 and the two profile tables to 2,097,152 cells. Only m=13 was executed; other moduli and rejection branches were source-inspected rather than separately exercised. Safe integers and Uint8 values suffice for the bounded modular construction. Large lift arithmetic uses BigInt.

openCyclicBases(snapshot) consumes the complete saved snapshot. It checks schema/version, dimensions, row encoding lengths and pair IDs. It does not re-prove profiles, coverage, optimality, the conductor or source semantics. Consumers should bind the transported data to its saved identities and treat the supplied snapshot as immutable. Returned records are copied; new unordered/diagonal fields are explicitly counted query arithmetic.

| Method | Result |
|---|---|
| summary() | Complete saved census summary |
| profile(mask) | Ordered/carry profiles, derived diagonal/unordered counts and classification |
| profilesPage(offset,limit) | Consecutive subset profiles |
| familyCount(filter) | Number of matching saved subsets |
| familyPage(filter,offset,limit) | Matching masks and element lists |
| familySelect(filter,rank) | Selected matching subset and profile |
| familyRank(filter,mask) | Zero-based rank, or member:false and rank −1 |
| pairFiber(mask,residue,order) | Saved modular pair records filtered by the subset |
| deletionCertificate(mask) | Missing residue witnesses for each one-element deletion |
| liftCount(mask,target) | Exact ordered, diagonal and unordered integer counts |
| liftBranches(mask,target,order) | Complete positive quotient-split branches |
| liftSelect(mask,target,rank,order) | One integer representation with branch and quotient split |
| liftRank(mask,x,y,order) | Rank of a supplied integer representation, if admitted |
| statistics() | Explicit reader work counters |

A filter can specify basis (true by default, false or null for either status), exact size, required_mask, forbidden_mask, maximum_ordered_at_most and Boolean minimal. Contradictory required/forbidden masks are rejected. Omitted minimal leaves both possibilities. Family methods scan saved classification rows; they do not recompute those classifications or run the profile recurrence. They may describe an empty family.

Masks range from 0 through 8,191 for this input. Offsets may equal the relevant collection size. Family pages allow limits 0 through 256; profile pages allow 0 through 128. Ranks and offsets for finite families are safe integers. A nonmember familyRank returns −1; a nonmember liftRank returns null. Selection out of range is an error.

order is exactly "ordered" or "unordered". In pairFiber, unordered means canonical residues a≤b. In lift operations it means actual integers x≤y. liftRank requires callers to supply the latter order explicitly for unordered pairs.

Targets, lift ranks and supplied integers are nonnegative safe integers or canonical decimal strings of at most 1,200 digits. An output can be slightly longer than its input because of multiplication by a bounded count. No dense prefix of the infinite set is constructed. Membership for an individual summand is residue membership, with its nonnegative quotient included in the selected/ranked result.

The periodic count formulas work for every saved subset, including nonbases and the empty set. A positive result for an individual target does not make that subset a basis. No arbitrary infinite set or conjectural basis predicate is exposed.

## Complete files and restoration

The constructor source is 6714b496f7ee9ae7471841f5fe73f529572f7c38, 11,395 UTF-8 bytes. Input identity: 0a2ac69b417685e06f6e9228d2a2804538508ec9, 1,259 bytes. Complete original result: ba08e0d7ecb2d8702397a9101b341c9314aa4981, 1,802,639 bytes. Complete fresh reader: 2c99da26691f98c317171119b41c544a20d75c0e, 249,464 bytes.

The published cyclic13_basis_certificate.json package has blob 6afc16fc931db53705633bf5c48cd51584722a2d, 210,617 bytes. It preserves the complete source input, formal text, ordered-pair catalog, residue fibers, every basis/minimal/optimum ID, profile signatures, summary and statistics. Only the exhaustive row array is moved into four complete compact shards; no profile is recomputed by packaging.

| Shard | Inclusive mask range | Blob |
|---|---|---|
| subsets_0000_2047.json | 0–2,047 | dd8029ddfa6ac12ab7debd4ee770b422d8dc240b |
| subsets_2048_4095.json | 2,048–4,095 | 0dd516c5fcf9940a35e30c3fd5f028f93f1a58f6 |
| subsets_4096_6143.json | 4,096–6,143 | d5d79a3383a2b5e85342ca7f3707453a65760857 |
| subsets_6144_8191.json | 6,144–8,191 | ef8c953ea1728559afefec3666895b6086eabbd0 |

Restore by concatenating records in manifest order:

    const packet = require("./cyclic13_basis_certificate.json");
    const snapshot = structuredClone(packet.construction.result.snapshot);
    const rows = [];
    for (const spec of snapshot.row_shards) {
      const shard = require("./" + spec.path);
      if (shard.start !== rows.length ||
          shard.end_exclusive - shard.start !== shard.rows.length) {
        throw new Error("subset shard gap");
      }
      rows.push(...shard.rows);
    }
    snapshot.rows = rows;
    delete snapshot.row_shards;
    const reader = openCyclicBases(snapshot);

The example checks assembly ranges; it does not authenticate external transport or revalidate the mathematical table. The manifest provides the expected identities.

## Fresh saved queries

A fresh context parsed the complete banked construction and recorded every query result before advancing to the next. All 31 outputs were then banked in the same producing call. There was no failed reader or missing response.

The outputs include all 39 minimum-cardinality bases, all 689 inclusion-minimal bases in three pages, all 156 multiplicity minimizers, an empty at-most-three family, and the 175 size-six minimal bases containing residue zero while excluding residue twelve. Eight of the latter were requested as a page; the count is complete while that page is intentionally partial.

The selected mask 183 has complete modular pair fibers and deletion witnesses. Empty/full subset profiles make those boundary objects explicit. Three small integer targets record zero and the carry transition. Huge-target ordered and unordered branches, first/middle/last selections and inverse ranks are retained in full, together with a genuine integer diagonal query.

Reader work: 81,920 saved rows scanned, 88 profile cells decoded, 234 saved pair rows examined, 37 positive lift branches formed, 19 derived diagonal terms and 39 derived unordered cells. Ordered/carry profile recurrences and subset classification recomputation are all zero. Scans, hexadecimal decoding, branch arithmetic and huge integer outputs are new query work, not described as free.

Publication uses the documented serial Contents route: actual path preimages, serial commit lineage, full content, aggregate changed paths, current-base preimages and expected PR head are checked. No independent Git-mode or whole-repository-tree verification is claimed. All native publication requests/responses are retained before parsing. No failed tree route from another task is retried.

The finite census and periodic-lift navigation neither prove the general natural-number conjecture nor provide an infinite bounded-representation counterexample, a new finite-group existence theorem, or an external extremal record.
