#!/usr/bin/env python3
"""Build a private, runnable partner installation from a Parcel deployment JSON.

Uses only supplied files; does not fetch, deploy, send, or create customer records.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import stat
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELDS = ('name', 'email', 'phone', 'address', 'service', 'preferred_date', 'notes')
PRESETS = ('client-intake', 'quote-request', 'service-request')
MAX_DEPLOYMENT_BYTES = 12_000_000
MAX_RUNNER_FILE_BYTES = 4_000_000


def text(value, label, maximum=6000):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f'{label} must be text of at most {maximum} characters')
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f'Non-finite JSON value is not allowed: {value}')


def strict_json_bytes(data: bytes, label='JSON'):
    try:
        source = data.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError(f'{label} must be UTF-8 JSON') from exc
    try:
        return json.loads(source, object_pairs_hook=_pairs, parse_constant=_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f'{label} is not valid JSON: {exc.msg}') from exc


def _fingerprint(info):
    return (
        info.st_mode,
        info.st_dev,
        info.st_ino,
        info.st_size,
        getattr(info, 'st_mtime_ns', int(info.st_mtime * 1_000_000_000)),
        getattr(info, 'st_ctime_ns', int(info.st_ctime * 1_000_000_000)),
    )


def _read_bounded(fd, maximum: int, label: str):
    chunks = []
    total = 0
    while True:
        chunk = os.read(fd, min(65536, maximum + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > maximum:
            raise ValueError(f'{label} exceeds {maximum} bytes')
    return b''.join(chunks), total


def read_regular(path: Path, label: str, maximum: int) -> bytes:
    """Read exactly one retained regular-file generation without following a final symlink."""
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0)
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(os.fspath(path), flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f'{label} must be a regular file')
        if before.st_size > maximum:
            raise ValueError(f'{label} exceeds {maximum} bytes')
        data, total = _read_bounded(fd, maximum, label)
        after = os.fstat(fd)
        if _fingerprint(before) != _fingerprint(after) or total != after.st_size:
            raise ValueError(f'{label} changed while it was being read')
        os.lseek(fd, 0, os.SEEK_SET)
        again, total2 = _read_bounded(fd, maximum, label)
        after2 = os.fstat(fd)
        if again != data or total2 != total or _fingerprint(after) != _fingerprint(after2):
            raise ValueError(f'{label} changed while it was being read')
        return data
    finally:
        os.close(fd)


def _optional_regular(path: Path, label: str, maximum: int):
    try:
        return read_regular(path, label, maximum)
    except FileNotFoundError:
        return None


def validate(raw):
    if not isinstance(raw, dict) or raw.get('format') != 'parcel.intake-handoff' or raw.get('version') != 1:
        raise ValueError('Expected a version 1 Parcel deployment JSON')
    if raw.get('preset') not in PRESETS:
        raise ValueError('Unknown intake preset')
    for key in ('agency', 'client', 'title', 'support', 'scope'):
        text(raw.get(key), key)
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', text(raw.get('brand'), 'brand', 7)):
        raise ValueError('Invalid brand color')
    mapping = raw.get('fieldMapping')
    if not isinstance(mapping, dict) or set(mapping) != set(FIELDS):
        raise ValueError('Supply the seven canonical destination fields')
    if any(not text(v, 'Source field', 120).strip() for v in mapping.values()) or len(set(mapping.values())) != len(FIELDS):
        raise ValueError('Source fields must be distinct, non-empty text')
    tasks = raw.get('tasks')
    if not isinstance(tasks, list) or len(tasks) != 3 or any(not text(t, 'Task', 500).strip() for t in tasks):
        raise ValueError('Supply three task titles')
    example = raw.get('exampleIntake')
    if not isinstance(example, dict) or not isinstance(example.get('payload'), dict):
        raise ValueError('Missing example intake')
    if not re.fullmatch(r'[A-Za-z0-9._:-]{1,120}', text(example.get('id'), 'Example intake ID', 120)):
        raise ValueError('Invalid example intake ID')
    for key in FIELDS:
        value = text(example['payload'].get(mapping[key]), key, 4000)
        if key in ('name', 'email', 'address', 'service') and not value.strip():
            raise ValueError(f'Example {key} cannot be blank')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', example['payload'][mapping['email']]):
        raise ValueError('Example email must be valid')
    value = example['payload'][mapping['preferred_date']]
    if value and date.fromisoformat(value).isoformat() != value:
        raise ValueError('Example preferred date must use YYYY-MM-DD')
    return raw


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _inode_key(info):
    return (info.st_dev, info.st_ino)


def _visible_created(path: Path, inode_key) -> bool:
    try:
        visible = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return stat.S_ISREG(visible.st_mode) and _inode_key(visible) == inode_key


def _cleanup_created(path: Path, inode_key) -> None:
    if _visible_created(path, inode_key):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _hash_stream(stream):
    stream.seek(0)
    digest = hashlib.sha256()
    total = 0
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
    return total, digest.hexdigest()


def build(deployment: Path, runner_dir: Path, output: Path, source_revision='not-supplied') -> dict:
    deployment_raw = read_regular(deployment, 'Deployment input', MAX_DEPLOYMENT_BYTES)
    raw = validate(strict_json_bytes(deployment_raw, 'Deployment input'))
    if source_revision != 'not-supplied' and not re.fullmatch(r'[0-9a-f]{40}', source_revision):
        raise ValueError('Source revision must be a full Git commit SHA or not-supplied')

    files = {}
    # Only runtime source files are packaged, never the runner's database or exports.
    for name in ('workflow.py', 'index.html'):
        files[name] = read_regular(runner_dir / name, f'Runner {name}', MAX_RUNNER_FILE_BYTES)
    compile(files['workflow.py'], 'workflow.py', 'exec')
    if not re.search(rb'<(?:body|header)\b', files['index.html'], re.I):
        raise ValueError('Runner dashboard needs an explicit body or leading header')
    upstream_readme = _optional_regular(runner_dir / 'README.md', 'Runner README.md', MAX_RUNNER_FILE_BYTES)
    if upstream_readme is not None:
        files['UPSTREAM-README.md'] = upstream_readme

    files['run.py'] = read_regular(ROOT / 'run_bundle.py', 'Parcel launcher', MAX_RUNNER_FILE_BYTES)
    files['parcel.json'] = json_bytes(raw)
    files['config.local.json'] = json_bytes({'mapping': raw['fieldMapping'], 'endpoint': ''})
    files['example-intake.json'] = json_bytes(raw['exampleIntake'])
    files['START-HERE.txt'] = (
        raw['agency'] + ' — ' + raw['title'] + '\n\n'
        'A private installation package, not a running service. Python 3.11+ is required.\n'
        'Extract into the intended existing private environment and run from this directory:\n\n'
        '  python run.py --db client.sqlite3 configure config.local.json\n'
        '  python run.py --db client.sqlite3 serve\n\n'
        'The launcher checks MANIFEST.json against its immutable packaged runtime files before\n'
        'loading workflow.py. config.local.json is intentionally editable operator configuration.\n'
        'The launcher removes the package directory from Python import search before loading\n'
        'shadowable standard-library modules or the verified workflow generation.\n'
        'This internal integrity check is not a signed provenance or authenticity guarantee.\n\n'
        'Open http://127.0.0.1:8789 in that environment. This is a trusted single-workspace\n'
        'operator service, not an internet-facing or multi-tenant deployment.\n\n'
        'Exercise the sample in a SEPARATE throwaway database, not the client database:\n'
        '  python run.py --db smoke.sqlite3 configure config.local.json\n'
        '  python run.py --db smoke.sqlite3 ingest example-intake.json\n'
        '  python run.py --db smoke.sqlite3 ingest example-intake.json\n'
        '  python run.py --db smoke.sqlite3 work --limit 20\n'
        '  python run.py --db smoke.sqlite3 export\n\n'
        'The duplicate sample ID should yield one customer, one job, three tasks and one\n'
        'local notification. Real intake IDs must be stable for retries and new for new jobs.\n'
        'This launcher reuses the supplied workflow.py without editing its bytes; it selects\n'
        'the three task titles for this preset and adds a branded dashboard header.\n'
        'The existing event type remains cleaning.job.created for interface compatibility.\n'
        'Task instructions are operator work, not automatic quoting, sending or scheduling.\n'
        'Worker delivery is explicit. Provider-specific writes and email are not included.\n'
        'The receiver endpoint starts empty (local notifications). HTTP receivers need\n'
        'durable event-ID deduplication; an acknowledgement is not a universal CRM guarantee.\n'
        'Reconfiguring an existing database is explicit; preserve its data and mapping.\n'
        'Keep databases, sidecars, this client package and exports private. Preserve the\n'
        'database with SQLite backup or a stopped-service copy including required sidecars.\n\n'
        'Scope: ' + raw['scope'] + '\nSupport: ' + (raw['support'] or 'Not yet recorded') + '\n\n'
        'Record the actual installation and client walkthrough in the Parcel checklist.\n'
        'No deployment, customer contact or payment happened merely by building this ZIP.\n'
    ).encode('utf-8')

    operator_editable = ['config.local.json']
    runtime_immutable = sorted(name for name in files if name not in operator_editable)
    manifest = {
        'format': 'parcel.bundle-manifest',
        'version': 1,
        'sourceRevisionSupplied': source_revision,
        'sourceRevisionIndependentlyVerified': False,
        'runtimeImmutable': runtime_immutable,
        'operatorEditable': operator_editable,
        'files': {
            name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
            for name, data in sorted(files.items())
        },
    }
    files['MANIFEST.json'] = json_bytes(manifest)

    output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(os.fspath(output), flags, 0o600)
    created = os.fstat(fd)
    created_key = _inode_key(created)
    try:
        with os.fdopen(fd, 'w+b', closefd=True) as stream:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in sorted(files.items()):
                    info = zipfile.ZipInfo(name, date_time=(2026, 9, 8, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o600 << 16
                    archive.writestr(info, data)
            stream.flush()
            os.fsync(stream.fileno())
            before_hash = os.fstat(stream.fileno())
            byte_count, bundle_sha256 = _hash_stream(stream)
            after_hash = os.fstat(stream.fileno())
            if (
                _fingerprint(before_hash) != _fingerprint(after_hash)
                or byte_count != after_hash.st_size
            ):
                raise RuntimeError('Created package changed while it was being hashed')
            byte_count2, sha2 = _hash_stream(stream)
            after2 = os.fstat(stream.fileno())
            if (
                byte_count2 != byte_count
                or sha2 != bundle_sha256
                or byte_count2 != after2.st_size
                or _fingerprint(after_hash) != _fingerprint(after2)
            ):
                raise RuntimeError('Created package changed while it was being hashed')
            visible = os.stat(output, follow_symlinks=False)
            if (
                not stat.S_ISREG(visible.st_mode)
                or _inode_key(visible) != created_key
                or _fingerprint(visible) != _fingerprint(after2)
            ):
                raise RuntimeError('Output path no longer names the hashed package generation')
            return {
                'output': str(output),
                'bytes': byte_count,
                'sha256': bundle_sha256,
                'files': len(files),
            }
    except BaseException:
        _cleanup_created(output, created_key)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('deployment', type=Path)
    parser.add_argument('--runner-dir', type=Path, default=ROOT.parent / 'intake-crm-workflow')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-revision', default='not-supplied')
    args = parser.parse_args()
    try:
        result = build(args.deployment, args.runner_dir, args.output, args.source_revision)
    except (OSError, ValueError, TypeError, SyntaxError, RuntimeError) as exc:
        parser.exit(1, f'Bundle not created: {exc}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
