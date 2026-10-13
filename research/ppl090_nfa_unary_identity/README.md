# Exact finite NFA separator from a unary identity

For **w = 0^65 1^5** and **x = 0^5 1^65**, the retained certificate gives **nsep(w,x) = 4**. Both words have length 70.

| File | Contents |
| --- | --- |
| [unary_identity_index.cjs](unary_identity_index.cjs) | Generic bounded Boolean-power atlas, source-family upper constructor and saved reader |
| [UNARY_IDENTITY_API.md](UNARY_IDENTITY_API.md) | Complete finite lower/upper arguments, conventions, contracts and actual results |
| [n4_pair_identity.json](n4_pair_identity.json) | Full 512-relation atlas, four-state witness and all eleven reader outputs |

Shallit's [official presentation](https://cs.uwaterloo.ca/~shallit/Talks/bc4.pdf), slides 20–24, supplies the source family and its presented 2n-state construction. This is the n=4 instance, with t=6 and lcm(1,…,6)=60. No new general NFA-separation bound or novelty is asserted.

The lower certificate contains **every one of the 512 Boolean relations on three labelled states**. Each has equal fifth and sixty-fifth powers. Applying that identity to both symbol relations makes the two words induce the same relation in every three-state NFA, for all initial and accepting subsets. Isolated-state padding covers smaller machines; epsilon closure can be incorporated without adding states. No binary-NFA table census or arbitrary-matrix transient theorem is assumed.

The upper witness has zero masks **[2,4,9,1]**, one masks **[1,0,0,0]**, and state 0 initial and accepting. Its shared zero cycles have lengths 3 and 4: 65 = 19·3 + 2·4, while 5 is not a nonnegative combination. Final masks are 1 for w and 0 for x. The one-loop also permits interleaved blocks, so this machine's whole language is not claimed to be exactly a two-block language.

The source was frozen at blob `34c6959f5ad5e251939de50d96971cee347853b9`. Complete source and execution packets were checkpointed in Git before documentation. All binary-power and accumulator matrices are retained, along with every reader output. The saved reader exported the full atlas through four pages, performing structural/equality checks and nine query row unions, with no power or atlas reconstruction. Its loader does not independently re-certify the saved matrix products.

Only this new source-family input and its eleven queries ran. Earlier DFA/separation and length-universality computations were not replayed. Other branches were source-inspected, with no synthetic suite, native process, sponsor contact or global-status claim.
