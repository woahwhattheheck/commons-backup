# Truth ledger

| Claim | Status | Evidence |
|---|---|---|
| Kuhn cube has 6 tets of equal volume 1/6 | CERTIFIED | kuhn.kuhn_tets + tet_volume_times_6 == 1 |
| Affine n-grid has 6 n^3 tets | CERTIFIED | refine_n |
| Local div : [P_k]^3 -> P_{k-1} surjective on one tet, k=1..6 | CERTIFIED | exact Q-rank of monomial div matrix |
| Protected degree-four body-diagonal lift for all 12 endpoint-zero trace coefficients, with zero cell means on the fixed two-cube patch | CONSTRUCTED | p4_body_diagonal_lift.py; 189×12 rational map, 270 nonzeros; all edge/mean identities checked during construction |
| Protected degree-five body-diagonal lift for all 18 endpoint-zero trace coefficients, with zero cell means on the fixed two-cube patch | CONSTRUCTED | p5_body_diagonal_lift.py; 432×18 rational map, 1,763 nonzeros; exact degree elevation and combined edge/mean identities |
| Fixed interior face-diagonal source space and mean-preserving protected lifts, k=4,5 | CONSTRUCTED | face_diagonal_lift.py; full-source checkerboard identity; dimensions 6/9; 34/174 nonzeros with combined exact edge/mean identities |
| Zhang k>=6 mesh-uniform inf-sup on Freudenthal | LITERATURE | Zhang 2011; not re-proved here |
| Sponsor conjecture k>=4 mesh-uniform inf-sup | OPEN | prize PDF; Farrell-Mitchell-Scott 2024 |
| Analytical refutation of k=4 or k=5 | NOT FOUND | no exact degenerate pressure sequence constructed here |
| Alfyorov 2026 Research Square proof | EXTERNAL UNVERIFIED | not reviewed into this ledger as a theorem |
| Prize / payment / sponsor email | FORBIDDEN by issue | not performed |

Branch identity: grok/issue-14999
