# Finite graph-isomorphism transcripts

Exact real/simulator correspondence and navigation for a declared labelled six-cycle instance of the classical GMW protocol.

The certificate contains 720 permutations, 60 commitment graphs and 240 challenge cells. Its 2,880 real choices correspond bijectively to the 2,880 accepted choices among 5,760 simulator trials. Verifier coins stay fixed during rejection retries.

- [Conventions, proof, sources and API](GI_TRANSCRIPTS_API.md)
- [CommonJS module](gi_transcripts.cjs)
- [Complete finite certificate](six_cycle_transcript_certificate.json)
- [Public-only simulator tables](public_simulator.json)
- [All 31 saved-reader outputs](saved_reader_queries.json)

The public simulator contains no isomorphism witness or real-view coupling. It supports exact trial and rejection-run rank/select from saved public images and challenges. The reader includes a rank of 10^200 among runs with 100 failures.

GMW protocol and simulator credit is explicit. Source access is distinguished between the directly read author bibliography, indexed primary passages and unavailable full-paper/image content. This finite index is not a new zero-knowledge theorem, SZK/PZK comparison, or cryptographic deployment.
