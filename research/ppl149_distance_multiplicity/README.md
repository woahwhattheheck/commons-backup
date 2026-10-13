# Rectangular distance multiplicity

An exact implicit index of unordered pairs in a finite rectangular integer grid.

The new 53 by 89 consumer has 4,717 points and 11,122,686 unordered distinct pairs. Its 4,716 displacement blocks give 2,397 realized positive distances. Exactly 1,589 non-diameter classes occur in at most 4,717 pairs. The diameter has squared length 10,448 and multiplicity two.

## Files

- [rectangle_distance_index.cjs](rectangle_distance_index.cjs): block compiler, distance filters and exact pair rank/select.
- [DISTANCE_FIBERS_API.md](DISTANCE_FIBERS_API.md): counting proof, sources, conventions, limits and complete query contract.
- [rectangle53_89_distances.json](rectangle53_89_distances.json): every displacement block, class, multiplicity and prefix, plus all 26 fresh-reader outputs.

## Use the saved index

    const { open } = require("./rectangle_distance_index.cjs");
    const packet = JSON.parse(savedText);
    const reader = open(packet.construction.snapshot);
    const rare = reader.openSlice(reader.lowMultiplicity(true));
    const pair = rare.selectPair(1188522);
    const originalRank = reader.rankPair(pair.points);

The reader does not enumerate pairs or rebuild geometry. Selected pairs can be translated and positively scaled by exact large integers, with matching inverse rank queries. Structural loading does not independently authenticate the saved counting formulas.

Distances use exact squared keys; zero and self-pairs are excluded. Each unordered pair is counted once, without ordered-pair doubling. Pages and ranks follow documented distance/block/orientation/translation order.

The published 2025 source states the general non-diameter question for n at least five. This one finite rectangle is an example, not a proof for arbitrary planar sets. The catalogue's stronger diverging-count formulation remains separately qualified. Formal132's one 404 is preserved without retry. No old pinned-profile or line computation was replayed.
