# SPDX-License-Identifier: Apache-2.0
"""Add one default-OFF V4 lane without executing the input generator.

This ancestry-neutral donor edits only literal postimages of the established
V4 recipe and adds a literal Policy.act seam. The queue owner must bind the
then-current source with --expected-blob; no refs, archives or flags are moved.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

KEY = 'r04_fast_tape_clone'
FLAG = 'FAST_TAPE_CLONE'
OLD_CLONE = '        action = copy.deepcopy(tape[step])\n'
NEW_CLONE = (
    '        if FAST_TAPE_CLONE:\n'
    '            import r04_fast_tape_clone\n'
    '            action = r04_fast_tape_clone.apply_fast_tape_clone(tape[step])\n'
    '        else:\n'
    '            action = copy.deepcopy(tape[step])\n'
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def once(text, old, new):
    require(text.count(old) == 1, 'missing or duplicate literal anchor: ' + repr(old))
    return text.replace(old, new, 1)


def transform(source):
    require(type(source) is bytes, 'source must be bytes')
    source.decode('utf-8')
    require(KEY.encode() not in source and FLAG.encode() not in source, 'lane already present')
    tree = ast.parse(source)
    keys = [n for n in tree.body if isinstance(n, ast.Assign)
            and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id == 'KEYS']
    require(len(keys) == 1 and isinstance(keys[0].value, ast.Tuple), 'unique literal KEYS tuple required')
    values = ast.literal_eval(keys[0].value)
    require(all(type(v) is str and v.startswith('r04_') for v in values), 'nonliteral lane key')
    require(len(values) == len(set(values)), 'duplicate existing key')
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'apply']
    require(len(funcs) == 1, 'unique apply function required')
    body = funcs[0].body
    patches = {}
    writer = []
    for statement in body:
        if (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Name) and statement.value.func.id == 'write'
                and len(statement.value.args) == 2
                and isinstance(statement.value.args[0], ast.Constant)
                and statement.value.args[0].value == 'r04_full_router.py'):
            require(isinstance(statement.value.args[1], ast.Name)
                    and statement.value.args[1].id == 'router', 'unexpected router write')
            writer.append(statement)
        if not (isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Name)
                and statement.value.func.id == '_replace_once'):
            continue
        call = statement.value
        require(len(call.args) == 4 and not call.keywords, 'unexpected patch call')
        require(len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name), 'patch target')
        target = statement.targets[0].id
        require(isinstance(call.args[0], ast.Name) and call.args[0].id == target, 'patch receiver')
        require(all(isinstance(n, ast.Constant) and type(n.value) is str for n in call.args[1:]),
                'nonliteral patch operands')
        label = call.args[3].value
        require(label not in patches, 'duplicate patch label')
        patches[label] = (target, call.args[2], call.args[2].value)
    require(len(writer) == 1, 'unique router writer required')
    changes = [(keys[0].value, repr(values + (KEY,)))]

    def edit(label, target, function):
        require(label in patches and patches[label][0] == target, 'missing expected patch: ' + label)
        _, node, value = patches[label]
        if target == 'router':
            require(node.lineno < writer[0].lineno, 'router patch after write')
        changes.append((node, repr(function(value))))

    edit('R04 V4 flags', 'router', lambda s: once(s, '_TERMINAL_FERTILIZER_AGENT = None\n',
         FLAG + ' = False\n_TERMINAL_FERTILIZER_AGENT = None\n'))
    edit('R04 V4 install parameters', 'router', lambda s: once(s, '):\n', ', fast_tape_clone=None):\n'))
    edit('R04 V4 globals', 'router', lambda s: once(s, '\n', ', FAST_TAPE_CLONE\n'))
    edit('R04 V4 install setters', 'router', lambda s: once(s, '    return v3_agent\n',
         '    if fast_tape_clone is not None:\n        FAST_TAPE_CLONE = bool(fast_tape_clone)\n'
         '    return v3_agent\n'))
    edit('Features V4 fields', 'runtime', lambda s: once(s, '\n\n    def __post_init__(self):',
         '\n    r04_fast_tape_clone: bool = False\n\n    def __post_init__(self):'))
    edit('TitanAgent V4 install arguments', 'runtime', lambda s: once(s, '))(observation, configuration)\n',
         '),\n                                 fast_tape_clone=bool(self.features.r04_fast_tape_clone))'
         '(observation, configuration)\n'))
    edit('TitanAgent V4 diagnostics', 'runtime', lambda s: s +
         "                self.diagnostics['fast_tape_clone'] = bool(self.features.r04_fast_tape_clone)\n")
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    spans = []
    for node, replacement in changes:
        a = starts[node.lineno - 1] + node.col_offset
        b = starts[node.end_lineno - 1] + node.end_col_offset
        spans.append((a, b, replacement.encode()))
    offset = starts[writer[0].lineno - 1]
    insertion = ('    router = _replace_once(\n        router, ' + repr(OLD_CLONE) + ',\n        '
                 + repr(NEW_CLONE) + ", 'R04 V4 fast tape clone seam')\n").encode()
    spans.append((offset, offset, insertion))
    spans.sort()
    require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), 'overlapping edits')
    result = source
    for a, b, replacement in reversed(spans):
        result = result[:a] + replacement + result[b:]
    compile(result, '<V4 fast-clone generator>', 'exec')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--expected-blob', required=True)
    args = parser.parse_args()
    require(args.source.resolve() != args.output.resolve(), 'output must not overwrite source')
    data = args.source.read_bytes()
    require(git_blob(data) == args.expected_blob, 'input Git blob mismatch')
    result = transform(data)
    with args.output.open('xb') as handle:
        handle.write(result)
    require(args.output.read_bytes() == result, 'output readback mismatch')
    print(json.dumps({'input_blob': git_blob(data), 'output_blob': git_blob(result),
                      'bytes': len(result), 'sha256': hashlib.sha256(result).hexdigest(),
                      'key': KEY, 'default': False}, sort_keys=True))


if __name__ == '__main__':
    main()
