# Primitive binary-word index

Exact prefix counts and lexicographic count/rank/select operations for a fixed positive binary-word length, using a saved Möbius ledger rather than a list of words.

| File | Contents |
| --- | --- |
| [primitive_word_index.cjs](primitive_word_index.cjs) | Bounded pure-JavaScript constructor and saved reader |
| [PRIMITIVE_WORD_API.md](PRIMITIVE_WORD_API.md) | Formula, navigation argument, contracts, attribution and complete actual scope |
| [length70_words.json](length70_words.json) | All eight divisor rows, 71 powers, provenance and 13 complete saved-reader outputs |

The one actual length-70 index counts **1,180,591,620,683,051,547,810 primitive words** and **34,359,755,614 nonprimitive words**. These evaluate the classical Möbius formula recorded by Golomb, Gordon and Welch; no new enumeration formula or complexity result is claimed.

The two source words from accepted #31503 are used only as new lexical inputs. The word with 65 zeros followed by five ones has rank **30**; five zeros followed by 65 ones has rank **36,893,488,146,345,360,868**. Both are primitive. The median selected word is one 1 followed by 69 zeros. All three 70-step navigation traces, membership periods, three prefix ledgers and 13 paged words are retained.

The saved reader performs structural and saved-total-partition checks, with no constructor, factorization, power doubling or family enumeration. Saved arithmetic correctness and complete divisor coverage remain identified constructor premises. Its loader is not an independent mathematical certificate checker.

Primitive means nonempty and not a proper whole-word power. Repeated letters are allowed, leading zeros matter, and rotations are distinct words. The empty prefix is permitted at positive length; the empty word is not a primitive object. Ranks are zero-based under 0 < 1.

The [STACS 2026 primary paper](https://drops.dagstuhl.de/storage/00lipics/lipics-vol364-stacs2026/html/LIPIcs.STACS.2026.5/LIPIcs.STACS.2026.5.html) still describes nonunary primitive-language context-freeness as unknown and already establishes a related counting result. This finite API does not settle Shallit's language question. Source attribution and exact scope are in the guide.

Executed source: `bc3500734709a14055708a559530e57cf0e6232e`. Source and complete construction/reader data were checkpointed in Git before documentation. Larger inputs and error branches were source-inspected only; no old NFA computation, synthetic suite or native execution was performed.
