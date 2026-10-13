"""Use the existing UIOWA-032 extractor and workshare implementation unchanged."""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "uiowa_rfq_18649_workshare"
EXTRACTOR = HERE.parent / "uiowa_rfq_18649_document_extraction" / "extract.py"


def workshare_modules():
    location = str(PARENT)
    if location not in sys.path:
        sys.path.insert(0, location)
    modules = [importlib.import_module(name) for name in
               ("workshare_compile", "workshare_verify", "workshare_core")]
    for module in modules:
        if Path(module.__file__).resolve().parent != PARENT:
            raise ValueError("Conflicting workshare import; use a fresh interpreter")
    return modules


def inspect(candidate: dict, authority: dict, evaluated_at: str) -> dict:
    compilation, _, _ = workshare_modules()
    report = compilation.compile_untrusted_inspection(candidate, authority, now=evaluated_at)
    verify_inspection(report)
    return report


def verify_inspection(report: dict) -> dict:
    _, verification, _ = workshare_modules()
    result = verification.verify_report_integrity(report)
    if report["mode"] != "UNTRUSTED_INSPECTION":
        raise ValueError("Citation workflow expects the workbench's UNTRUSTED_INSPECTION report")
    if report["trust"]["current_evidence_review_authority"] is not False:
        raise ValueError("Inspection must not carry current review authority")
    if any(flag is not False for flag in report["external_authority"].values()):
        raise ValueError("Inspection must not carry external authority")
    if any(cell["maturity"] is not None or cell["confidence_bp"] is not None
           for cell in report["assessment_matrix"]):
        raise ValueError("Public inspection cannot export maturity or confidence")
    return result


def extract_snapshot(data: bytes, name: str) -> dict:
    """Extract an immutable copy of the exact bytes being cited, not a live pathname."""
    module_name = "_uiowa_citation_existing_extractor"
    module = sys.modules.get(module_name)
    if module is None:
        spec = importlib.util.spec_from_file_location(module_name, EXTRACTOR)
        if spec is None or spec.loader is None:
            raise ValueError("UIOWA-032 extractor is missing from this checkout")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="uiowa-citation-") as temp:
        source = Path(temp) / Path(name).name
        source.write_bytes(data)
        result = module.extract(source)
    if result["document"]["sha256"] != hashlib.sha256(data).hexdigest():
        raise ValueError("Extractor/source digest disagreement")
    return result


def dependency_receipt() -> list[dict[str, Any]]:
    workshare_modules()
    paths = {EXTRACTOR}
    for name, module in list(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if name.startswith("workshare_") and filename:
            path = Path(filename).resolve()
            if path.parent == PARENT:
                paths.add(path)
    rows = []
    for path in sorted(paths):
        data = path.read_bytes()
        rows.append({"path": path.relative_to(HERE.parent.parent).as_posix(),
                     "sha256": hashlib.sha256(data).hexdigest(),
                     "git_blob_sha1": hashlib.sha1(
                         b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()})
    return rows
