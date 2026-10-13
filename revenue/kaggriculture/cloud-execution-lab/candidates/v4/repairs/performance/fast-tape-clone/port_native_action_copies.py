# SPDX-License-Identifier: Apache-2.0
"""Stage native action-only clone consumers; never install or change Features.

Reuse the existing ORBIT helper. No observation, farm, private, receipt, market
row, deadline, or checkpoint copy is replaced. Explicit reviewed input pins
permit semantic composition without replacing a peer's whole-file postimage.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

HELPER_BLOB = 'b7c1fd2f7f786c5dc5f8a3b9a7116815ea40607a'
PINS = {
    'integrated_selected.py': 'defa9b84c77fff28ae107bce291b6235bec5d26c',
    'frozen_selected.py': 'fc7baf5c179818a55037f6a61d92984d81d1a21c',
    'spatial_tempo.py': 'edbc423023479dbe2e78131495334384a87b607f',
}
ALIAS = '_tapeport_clone_action'
IMPORT = 'from r04_fast_tape_clone import apply_fast_tape_clone as ' + ALIAS + '\n'
# Each key binds the actual lexical class/function and complete action argument.
TARGETS = {
    'integrated_selected.py': {
        ('IntegratedSelectedAgent._projection', 'route[step]'): 1,
        ('IntegratedSelectedAgent.transform', 'selected'): 4,
        ('IntegratedSelectedAgent.transform', 'proposed'): 1,
        ('IntegratedSelectedAgent.transform', 'seeded'): 2,
        ('IntegratedSelectedAgent.transform', 'fallback'): 1,
    },
    'frozen_selected.py': {('FrozenSelected.transform', 'base'): 2},
    'spatial_tempo.py': {
        ('SpatialTempo.guard_crop_returned', 'returned'): 2,
        ('SpatialTempo.guard_returned', 'returned'): 2,
        ('SpatialTempo._begin', 'routes[route][t]'): 1,
        ('SpatialTempo._repair_positions', 'route[now + k]'): 2,
        ('SpatialTempo.install.act', 'result'): 1,
        ('SpatialTempo._weed_witness', 'route[t]'): 1,
        ('SpatialTempo._continue_weed', 'route[t]'): 1,
        ('SpatialTempo._deliver_idle_fertilizer', 'selected'): 2,
        ('SpatialTempo._collect_idle_fertilizer', 'selected'): 1,
        ('SpatialTempo._collect_idle_fertilizer', 'route[t]'): 1,
        ('SpatialTempo.transform', 'selected'): 1,
        ('SpatialTempo.transform', 'old'): 1,
    },
}


def blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def _calls(tree):
    found = []
    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.scope = []
        def visit_ClassDef(self, node):
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()
        visit_FunctionDef = visit_ClassDef
        visit_AsyncFunctionDef = visit_ClassDef
        def visit_Call(self, node):
            if len(node.args) == 1 and not node.keywords:
                found.append(('.'.join(self.scope), ast.unparse(node.args[0]), node))
            self.generic_visit(node)
    Visitor().visit(tree)
    return found


def compose(sources: dict[str, bytes], helper: bytes, *, enabled: bool = False,
            pins: dict[str, str] | None = None) -> dict[str, bytes]:
    """Return detached source mapping. Enabled is a staging switch, not a key.

    Nonbaseline pins MUST be independently reviewed by the integrating caller;
    this adapter validates identity and edit boundaries, not peer-policy merit.
    """
    if type(enabled) is not bool:
        raise ValueError('enabled must be a literal bool')
    pins = PINS if pins is None else pins
    if set(pins) != set(PINS) or set(sources) != set(PINS):
        raise ValueError('exact three-source mapping required')
    if blob(helper) != HELPER_BLOB:
        raise ValueError('existing helper identity mismatch')
    outputs = {}
    for name, data in sources.items():
        if blob(data) != pins[name]:
            raise ValueError('input identity mismatch: ' + name)
        source = data.decode('utf-8')
        tree = ast.parse(source)
        if ALIAS in source or 'r04_fast_tape_clone' in source:
            raise ValueError('already applied or overlapping helper import: ' + name)
        edits, counts = [], Counter()
        lines = data.splitlines(keepends=True)
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        function = 'copy.deepcopy' if name == 'frozen_selected.py' else 'deepcopy'
        for scope, argument, node in _calls(tree):
            key = (scope, argument)
            if key in TARGETS[name] and ast.unparse(node.func) == function:
                counts[key] += 1
                start = offsets[node.func.lineno-1] + node.func.col_offset
                end = offsets[node.func.end_lineno-1] + node.func.end_col_offset
                edits.append((start, end, ALIAS.encode()))
        if counts != Counter(TARGETS[name]):
            raise ValueError('action consumer cardinality/scope drift: ' + name)
        imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
        if not imports:
            raise ValueError('missing module import boundary')
        at = offsets[imports[-1].end_lineno]
        edits.append((at, at, IMPORT.encode()))
        candidate = data
        for start, end, replacement in sorted(edits, reverse=True):
            candidate = candidate[:start] + replacement + candidate[end:]
        compile(candidate, name, 'exec')
        # The complete AST must be identical after undoing ONLY our call aliases
        # and import; this disallows opportunistic policy edits in the transform.
        restored = ast.parse(candidate)
        restored.body = [n for n in restored.body if not (
            isinstance(n, ast.ImportFrom) and n.module == 'r04_fast_tape_clone')]
        for _, _, node in _calls(restored):
            if isinstance(node.func, ast.Name) and node.func.id == ALIAS:
                node.func = ast.parse(function, mode='eval').body
        if ast.dump(tree, include_attributes=False) != ast.dump(restored, include_attributes=False):
            raise ValueError('non-copy semantic edit: ' + name)
        outputs[name] = candidate if enabled else data
    if enabled:
        outputs['r04_fast_tape_clone.py'] = helper
    return outputs


def stage(root: Path, output: Path, helper: Path, *, enabled: bool = False,
          pins: dict[str, str] | None = None) -> dict[str, str]:
    root, output = root.resolve(), output.resolve()
    if output.exists() or output == root or root in output.parents:
        raise ValueError('output must be a new directory outside input')
    originals = {name: (root/name).read_bytes() for name in PINS}
    outputs = compose(originals, helper.read_bytes(), enabled=enabled, pins=pins)
    output.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='.tapeport-', dir=output.parent))
    try:
        shutil.copytree(root, scratch/'package', ignore=shutil.ignore_patterns('__pycache__'))
        for name, data in outputs.items():
            (scratch/'package'/name).write_bytes(data)
        if any((root/name).read_bytes() != data for name, data in originals.items()):
            raise ValueError('input moved during staging')
        # copytree reserves the output with an exclusive mkdir; it never
        # replaces an empty directory created by a concurrent caller.
        shutil.copytree(scratch/'package', output)
    finally:
        shutil.rmtree(scratch)
    return {name: blob(data) for name, data in outputs.items()}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--helper', type=Path, default=Path(__file__).with_name('r04_fast_tape_clone.py'))
    p.add_argument('--enable', action='store_true')
    p.add_argument('--pins', type=Path, help='explicit independently reviewed composition pins JSON')
    a = p.parse_args()
    print(json.dumps(stage(a.root, a.output, a.helper, enabled=a.enable,
                           pins=json.loads(a.pins.read_text()) if a.pins else None), indent=2))
