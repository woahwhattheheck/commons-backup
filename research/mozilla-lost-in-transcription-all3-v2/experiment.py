from __future__ import annotations
import argparse, json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from core import TRACKS, Hypothesis, TrackPrior, choose_consensus, corpus_wer, canonical_json


def _load_priors(path: Path | None) -> dict[str, TrackPrior]:
    if path is None: return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: TrackPrior(**v) for k, v in raw["priors"].items()}


def run(dataset: Path, output: Path, priors_path: Path | None = None) -> dict:
    records = []
    raw_bytes = dataset.read_bytes()
    for lineno, line in enumerate(raw_bytes.decode("utf-8").splitlines(), 1):
        if not line.strip(): continue
        item = json.loads(line)
        if item.get("track") not in TRACKS or item.get("evidence_class") not in {"public", "authorized_local", "synthetic"}:
            raise ValueError(f"inadmissible record line {lineno}")
        if not item.get("reference") or len(item.get("hypotheses", [])) < 2:
            raise ValueError(f"incomplete record line {lineno}")
        records.append(item)
    priors = _load_priors(priors_path)
    by_track = {}
    detail = []
    for track in sorted(TRACKS):
        rows = [r for r in records if r["track"] == track]
        if not rows: raise ValueError(f"missing experiment rows for {track}")
        refs, top1, consensus = [], [], []
        abstains = 0
        for row in rows:
            hs = [Hypothesis(**h) for h in row["hypotheses"]]
            result = choose_consensus(track, hs, prior=priors.get(track))
            refs.append(row["reference"]); top1.append(hs[0].text); consensus.append(result.text)
            abstains += int(result.abstain)
            detail.append({"id": row["id"], "track": track, **asdict(result)})
        b = corpus_wer(top1, refs); c = corpus_wer(consensus, refs)
        by_track[track] = {"rows": len(rows), "top1_wer": b, "consensus_wer": c, "wer_delta": c-b, "abstains": abstains}
    report = {"schema_version": 1, "dataset_sha256": sha256(raw_bytes).hexdigest(), "tracks": by_track, "detail": detail}
    output.write_text(canonical_json(report), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("dataset", type=Path); ap.add_argument("output", type=Path); ap.add_argument("--priors", type=Path)
    a=ap.parse_args(); run(a.dataset,a.output,a.priors)
if __name__ == "__main__": main()
