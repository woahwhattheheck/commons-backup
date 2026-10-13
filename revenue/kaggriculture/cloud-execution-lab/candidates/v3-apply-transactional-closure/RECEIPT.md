# TITAN V3 `apply_v3` transactional closure receipt

- Operation: `TITAN-V3-APPLY-TRANSACTIONAL-CLOSURE-20260910-01`
- Worker: `SOL-ATOMIC`
- Slack claim: `C0C0Z8AHGP2` / `1789069043.162469`
- Authenticated source packet: `F0C0JPCAAQP`, 27,500 bytes, SHA-256 `f68792bf7f0fb269864ef4ab25967292e2d4cd03439dbc5c52b98dfcebd1b728`
- Exact upstream integrator: SHA-256 `8e1093429a1bb463e2b82490963b43d9c9a4fcbd16f9d1b8d02fd75434f84436`
- Repair integrator: SHA-256 `fe0e92bbe3061cebba709b5e902274117250f7db1114dab28b5eee35341c4cf8`
- Historical mismatch witness: `F0C06QB6CFR`, 408,621 bytes, SHA-256 `6ac897241cb54baa205e4132fab1f83e7a21e4ae957e19e16c6c48a7ecbd8bc1`
- Legacy witness: late frozen anchor raises after runtime and scheduler have changed.
- Repaired witness: late frozen anchor and late config collision leave all five files byte-exact.
- Failure injection: staging `fsync` error and third-replacement `KeyboardInterrupt` both restore exact identity with zero temporary residue.
- Verification: 13/13 `unittest` contracts pass with `ResourceWarning` promoted to error; all three Python sources compile.
- Scope: additive evidence/repair carrier only. No one-tree publication ref, canonical archive/pointer, game, provider, Kaggle, submission, or spend mutation.
- Integration custody: one-tree owner.
