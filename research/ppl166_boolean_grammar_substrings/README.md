# PPL166: retained Boolean-grammar substring certificates

A dependency-free JavaScript API for a complete bounded substring chart, with saved membership, occurrence count/rank/select/pages, positive and negative split evidence, positive parse certificates and finite ambiguity diagnostics.

The source input is an explicitly normalized version of [Alexander Okhotin's Example 4](https://arxiv.org/pdf/2012.03538). One new word uses the 24 retained #31434 prime-exponent values as lengths of a-blocks followed by b. No factorial valuation, divisor or prime computation was repeated.

## Completed finite consumer

The word has **231 symbols**. Its chart covers **26,796 nonempty substring occurrences** and **12,326,160 candidate split checks** over six shared binary pairs. It retains 5,402 nonzero pair records and 5,863 rule/nonterminal count records each, with an explicit zero convention for the remaining domain.

The start symbol S accepts **3,663 occurrences**. The whole word has one positive parse. The saved reader distinguishes:

| Substring | Result |
| --- | --- |
| `aaabaaab` at [191,199) | Rejected: the negative C·Tb condition finds an equal-length block. |
| `aaabaabaab` at [195,205) | Accepted: later blocks may equal each other while differing from the first. |
| `aaabaaabaab` at [191,202) | Rejected: the required earlier S-prefix has already failed. |

Both finite rule-overlap and multiple-partition diagnostic lists are empty for these substrings. **This does not establish global Boolean unambiguity or inherent unambiguity.** Definition 5 also constrains concatenations in negative and rejected contexts; a unique positive parse alone is insufficient.

## Files

| File | Contents |
| --- | --- |
| [boolean_substring_index.cjs](boolean_substring_index.cjs) | Constructor, retained reader and bounded query API. |
| [BOOLEAN_SUBSTRING_API.md](BOOLEAN_SUBSTRING_API.md) | Source attribution, explicit normalization, semantic proof, full contract and actual results. |
| [factorial89_exponent_word_chart.json](factorial89_exponent_word_chart.json) | Complete 932,834-byte artifact; open its `snapshot` field. |

## Use the saved chart

With the complete fetched module and JSON supplied as `sourceText` and `dataText`:

```javascript
const loaded = { exports: {} };
new Function("module", "exports", sourceText)(loaded, loaded.exports);

const saved = JSON.parse(dataText);
const index = loaded.exports.openRetainedBooleanSubstringIndex(saved.snapshot);

const count = index.countOccurrences("S"); // "3663"
const evidence = index.ruleEvidence(0, 191, 199);
const witness = index.splitPage(1, 191, 199, { offset: 0, limit: 8 });
```

Spans are zero-based and end-exclusive. Occurrence ranks use increasing length, then start; equal texts at different positions remain separate occurrences. The chart covers this word, not all words through length 231.

Every binary production has an explicit negative-epsilon guard. Together with terminal-only base productions and nonempty splits, it makes membership well-defined by length induction. The public contract rejects nullable/unit/general-conjunct grammars instead of assigning an unjustified fixed-point interpretation.

The fresh reader made 20 calls without rebuilding the chart or searching candidate splits. Opening still checked 348,348 rule guards against saved masks, additive count totals, masks and occurrence indices. Individual child-membership convolutions and multiplicative parse-count identities remain retained construction premises. Query products are counted separately. All 24 page records, two split witnesses and parse certificates with 461 and 13 nodes are saved.

Executed source blob: `77bea4f678a0134f9714fc18ee2309f05bfa07ad`. Complete data blob: `df544623b2a0835b341b8390e8f7f1e67b678b72`. No inherent-ambiguity resolution, novelty, general complexity or external-frontier claim.
