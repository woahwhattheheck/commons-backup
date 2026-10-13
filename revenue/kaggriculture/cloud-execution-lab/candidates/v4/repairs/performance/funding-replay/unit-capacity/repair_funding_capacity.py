"""Source-only repair of the current frozen funding trace's physical shed limit.

This does not install, enable or publish a policy. Only the authenticated
_funding_trace unit-call argument changes; other capacity-pressure simulations
intentionally retain their oversized limit.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path

FUNCTION_SHA256 = 'd9ca4d0737b5ab3344c0df588014a83a5c634464327fdd175b8ec862c2d7beb9'
OLD_CALL = "m._apply_unit_action(f, p, i, a, len(f['tiles']), t // 24, 24, 10**6)"
NEW_CALL = "m._apply_unit_action(f, p, i, a, len(f['tiles']), t // 24, 24, cap)"


def function_span(source: str) -> tuple[int, int]:
    """Return the unique top-level function's exact source-character span."""
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == '_funding_trace']
    if len(nodes) != 1 or not isinstance(nodes[0], ast.FunctionDef):
        raise ValueError('Expected one synchronous top-level _funding_trace')
    n = nodes[0]
    if n.decorator_list:
        raise ValueError('Decorated funding trace is not the authenticated input')
    lines = source.splitlines(keepends=True)
    return sum(map(len, lines[:n.lineno-1])), sum(map(len, lines[:n.end_lineno]))


def repair(source: str) -> str:
    """Patch the pinned function while retaining every unrelated source byte."""
    compile(source, '<funding-input>', 'exec')
    start, end = function_span(source)
    original = source[start:end]
    digest = hashlib.sha256(original.encode('utf-8')).hexdigest()
    normalized = original.replace(NEW_CALL, OLD_CALL)
    if (original.count(NEW_CALL) == 1 and OLD_CALL not in original
            and hashlib.sha256(normalized.encode('utf-8')).hexdigest() == FUNCTION_SHA256):
        return source  # Exact repaired function; idempotent composition.
    if digest != FUNCTION_SHA256 or original.count(OLD_CALL) != 1:
        raise ValueError('Funding-function drift: compose manually, do not overwrite peer work')
    changed = original.replace(OLD_CALL, NEW_CALL, 1)
    result = source[:start] + changed + source[end:]
    compile(result, '<funding-output>', 'exec')
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        # Byte decoding avoids newline normalization of unrelated source text.
        raw = args.source.read_bytes()
        output = repair(raw.decode('utf-8')).encode('utf-8')
        # Exclusive creation prevents an implicit runtime/source overwrite.
        with args.output.open('xb') as stream:
            stream.write(output)
        print(hashlib.sha256(output).hexdigest())
        return 0
    except (OSError, ValueError, SyntaxError) as exc:
        parser.exit(2, f'funding capacity repair: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
