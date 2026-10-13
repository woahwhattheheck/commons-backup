# Integer Hankel prefix family

All 54,331 admissible length-eleven words over {5,7,11}, every valid shorter prefix and every first-zero rejection branch are retained. The 88,452-node tree and 64,081 determinant records support exact completion counts, lexicographic rank/select, rejection matrices and positional marginals. All 65 actual reader responses and 21 inverse matches are included.

Start with [the API guide](INTEGER_HANKEL_PREFIX_API.md). Load [prefix_manifest.json](prefix_manifest.json) and its complete shards using [unpack_prefix_index.cjs](unpack_prefix_index.cjs), then open [integer_hankel_prefix_index.cjs](integer_hankel_prefix_index.cjs). Lossless array encoding reconstructs the original complete snapshot byte-for-byte; no mathematical calculation is replayed.

Shallit's official page reports the three-real-number question solved, while its integer variant remains unresolved. This package fixes one integer alphabet and length; it does not produce an infinite sequence. All new matrix entries differ from the accepted four-symbol morphic inputs, which remain untouched. No linked proof, published example, old determinant or prize claim is involved.
