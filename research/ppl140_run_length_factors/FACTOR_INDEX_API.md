# Published run-length prefixes: exact finite factor comparison

This package compares the factors of two supplied finite binary words. It uses one generalized suffix array and longest-common-prefix table, then retains compact intervals representing every distinct target factor. The saved reader counts, ranks and selects factors, partitions them by occurrence in the source, and returns occurrence pages and earliest positions.

The actual inputs are literal published data:

- source S: A025142, indices 1 through 1004;
- target T: the complete currently retrieved A025143 synthesized b-file, indices 1 through 111.

The target has 5,124 distinct nonempty factors. Exactly 2,787 occur in S and 2,337 are absent from S. Every factor of this target of length at most 26 occurs in this source prefix. The shortest absent length is 27, with exactly two words. These finite absences are not counterexamples to infinite containment.

## Author's question and source custody

Clark Kimberling's section 11 defines the run-length operator r on sequences over {1,2}. It asks about the unique nontrivial sequence s starting with 1 for which r(r(s))=s: does every finite contiguous segment of t=r(s) occur in s?

The author page is:
https://faculty.evansville.edu/ck6/integer/unsolved.html#11

Its subsequent illustration describes an s-prefix occurring in t, reversing the direction of the stated question. This package follows the actual question, t into s; it does not reinterpret the example as a new direction. The cited origin is Kimberling, Problem 90, “Run-length sequences,” Mathematische Semesterberichte 44 (1997), 94–95. That original journal item was not independently retrieved here.

The author-maintained sequence entries are:
https://oeis.org/A025142
https://oeis.org/A025143

A025142 explicitly distinguishes the nontrivial two-cycle r²(s)=s≠r(s) from a fixed point of r. A025143 is its companion t, starts with 2, and satisfies r(t)=s in the sequence definition. Both mathematical indices begin at 1. The second component of an OEIS OFFSET field does not shift that starting index.

The data locators are:
https://oeis.org/A025142/b025142.txt
https://oeis.org/A025143/b025143.txt

The first source advertises 10,000 rows, but the retained response supplies only the contiguous initial rows 1–1004 plus a separate tail excerpt. Only those 1,004 complete initial rows are consumed. The unavailable remainder is not reconstructed or silently treated as present. Its initial source rows are credited to Jean-Christophe Hervé's linked b-file. The second source explicitly says its b-file is synthesized from the sequence entry and contains 111 complete indexed rows.

The exact symbol strings, bounds, URLs and these custody limits are embedded in published_input. This is a transfer of source data, not sequence generation, proof of either recurrence, or certification of the infinite identities. No source establishes an automatic terminal-run convention for a truncated prefix. In particular, its final run might continue beyond the retained endpoint, so this package never computes a finite run-length encoding and labels it an infinite run-length prefix.

The source question and its finite-data interpretation remain separate. No sponsor contact, submission, prize claim or current exhaustive status survey is made.

## Complete result for these prefixes

All positions in this table are one-based source indices. API offsets and suffix-array positions are zero-based.

| Fact | Exact result |
|---|---|
| Source length | 1004 |
| Target length | 111 |
| Target factor lengths included | 1 through 111; empty word excluded |
| All distinct target factors | 5124 |
| Present in source prefix | 2787 |
| Absent from source prefix | 2337 |
| Shortest absent length | 27 |
| Distinct target factors of length 27 | 85 |
| Present / absent at length 27 | 83 / 2 |
| Longest shared factor length | 66 |
| Number of shared factors of length 66 | 1 |

The two shortest absent words are:

| Word | Target position |
|---|---:|
| 112212211212212112112212211 | 82 |
| 121121122122121121221121121 | 30 |

Each occurs once in the retained target and zero times in the retained source. Their maximal source matches have length 26. “Absent” always means absent from the supplied 1,004-symbol word, not absent from the infinite A025142 sequence or the unretained remainder of its b-file.

The unique length-66 shared factor is

    211211221221211212211211212212211212212112112212212112212211212212

It occurs once in each retained word: at target index 31 and source index 325. This establishes an explicit finite occurrence witness, not an infinite recurrence theorem.

The source query for the single symbol 1 returns 503 occurrences, first at index 1. Its eight returned page offsets are [1003,1000,612,117,585,676,409,289]. They are intentionally in lexicographic suffix order, not increasing numerical position. The separate first_index field gives the earliest numerical occurrence.

## Generalized suffix index

For nonempty words S,T over {1,2}, form

    C = S + "0" + T.

The separator is outside the input alphabet and orders below both input symbols. A suffix of S terminates, for comparison purposes, before that separator. Consequently restricting the sorted suffixes of C to starts in S gives the ordinary lexicographic suffix order of S. Restricting to starts in T gives the ordinary suffix order of T. The separator's own suffix is excluded from both lists.

The constructor sorts suffixes by doubling the compared prefix width. Initially a suffix's rank is its first character. At width w, the ordered pair of ranks at starts i and i+w gives the rank for a prefix of length 2w; a missing second half has rank -1. Induction therefore gives exact prefix ranks. When all ranks are distinct, or the compared width covers the text, this is the complete suffix order. This doubles comparison widths, not either source sequence.

The longest-common-prefix array L has L[0]=0 and L[r] equal to the common prefix length of adjacent sorted suffixes r-1 and r. The constructor uses the usual carried-prefix scan: when a suffix start advances by one, an already known common prefix can decrease by at most one before new comparisons. The saved array includes every adjacent pair of generalized suffixes.

For suffix-array positions a<b, their common prefix length is

    min L[a+1], …, L[b].

All suffixes between two strings sharing a prefix also share that prefix. Conversely, the first adjacent boundary losing a character prevents the endpoint strings from sharing it. This proves the interval-minimum identity.

For a target suffix, its maximum common prefix with any source suffix is attained at one of the nearest source suffixes on its left or right in the generalized order. A farther source suffix's LCP interval contains the nearer one's interval and cannot have a larger minimum. Two linear sweeps therefore compute the maximum source-match length and retain an actual source start attaining it.

These matches cannot cross the source endpoint: the separator 0 cannot equal a target symbol. They cannot cross the target endpoint either. No infinite continuation is assumed.

## One interval per target suffix

Let the target suffixes be in lexicographic order. For one suffix starting at j, let b be its LCP with the preceding target suffix, or zero for the first. Its new distinct factors are precisely its prefixes of lengths

    b+1 through |T|-j.

Prefixes of length at most b already occurred earlier. Any prefix longer than b is new: if it occurred in any earlier suffix, the interval-minimum identity would force it to occur in the immediately preceding suffix too. Thus every nonempty distinct target factor appears exactly once in these intervals.

Let m be this suffix's maximum match with the source, and let H=min(max_length,|T|-j). The canonical row's intervals are:

- all: [b+1,H];
- present: [b+1,min(H,m)];
- absent: [max(b+1,m+1),H].

An interval with its lower endpoint above its upper endpoint is empty. These formulas partition every canonical factor by exact finite source membership.

Concatenating the rows in suffix order, and increasing the length within each row, gives lexicographic order on the distinct factors, with a proper prefix before a longer word. This order underlies all global ranks; rank is not order by word length.

Prefix sums of interval sizes give total counts and weighted row selection. For rank r, binary search finds its row, and the offset inside that row determines the factor length. Conversely, the first target suffix beginning with a queried factor is its canonical row; the length determines its offset there.

To count at every length, the constructor adds one to a difference array at each interval's start and subtracts one after its end. Taking a cumulative sum counts all rows containing each length. No list of all 5,124 word strings is required.

## Occurrence and earliest-position queries

All suffixes starting with a requested word form one contiguous suffix-array interval. Two binary searches locate that interval by comparisons against the retained text. Its size is the occurrence count, including overlaps.

Each text has a retained minimum segment tree over its suffix starts. A range-minimum query returns the smallest numerical start in an occurrence interval. Pages return individual starts in lexicographic suffix order. They do not silently sort each page by position, because that would change the relationship between page offsets and the complete occurrence family.

The retained source-match position in a factor record is a valid occurrence witness for present factors. It need not be the earliest one. Use occurrences(...).first_index when earliest occurrence is required.

## CommonJS API

The module has no I/O or external dependencies.

    const { open } = require("./finite_factor_index.cjs");
    const packet = JSON.parse(savedText);
    const reader = open(packet.construction.snapshot);
    const shortest = reader.openSlice(reader.shortestAbsent());
    const words = shortest.page(0,64);
    const positions = reader.occurrences("target", words.items[0].word, 0, 8);

Consumers of this artifact should open saved data. compile(sourceText,targetText,maxLength) is for a new finite input, not a request to regenerate this accepted index. Exports also include LIMITS and SCHEMA.

### Constructor contract

- Each text is a nonempty JavaScript string over exactly the symbols 1 and 2.
- Each has at most 8,192 symbols.
- maxLength defaults to target length and must be an integer between 1 and target length.
- Both inputs are literal finite words; neither is required to be a run-length sequence.
- Empty words are excluded from the represented factor family.
- The generalized text has at most 16,385 suffixes. All counts and ranks are safely represented by Number under these limits.
- Imported JSON is capped at 16,000,000 characters. Pages are capped at 64 records.
- The bounds cap dimensions and storage; they do not promise a wall-clock runtime.
- Only the stated 1004/111 consumer was executed. Other dimensions, capped maxLength, empty-input rejection and malformed-input branches were source-inspected without a synthetic suite.

### Reader methods

A kind is exactly "all", "present" or "absent", always referring to factors of the target.

| Method | Meaning |
|---|---|
| summary() | Input lengths, counts, shortest absent length, constructor counters |
| count(kind,length=null) | Whole family count or exact length count; length 0 gives 0 |
| select(kind,rank) | Zero-based lexicographic factor selection |
| rank(kind,word) | Rank or null when outside the named family or maximum length |
| page(kind,start=0,limit=64) | Global factor page |
| lengthSlice(kind,length) | Saved row IDs for one positive length; one explicit target-row scan |
| shortestAbsent() | Saved shortest-absent length slice, or null if every represented target factor is present |
| openSlice(slice) | Navigation over saved fixed-length row IDs |
| occurrences("source" or "target",word,start=0,limit=64) | Occurrence count, earliest index and suffix-order position page |
| rowsPage(start=0,limit=64) | Complete target-row records in pages |
| lengthsPage(start=1,limit=64) | [length,all,present,absent] counts |
| stats() | Independent copy of reader counters |
| snapshot() | Independent full snapshot copy |

Every query word must be nonempty and binary and obey the text-size bound. rank returns null for a valid query exceeding the represented maximum length. select throws for an empty family or an out-of-range rank. Page start may equal family size, producing an empty terminal page. A zero page size is permitted and makes no progress when more records remain.

A slice offers summary(), select(rank), page(start,limit), rank(word), snapshot(). Its order is lexicographic at its fixed length. It stores both literal input texts and maximum length to bind it to the original snapshot. An opened slice checks supplied row IDs and their local interval membership; it does not discover omitted rows or reconstruct the complete slice.

Returned factor records provide:
row_id, length, word, target_start, target_index, present_in_source, maximum_source_match, source_witness_start, source_witness_index.
Global selections also give kind and rank. Fixed-length selections give slice_rank.

The target_start identifies the canonical target occurrence chosen by suffix order, not necessarily its earliest numerical occurrence. The companion target_index is one-based. Source witness fields are null for absent factors.

## Saved data and trust boundary

construction.snapshot has schema commons.finite_factor_comparison/v1. It retains both words, max_length, separator, all 1,116 generalized suffix starts and LCP entries, all 1,004 source suffix starts, 111 target rows, three cumulative count tables, three per-length count tables, totals, shortest absent length, and both occurrence-minimum trees.

Target row columns are:

    [target_start, previous_target_lcp, maximum_source_match, source_match_start].

The complete packet also retains the source-input provenance, source identity, constructor observation, all 28 new reader outputs, shortest-absent and longest-present slice snapshots, and explicit work counters.

The loader checks schemas, binary alphabets and bounds, permutation dimensions and uniqueness, row bounds, count-array dimensions/order/partition sums, family totals, and minimum-tree dimensions/value ranges. It makes a defensive copy before exposing methods.

It does not re-sort suffixes, recompute LCPs, rederive source matches or count intervals, verify minimum-tree recurrence, or authenticate the mathematics. A structurally accepted dataset remains dependent on its provenance. Saved slice validation similarly checks membership of supplied rows but not completeness. Binding the exact published data and source identities is required before treating their results as authentic.

Opening and querying saved tables therefore do not establish the infinite sequence identities or independently certify this finite construction.

## Actual computation and publication custody

The implementation was parsed, frozen and checkpointed before its sole construction:

- finite_factor_index.cjs: 4d709c5c79f7d6220ad2f68c9bf58de631af4cd9, 12,679 UTF-8 bytes.
- Exact published-input packet: f0fa6507d4008809bddbe60f6be8b5c2b165c5b9, 1,880 UTF-8 bytes.
- Initial complete constructor packet: 7dda6e87f246014c21d5d36651965197e26ac2d4, 27,973 characters.
- Final complete data/query packet: 26c60099346acf2dffb35d65e3846db703aaf9c5, 42,083 UTF-8 bytes.

All checkpoints were durable Git blobs before the guide was composed. Neither source sequence was regenerated.

The constructor used seven suffix-sort rounds, 32,809 rank-pair comparator calls, 2,199 LCP character comparisons and two nearest-source sweeps. Its single wall observation was 6 ms. A fresh source context opened the saved snapshot in an observed 2 ms. These are observations rather than performance claims.

The separate reader made 28 calls. Two fixed-length slices scanned 222 saved rows. Query binary searches made 184 suffix comparisons and 1,718 character comparisons; earliest-position queries visited 12 minimum-tree nodes; selection used 27 prefix-index steps and extracted 250 symbols. It performed zero suffix-sort rounds, LCP construction steps or source-sequence steps.

The reader exported all 111 target rows and all per-length counts, both shortest absent words with source/target occurrence results and ranks, the unique longest shared word with both positions, selected absent/present ranks, and the single-symbol occurrence page. These are actual saved-data operations; no construction, accepted calculation, test suite, native executor or workflow was replayed.

This package provides a finite factor-language index and explicit data boundaries. It does not prove or refute Kimberling's infinite segment-containment question, make a new recurrence or status claim, or establish any external frontier.
