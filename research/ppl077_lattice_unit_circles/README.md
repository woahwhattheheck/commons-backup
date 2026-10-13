# Exact unit circles in a rational rectangle

For the 493 points (i/5,j/5), 0<=i<17 and 0<=j<29, this complete finite index records 837 distinct unit circles through at least three points, 5,680 incidences and 51,576 determining triples. The circles are stored in two complete consecutive shards.

- [API, exact geometry, validation and source scope](LATTICE_UNIT_CIRCLE_API.md)
- [CommonJS module](lattice_unit_circles.cjs)
- [Kernel, incidence index and shard manifest](rectangle17x29_scale5_unit_circles.json)
- [Circle IDs 0–418](circles_0000_0418.json)
- [Circle IDs 419–836](circles_0419_0836.json)
- [All 17 corrected saved-reader outputs](saved_reader_queries.json)

The local construction retains 316 offsets and 660 successful determinant witnesses from 49,770 pairs, yielding 12 exact kernel centers. Translation and exact merging build the finite rectangle index without enumerating its point triples. Subset, incidence, rank/select and huge rational translation queries use saved records.

The geometric constructor ran once under version 1.0.0. The published version 1.0.1 fixes an internal rank type conversion exposed during the first reader attempt and opens that unchanged snapshot. Eleven preceding ephemeral reader responses were not retained and are explicitly unavailable; the 17-query continuation is complete. No geometric calculation or successful preceding query was replayed.

The result gives maxUnitCircleCount(493)>=837, not equality or an extremal record. The formal Erdős 104 asymptotic question concerns all planar configurations; this input does not settle it. Published geometric attribution and source-access limits are explicit in the guide.
