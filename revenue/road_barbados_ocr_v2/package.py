from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

FILES = [
    "revenue/road_barbados_ocr_v2/__init__.py",
    "revenue/road_barbados_ocr_v2/core.py",
    "revenue/road_barbados_ocr_v2/profile.py",
    "revenue/road_barbados_ocr_v2/artifacts.py",
    "revenue/road_barbados_ocr_v2/engine.py",
    "revenue/road_barbados_ocr_v2/cli.py",
    "revenue/road_barbados_ocr_v2/package.py",
    "revenue/road_barbados_ocr_v2/test_support.py",
    "revenue/road_barbados_ocr_v2/test_policy.py",
    "revenue/road_barbados_ocr_v2/test_pipeline.py",
    "revenue/road_barbados_ocr_v2/test_engine.py",
    "revenue/road_barbados_ocr_v2/README.md",
    "revenue/road_barbados_ocr_v2/rules.json",
    ".github/workflows/road-ocr-v2.yml",
]


def build(root: Path, output: Path, sbom: Path) -> dict:
    rows = []
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(FILES):
            data = (root / name).read_bytes()
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
            rows.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    result = {
        "format": 1,
        "product": "ROAD_OCR_V2_SOURCE_PACKAGE",
        "files": rows,
        "archive_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "authority": {
            "challenge_data_included": False,
            "model_weights_included": False,
            "zindi_submission_included": False,
        },
    }
    sbom.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return result


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    output = root / "road_ocr_v2_source.zip"
    sbom = root / "road_ocr_v2_sbom.json"
    for path in (output, sbom):
        if path.exists():
            path.unlink()
    result = build(root, output, sbom)
    print(result["archive_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
