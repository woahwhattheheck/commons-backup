"""Buyer-neutral multi-framework evidence freshness gate."""

from . import gate as _gate
from .custody import read_bounded_regular as _read_bounded_regular

# Install the hardened retained-descriptor reader before exposing the public
# gate surface. Normal package/submodule imports execute this package first,
# so gate.load_strict_json() resolves the hardened generation reader.
_gate._read_bounded_regular = _read_bounded_regular

compile_packet = _gate.compile_packet
verify_packet = _gate.verify_packet
render_markdown = _gate.render_markdown
load_strict_json = _gate.load_strict_json

__all__ = ["compile_packet", "verify_packet", "render_markdown", "load_strict_json"]
