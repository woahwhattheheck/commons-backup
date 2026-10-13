# CRT residue-covering index

A bounded pure-JavaScript index for every assignment of one residue class per supplied pairwise-coprime modulus. A complete saved zero-class period turns coverage into gap intervals, enabling exact threshold counts and assignment rank/select.

| File | Contents |
| --- | --- |
| [residue_covering_index.cjs](residue_covering_index.cjs) | Constructor, saved period reader and independent saved slice reader |
| [RESIDUE_COVERING_API.md](RESIDUE_COVERING_API.md) | CRT/gap derivation, contracts, published attribution and actual scope |
| [primes_through17.json](primes_through17.json) | Complete period, 23 query outputs, three slices and all selected assignments |

The one actual input is **[2,3,5,7,11,13,17]**, product **510510**. It retains all **92,160** zero-free residues and cyclic gaps. The published maximum gap **26** corresponds to covered length **25**, not 26; Ziller–Morack and OEIS A048670/A058989 retain attribution.

The complete covering families contain **248** assignments at threshold 20, **4** at threshold 24 and **2** at threshold 25. All 254 requested assignment records are retained. The two maximal phases are **217127** and **293357**. Ordering is increasing CRT phase, not lexicographic residue order or a quotient by symmetry.

The saved query for **217127 + 510510 times 10^100** supplies 25 divisor/quotient witnesses and a first-uncovered witness at offset 26, without repeating the sieve. Uncovered does not mean prime. Generic composite-modulus survivors need not be totatives; that interpretation applies to this prime input.

Source **c03b7acfc3af836b159224df627977357b6bb4c0** was frozen before construction. Complete source and execution packets were checkpointed before documentation. The saved reader checks gap relationships and structural fields but does not independently authenticate the sieve or CRT inverses. Slice creation scans saved gaps; the independent slice reader then navigates only saved intervals. All actual work is counted explicitly.

This is an exact finite family-navigation capability. It makes no new maximum, asymptotic estimate, mathematical novelty or prize claim for Erdős 687. No old prime, word, Markov or other accepted computation was replayed.
