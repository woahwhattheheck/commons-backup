# Titan V5 WF1 current-native component

This package carries the existing WF1 wheat-fertilize source and current adapter into the single V5 evaluation line. It preserves the proven ordering: the normal V5 parent action is produced first, then WF1 may transform that returned action.

`production20f_component.py` closes the standard-entry gap for the exact
production20f archive. It authenticates archive SHA256
`20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`
and `main.py` SHA256
`b98aec64f83ea9a216def7ab1fef320a6498ae37816f506af1f891c934027035`,
then emits a held staging component which replaces only `main.py` and adds the
two pinned WF1 modules. The wrapper calls the parent, preserves the parent's
delivery-choice commit, and only then invokes the fail-closed adapter.
On Windows, the builder canonicalizes checkout-expanded CRLF back to the exact
pinned Git-blob bytes before packaging the donor modules.

```bash
python -B production20f_component.py \
  --baseline /path/to/titan-v5-production-recovery-v3.tar.gz \
  --out-dir /fresh/wf1-production20f-component
```

An exact dry materialization from the pinned archive produces component
manifest SHA256
`40247b3d375b1248198a596b3eca372a05d915c0ebc589e721cdea65ff7934a9`
and a deterministic 94-member candidate archive SHA256
`7c9126d961915acbe1c69930d7cebc4938641233fe50323f2fb043c08334ac3d`.
Those hashes establish source and package identity only.

The generated component is checked in at
`../selective-carrot/components/wf1-production20f-v1/COMPONENT.json`. It also
composes without overlap after `future-own-supply-v1`. That two-component
structural proof has 95 members and archive SHA256
`db605e8db69d1a8392c9bc448d50abed165d024096b749d75aa91b921df3353f`.
The two-component interaction remains unmeasured.

The source is authenticated against the existing canonical donor blob `b35a30431f64c1d6b40d1d599190338a9d50b555`, adapter blob `5b8f4c0144ce43ae449373a6a188ce03409a16ee`, and retained field-receipt blob `e703d88cd40bb5af96aabaaa4327c1b7a81380aa`.

That retained paired field receipt completed 8/8 cells with zero failures and positive margin in every cell. Mean margin delta was +143.25 and mean own-score delta was +132.375. This package does not change canonical defaults or authorize activation; it makes the measured component reproducible against an explicitly identified V5 baseline.

`LOCAL-SCREEN.json` records the exact-current development screen against the
pinned production-v3 archive and responsive Arlene. All 12 matched cells across
six seeds and both mirrored seats engaged and improved paired margin: mean
`+385.5`, median `+353`, range `+314` to `+479`, zero failures, and no
win-to-loss conversion. The six distinct worlds were also 6/6 positive. Mean
own-cash delta was `+354.83`; mean rival-cash delta was `-30.67`.

This result admits the exact component to the held composition intake. It does
not establish hosted rating or broad-opponent performance: mirrored seats are
correlated, local timers were disabled, and the opponent was Arlene only. The
native Apex/Arlene and top-30-union gates remain required before promotion.
