#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only TITAN archive/consumer mechanics preflight (Python 3.10+).

Does not import the archive, run games, enable a feature, or repair source.
Direct ``import mechanics``/``from mechanics import`` references are inferred.
For dependency-injected parameters, use --alias mechanics (or self.mechanics).
This is a bounded static check, not a full proof of dynamic Python behavior.
"""
from __future__ import annotations

import argparse
import ast
import builtins
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import symtable
import sys
import tarfile
from typing import Any

MAX_ARCHIVE = 32 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_MEMBERS = 2000


class InvalidArchive(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_archive(path: Path, expected_sha256: str | None = None) -> tuple[dict[str, bytes], dict[str, Any]]:
    if path.stat().st_size > MAX_ARCHIVE:
        raise InvalidArchive('compressed archive exceeds size limit')
    data = path.read_bytes()
    digest = sha256(data)
    if expected_sha256 is not None and digest != expected_sha256:
        raise InvalidArchive('archive SHA256 does not match expected bytes')
    members: dict[str, bytes] = {}
    seen: set[str] = set()
    expanded = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
        for number, member in enumerate(archive, 1):
            if number > MAX_MEMBERS:
                raise InvalidArchive('too many archive members')
            name = member.name
            parts = PurePosixPath(name)
            if not name or parts.is_absolute() or '..' in parts.parts or '\\' in name:
                raise InvalidArchive(f'unsafe member name: {name!r}')
            normalized = str(parts)
            if normalized in ('.', '') or normalized in seen:
                raise InvalidArchive(f'empty or duplicate member: {name!r}')
            seen.add(normalized)
            if member.isdir():
                continue
            if not member.isfile():
                raise InvalidArchive(f'non-regular member: {name!r}')
            expanded += member.size
            if member.size < 0 or expanded > MAX_EXPANDED:
                raise InvalidArchive('expanded archive exceeds size limit')
            stream = archive.extractfile(member)
            if stream is None:
                raise InvalidArchive(f'unreadable member: {name!r}')
            value = stream.read(member.size + 1)
            if len(value) != member.size:
                raise InvalidArchive(f'incomplete member: {name!r}')
            members[normalized] = value
    if 'SOURCE.json' not in members or 'mechanics.py' not in members:
        raise InvalidArchive('SOURCE.json and mechanics.py are required')
    source = json.loads(members['SOURCE.json'])
    if not isinstance(source, dict):
        raise InvalidArchive('SOURCE.json must be an object')
    runtime = source.get('runtime')
    if not isinstance(runtime, dict):
        raise InvalidArchive('SOURCE.json runtime must be a mapping')
    if set(runtime) != set(members) - {'SOURCE.json'}:
        missing = sorted(set(runtime) - set(members))
        extra = sorted(set(members) - set(runtime) - {'SOURCE.json'})
        raise InvalidArchive(f'manifest membership mismatch: missing={missing}, extra={extra}')
    for name, spec in runtime.items():
        if not isinstance(spec, dict):
            raise InvalidArchive(f'invalid manifest record: {name}')
        payload = members[name]
        if spec.get('bytes') != len(payload) or spec.get('sha256') != sha256(payload):
            raise InvalidArchive(f'manifest digest/size mismatch: {name}')
    return members, {'archive_sha256': digest, 'archive_bytes': len(data),
                     'source_sha256': sha256(members['SOURCE.json']),
                     'runtime_files_verified': len(runtime), 'expanded_bytes': expanded}


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        root = _dotted(node.value)
        return f'{root}.{node.attr}' if root else None
    return None


def consumer_requirements(text: str, filename: str, aliases: tuple[str, ...] = ()) -> dict[str, Any]:
    """Conservative lexical references; aliases must identify actual mechanics objects.

    Import aliases are collected throughout this file, so shadowing can over-report.
    Dynamic getattr is reported as unresolved rather than certified complete.
    """
    tree = ast.parse(text, filename)
    names = set(aliases)
    required: dict[str, list[int]] = {}
    dynamic: list[int] = []
    def add(name: str, lineno: int) -> None:
        required.setdefault(name, []).append(lineno)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name == 'mechanics':
                    names.add(imported.asname or imported.name)
        elif isinstance(node, ast.ImportFrom) and node.module == 'mechanics':
            for imported in node.names:
                if imported.name == '*':
                    dynamic.append(node.lineno)
                else:
                    add(imported.name, node.lineno)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and _dotted(node.value) in names:
            if isinstance(node.ctx, ast.Load):
                add(node.attr, node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ('getattr', 'hasattr') and node.args and _dotted(node.args[0]) in names:
                # hasattr/defaulted getattr are optional queries, not mandatory dependencies.
                if (node.func.id == 'getattr' and len(node.args) == 2
                        and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
                    add(node.args[1].value, node.lineno)
                else:
                    dynamic.append(node.lineno)
    return {'path': filename, 'sha256': sha256(text.encode()),
            'aliases': sorted(names),
            'required': {key: sorted(set(value)) for key, value in sorted(required.items())},
            'unresolved_dynamic_lines': sorted(set(dynamic))}


def provider_inventory(text: str) -> tuple[set[str], dict[str, list[str]]]:
    table = symtable.symtable(text, 'mechanics.py', 'exec')
    exports = {s.get_name() for s in table.get_symbols()
               if s.is_assigned() or s.is_imported() or s.is_namespace()}
    builtin_names = set(dir(builtins)) | {'__name__', '__file__', '__package__', '__doc__', '__builtins__'}
    undefined: dict[str, list[str]] = {}
    def walk(scope: Any, name: str) -> None:
        missing = sorted({s.get_name() for s in scope.get_symbols()
                          if s.is_global() and s.is_referenced()
                          and s.get_name() not in exports | builtin_names})
        if missing:
            undefined[name] = missing
        for child in scope.get_children():
            walk(child, f'{name}.{child.get_name()}')
    walk(table, 'mechanics')
    return exports, undefined


def check_contract(provider: str, consumers: list[dict[str, Any]]) -> dict[str, Any]:
    exports, undefined = provider_inventory(provider)
    missing = []
    unresolved = []
    for consumer in consumers:
        for name, lines in consumer['required'].items():
            if name not in exports:
                missing.append({'consumer': consumer['path'], 'name': name, 'lines': lines})
        if consumer['unresolved_dynamic_lines']:
            unresolved.append({'consumer': consumer['path'], 'lines': consumer['unresolved_dynamic_lines']})
    status = 'FAIL' if missing or undefined else ('REVIEW' if unresolved else 'PASS')
    return {'status': status, 'missing_api': missing,
            'undefined_provider_globals': undefined, 'unresolved_dynamic_access': unresolved,
            'consumer_count': len(consumers),
            'distinct_required_names': sorted({name for c in consumers for name in c['required']}),
            'scope': 'Static direct mechanics references and provider globals only; no gameplay or dynamic-import proof.'}



def selected_provider(members: dict[str, bytes], path: str) -> tuple[str, dict[str, Any]]:
    """Resolve only the archived, exact known terminal-mechanics base-copy form.

    Never executes imports or globals().update. Rejects other composition forms
    instead of silently assuming a supplied base provides an injected API.
    """
    if path not in members:
        raise InvalidArchive(f'provider not found in archive: {path}')
    text = members[path].decode('utf-8')
    identity: dict[str, Any] = {'path': path, 'sha256': sha256(members[path])}
    if path == 'mechanics.py':
        return text, identity
    tree = ast.parse(text, path)
    base_aliases = [(index, item.asname or item.name)
                    for index, node in enumerate(tree.body) if isinstance(node, ast.Import)
                    for item in node.names if item.name == 'mechanics']
    recognized = []
    for index, alias in base_aliases:
        template = ast.parse(f'globals().update({{k:v for k,v in vars({alias}).items() if not k.startswith("__")}})').body[0]
        matches = [position for position, node in enumerate(tree.body)
                   if ast.dump(node, include_attributes=False) == ast.dump(template, include_attributes=False)]
        if len(matches) == 1 and index < matches[0]:
            recognized.append((alias, matches[0]))
    if len(recognized) != 1:
        raise InvalidArchive('non-default provider must use the recognized explicit mechanics base-copy form')
    alias, copy_index = recognized[0]
    # Copy must precede all wrapper definitions, and wrappers cannot override
    # base exports: concatenation would otherwise alter global resolution.
    base_text = members['mechanics.py'].decode('utf-8')
    base_exports, _ = provider_inventory(base_text)
    own_definitions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    if any(tree.body.index(node) < copy_index for node in own_definitions):
        raise InvalidArchive('wrapper definitions precede the base copy')
    if any(node.name in base_exports for node in own_definitions):
        raise InvalidArchive('wrapper overrides a base export; static composition requires review')
    identity['base'] = {'path': 'mechanics.py', 'sha256': sha256(members['mechanics.py'])}
    identity['composition'] = 'Recognized unchanged globals-copy wrapper, composed statically; not imported'
    return base_text + '\n' + text, identity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--provider', default='mechanics.py',
                        help='Archived provider injected into additional consumers only; root imports remain mechanics.py.')
    parser.add_argument('--consumer', type=Path, action='append', default=[],
                        help='Additional proposed consumer; repeat for several files.')
    parser.add_argument('--alias', action='append', default=[],
                        help='Mechanics injection path in additional consumers, e.g. mechanics or self.m.')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.report and args.report.resolve() in {args.archive.resolve(), *(path.resolve() for path in args.consumer)}:
        parser.error('--report cannot overwrite an archive or consumer input')
    if args.expected_sha256 and not re.fullmatch(r'[a-f0-9]{64}', args.expected_sha256):
        parser.error('--expected-sha256 must be 64 lowercase hex characters')
    try:
        members, archive_info = read_archive(args.archive, args.expected_sha256)
        # Only root runtime modules directly bind this particular mechanics module.
        # Vendored references use separate loaders/namespaces; add them explicitly as needed.
        consumers = [consumer_requirements(value.decode('utf-8'), name)
                     for name, value in sorted(members.items())
                     if name.endswith('.py') and '/' not in name and name != 'mechanics.py']
        proposed = [consumer_requirements(path.read_text(encoding='utf-8'), str(path), tuple(args.alias))
                    for path in args.consumer]
        provider_text, provider_identity = selected_provider(members, args.provider)
        packaged = check_contract(members['mechanics.py'].decode(), consumers)
        external = check_contract(provider_text, proposed)
        statuses = {packaged['status'], external['status']}
        overall = 'FAIL' if 'FAIL' in statuses else ('REVIEW' if 'REVIEW' in statuses else 'PASS')
        report = {'archive': archive_info, 'contract': {'status': overall,
                  'packaged_direct': packaged, 'proposed_consumers': external},
                  'proposed_provider': provider_identity, 'consumers': consumers + proposed}
        code = 0 if overall == 'PASS' else 1
    except (OSError, ValueError, SyntaxError, UnicodeError, tarfile.TarError) as exc:
        report = {'status': 'ERROR', 'error_type': type(exc).__name__, 'error': str(exc)}
        code = 2
    encoded = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.report:
        try:
            args.report.write_text(encoded, encoding='utf-8')
        except OSError as exc:
            print(f'Cannot write report: {exc}', file=sys.stderr)
            return 2
    print(encoded, end='')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
