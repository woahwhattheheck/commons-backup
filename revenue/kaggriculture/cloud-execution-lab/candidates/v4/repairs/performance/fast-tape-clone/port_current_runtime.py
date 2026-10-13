# SPDX-License-Identifier: Apache-2.0
"""Port recovered #12431 cloning into the current TitanAgent checkpoint.

This is NOT the legacy R04 materializer. It adds one default-OFF Features
field and one branch inside TitanAgent.act's existing deadline context.
The caller must authenticate the exact source; this tool never overwrites it,
changes a configuration, runs a source generator, or enables the feature.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

KEY = 'r04_fast_tape_clone'
REFERENCE_RUNTIME = 'b952c9c228ecbde592bf3d2df01638677abb0d24'
OLD_FIELD = '    early_capital: bool = False\n'
NEW_FIELD = OLD_FIELD + '    r04_fast_tape_clone: bool = False\n'
OLD_CHECKPOINT = '                self.selected = deepcopy(selected)\n'
NEW_CHECKPOINT = (
    '                if self.features.r04_fast_tape_clone:\n'
    '                    from r04_fast_tape_clone import apply_fast_tape_clone\n'
    '                    self.selected = apply_fast_tape_clone(selected)\n'
    '                else:\n'
    '                    self.selected = deepcopy(selected)\n'
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def only_class(tree, name):
    matches = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name]
    require(len(matches) == 1, 'unique top-level class required: ' + name)
    return matches[0]


def transform(source, expected_blob):
    require(type(source) is bytes, 'source must be bytes')
    require(type(expected_blob) is str and len(expected_blob) == 40,
            'explicit full input Git blob required')
    require(git_blob(source) == expected_blob, 'input Git blob mismatch')
    require(b'\r' not in source, 'LF source required')
    require(KEY.encode() not in source, 'feature already present')
    text = source.decode('utf-8')
    tree = ast.parse(source)
    features = only_class(tree, 'Features')
    agent = only_class(tree, 'TitanAgent')
    fields = [n for n in features.body if isinstance(n, ast.AnnAssign)]
    require(fields and isinstance(fields[-1].target, ast.Name)
            and fields[-1].target.id == 'early_capital', 'feature field append boundary changed')
    field = fields[-1]
    require(ast.get_source_segment(text, field) == 'early_capital: bool = False',
            'feature field source changed')
    methods = [n for n in agent.body if isinstance(n, ast.FunctionDef) and n.name == 'act']
    require(len(methods) == 1, 'unique TitanAgent.act required')
    act = methods[0]
    # Require the real current checkpoint, directly after production, in its
    # original timer. Do not accept lookalikes in nested functions or strings.
    tries = [n for n in act.body if isinstance(n, ast.Try)]
    require(len(tries) == 1, 'unique action try required')
    contexts = [n for n in tries[0].body if isinstance(n, ast.With)]
    require(len(contexts) == 1, 'unique action deadline context required')
    context = contexts[0]
    require(len(context.items) == 1 and isinstance(context.items[0].context_expr, ast.Name)
            and context.items[0].context_expr.id == 'timer', 'deadline context changed')
    checkpoints = [n for n in context.body if isinstance(n, ast.Assign)
                   and ast.get_source_segment(text, n) == 'self.selected = deepcopy(selected)']
    require(len(checkpoints) == 1, 'unique in-timer selected checkpoint required')
    checkpoint = checkpoints[0]
    index = context.body.index(checkpoint)
    require(index > 0 and index + 1 < len(context.body), 'checkpoint neighbors missing')
    require(ast.get_source_segment(text, context.body[index - 1])
            == 'selected = self.production.act(obs)', 'production neighbor changed')
    require(ast.get_source_segment(text, context.body[index + 1])
            == 'selected_checkpoint = (self.selected, self.controller.cur)',
            'checkpoint commit neighbor changed')
    lines = text.splitlines(keepends=True)
    require(lines[field.lineno - 1] == OLD_FIELD, 'field line changed')
    require(lines[checkpoint.lineno - 1] == OLD_CHECKPOINT, 'checkpoint line changed')
    require(text.count(OLD_FIELD) == text.count(OLD_CHECKPOINT) == 1,
            'duplicate textual anchor')
    # Only two known lines are replaced; all unrelated source bytes survive.
    lines[checkpoint.lineno - 1] = NEW_CHECKPOINT
    lines[field.lineno - 1] = NEW_FIELD
    result = ''.join(lines).encode('utf-8')
    compile(result, '<current-runtime fast-clone port>', 'exec')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--expected-blob', required=True)
    args = parser.parse_args()
    require(args.source.resolve() != args.output.resolve(), 'source cannot be overwritten')
    source = args.source.read_bytes()
    result = transform(source, args.expected_blob)
    with args.output.open('xb') as handle:
        handle.write(result)
    require(args.output.read_bytes() == result, 'output readback mismatch')
    print(json.dumps({'input_blob': git_blob(source), 'output_blob': git_blob(result),
                      'bytes': len(result), 'sha256': hashlib.sha256(result).hexdigest(),
                      'feature': KEY, 'default': False}, sort_keys=True))


if __name__ == '__main__':
    main()
