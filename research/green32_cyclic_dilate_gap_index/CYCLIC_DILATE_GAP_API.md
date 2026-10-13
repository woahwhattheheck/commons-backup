# Cyclic dilate-gap index

This package navigates gaps in every nonzero dilate of every subpalette of sixteen supplied residues modulo 257. It saves the modular images and their circular order once. A later query filters that order, forms the new maximal gaps for its selected subpalette, and counts or selects exact-length gap witnesses. It can also translate every occupied residue by an arbitrary signed integer.

The actual palette is
\[
P=\{2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,53\}\subset\mathbb Z/257\mathbb Z.
\]
It has size 16, which is \(\lfloor\sqrt{257}\rfloor\). The API admits all 65,536 subpalettes through a mask; the saved first consumer evaluates seven masks, including the full palette. It does not enumerate or classify all subpalettes in advance.

## Source and conventions

Ben Green's *100 Open Problems*, Problem 32, printed page 17, asks whether a set of size approximately \(\sqrt p\) in \(\mathbb Z/p\mathbb Z\) has a dilate with a gap of length \(100\sqrt p\):

https://people.maths.ox.ac.uk/greenbj/papers/open-problems.pdf#problem.32

The two-line author statement is abbreviated. The exact implementation convention comes from the complete FormalConjectures file read for this task:

- Repository: google-deepmind/formal-conjectures.
- Path: FormalConjectures/GreensOpenProblems/32.lean.
- Native request used the default ref: https://api.github.com/repos/google-deepmind/formal-conjectures/contents/FormalConjectures/GreensOpenProblems/32.lean .
- Observed complete content: 6,241 UTF-8 bytes.
- Independently calculated Git blob identity: b4e9c3bb27f0fc65bfc3db6dd810abc161f8e8c0.

No immutable repository commit was returned by that contents request; the content identity is not presented as a commit pin. Its definition uses a unit multiplier and a gap of length \(L\) consisting of precisely
\[
x,x+1,\ldots,x+L-1
\]
outside the set, with arithmetic modulo \(p\). This is the number of absent residues, not the distance between occupied endpoints. Zero length is vacuous. For an empty set every finite length is possible, including lengths larger than \(p\).

The read formal source annotates the main large-prime question and logarithmic regime as research open, and records solved Shakan and finite-field variants with local theorem placeholders. Those are source annotations, not proofs verified by this package. No Shakan proof, known example, Sanders result, finite-field calculation, threshold or prize claim is reproduced here.

## Identified input and reuse

The input consumes only literal retained arithmetic from the completed prime-product index:

- Commons PR: https://github.com/woahwhattheheck/commons/pull/31799
- Merge: f90eb9af42615c20640dcc7c20a57a318cfaac69
- Path: research/green62_prime_product_deletion_index/prime257_deletion_index.json
- Blob: 49d5aa89b1d7c909d3dc0316d4daf58b69b486f7

The modulus and full list of 54 primes below it are premises. The first sixteen values form this package's palette. The input also copies exactly 744 old unordered pair records having at least one endpoint in those sixteen primes. These records supply 864 dilation image cells when the multiplier is one of the retained 54 primes; different ordered uses can refer to the same unordered record.

The constructor computes only the remaining 3,232 modular image cells. It performs no sieve, primality test, old modular product, old deletion-family recurrence or earlier conjecture calculation. The stored integer products and quotients in the inherited records are provenance; this constructor only consumes their residue targets.

The input was banked before construction:
113,566 bytes, blob a705e45aeed03ae92503532dfe0d72e7a4cecef9.

## Exhaustiveness of the finite index

For this prime modulus, the units are exactly the integers \(c=1,\ldots,256\). The constructor visits every such \(c\) and every palette element exactly once, obtaining
\[
r_i=cP_i\bmod257.
\]
It saves the residue array indexed by the original palette labels and the labels sorted by residue.

For a nonempty selected subpalette, retain only its labels in that saved order. If consecutive selected occupied residues are \(u<v\), the intervening maximal empty gap starts at \(u+1\) and has length \(v-u-1\). For the final and first selected residues the corresponding length is \(v+257-u-1\). This includes a singleton: its only maximal gap has length 256. A gap of length zero between adjacent occupied residues is retained but contributes no positive-length starts.

Every positive-length empty interval lies within exactly one such maximal gap. A maximal gap with start \(s\) and length \(g\) contributes
\[
\max(0,g-L+1)
\]
starts for length \(L>0\). These starts form a cyclic interval. Adding a translation and splitting any wrapped interval at residue zero gives disjoint ordinary intervals in \([0,256]\). Sorting these intervals and accumulating their lengths gives exact count, rank and selection operations.

For \(L=0\), every start is valid regardless of the mask: 256 multipliers times 257 starts gives 65,792 witnesses. For an empty subpalette the same count holds for every finite \(L\); its maximum length is unbounded and is represented by the fields unbounded: true and maximum: null. A nonempty subpalette has no gap with \(L\ge257\). Empty-palette long intervals may revisit residues; this matches the formal cyclic quantifier.

The indexed objects are labelled pairs (multiplier, start) for a chosen mask, length and translation. Different multipliers are retained even if they produce identical occupied sets or reflected gaps. Counts are not numbers of isomorphism classes or distinct residue sets.

## Actual construction

The one construction retains:

| Item | Count |
|---|---:|
| Multipliers | 256 |
| Dilation image cells | 4,096 |
| Copied image cells | 864 |
| New multiplications | 3,232 |
| New modular remainders | 3,232 |
| Sort comparisons | 10,715 |
| Full-palette gap records | 4,096 |
| Primality tests | 0 |
| Old product recomputations | 0 |

For the full palette, the largest gap over all dilates is 205, attained only by multipliers 1 and 256. Its complete length-205 witness family is:

| Multiplier | Start | Last absent residue | Occupied left endpoint | Occupied right endpoint |
|---:|---:|---:|---:|---:|
| 1 | 54 | 1 | 53 | 2 |
| 256 | 256 | 203 | 255 | 204 |

Both gaps wrap across zero. Endpoint spacing is 206, while the reported absent length is 205. No longer gap occurs in this complete finite multiplier family.

The distribution of the largest gap for each individual multiplier is retained completely. Its smallest value is 21 and its largest is 205; the query is not claiming that every multiplier attains the global maximum.

The complete index has 698,109 UTF-8 bytes and blob identity
9aaaa4952b4dbf32eb5b723e8e6d3427c31890eb.

## API

The CommonJS source cyclic_dilate_gap_index.cjs exports:

- compile(input): construct the saved dilation orders and full-palette gaps.
- openIndex(data, caches?): open saved data, optionally with exact saved reader caches.

The caller supplies a prime modulus. Structural guards and injectivity checks are not a primality proof. The actual input's prime status is an identified premise.

Masks use bit \(i\) for palette index \(i\), with bit zero corresponding to 2. Mask strings are nonnegative decimal integers. Safe integer Numbers are also accepted. Exact signed lengths and translations accept decimal strings or safe integer Numbers; negative lengths are rejected. A translation is reduced modulo the fixed modulus. Multipliers and starts use their canonical integer residues.

Reader methods:

| Method | Result |
|---|---|
| summary() | Fixed input, full-palette summary and constructor work |
| dilation(c) | Saved image array and sorted palette-label order |
| condition(mask) | Selected size, maximum gap, maximizing multipliers and complete histogram |
| conditionRows(mask) | Complete maximal-gap rows for that mask |
| family(mask, L, shift="0") | Count and per-multiplier counts for exactly length \(L\) |
| select(mask, L, rank, shift="0") | Witness at zero-based rank |
| rank(mask, L, c, start, shift="0") | Membership and zero-based rank, or member: false |
| page(mask, L, offset=0, limit=20, shift="0") | Bounded witness page |
| membership(mask, c, start, L, shift="0") | Exact answer with an occupied-residue obstruction if invalid |
| caches() | Complete new condition and interval-family caches |
| work() | Explicit counters for the reader operations instrumented here |

Ranks order first by increasing multiplier, then increasing numeric start residue. They do not order by gap length, palette mask, original unbounded translation or a reflection quotient. The page cap is 1,000 records. Counts and ranks fit safe integers for the declared modulus cap.

Selection returns the requested length, canonical shift, last residue, wrap count, and a containing maximal-gap record where applicable. The empty and zero-length cases have no containing maximal gap. An invalid membership query returns a selected palette index, its occupied image and the first encountered offset witnessing intersection; it is a valid obstruction, not necessarily the smallest offset.

The returned arrays and cache objects are treated as immutable data by callers. Loaded cache provenance must be retained together with the data. The loader binds modulus, palette and mask width and checks basic shapes; it does not reconstruct or prove the arithmetic of supplied caches.

## Saved first reader

The fresh reader produced 50 banked query responses and 12 exact rank/select inverse matches. Every output was stored immediately. There was no failed constructor or reader invocation and no lost response in this task.

The seven selected masks were the full palette, the first eight values, both alternating-index halves, the singleton \(\{2\}\), the empty set, and the full palette with 2 removed. The full-palette condition is part of the construction. The six other complete conditions are new reader work and are all retained in the cache shards.

Selected results:

| Selection | Maximum over multipliers | Maximizing multipliers |
|---|---:|---|
| Full sixteen values | 205 | 1, 256 |
| First eight values | 239 | 1, 256 |
| Even palette indices | 211 | 1, 256 |
| Odd palette indices | 231 | 128, 129 |
| Full palette minus 2 | 231 | 128, 129 |
| Singleton \(\{2\}\) | 256 | All 256 |
| Empty set | Unbounded | All 256 |

Thus deleting 2 changes both the maximum gap and the maximizing multipliers. These are answers for this supplied palette, not worst-case-set bounds.

Selected exact-length family counts:

| Mask and length | Witness pairs |
|---|---:|
| Full palette, \(L=0\) | 65,792 |
| Full palette, \(L=1\) | 61,696 |
| Full palette, \(L=21\) | 15,122 |
| Full palette, \(L=205\) | 2 |
| Full palette, \(L=206\) | 0 |
| Even palette indices, \(L=64\) | 6,232 |
| Singleton, \(L=256\) | 256 |
| Singleton, \(L=257\) | 0 |

The reader exports every full-palette maximum witness and every first-eight maximum witness. It also queries translation
\[
-(10^{100}+123456789),
\]
whose residue is 170. The two translated length-205 starts are 224 for multiplier 1 and 169 for multiplier 256. Rank inverses and occupied-residue membership checks accompany these records.

An empty-palette query uses \(L=10^{100}+31\). It still has 65,792 (multiplier, start) witnesses, with exact last residue and wrap count computed arithmetically rather than by emitting the interval. The final zero-length query and the singleton length-257 obstruction keep the boundary conventions observable.

Instrumented reader work:

| Operation | Count |
|---|---:|
| New conditions | 6 |
| Selected-mask probes in saved orders | 20,480 |
| Saved image lookups while conditioning | 10,240 |
| New conditional gap calculations | 10,240 |
| New fixed-length families | 12 |
| Maximal-gap scans for those families | 24,832 |
| Retained ordinary interval segments | 6,277 |
| Selection row probes | 128 |
| Selection segment probes | 17 |
| Rank segment scans | 13 |
| Explicit parameter BigInt remainders | 51 |
| Selected endpoint lookups | 28 |
| Membership image lookups | 65 |
| Dilation multiplications, sorts and prime tests | 0 |

These counters name particular logical operations; they are not a count of every JavaScript addition, comparison, allocation or BigInt operation. The new conditional gaps and interval caches are not presented as cost-free reads. The reader does not rerun the constructor, recompute inherited prime products or regenerate sorted dilation orders.

## Files and reconstruction

- input257.json: complete literal input and provenance.
- cyclic_dilate_gap_index.cjs: reusable compiler and reader.
- prime257_dilate_gap_index.json: complete construction.
- saved_reader_queries.json: exact reader program, requests, all responses, inverse count and counters.
- cache_manifest.json: identities and order of the three cache shards.
- cache_00.json, cache_01.json, cache_02.json: every condition and interval-family cache.
- This guide and README.md.

Cache shards are compact JSON. Rebuild the cache object by taking the manifest's cache_format, modulus, palette and full_mask, then concatenating each shard's conditions and families arrays in manifest order. The original pretty serialization is JSON.stringify(cache, null, 2) plus a newline. It is 2,932,295 bytes with blob facc2ad991d473a29080e82c00832e75764ff4c1. The retained assembly comparison checks byte identity only; it does not replay any mathematical construction.

Example loading code, not an additional executed query:

~~~javascript
const fs = require("node:fs");
const path = require("node:path");
const { openIndex } = require("./cyclic_dilate_gap_index.cjs");
const read = name => JSON.parse(fs.readFileSync(path.join(__dirname, name), "utf8"));
const data = read("prime257_dilate_gap_index.json");
const manifest = read("cache_manifest.json");
const cache = {
  format: manifest.cache_format,
  modulus: manifest.modulus,
  palette: manifest.palette,
  full_mask: manifest.full_mask,
  conditions: [],
  families: []
};
for (const entry of manifest.shards) {
  const shard = read(entry.name);
  cache.conditions.push(...shard.conditions);
  cache.families.push(...shard.families);
}
const index = openIndex(data, cache);
const summary = index.condition("65534"); // Full palette minus 2.
~~~

The work was performed in the available JavaScript isolate, with source and input banked first, construction output banked next, and each reader response banked separately. The loader example was not run as an extra test. A guide-template parsing error occurred before any documentation store or provider action; correcting its Markdown quoting did not invoke or repeat the constructor or reader.

## Limits

This index concerns one fixed modulus and subpalettes of one supplied sixteen-element set. It does not enumerate every sixteen-element subset of \(\mathbb Z/257\mathbb Z\), classify affine orbits of sets, or establish a uniform guarantee at any larger modulus. The author's eventual large-prime question cannot be established or refuted by this one small modulus.

The ability to give exact gap witnesses is a finite API capability. It is not asserted as a new Shakan bound, a proof of the solved finite-field variant, an asymptotic result, a record, or prize eligibility. No sponsor contact or submission was made.
