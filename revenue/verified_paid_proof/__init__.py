"""Verified paid-proof compiler."""
from .core import ProofError, strict_json_loads
from .compiler import (
    compile_proof,
    compile_text,
    public_json,
    public_payload,
)
from .custody import write_outputs
from . import compiler as _compiler

# Keep the historical module import path safe as well as the package/CLI surface.
_compiler.write_outputs = write_outputs

__all__ = [
    "ProofError",
    "compile_proof",
    "compile_text",
    "public_json",
    "public_payload",
    "strict_json_loads",
    "write_outputs",
]
