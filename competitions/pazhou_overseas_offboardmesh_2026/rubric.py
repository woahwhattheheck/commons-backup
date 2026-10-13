#!/usr/bin/env python3
import json
from pathlib import Path

MAXIMA = {
    "technical_or_product_leadership": 35,
    "business_model_and_implementation": 35,
    "team_competitiveness": 20,
    "project_feasibility": 10,
}

def evaluate(path: Path | None = None):
    path = path or Path(__file__).with_name("rubric_evidence.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "tjl.pazhou-offboardmesh-rubric-evidence/v1"
    assert data["warning"] == "INTERNAL_PREPARATION_SCORE_NOT_ORGANIZER_SCORE"
    seen = set()
    total = 0
    max_total = 0
    gaps = []
    for item in data["categories"]:
        cid = item["id"]
        assert cid in MAXIMA and cid not in seen
        seen.add(cid)
        assert item["maxPoints"] == MAXIMA[cid]
        points = item["evidencePoints"]
        assert type(points) is int and 0 <= points <= item["maxPoints"]
        assert isinstance(item["evidenceRefs"], list) and isinstance(item["gaps"], list)
        if points and not item["evidenceRefs"]:
            raise AssertionError(f"{cid}: points require evidence")
        total += points
        max_total += item["maxPoints"]
        gaps.extend({"category": cid, "gap": gap} for gap in item["gaps"])
    assert seen == set(MAXIMA)
    assert max_total == 100
    return {"internalEvidenceCoverage": total, "maxPoints": 100, "organizerScoreClaimed": False, "gaps": gaps}

if __name__ == "__main__":
    print(json.dumps(evaluate(), sort_keys=True, separators=(",", ":")))
