# S02 MPC batch RESULTS

Engine pin: kaggle-environments==1.32.7 commit 28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c
Hashes: kaggriculture.py bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e
kaggriculture.json a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867
utils.py 537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b
Archive titan-current.tar.gz f8f1750266b3cfaea0ebfe663f287aa9c5a2682f6fc47bc932957e1d48e63f1c 409345 bytes

## Commands
```
bash tools/v25_sims/setup.sh
python tools/v25_sims/gauntlet.py --seeds 2611021001,2611021002 --opponents arlene --workers 2 --action-timeout 15.0 --candidate /tmp/v25/cand_f8f1/main.py --outdir /tmp/v25/out_smoke_can
python tools/v25_sims/gauntlet.py --seeds 2611021001,2611021002 --opponents arlene --workers 2 --action-timeout 15.0 --candidate /tmp/v25/cand_h6/main.py --outdir /tmp/v25/out_smoke_h6
```

## Canonical SUMMARY.json
```
{"wall_seconds": 7.7, "workers": 2, "scheduled": 4, "completed": 4, "failed": 0, "throughput_games_per_min": 31.02, "shard_seconds": [7.7, 7.6], "per_opponent": {"arlene": {"games": 4, "W": 4, "T": 0, "L": 0, "mean_margin": 1432.0}}, "failures": []}
```

## Canonical GAMES.jsonl
```
{"opponent": "arlene", "seed": 2611021001, "candidate_seat": 0, "status": "complete", "scores": [126220.0, 124828.0], "failure": null}
{"opponent": "arlene", "seed": 2611021001, "candidate_seat": 1, "status": "complete", "scores": [124828.0, 126220.0], "failure": null}
{"opponent": "arlene", "seed": 2611021002, "candidate_seat": 0, "status": "complete", "scores": [112488.0, 110894.0], "failure": null}
{"opponent": "arlene", "seed": 2611021002, "candidate_seat": 1, "status": "complete", "scores": [111059.0, 112409.0], "failure": null}
```

## H=6 SUMMARY.json
```
{"wall_seconds": 36.5, "workers": 2, "scheduled": 4, "completed": 4, "failed": 0, "throughput_games_per_min": 6.57, "shard_seconds": [36.2, 36.5], "per_opponent": {"arlene": {"games": 4, "W": 0, "T": 0, "L": 4, "mean_margin": -88615.5}}, "failures": []}
```

## H=6 GAMES.jsonl
```
{"opponent": "arlene", "seed": 2611021001, "candidate_seat": 0, "status": "complete", "scores": [17953.0, 86486.0], "failure": null}
{"opponent": "arlene", "seed": 2611021001, "candidate_seat": 1, "status": "complete", "scores": [86486.0, 17953.0], "failure": null}
{"opponent": "arlene", "seed": 2611021002, "candidate_seat": 0, "status": "complete", "scores": [24226.0, 132924.0], "failure": null}
{"opponent": "arlene", "seed": 2611021002, "candidate_seat": 1, "status": "complete", "scores": [132924.0, 24226.0], "failure": null}
```

## Planning time H=6 (2872 turns logged)
max=0.078183 p50=0.020146 timeouts=0 errors=0 alts=438

## Paired own-cash vs canonical
2611021001 seat0 delta=-108267
2611021001 seat1 delta=-108267
2611021002 seat0 delta=-88262
2611021002 seat1 delta=-88183

H=6 kept as specified (no retune). H=12/24 and 16-seed x 6-opp matrix not finished this seat after VM wipe. Archive promotion left to Bryce.
