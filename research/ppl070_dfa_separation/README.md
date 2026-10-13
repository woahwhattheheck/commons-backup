# PPL070: compressed-word DFA separation index

A bounded pure-JavaScript catalogue for every labelled complete binary transition table with one through four states, with start state 0. Cached unary powers evaluate run-length encoded words without expanding their repeated blocks. Retained endpoints support exact accepting-set count/rank/select.

| File | Purpose |
|---|---|
| [rle_dfa_separator_index.cjs](rle_dfa_separator_index.cjs) | Compiler, saved index, full-DFA navigation and conflict-table pages |
| [RLE_DFA_SEPARATOR_API.md](RLE_DFA_SEPARATOR_API.md) | Complete coverage argument, encoding, bounds, conventions and source scope |
| [period210_separator_catalog.json](period210_separator_catalog.json) | All 66,282 endpoint rows, unary maps/orbits/powers and complete consumer results |

The new pair $0^{212}1^2,\ 0^21^{212}$ uses the retained value 210 from Commons #31360 as an identified input premise. Both orientations and their joint acceptance requirement need four states. At that minimum, there are 18,624 labelled full DFAs for either orientation and 6,840 for one common accepting set. All 48 tables that distinguish both pairs separately but cannot share an accepting set are retained explicitly.

Counts preserve labels and permit unreachable states; no isomorphism quotient is applied. Ordinary/reversed endpoint distinction and one common final-set assignment are separate notions. Loading builds weights from saved endpoints without re-evaluating the full transition catalogue; selected traces read saved power rows. The loader assumes the mathematical provenance of its identified source.

The reversal-gap problem itself was solved by [Ebrahimnejad, TCS 711 (2018),79–91](https://arxiv.org/html/1605.04835v3). The guide credits that result and Shallit's earlier unary-tail/cycle lower-bound framework. This package supplies a finite reusable index, not a new gap theorem, minimum-state priority claim, general bound or external frontier.
