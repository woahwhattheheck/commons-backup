from __future__ import annotations

import json
import unittest
from pathlib import Path

# Re-export the product's hostile contract suite into the retained root battery.
# host/ci_battery.py discovers root test_*.py files, not nested revenue suites.
from revenue.procurement_runway_gate.test_gate import GateTests  # noqa: F401


ROOT = Path(__file__).resolve().parent
STANDALONE = ROOT / ".github" / "workflows" / "procurement-runway-gate.yml"
PATH_MANIFEST = ROOT / ".github" / "workflows" / "path-manifest.yml"
SURFACE = ROOT / "ci" / "workflow-surface.json"


class ProcurementRunwayWorkflowBudgetTests(unittest.TestCase):
    def test_procurement_gate_does_not_consume_a_68th_workflow_slot(self) -> None:
        manifest = json.loads(SURFACE.read_text(encoding="utf-8"))
        workflow_dir = ROOT / ".github" / "workflows"
        active = sorted(
            path
            for path in workflow_dir.iterdir()
            if path.is_file() and path.suffix in {".yml", ".yaml"}
        )
        self.assertEqual(manifest["max_active_workflows"], 67)
        self.assertLessEqual(len(active), manifest["max_active_workflows"])
        self.assertFalse(STANDALONE.exists())
        self.assertNotIn(
            ".github/workflows/procurement-runway-gate.yml",
            manifest["retained"],
        )

    def test_retained_path_manifest_preserves_direct_main_push_trigger(self) -> None:
        workflow = PATH_MANIFEST.read_text(encoding="utf-8")

        # Bind the retired standalone workflow's direct-main-push coverage to the
        # retained in-slot workflow. A generic product-path substring is not enough:
        # deleting the entire push event must make this predecessor fail.
        push_start = workflow.index("  push:\n")
        workflow_dispatch_start = workflow.index("  workflow_dispatch:\n", push_start)
        push_block = workflow[push_start:workflow_dispatch_start]
        self.assertIn("    branches:\n      - main\n", push_block)
        for path in (
            "revenue/procurement_runway_gate/**",
            "test_procurement_runway_workflow_budget.py",
            ".github/workflows/path-manifest.yml",
        ):
            self.assertIn(f"      - '{path}'\n", push_block)

        detect_start = workflow.index("      - name: detect procurement runway gate delta\n")
        setup_start = workflow.index("      - uses: actions/setup-python@v5\n", detect_start)
        detect_block = workflow[detect_start:setup_start]
        self.assertIn("EVENT_NAME: ${{ github.event_name }}", detect_block)
        self.assertIn(
            'if [ "$EVENT_NAME" = "workflow_dispatch" ] || [ "$EVENT_NAME" = "push" ]; then',
            detect_block,
        )
        self.assertIn("echo 'changed=true' >> \"$GITHUB_OUTPUT\"", detect_block)

    def test_retained_path_manifest_preserves_full_product_proof(self) -> None:
        workflow = PATH_MANIFEST.read_text(encoding="utf-8")
        required = (
            "revenue/procurement_runway_gate",
            "python-version: '3.11'",
            "python-version: '3.13'",
            "python -m py_compile revenue/procurement_runway_gate/*.py",
            "python -m unittest revenue.procurement_runway_gate.test_gate",
            "python -O -m unittest revenue.procurement_runway_gate.test_gate",
            "python -m revenue.procurement_runway_gate compile",
            "python -m revenue.procurement_runway_gate verify",
        )
        for needle in required:
            self.assertIn(needle, workflow)


if __name__ == "__main__":
    unittest.main()
