# SPDX-License-Identifier: MIT
"""DaT challenge entrypoint template. Replace only model_backend implementation."""
from pathlib import Path
import csv
import math
from model_backend import predict_probability

ROOT = Path("/code_execution")
FORMAT = ROOT / "data" / "submission_format.csv"
NIFTIS = ROOT / "data" / "niftis"
OUTPUT = ROOT / "submission.csv"

def main() -> None:
    with FORMAT.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ("uid", "is_pathologic"):
            raise RuntimeError("unexpected submission_format.csv columns")
        uids = [(row.get("uid") or "").strip() for row in reader]
    if any(not uid for uid in uids) or len(uids) != len(set(uids)):
        raise RuntimeError("submission format has empty or duplicate uid")

    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("uid", "is_pathologic"))
        for uid in uids:
            scan = NIFTIS / f"{uid}.nii.gz"
            if not scan.is_file():
                raise FileNotFoundError(scan)
            # The predictor receives this scan path only; no prior prediction or other
            # test-row content is supplied. It must not fit/retrain on test data.
            probability = float(predict_probability(scan))
            if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
                raise RuntimeError("model returned invalid probability")
            writer.writerow((uid, probability))

if __name__ == "__main__":
    main()
