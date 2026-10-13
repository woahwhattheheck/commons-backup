# Green 32: cyclic dilate-gap navigation

This package stores every nonzero dilation of the sixteen retained primes from 2 through 53 modulo 257. Saved queries can select any subpalette, count or rank exact-length cyclic gaps, and translate the gap starts by arbitrary signed integers.

For the full palette the largest gap is 205 absent residues, attained only by multipliers 1 and 256. Removing 2 increases the maximum to 231 and changes the maximizing multipliers to 128 and 129. The saved reader contains 50 complete responses, 12 rank/select inverse matches, six new complete subpalette conditions and twelve interval-family caches.

The constructor copies 864 identified old modular-product values and computes 3,232 new ones. Reader conditioning performs new, explicitly counted gap arithmetic; it does not rebuild the dilation images or sorted orders. Empty palettes have unbounded gaps, while length zero is vacuous.

Start with [the API guide](CYCLIC_DILATE_GAP_API.md). The input, complete construction, three cache shards and all reader evidence are included. The guide gives exact source/input identities, the absent-length convention, ordering, reconstruction instructions and limitations.

This finite navigator covers one palette family. It does not settle Green's large-prime conjecture, classify all sets of the same size, replay a published proof, or claim a new bound or prize result.
