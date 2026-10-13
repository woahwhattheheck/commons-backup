# Finite minimum-overlap partition index

This package exhausts all labelled balanced partitions A,B of {1,...,18} and retains every signed overlap profile. It represents all 48,620 partitions, and the smallest maximum overlap is 4, attained by 156 labelled splits. The reusable reader supplies conditional families, ranks, selected partitions, position participation, symmetries and the actual pairs at a requested shift.

The two roles A and B stay distinct. The symmetry index supplements the labelled family; it does not quotient its counts. The result is an exact finite calculation at n=9, not an asymptotic overlap bound or a claim to a new record.

## Definitions, attribution and status

Ethan Patrick White, *Erdős' minimum overlap problem*, arXiv:2201.05704v1 (14 January 2022), introduction, attributes the problem to Erdős (1955). It takes positive integer n and complementary ordinary sets A,B partitioning [2n]={1,...,2n}, with |A|=|B|=n. For signed integer k,
M_k(A,B) = #{(a,b) in A x B : a-b=k}.
Then M(n) is the minimum over balanced partitions of max_{-2n<k<2n} M_k.

Primary pages actually read:
- https://arxiv.org/abs/2201.05704
- https://arxiv.org/pdf/2201.05704, printed page 1 introduction.

These were statement/convention reads only. No table, source example, proof or quantitative bound was evaluated or checked. Signed differences distinguish ordered roles A x B; this is not a count of unordered absolute distances. Since A and B are disjoint, M_0=0. Differences outside [-(2n-1),2n-1] have no contributing pair, so maximizing over all integers is equivalent. The API may retain both complementary orientations; neither definition requires identifying them.

The full FormalConjectures/ErdosProblems/36.lean file was read at blob **4577e963519fc88a9394184e8086028bc4592670**. It separately annotates the value of the limiting quotient and improvements to named bounds as research open, and annotates existence/bound variants as solved. Those source annotations and local placeholders are not a proof audit. The board's broad "research solved" label must not collapse those distinct statements.

This work neither determines lim M(n)/n nor improves an asymptotic lower or upper bound. Its finite result is not described as a newly discovered value, an independently checked literature record, a qualifying prize result or a sponsor submission. There was no sponsor contact.

## New input and execution custody

The actual input is half_size=9, host {1,...,18}, with all balanced A subsets allowed and B their complements. It is a new finite input; no previously accepted graph, sequence, partition or correlation calculation is reused or rerun.

The exact implementation blob is **c7d9f1294c088dae46aef261beb70b8c88144b2a**. The source and exact input blob **914c3cdccd7ae2d0400f013f05be09065aedff35** were banked before production. There was one build. Its full index and all twelve row shards were banked before the separate reader ran. Each reader output was retained before the next query, and the complete output and condition files were banked before documentation. No implementation patch or build replay followed this production run.

## Exact finite construction

For a validated positive n, recursively choose n distinct positions from {1,...,2n}. At each recursive level the next position is greater than the previous one, so every n-subset occurs exactly once. Its complement supplies B uniquely. Thus the complete row family has binomial(2n,n) members.

For one row, initialize one counter for every signed difference from -(2n-1) through 2n-1. For each pair (a,b) in A x B, increment exactly its a-b counter. Every ordered-role pair contributes once; hence the sum of the profile is n^2. Its largest entry is that partition's maximum overlap. The minimum over the complete row family is M(n) by the definition above.

The actual build records:
- 48,620 complete partitions.
- 3,938,220 pair increments, equal to 81 per partition.
- 1,701,700 profile cells, equal to 35 per partition.
- 194,480 symmetry-image operations.
- 12,283 symmetry-orbit records.

These operation counts are retained counters. Individual pair-increment events are not stored as separate records. Every complete final profile is stored, and the reader can return the actual pair fiber for a selected row and shift.

The exact maximum-overlap histogram is:

| Maximum overlap | Labelled partitions |
| ---: | ---: |
| 0, 1, 2, 3 | 0 each |
| 4 | 156 |
| 5 | 15,696 |
| 6 | 26,762 |
| 7 | 5,634 |
| 8 | 366 |
| 9 | 6 |

The finite minimum is therefore 4, and all 156 minimizer row identifiers are retained in the index. The six rows with maximum 9 are not additional minimizers; the maximum column is the objective being minimized.

## Complement and reflection

Let C exchange A and B, and let R send every host label x to 2n+1-x. These commuting involutions generate a group with operations I,C,R,CR.

For C, exchange the two pair coordinates: M_k(C(A,B))=M_-k(A,B). For R, reflect each pair: its difference changes sign, so M_k(R(A,B))=M_-k(A,B). Applying both gives M_k(CR(A,B))=M_k(A,B). All four preserve the maximum overlap and balance.

Each orbit is represented by the smallest numeric A mask among its images, plus the complete distinct member row identifiers and common maximum. Some operations can have the same image; the compiler deduplicates those images. It does not assume every orbit has four members. The actual atlas has 12,283 orbits, while its labelled count remains 48,620. No graph-isomorphism or unrelated equivalence relation is used.

The reader's symmetry method computes the requested simple mask transformation and looks up its saved row. This is fresh query arithmetic, not reconstruction of the whole orbit partition. The guide's symmetry argument is mathematical justification for the stored navigation; no separate group enumeration was executed after the build.

## Storage format

A host integer j is represented by bit j-1 of A_mask. B_mask is full_mask XOR A_mask. Row order is increasing numeric A_mask; it is not the lexicographic order of increasing A lists.

Every row is:
[A_mask, signed_overlap_hex, maximum_overlap, symmetry_orbit_id].

The profile string has one lowercase hexadecimal digit per signed shift, in increasing order. The actual n=9 uses only digits 0 through 9; the generic n=10 contract also permits a for count 10. The zero-shift position is included. For n=9, string position j represents shift j-17, for j=0,...,34.

balanced9_index.json contains the input/source lineage, exact implementation and input pins, all orbit records, all minimum-row identifiers, the objective histogram, work counters and all twelve complete shard identities. Its blob is **938bd75a6e003aca66dea677466e74c659adc215**.

| Shard | Blob | UTF-8 bytes |
| --- | --- | ---: |
| partition_rows_00000_04095.json | a14e74242213ff1de841efe2028008fadbf53a2a | 214939 |
| partition_rows_04096_08191.json | 5204b783bc3d9a6beab7406e8c404d5f735442ba | 216962 |
| partition_rows_08192_12287.json | bf43fc5dcb3fb9e0a7e3ae4c9d944b85f3242d18 | 216979 |
| partition_rows_12288_16383.json | f4391a05d725d6fc13644a5db4476437b8fafd4d | 218082 |
| partition_rows_16384_20479.json | 93e662028a48a5d7db24341b5174b5463ba6eda1 | 221229 |
| partition_rows_20480_24575.json | 6dbd307c91e3f143379016d9161d207ddf5779d4 | 222695 |
| partition_rows_24576_28671.json | 9c459d1541e49f5b1302fd379c529b8a36d1f9cb | 222888 |
| partition_rows_28672_32767.json | 3ae16b96653f0203dab371dd1bd5e3bf25d904b7 | 222918 |
| partition_rows_32768_36863.json | 39880b4839438c80789d4bccad06ec8a00d02344 | 221935 |
| partition_rows_36864_40959.json | 9697d831d86f1e41ea57ff32acfc86f8d5220045 | 221075 |
| partition_rows_40960_45055.json | 15a55239b11e8fdd9ded2039374f77427b694b2a | 221077 |
| partition_rows_45056_48619.json | 450fc4328c681217da82f36fb21283cce6a5577b | 191155 |

Rows cover 0 through 48,619 without gaps. All counts at this bounded scale fit safe JavaScript integers; public family ranks and totals are nevertheless canonical decimal strings. Pair translations use BigInt and return decimal strings.

## API and bounded contract

The CommonJS module exports SCHEMA, SHARD, LIMITS, buildIndex(input), openIndex(index, shards).

Constructor limits are n in [1,10], at most 200,000 rows, and at most 4,096 rows per shard. The host length is at most twenty, so masks fit the positive bitwise-integer range. Enumeration and storage are exponential in n through binomial(2n,n); no polynomial-time general algorithm is asserted. The input is always a positive half-size; an empty n=0 convention is intentionally outside this API.

openIndex takes the parsed index field of the enclosing certificate and all parsed shards in order. It copies the data and checks schema, host length, shard spans, row ordering, profile-string shape, row/orbit identifier ranges and complete row coverage. These are structural checks. Reopening does not prove balance of every mask, recompute every profile or orbit, validate source provenance, or independently certify mathematical completeness. The caller must bind full file identities to the enclosing certificate; openIndex does not hash files.

| Reader method | Meaning |
| --- | --- |
| summary() | Saved n, family size, minimum, minimizer count, orbits and histogram |
| row(i) | A, B, mask, maximum and orbit identifier |
| profile(i) | All signed shifts and saved overlap counts |
| family(condition) | Exact number of admitted saved rows |
| select(rank, condition) | Partition at a zero-based rank |
| rank(A, condition) | Inverse rank of a supplied n-set A |
| page(start, count, condition) | Up to 64 selected partitions |
| orbit(id) | Complete saved orbit and its member partitions |
| symmetry(i, operation) | One of the four indicated image rows |
| pairs(i, k, translation) | All actual pairs for one shift, optionally translated together |
| participation(condition) | Exact A/B participation counts for every position |
| conditions() | Complete cached condition response, including all admitted rows |
| work() | Reader operation counters |

A condition has only these optional fields:
- in_A and in_B: distinct host positions required on the indicated side.
- maximum: an inclusive [low,high] interval for the saved maximum overlap.
- shifts: triples [signed_shift,low,high], imposing inclusive bounds on particular signed-profile entries.

Positions must be integers in [1,2n]. Bounds are integers in [0,n] with low<=high. Shift inputs are bounded to [-10^9,10^9]; outside the possible difference range their overlap is zero. Duplicate positions within one field or duplicate signed shifts are rejected. A position appearing in both in_A and in_B is a legitimate contradictory condition and yields an empty family. Unknown fields and malformed numeric inputs are rejected.

Normalization sorts the required positions and shift triples. At most 32 distinct normalized conditions are cached in a reader. Each new condition scans the saved rows and applies exact mask, maximum and profile tests. This is reported query work, not a new correlation calculation. The condition's complete admitted row list is ordered increasingly, so selection is an array lookup and ranking uses a binary search of those saved row identifiers. New readers do not import the saved condition files into their caches; those files are complete query evidence. Reopening the construction and asking a condition again requires another explicitly reported scan.

Rank input must be a nonnegative canonical decimal string. The first rank is zero, and a rank equal to the family count is invalid. Page start equal to the count is allowed and returns no values. A submitted A list must have exactly n distinct valid labels; its ordering does not change the represented set.

The optional common pair translation is a signed canonical decimal string with at most 2,048 magnitude digits; "-0" is rejected. If (a,b) contributes at shift k, then (a+t)-(b+t)=k for every integer t. Thus the saved profile remains valid after common translation. The API emits complete decimal pair coordinates for the requested finite query, not every translated profile or a new correlation atlas. Negative translations may produce nonpositive coordinates; this is an explicit integer translation of the finite sets, not a redefinition of the normalized [1,2n] problem.

Example saved-reader usage, not a second executed consumer:

~~~javascript
const {openIndex} = require('./overlap_partitions.cjs');
const certificate = /* parsed balanced9_index.json */;
const shards = /* parsed files in certificate.shard_files order */;
const reader = openIndex(certificate.index, shards);
const condition = {maximum:[4,4], in_A:[1], in_B:[18]};
reader.family(condition); // total "4"
const chosen = reader.select("0", condition);
reader.rank(chosen.A, condition); // rank "0"
reader.pairs(chosen.row, -3, "1000000000000000000000");
~~~

## Actual saved reader

saved_reader_queries.json, blob **3bc2c5a1a9b7a7e985e42f822283f78c759b0725**, retains 39 complete ordinary outputs and identities for the nine members of one complete conditions() response. Therefore the logical reader query counter is 40.

Three pages of sizes 64,64,28 export every one of the 156 minimizers. Comparison of those saved outputs confirms 156 distinct rows in ranks 0 through 155; that comparison uses saved responses only. The first, middle and last minimizers were separately ranked, and their retained inverse ranks are 0,78,155.

The first minimizer is:
A={4,5,6,7,9,10,11,13,14},
B={1,2,3,8,12,15,16,17,18}.
Its row is 1504, mask 14200 and orbit identifier 1410. The last minimizer exchanges these A and B sets. All four distinct members of orbit 1410 and the profiles of all three nonidentity images are retained by the reader.

At shift -11 the first minimizer has exactly the pairs
(4,15),(5,16),(6,17),(7,18).
The full coordinates of their common translate by 10^1000 are retained in the query file. At shift +11 it has only (13,2),(14,3); the reader also returns these translated by -10^21. This unequal pair count at opposite shifts makes the signed convention concrete. Zero shift and shift 10^9 return empty fibers. All six pair queries inspect only the chosen A-side positions.

The complete retained conditions are:

| ID | Additional restrictions | Count |
| --- | --- | ---: |
| 0 | None | 48,620 |
| 1 | Maximum = 4 | 156 |
| 2 | Maximum = 4, 1 in A | 78 |
| 3 | Maximum = 4, 1 in A, 18 in B | 4 |
| 4 | Maximum = 4, both shifts -1 and +1 have overlap <=2 | 4 |
| 5 | Maximum <=5 | 15,852 |
| 6 | Maximum = 4, zero-shift overlap =1 | 0 |
| 7 | Position 1 in both A and B | 0 |
| 8 | Maximum =4, 4,5,6,7,9,10,11,13 all in A | 1 |

The unique condition-8 partition is exported and ranked. For all minimizers, every one of the eighteen positions belongs to A in 78 rows and to B in 78 rows. These labelled participation counts are consistent with swapping the two roles; they do not describe quotient-orbit multiplicities.

| Complete condition file | Blob | UTF-8 bytes |
| --- | --- | ---: |
| condition_00.json | 0ba88199652f869fbcdefd93617885c1bccfe90b | 280710 |
| condition_01.json | 28b8be5ac05159850f0411e9875df94f2e2661ea | 973 |
| condition_02.json | a8836e7f12a98d3df2ed6d4d30075dddaa2c3ef2 | 566 |
| condition_03.json | 140b497890ac4d876f5ae7c6f7042709fd28421f | 123 |
| condition_04.json | 7c957f716e3ccdef7abc4c7f6cd7164c5c26ed98 | 134 |
| condition_05.json | d89f7d4cac27904713d8b0db58f644d28991eb54 | 92050 |
| condition_06.json | 190dac328104cbbd250b03c7af2fd229c030613e | 104 |
| condition_07.json | 7f326463e6386693b6857cf0e36475338269255a | 99 |
| condition_08.json | 61e8cadb75147d04a445bb6fc4dcbe25a4165227 | 119 |

The reader indexes 48,620 saved rows. Its nine conditions perform 437,580 saved-row scans and 322 named profile-entry lookups. Position participation performs 2,808 membership-bit checks; the six pair queries perform 54 candidate checks. Four symmetry/orbit lookups are recorded. The new-partition-row, new-correlation-increment and new-orbit-construction counters are all zero. These counters measure the named operations, not all language-level arithmetic, structural checks, mask transforms or output serialization.

No complete labelled family was enumerated again by the reader. Its minimizer pages are selected from the saved admitted-row index. The complete construction and all reader responses are banked; there are no missing ephemeral query results for this consumer.

## Limits of the result

The index establishes an exact classification for one finite half-size and a reusable bounded API. It does not compute the asymptotic constant, prove an improved bound, classify every n, or validate the cited formal developments. The twelve row shards are the finite exhaustive evidence; source proof and primary status assertions are kept distinct.

Complement/reflection classes are only the stated four-operation symmetry orbits. A record shared by two transformations is counted once within its orbit, but both labelled A/B orientations remain in the main family. This distinction matters for all counts, ranks and participation queries.
