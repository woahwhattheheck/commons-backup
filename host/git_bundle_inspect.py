#!/usr/bin/env python3
"""Inspect/export Git bundle objects offline, including recoverable thin-pack data.

No payload execution, Git subprocess, network, checkout, or repository mutation.
A successfully inspected pack is NOT a verified repository restore. Prerequisite
history and graph closure still need Git verification in the receiving repo.

Bundle and base-object inputs must resolve to regular files. Symlinks to regular
files are supported; FIFOs and devices are refused before reading.

Format references: https://git-scm.com/docs/bundle-format
                   https://git-scm.com/docs/gitformat-pack
"""
from __future__ import annotations

import argparse
import base64
import binascii
from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import sys
import tempfile
import zlib

KINDS = {1: 'commit', 2: 'tree', 3: 'blob', 4: 'tag'}


class BundleError(ValueError):
    """Malformed input, an unsupported required format, or a resource limit."""


@dataclass(frozen=True)
class Limits:
    input_bytes: int = 64 * 1024 * 1024
    header_bytes: int = 1024 * 1024
    object_bytes: int = 64 * 1024 * 1024
    total_bytes: int = 256 * 1024 * 1024
    objects: int = 100_000

    def __post_init__(self) -> None:
        for name in ('input_bytes', 'header_bytes', 'object_bytes', 'total_bytes', 'objects'):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value < sys.maxsize:
                raise BundleError(f'{name} must be a nonnegative platform-sized integer')


@dataclass
class Entry:
    offset: int
    representation: int
    packed_size: int
    payload: bytes
    base: int | str | None = None
    kind: str | None = None
    data: bytes | None = None
    oid: str | None = None


def object_id(kind: str, data: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, kind.encode('ascii') + b' ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def _byte(data: bytes, position: int) -> tuple[int, int]:
    if position >= len(data):
        raise BundleError('Truncated variable-length field or delta instruction')
    return data[position], position + 1


def _size(data: bytes, position: int, maximum: int) -> tuple[int, int]:
    value = shift = 0
    for _ in range(10):
        octet, position = _byte(data, position)
        value |= (octet & 0x7f) << shift
        if value > maximum:
            raise BundleError('Size exceeds configured object limit')
        if not octet & 0x80:
            return value, position
        shift += 7
    raise BundleError('Overlong size encoding')


def apply_delta(base: bytes, delta: bytes, maximum: int) -> bytes:
    base_size, position = _size(delta, 0, maximum)
    result_size, position = _size(delta, position, maximum)
    if base_size != len(base):
        raise BundleError('Delta base size does not match its resolved base')
    result = bytearray()
    while position < len(delta):
        instruction, position = _byte(delta, position)
        if instruction & 0x80:
            offset = length = 0
            for bit in range(4):
                if instruction & (1 << bit):
                    value, position = _byte(delta, position)
                    offset |= value << (8 * bit)
            for bit in range(3):
                if instruction & (1 << (bit + 4)):
                    value, position = _byte(delta, position)
                    length |= value << (8 * bit)
            length = length or 0x10000
            if offset + length > len(base):
                raise BundleError('Delta copy extends beyond its base')
            if len(result) + length > result_size:
                raise BundleError('Delta copy exceeds the declared result size')
            result.extend(memoryview(base)[offset:offset + length])
        elif instruction:
            end = position + instruction
            if end > len(delta):
                raise BundleError('Truncated delta insertion')
            if len(result) + instruction > result_size:
                raise BundleError('Delta insertion exceeds the declared result size')
            result.extend(memoryview(delta)[position:end])
            position = end
        else:
            raise BundleError('Reserved zero delta instruction')
    if len(result) != result_size:
        raise BundleError('Reconstructed delta size does not match its declaration')
    return bytes(result)


def _header(bundle: bytes, limits: Limits) -> tuple[dict, bytes]:
    end = bundle.find(b'\n\n', 0, limits.header_bytes + 2)
    if end < 0 or end > limits.header_bytes:
        raise BundleError('Missing or oversized bundle header')
    lines = bundle[:end].split(b'\n')
    if not lines or lines[0] not in (b'# v2 git bundle', b'# v3 git bundle'):
        raise BundleError('Expected a v2 or v3 Git bundle signature')
    version = 2 if lines[0] == b'# v2 git bundle' else 3
    capabilities: dict[str, str] = {}
    payload_lines = []
    seen_payload = False
    for line in lines[1:]:
        if b'\0' in line or b'\r' in line:
            raise BundleError('Invalid control byte in bundle header')
        if line.startswith(b'@'):
            if version != 3 or seen_payload:
                raise BundleError('Capabilities must precede v3 prerequisite/reference lines')
            key, separator, value = line[1:].partition(b'=')
            if key not in (b'object-format', b'filter'):
                raise BundleError('Unsupported bundle header flag: ' + repr(key))
            name = key.decode('ascii')
            if name in capabilities or not separator or not value:
                raise BundleError('Duplicate or missing bundle capability value')
            capabilities[name] = value.decode('utf-8', errors='backslashreplace')
        else:
            seen_payload = True
            payload_lines.append(line)
    algorithm = capabilities.get('object-format', 'sha1')
    if algorithm not in ('sha1', 'sha256'):
        raise BundleError('Unsupported object-format capability: ' + algorithm)
    oid_length = hashlib.new(algorithm).digest_size * 2
    prerequisites, references = [], []
    seen_reference = False
    for line in payload_lines:
        prerequisite = line.startswith(b'-')
        fields = (line[1:] if prerequisite else line).split(b' ', 1)
        if len(fields) != 2 or not re.fullmatch(rb'[0-9a-f]{' + str(oid_length).encode('ascii') + rb'}', fields[0]):
            raise BundleError('Malformed prerequisite or reference object ID')
        text = fields[1].decode('utf-8', errors='backslashreplace')
        if prerequisite:
            if seen_reference:
                raise BundleError('Prerequisites must precede bundle references')
            prerequisites.append({'oid': fields[0].decode('ascii'), 'comment': text})
        else:
            if not fields[1] or b' ' in fields[1] or b'\t' in fields[1]:
                raise BundleError('Malformed reference name')
            seen_reference = True
            references.append({'oid': fields[0].decode('ascii'), 'name': text})
    return {'bundle_version': version, 'object_format': algorithm, 'capabilities': capabilities,
            'prerequisites': prerequisites, 'references': references}, bundle[end + 2:]


def _pack(pack: bytes, algorithm: str, limits: Limits) -> tuple[int, list[Entry], int]:
    digest_size = hashlib.new(algorithm).digest_size
    if len(pack) < 12 + digest_size or pack[:4] != b'PACK':
        raise BundleError('Missing or truncated PACK stream')
    if hashlib.new(algorithm, pack[:-digest_size]).digest() != pack[-digest_size:]:
        raise BundleError('PACK trailer checksum mismatch')
    version, count = struct.unpack('>II', pack[4:12])
    if version not in (2, 3):
        raise BundleError('Unsupported PACK version')
    if count > limits.objects:
        raise BundleError('PACK object count exceeds configured limit')
    stream = pack[:-digest_size]
    position, total = 12, 0
    entries: list[Entry] = []
    offsets: set[int] = set()
    for _ in range(count):
        start = position
        value, position = _byte(stream, position)
        kind, size, shift, steps = (value >> 4) & 7, value & 15, 4, 0
        while value & 0x80:
            value, position = _byte(stream, position)
            size |= (value & 0x7f) << shift
            shift += 7
            steps += 1
            if steps > 9 or size > limits.object_bytes:
                raise BundleError('PACK object size exceeds configured limit')
        if size > limits.object_bytes or total + size > limits.total_bytes:
            raise BundleError('Inflated PACK data exceeds configured limit')
        if kind not in (*KINDS, 6, 7):
            raise BundleError('Invalid or reserved PACK object type')
        base: int | str | None = None
        if kind == 7:
            if position + digest_size > len(stream):
                raise BundleError('Truncated REF_DELTA base ID')
            base = stream[position:position + digest_size].hex()
            position += digest_size
        elif kind == 6:
            value, position = _byte(stream, position)
            distance, steps = value & 0x7f, 0
            while value & 0x80:
                value, position = _byte(stream, position)
                distance = ((distance + 1) << 7) | (value & 0x7f)
                steps += 1
                if steps > 9 or distance > start:
                    raise BundleError('Invalid OFS_DELTA distance')
            base = start - distance
            if not distance or base not in offsets:
                raise BundleError('OFS_DELTA does not reference an earlier object boundary')
        # Feed bounded chunks: passing the entire remaining pack to zlib would
        # copy a potentially huge unused_data tail for every small object.
        inflater = zlib.decompressobj()
        pieces = []
        produced = 0
        while not inflater.eof:
            chunk = memoryview(stream)[position:position + 8192]
            if not chunk:
                raise BundleError('Truncated compressed PACK object')
            try:
                piece = inflater.decompress(chunk, size + 1 - produced)
            except zlib.error as error:
                raise BundleError('Invalid compressed PACK object') from error
            produced += len(piece)
            if produced > size:
                raise BundleError('Compressed object exceeds its declared size')
            consumed = len(chunk) - len(inflater.unused_data) - len(inflater.unconsumed_tail)
            if consumed <= 0 and not piece:
                raise BundleError('Compressed PACK object made no progress')
            position += consumed
            pieces.append(piece)
        payload = b''.join(pieces)
        if len(payload) != size:
            raise BundleError('Inflated object size does not match its declaration')
        total += size
        entries.append(Entry(start, kind, size, payload, base))
        offsets.add(start)
    if position != len(stream):
        raise BundleError('Trailing PACK bytes or incorrect object count')
    return version, entries, total


def inspect_bundle(bundle: bytes, *, limits: Limits = Limits(), bases: tuple[tuple[str, bytes], ...] = ()) -> tuple[dict, dict[str, tuple[str, bytes]]]:
    """Return a JSON-ready manifest and resolved object payloads keyed by Git OID."""
    if len(bundle) > limits.input_bytes:
        raise BundleError('Bundle exceeds configured input limit')
    header, pack = _header(bundle, limits)
    algorithm = header['object_format']
    version, entries, total = _pack(pack, algorithm, limits)
    objects: dict[str, tuple[str, bytes]] = {}
    waiting: dict[tuple[str, int | str], list[Entry]] = defaultdict(list)
    ready: deque[tuple[tuple[str, int | str], str, bytes]] = deque()
    supplied = []
    for entry in entries:
        if entry.representation in (6, 7):
            assert entry.base is not None
            waiting[('offset' if entry.representation == 6 else 'oid', entry.base)].append(entry)

    def publish(kind: str, data: bytes, entry: Entry | None = None) -> str:
        oid = object_id(kind, data, algorithm)
        previous = objects.get(oid)
        if previous is not None and previous != (kind, data):
            raise BundleError('Conflicting object contents for the same Git ID')
        if previous is None:
            objects[oid] = (kind, data)
            ready.append((('oid', oid), kind, data))
        if entry is not None:
            entry.kind, entry.data, entry.oid = kind, data, oid
            ready.append((('offset', entry.offset), kind, data))
        return oid

    for kind, data in bases:
        if kind not in KINDS.values() or len(data) > limits.object_bytes:
            raise BundleError('Invalid or oversized supplied base object')
        total += len(data)
        if total > limits.total_bytes:
            raise BundleError('Supplied base data exceeds configured total limit')
        oid = publish(kind, data)
        supplied.append({'oid': oid, 'type': kind, 'size': len(data)})
    for entry in entries:
        if entry.representation in KINDS:
            publish(KINDS[entry.representation], entry.payload, entry)
    while ready:
        key, kind, data = ready.popleft()
        for entry in waiting.pop(key, []):
            _, offset = _size(entry.payload, 0, limits.object_bytes)
            target_size, _ = _size(entry.payload, offset, limits.object_bytes)
            if total + target_size > limits.total_bytes:
                raise BundleError('Reconstructed delta data exceeds configured total limit')
            result = apply_delta(data, entry.payload, limits.object_bytes)
            total += len(result)
            publish(kind, result, entry)
    rows = []
    for entry in entries:
        row = {'pack_offset': entry.offset, 'representation': KINDS.get(entry.representation, 'ofs-delta' if entry.representation == 6 else 'ref-delta'),
               'packed_inflated_bytes': entry.packed_size, 'resolved': entry.data is not None}
        if entry.base is not None:
            row['base_offset' if isinstance(entry.base, int) else 'base_oid'] = entry.base
        if entry.data is not None:
            row.update(oid=entry.oid, type=entry.kind, size=len(entry.data), content_sha256=hashlib.sha256(entry.data).hexdigest())
        rows.append(row)
    unresolved = sum(not row['resolved'] for row in rows)
    manifest = {**header, 'bundle_sha256': hashlib.sha256(bundle).hexdigest(),
                'pack_version': version, 'pack_checksum_verified': True,
                'pack_objects': len(entries), 'resolved_pack_objects': len(entries) - unresolved,
                'unresolved_pack_objects': unresolved, 'status': 'PARTIAL_THIN_PACK' if unresolved else 'PACK_OBJECTS_RESOLVED',
                'git_restore_verified': False,
                'restore_note': 'Object recovery is not repository/graph verification. Supply prerequisite history and use git bundle verify/fetch in the receiving repository.',
                'supplied_bases': supplied, 'accounted_inflated_bytes': total, 'objects': rows}
    # Only export objects recovered from this bundle, not unrelated supplied bases.
    recovered = {entry.oid: objects[entry.oid] for entry in entries if entry.oid is not None}
    return manifest, recovered


def _read(path: Path, maximum: int) -> bytes:
    # The allowance bounds total input, not a speculative allocation for each read.
    pieces = []
    remaining = maximum + 1
    with open(path, 'rb', opener=lambda name, flags: os.open(name, flags | getattr(os, 'O_NONBLOCK', 0))) as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise BundleError('Input must be a regular file: ' + str(path))
        while remaining:
            piece = stream.read(min(64 * 1024, remaining))
            if not piece:
                break
            pieces.append(piece)
            remaining -= len(piece)
    if not remaining:
        raise BundleError('File exceeds configured byte limit: ' + str(path))
    return b''.join(pieces)


def tree_inventory(manifest: dict, objects: dict[str, tuple[str, bytes]], reference: str,
                   *, max_entries: int = 100_000) -> dict:
    """Map recovered objects to paths without checkout or pathname writes.

    Missing objects are expected in incremental/thin bundles. Directory coverage
    and content availability are separate, and gitlinks remain external entries.
    """
    if type(max_entries) is not int or max_entries <= 0:
        raise BundleError('Tree inventory limit must be a positive integer')
    width = hashlib.new(manifest['object_format']).digest_size
    candidates = {row['oid'] for row in manifest['references'] if row['name'] == reference}
    if not candidates and re.fullmatch('[0-9a-f]{' + str(width * 2) + '}', reference):
        candidates.add(reference)
    if len(candidates) != 1:
        raise BundleError('Tree reference is missing or ambiguous: ' + reference)
    root_oid = oid = candidates.pop()
    seen = set()
    missing: dict[str, str] = {}
    tree_oid = None
    while oid in objects:
        if oid in seen:
            raise BundleError('Cycle while resolving selected commit/tag')
        seen.add(oid)
        kind, data = objects[oid]
        if kind == 'tree':
            tree_oid = oid
            break
        if kind not in ('commit', 'tag'):
            raise BundleError('Selected object is not a commit, tag or tree')
        prefix = b'tree ' if kind == 'commit' else b'object '
        header = data.split(b'\n\n', 1)[0].splitlines()
        targets = [line[len(prefix):] for line in header if line.startswith(prefix)]
        if len(targets) != 1 or not re.fullmatch(rb'[0-9a-f]{' + str(width * 2).encode() + rb'}', targets[0]):
            raise BundleError('Selected commit/tag has an invalid target header')
        oid = targets[0].decode('ascii')
    if tree_oid is None:
        missing[oid] = 'root'

    entries = []
    pending = [(b'', tree_oid)] if tree_oid is not None else []
    path_bytes = 0
    truncated = False
    missing_trees = 0
    missing_blobs = 0
    while pending and not truncated:
        parent_path, current = pending.pop()
        kind, data = objects[current]
        if kind != 'tree':
            raise BundleError('Directory entry resolves to a non-tree object')
        position = 0
        names = set()
        while position < len(data):
            space = data.find(b' ', position)
            nul = data.find(b'\0', space + 1) if space >= 0 else -1
            if space < 0 or nul < 0 or nul + 1 + width > len(data):
                raise BundleError('Malformed recovered tree object: ' + current)
            raw_mode, name = data[position:space], data[space + 1:nul]
            if not re.fullmatch(rb'[0-7]{5,6}', raw_mode) or not name or b'/' in name or name in names:
                raise BundleError('Invalid or duplicate recovered tree entry')
            names.add(name)
            child = data[nul + 1:nul + 1 + width].hex()
            position = nul + 1 + width
            path = parent_path + name
            if len(entries) >= max_entries or path_bytes + len(path) > 8 * 1024 * 1024:
                truncated = True
                break
            path_bytes += len(path)
            mode = raw_mode.decode('ascii')
            entry_type = {0o040000: 'tree', 0o100000: 'blob', 0o120000: 'blob', 0o160000: 'gitlink'}.get(int(mode, 8) & 0o170000)
            if entry_type is None:
                raise BundleError('Unsupported recovered tree mode: ' + mode)
            available = child in objects
            if available and entry_type != 'gitlink' and objects[child][0] != entry_type:
                raise BundleError('Recovered object type differs from its tree entry')
            entries.append({'path': path.decode('utf-8', 'surrogateescape'), 'mode': mode,
                            'type': entry_type, 'oid': child, 'available': available,
                            'size': len(objects[child][1]) if available and entry_type == 'blob' else None})
            if entry_type == 'tree':
                if available:
                    pending.append((path + b'/', child))
                else:
                    missing[child] = 'tree'
                    missing_trees += 1
            elif entry_type == 'blob' and not available:
                missing[child] = 'blob'
                missing_blobs += 1
    complete = tree_oid is not None and not missing_trees and not truncated
    entries.sort(key=lambda row: row['path'])
    return {'requested_reference': reference, 'root_oid': root_oid, 'tree_oid': tree_oid,
            'tree_complete': complete, 'content_complete': complete and not missing_blobs,
            'truncated': truncated, 'max_entries': max_entries,
            'max_path_bytes': 8 * 1024 * 1024, 'path_bytes': path_bytes,
            'observed_entries': len(entries), 'missing_tree_entries': missing_trees,
            'missing_blob_entries': missing_blobs,
            'missing_objects': [{'oid': key, 'type': value} for key, value in sorted(missing.items())],
            'entries': entries}


def export_objects(output: Path, manifest: dict, objects: dict[str, tuple[str, bytes]]) -> None:
    """Stage payload writes and remove this new destination if export fails."""
    # Reserve the destination exclusively before creating anything beneath it.
    # An existing file, directory or symlink must never enter our cleanup path.
    output.mkdir(parents=True, exist_ok=False)
    try:
        with tempfile.TemporaryDirectory(prefix='.git-bundle-export-', dir=output.parent) as temporary:
            staging = Path(temporary)
            folder = staging/'objects'
            folder.mkdir()
            for oid, (kind, payload) in objects.items():
                (folder/(oid+'.'+kind)).write_bytes(payload)
            (staging/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
            folder.rename(output/'objects')
            (staging/'manifest.json').rename(output/'manifest.json')
    except BaseException:
        shutil.rmtree(output)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--base64', action='store_true', help='Input is whitespace-wrapped base64, not a binary bundle')
    parser.add_argument('--sha256', help='Expected SHA256 of the decoded binary bundle')
    parser.add_argument('--base-object', action='append', default=[], metavar='TYPE:PATH', help='Supply raw commit/tree/blob/tag bytes for delta resolution and tree lookup; repeatable')
    parser.add_argument('--output', type=Path, help='Create a NEW directory containing manifest.json and hash-named raw payloads')
    parser.add_argument('--fail-on-unresolved', action='store_true', help='Return 3 for partial recovery, while still exporting available objects')
    parser.add_argument('--max-input-mib', type=int, default=64)
    parser.add_argument('--max-object-mib', type=int, default=64)
    parser.add_argument('--max-total-mib', type=int, default=256)
    parser.add_argument('--tree', metavar='REF_OR_OID', help='Inventory paths from a recovered commit/tag/tree without checkout')
    parser.add_argument('--max-tree-entries', type=int, default=100_000, help='Bound optional tree inventory entries (default: 100000)')
    args = parser.parse_args(argv)
    try:
        if min(args.max_input_mib, args.max_object_mib, args.max_total_mib) <= 0:
            raise BundleError('Byte limits must be positive')
        limits = Limits(input_bytes=args.max_input_mib * 1024 * 1024,
                        object_bytes=args.max_object_mib * 1024 * 1024,
                        total_bytes=args.max_total_mib * 1024 * 1024)
        data = _read(args.bundle, limits.input_bytes)
        if args.base64:
            try:
                data = base64.b64decode(b''.join(data.split()), validate=True)
            except (ValueError, binascii.Error) as error:
                raise BundleError('Invalid base64 bundle input') from error
        if args.sha256:
            if not re.fullmatch('[0-9a-fA-F]{64}', args.sha256) or hashlib.sha256(data).hexdigest() != args.sha256.lower():
                raise BundleError('Decoded bundle SHA256 does not match the supplied value')
        bases = []
        base_bytes = 0
        for specification in args.base_object:
            kind, separator, path = specification.partition(':')
            if not separator or kind not in KINDS.values() or not path:
                raise BundleError('--base-object must be commit/tree/blob/tag:PATH')
            # Check the aggregate while loading, not after retaining every file.
            value = _read(Path(path), min(limits.object_bytes, limits.total_bytes - base_bytes))
            base_bytes += len(value)
            bases.append((kind, value))
        manifest, objects = inspect_bundle(data, limits=limits, bases=tuple(bases))
        if args.tree:
            inventory_objects = dict(objects)
            for kind, payload in bases:
                inventory_objects[object_id(kind, payload, manifest['object_format'])] = (kind, payload)
            manifest['tree_inventory'] = tree_inventory(manifest, inventory_objects, args.tree, max_entries=args.max_tree_entries)
        if args.output:
            export_objects(args.output, manifest, objects)
        print(json.dumps(manifest, indent=2))
        return 3 if args.fail_on_unresolved and manifest['unresolved_pack_objects'] else 0
    except (BundleError, OSError) as error:
        print('git_bundle_inspect: '+str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
