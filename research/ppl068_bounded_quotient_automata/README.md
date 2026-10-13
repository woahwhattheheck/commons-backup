# Bounded-quotient automata

Exact product graphs and saved navigation for paired-digit DFA inputs satisfying y=q*x, with positive x and a supplied finite list of positive quotients.

The new consumer uses a declared product of the classical Thue–Morse parity recognizers, accepting pairs with both binary digit sums odd. For q=2 through 13, the complete product has **372 nodes**, **344 reachable nodes** and **732 valid arcs**. Every selected quotient has a shortest accepted positive pair.

All-length reachability is separate from the saved fixed-length tables. The **26,412 coefficient cells** cover lengths 0 through 70 and represent **450,850,183,389,303,088,663 canonical pairs of length 70**. No integer-pair census was enumerated.

| File | Contents |
| --- | --- |
| [quotient_automata.cjs](quotient_automata.cjs) | Bounded compiler and separate saved-graph/table reader. |
| [QUOTIENT_API.md](QUOTIENT_API.md) | Residual-state proof, conventions, API, limits and actual results. |
| [thue_morse_quotients_2_13.json](thue_morse_quotients_2_13.json) | Complete input, graphs, BFS certificates, coefficients and twenty reader queries. |

Saved operations include prefix counts, rank/select, pages, explicit shortest witnesses and membership of large integer pairs. Reader work performs no product-graph reconstruction, BFS rerun, coefficient recurrence or old Thue–Morse kernel computation.

Shallit's [2013 Fields presentation](https://cs.uwaterloo.ca/~shallit/Fields/shallit.pdf) supplies the paired MSD encoding and general divisibility question. [Mousavi's Walnut account](https://cs.uwaterloo.ca/~shallit/Papers/aut3.pdf) supplies established fixed-multiplier automaton context. A finite quotient union does not decide unrestricted existential divisibility. No general solution, novelty, frontier or reward claim is made.
