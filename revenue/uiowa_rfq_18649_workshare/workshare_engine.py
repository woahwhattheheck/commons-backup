#!/usr/bin/env python3
"""Compatibility facade for compilation, verification, and rendering."""
from workshare_compile import compile_current, compile_historical, compile_untrusted_inspection
from workshare_verify import verify_current, verify_report_integrity, _verify_receipt
from workshare_render import render_markdown
