"""Fleet-wide advisory authority-boundary linter."""

from . import lint
from .js_provenance import install as _install_js_provenance

_install_js_provenance(lint)

from .lint import BASELINE_SCHEMA, REPORT_SCHEMA, Finding, build_report, render_markdown, run

__all__ = ["BASELINE_SCHEMA", "REPORT_SCHEMA", "Finding", "build_report", "render_markdown", "run", "lint"]
