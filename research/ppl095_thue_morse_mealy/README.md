# Thue–Morse: all two-state letter-to-letter outputs

All **256 labelled binary two-state Mealy machines**, with initial state 0 and one output bit per input bit, produce exactly **104 distinct infinite output streams** on the Thue–Morse input.

The complete atlas identifies entire streams by canonical minimal index automata. It does not infer equality from finite prefixes. The 16 shared kernels contain 143 states; the largest minimal output DFAO has nine states. Every machine's quotient map and all 1,650 minimal-state distinguishing words are retained.

The four basic streams—constant zero, complemented Thue–Morse, Thue–Morse, constant one—each have 30 labelled machine representatives. The full class-size distribution is 84 singleton classes, 8 classes of size 2, 4 of size 4, 4 of size 5 and 4 of size 30.

These are exact stream-equality classes in a bounded letter-to-letter family. Shallit's prime-degree question permits arbitrary finite state counts and empty or multi-letter outputs. This artifact makes no claim about general primeness, transduction-degree equivalence or an ultimate-periodicity classification.

## Files

| File | Purpose |
| --- | --- |
| [thue_morse_mealy_index.cjs](thue_morse_mealy_index.cjs) | Pure JavaScript atlas compiler and retained exact-query API. |
| [THUE_MORSE_MEALY_API.md](THUE_MORSE_MEALY_API.md) | Finite-kernel proof, certificate semantics, API and source scope. |
| [two_state_infinite_output_atlas.json](two_state_infinite_output_atlas.json) | Complete 256-machine family, 104 classes, all certificates, actual queries and work counters. |

## Saved use

With the complete texts available as `moduleText` and `dataText`:

```js
const module = { exports: {} };
new Function("module", "exports", moduleText)(module, module.exports);
const data = JSON.parse(dataText);
const atlas = module.exports.openRetainedThueMorseMealyAtlas(data.snapshot);

atlas.summary();
atlas.classesPage(0, 40);
atlas.difference(10, 198);
atlas.output(198, data.retained_consumer.query_index);
```

The original transducer consumes stream bits. Its index DFAO instead consumes the binary digits of a position, least significant first. This distinction lets the reader answer exact large-index and prefix-count queries without expanding the intervening stream.

## Actual consumer

One complete atlas compilation was followed by a fresh reader's 16 queries. The reader exported every class summary and all 30 machines whose output is exactly Thue–Morse, while recording zero kernel constructions, minimizations or expanded stream symbols.

For the new index \(N=10^{1000}+19\), machines 10, 5, 198 and 204 output 0, 1, 1 and 1. Machine 198 emits an initial zero followed by adjacent-bit differences. Its exact prefix counts for \(0\le n<N\) are \((2N-7)/3\) ones and \((N+7)/3\) zeros. These are the retained totals for this one bound; the complete decimal values and final digit-DP distribution are saved.

## Sources

- [Shallit's official slides](https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf), printed slides 36–37: the prime-under-transduction question.
- [Endrullis–Grabmayer–Hendriks–Zantema, The Degree of Squares is an Atom](https://arxiv.org/pdf/1506.00884), 2015, §3: the general sequential-transducer model and atom convention.

The broader model permits empty and multi-letter transition outputs. Its known Thue–Morse/period-doubling equivalence retains its source attribution. Exact initial symbols, finite-family bounds and the absence of a general degree claim are explicit in the guide.

Executed module blob: `301e11b501f67eeae9cea6f746edfdfaac7da0e6`.
