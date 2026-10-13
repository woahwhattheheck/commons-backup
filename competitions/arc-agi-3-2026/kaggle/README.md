# ARC3 SAGE — offline Kaggle packaging and runtime evidence

`package.py` discovers the dependency-free Python carrier, hashes every source byte, rejects network-capable imports/dynamic exec/credential-like literals, and emits a deterministic source bundle plus notebook. `profile.py` records return code, wall time, peak child RSS and output digests without shell execution. `readiness.py` is fail-closed: clean scan + successful smoke + configured safety margin are required, and an unknown platform memory limit remains a blocker rather than being invented.

The existing ARC3 source documents the notebook execution ceiling as **9 hours**. Use `32400` seconds only after revalidating the controlling competition rules; provide the actual current memory limit explicitly. Example conceptual flow:

```bash
python -c 'from pathlib import Path; from kaggle.package import build_bundle; build_bundle(Path("."), Path("/tmp/sage-bundle"))'
python -c 'from pathlib import Path; from kaggle.profile import run_profile; print(run_profile(["python","benchmark.py","--seeds","100"], cwd=Path("."), timeout_seconds=300))'
```

These tools do not register, upload or submit to Kaggle and never create a leaderboard score claim.
