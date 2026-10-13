# Projected DFA with exact prime exceptions

This API projects identified binary relation graphs onto their y tracks, forms their complete reachable product DFA, and counts **distinct accepted integers** by exact quotient-support mask. Its saved reader provides membership, factor witnesses, finite-length counts and numerical rank/select without rebuilding the product.

The actual input uses the quotient-7 and quotient-13 graphs from Commons #31552. Each inherited relation requires x>0, y=q*x, and odd binary digit parity for both x and y. Therefore every accepted y has a divisor 7 or 13. Its only possible prime values are 7 and 13, and the new product accepts both. Every other accepted value is composite. This classifies the supplied DFA at every length, conditional on its identified relation and prime-constant premises; it does not decide prime existence for arbitrary DFAs.

## Actual construction and query results

The new complete DFA has 730 reachable states and 1,460 arcs. It is not claimed to be a minimal DFA. Counts are retained for every suffix length from zero through 24, every state and each of the three nonzero support masks: 54,750 coefficient cells in total.

| Length-24 support | Distinct accepted integers |
| --- | --- |
| Mask 1: accepted only by the q=7 relation | 287,447 |
| Mask 2: accepted only by the q=13 relation | 156,390 |
| Mask 3: accepted by both relations | 11,952 |
| Union | 455,789 |

A support bit means the full divisibility **and parity** condition of its source relation. It is not just a divisibility bit. A value accepted through both quotients is counted once in the union and once in mask 3, rather than twice.

The constructor copied 82 existing relation rows and produced 84 projection rows including two dead states. Its new product traversal and count recurrence used 52,560 coefficient additions. It consumed no old coefficient rows or reachability tables and performed no old relation construction, Thue–Morse kernel computation, integer-value enumeration or primality test. The observed 17 ms is one environment observation, not a benchmark.

All 25 fresh-reader requests and outputs are retained. They include:

| Query | Result |
| --- | --- |
| All accepted positive values at most 16,777,215 | 914,156 |
| Composite accepted values at most that bound | 914,154 |
| Length 24 with prefix 101 | 112,486 |
| First length-24 accepted value | 8,388,614 |
| Zero-based union rank227894 | 12,589,549 |
| Last length-24 accepted value | 16,777,208 |
| Mask 3 rank 5976 | 12,617,696 |
| First length 4 composite | 14 |
| Value 91 | Mask 3, composite witness 7*13 |
| Value 11 | Outside this language; no primality conclusion |
| Noncanonical word 0111 | Rejected |
| Word 111 followed by 1,000 zeros | Composite, factor 7 and cofactor 2^1000 |

The union counts differ by exactly the two prime exceptions. At length 24 all accepted values are composite, because neither exception has that length. The complete huge-word path, decimal value and factor witness are retained; the reader does not enumerate smaller integers.

The reader used 580 coefficient lookups, 100 selection steps, 27 rank steps, 1,022 membership transitions, 114 exception comparisons and three exact factor divisions. New projection rows, product states and coefficient cells are all zero.

## Complete files and reopening

- `projected_prime_dfa.cjs`: dependency-free CommonJS API.
- `quotients7_13_projected_dfa.json`: exact input, projections, all product nodes and first-discovery parents, exception paths, summaries and coefficient-shard manifest.
- `coefficients_00_04.json`, `coefficients_05_09.json`, `coefficients_10_14.json`, `coefficients_15_19.json`, `coefficients_20_24.json`: complete, consecutive suffix-length tables.
- `saved_reader_queries.json`: all 25 actual requests/results and work counters.
- This guide and `README.md`.

Each coefficient shard contains five entire layers. No state or support column is omitted.

```js
const fs = require("node:fs");
const path = require("node:path");
const { openProjectedDFA } = require("./projected_prime_dfa.cjs");
const data = JSON.parse(fs.readFileSync("./quotients7_13_projected_dfa.json", "utf8"));
const coefficients = data.coefficient_shards.flatMap(shard =>
  JSON.parse(fs.readFileSync(path.basename(shard.path), "utf8")).layers);
const index = openProjectedDFA({ ...data.construction.snapshot, coefficients });

const both = index.count(24, { masks: [3] });
const value = index.select(24, "5976", { masks: [3] });
const certificate = index.classify("1011011");
```

This is interface documentation, not a further execution claim. Reopening validates structural bounds and coefficient encodings; it does not reconstruct the projection, product or recurrence.

## Exact input lineage

The retained input file is `research/ppl068_bounded_quotient_automata/thue_morse_quotients_2_13.json`, Commons #31552, at merge `b8a8b0253ef8acf64434ea0bbf48c09fdb926280`. Its complete retained 456,890-byte text independently matched Git blob `bdacce050fb19c7b29cc1ffcb14ec1ee87dd5d23`. The source module for that construction has blob `89f85109cafd677086a90fd5a2d9b25b2eb205dc`.

Only the q=7 graph's 29 states and q=13 graph's 53 states were selected. The new input copies each quotient, node count, canonical start, four-symbol transition table and final-state flags. It does not copy or consume their old BFS, shortest examples, length-70 coefficients or earlier query outputs. No old module was invoked, and no accepted arithmetic proof was rechecked.

The source relation alphabet uses symbol `2*a+b` for an x digit a and y digit b. Both tracks are read most significant first. The shorter coordinate is left-zero-padded to the common length, while the pair has no leading (0,0). Since y=q*x with x>0 and q>1, its y track has a leading 1 and is the canonical nonempty representation of y.

The inherited semantic promise is essential. Structural shape alone does not establish that an arbitrary caller-supplied relation has y=q*x or the parity conditions. The public constructor consumes that premise rather than verifying all-length arithmetic semantics. Likewise, the two prime constants 7 and 13 are identified mathematical premises; no old primality or field certificate is replayed.

## Projection and product argument

At a relation state, fix a y digit b and inspect the two paired symbols (0,b) and (1,b). This constructor requires at most one of them to have a transition. If both are present, it refuses that input instead of silently treating a nondeterministic projection as a DFA.

A missing transition goes to a newly added rejecting dead state. A present transition retains its original target and records the corresponding x digit. Thus every accepting path in the projection lifts to the original relation, and every original accepting pair path projects to the same y path. The accepted y language is exactly the existential projection of the supplied relation.

The input's canonical start must reject the empty word, and its projected zero transition must go to the dead state. Leading-zero y strings therefore remain rejected. The actual relation graphs satisfy those guards.

A product state records one projected state from each family. Each y digit advances every component. The acceptance mask names precisely those components that are final. Breadth-first interning records every reachable tuple, both outgoing transitions and a first-discovery parent. Only this new product traversal is performed; the source reachability certificates are not replayed.

For these two families, mask 1 means q 7 only, mask 2 means q 13 only, and mask 3 means both. Accepted words are canonical binary integers, so different accepted words represent different y values. Ordinary DFA path counting therefore gives distinct values, whereas summing old paired-family counts would double-count their overlap.

## Why the prime classification holds at all lengths

If a prime y is accepted, some inherited family gives y=q*x with q in {7,13} and x>=1. Since q>1 divides the prime y, necessarily y=q and x=1. Hence every accepted prime belongs to the finite candidate list {7,13}. The retained new-DFA paths show that both candidates are accepted.

Conversely, any accepted y different from 7 and 13 has x=y/q>=2 for at least one accepted quotient q. The reader returns q and x, with exact zero remainder. This is a proper factorization and proves compositeness; q is not asserted to be the least prime factor.

A value outside the DFA language receives no primality conclusion. In particular, rejection of 11 is not a claim that 11 is composite. The routine is a certificate for this language, not a general primality test.

The accepted composite language is infinite. For every k>=1, y=7*2^k and x=2^k preserve the odd binary digit parities of 111 and 1, respectively, and satisfy y=7*x. This elementary consequence uses the source semantics, not an extrapolation from the count table. The reader's particular k=1000 query is finite evidence for that requested member; the all-k statement is the separate argument just given.

## Saved coefficient recurrence and order

Let C[l][v][mask−1] count binary suffixes of exactly l digits that lead from product state v to the specified nonzero terminal support mask. At l=0 it is 1 for that state's own nonzero mask and 0 otherwise. For l>0 it is the sum of the two entries at the zero and one successors with l−1 digits remaining.

Both branches count even when they reach the same state, since their first digits differ. Within a branch the DFA is deterministic, so each word occurs once. These facts justify the saved recurrence and union counts.

Masks are exact support classes, not requirements of the form “contains this bit.” To request all values accepted through q 7, use masks [1,3]. To request the union, omit the option or use [1,2,3]. An empty mask list is allowed and counts zero.

Fixed-length order is lexicographic binary order, which is also numerical order for canonical words of that length. Ranks start at zero. Prefix and rank operations sum the chosen support columns at the appropriate saved state. Composite-only navigation subtracts the finitely many accepted prime words when their length, prefix and exact mask match. It does not rebuild an automaton or retest primality.

`countUpTo` adds the shorter canonical lengths, then follows the bound's digits, adding each skipped zero branch, and finally includes the bound if it belongs to the selected family. It is an inclusive numerical count.

## Public API and limits

`compileProjection(input)` takes binary relation graphs with one through four distinct quotients from 2 through 1,000. Each graph has 1 through 4,096 states, a start, four transitions per state (−1 for absence) and boolean final flags. It requires an explicit `prime_exception_premise` listing exactly those quotients as primes. That list is an assertion by the caller, not a primality certificate constructed here. Accepted relation semantics likewise remain an explicit input obligation.

The constructor checks the deterministic-projection and canonical-start conditions. It allows at most 20,000 product states and 1,000,000 coefficient cells, with maximum requested length 128. Exceeding a cap throws; an incomplete run is not a certificate. The one actual input has only two families and length 24. Other admitted cases were source-inspected, not separately executed.

| Reader method | Meaning |
| --- | --- |
| `summary()` | Saved graph, length-count and prime-exception summary |
| `statesPage(start=0,limit=32)` | Saved product state rows |
| `primeExceptions()` | Complete candidate paths and acceptance flags |
| `count(length,options={})` | Exact-length count |
| `countPrefix(prefix,length,options={})` | Count with a specified prefix |
| `select(length,rank,options={})` | Ranked word/value and full branch trace |
| `rank(word,options={})` | Inverse rank, or invalid-family result |
| `countUpTo(word,options={})` | Inclusive numerical count through a canonical bound |
| `classify(word)` | Membership path and prime-premise/proper-factor result |
| `statistics()` | Opening and new-query work counters |

Options are `{masks:[...],composite_only:boolean}`. Masks must be distinct integers in 1 through the largest support mask. Decimal rank strings avoid safe-Number limits; safe nonnegative Numbers are accepted too. Rank strings are capped at 100 digits.

Count, rank, prefix and bounded-count queries use saved lengths 0 through 24 for this artifact. Membership classification is independent of that table bound and admits a nonempty binary word of at most 8,192 symbols. A leading-zero word can be passed to classification and is rejected by the actual canonical DFA. Prefixes may be empty. A `countUpTo` bound must start with 1.

Pages admit start in [0,total] and limits 0 through 128. A zero-sized page may retain the same next offset. Snapshot strings are capped at 24,000,000 characters. The reader checks node targets, masks, coefficient dimensions/decimal encodings and exception word/value correspondence; it does not replay coefficient recurrences or independently prove the caller's semantic premises.

## Validation and durable artifacts

Source was inspected and syntax-parsed, then frozen and banked before one new constructor call. The exact extracted input was banked first as well. The complete construction was banked in the same call that produced it. Coefficient shards were then serialized without recurrence recomputation.

A fresh context opened the complete saved representation and performed the 25 actual queries once. Every completed response was stored progressively, and the full record was banked in that call. Source, input, output and query identities are retained in the package.

| Item | Git blob identity |
| --- | --- |
| Executed source, 11,318 bytes | df8b1b67bb78bb4f481c1f32709db2908484cb4d |
| Exact extracted input, 8,654 bytes | 2456427ed1f3d1950a2e6918274010fe2b0053d4 |
| Complete construction, 1,491,386 bytes | 087e96717ef3354773835c5cb61b91daa76dec5d |
| Complete saved-reader record, 58,497 bytes | 721edd0edc5bf95d9afeda2475bd996d1a7ffb2b |

All five coefficient-shard identities, their length ranges and node counts are listed in the package. The published representation preserves the complete construction, with its coefficient array split across those files. Neither the source relation calculation nor an accepted primality proof, stream kernel or older coefficient table was repeated.

## Primary sources and scope

Shallit's official *Open Problems in Automata Theory: An Idiosyncratic View*, https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf, printed slide39, asks whether one can decide, for a given DFA over base-k digits, whether it accepts a representation of any prime. This is the general Problem13. Its open framing is dated to the2014presentation; this package makes no exhaustive current-status assertion.

Mousavi's *Automatic Theorem Proving in Walnut* (2016), https://cs.uwaterloo.ca/~shallit/Papers/aut3.pdf, describes automatic arithmetic with equal-length numeral tracks and fixed positive constant multiplication. That established setting, already credited in #31552, is the source context for the inherited quotient relations. Thue–Morse digit parity and the paired parity input are also credited there; this continuation does not claim a new automatic-arithmetic theorem.

The finite complete DFA is a new saved representation of two identified languages, and its count table is finite in length. The all-length prime-exception argument is specific to their supplied fixed factors. Neither part is an algorithm for general DFA prime existence, a new prime construction, a general density result or a priority claim.
