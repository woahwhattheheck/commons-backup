"""Synthetic-only reproducible ablation for consensus selection."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from core import Hypothesis, NgramPrior, choose_consensus, corpus_wer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.fixture.read_bytes()
    payload = json.loads(raw)
    prior = NgramPrior.fit(payload["prior_transcripts"], source_sha256=sha256(raw).hexdigest())
    refs, baseline, consensus, diagnostics = [], [], [], []
    for record in payload["records"]:
        hyps = [Hypothesis(**item) for item in record["hypotheses"]]
        result = choose_consensus(hyps, prior=prior)
        refs.append(record["reference"])
        baseline.append(hyps[0].text)
        consensus.append(result.text)
        diagnostics.append({"id": record["id"], "chosen_source": result.chosen_source, "abstain": result.abstain, "disagreement": result.disagreement, "score_margin": result.score_margin, "evidence_sha256": result.evidence_sha256})
    report = {
        "evidence_class": "SYNTHETIC_ONLY",
        "fixture_sha256": sha256(raw).hexdigest(),
        "records": len(refs),
        "baseline_wer": corpus_wer(baseline, refs),
        "consensus_wer": corpus_wer(consensus, refs),
        "diagnostics": diagnostics,
    }
    out = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
