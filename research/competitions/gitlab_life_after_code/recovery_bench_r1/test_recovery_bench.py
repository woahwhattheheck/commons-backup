#!/usr/bin/env python3
import json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "recovery_bench.py"
CASES = HERE / "cases.jsonl"
CANDIDATE = HERE / "candidate.jsonl"
BASELINE = HERE / "baseline.jsonl"

def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True)

def load(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

def dump(path, rows):
    path.write_text("\n".join(json.dumps(x, separators=(",", ":")) for x in rows) + "\n")

def main():
    checks = []
    p = run(str(CASES), str(CANDIDATE), "--baseline", str(BASELINE))
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)

    checks.append(out["candidate"]["passed"] == 6 and out["baseline"]["passed"] == 3)
    checks.append(out["candidate"]["unsafe_promotions"] == 0)
    checks.append(out["candidate"]["recovery_success_rate"] == 1.0)

    candidate_rows = load(CANDIDATE)
    security_row = next(row for row in candidate_rows if row["id"] == "security-block")
    checks.append(security_row["decision"] == "block")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        rows = load(CANDIDATE)
        rows[0]["evidence_urls"] = ["https://example.com/evidence/dup", "https://example.com/evidence/dup"]
        dup = td / "dup.jsonl"; dump(dup, rows)
        out = json.loads(run(str(CASES), str(dup)).stdout)
        checks.append(any("unique" in e for result in out["candidate"]["case_results"] for e in result["errors"]))

        rows = load(CANDIDATE)[:-1]
        missing = td / "missing.jsonl"; dump(missing, rows)
        p = run(str(CASES), str(missing))
        checks.append(p.returncode != 0 and "case-set mismatch" in p.stderr)

        rows = load(CANDIDATE)
        rows[0]["evidence_urls"] = ["http://not-secure.example/e"]
        http = td / "http.jsonl"; dump(http, rows)
        out = json.loads(run(str(CASES), str(http)).stdout)
        checks.append(any("https://" in e for result in out["candidate"]["case_results"] for e in result["errors"]))

    assert all(checks), checks
    print(f"{len(checks)}/{len(checks)} focused checks PASS")

if __name__ == "__main__":
    main()
