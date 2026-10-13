"""Reopen the caption converter's own retained handoffs without extracting files."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import stat
import zipfile
import zlib

from caption_intake import IntakeError, canonical_episode, json_bytes, parse_captions

MAX_ARCHIVE_BYTES = 64_000_000
MAX_EXPANDED_BYTES = 256_000_000
MAX_HANDOFF_BYTES = 32_000_000


def _members(raw: bytes, budget: list[int], count: int, expanded_limit: int) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if not 1 <= len(entries) <= count:
            raise IntakeError('saved handoff has an unsupported number of archive members')
        names = [entry.filename for entry in entries]
        if len(set(names)) != len(names):
            raise IntakeError('saved handoff contains duplicate archive members')
        total = sum(entry.file_size for entry in entries)
        if total > expanded_limit or total > budget[0]:
            raise IntakeError('saved handoff exceeds the expanded-byte limit')
        budget[0] -= total
        files = {}
        for entry in entries:
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if (entry.is_dir() or '/' in entry.filename or '\\' in entry.filename
                    or entry.filename in ('', '.', '..') or len(entry.filename) > 100
                    or mode not in (0, stat.S_IFREG) or entry.flag_bits & 1
                    or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                raise IntakeError('saved handoff requires ordinary unencrypted named files')
            with archive.open(entry) as handle:
                payload = handle.read(entry.file_size + 1)
            if len(payload) != entry.file_size:
                raise IntakeError('saved handoff member size does not match the archive')
            files[entry.filename] = payload
        return files


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise IntakeError('saved handoff JSON contains a duplicate key')
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise IntakeError('saved handoff JSON contains a non-finite value')


def _document(raw: bytes) -> dict:
    result = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(result, dict):
        raise IntakeError('saved handoff JSON must contain an object')
    return result


def _single(raw: bytes, budget: list[int]) -> tuple[dict, dict]:
    files = _members(raw, budget, 4, MAX_HANDOFF_BYTES)
    sources = set(files) & {'source.srt', 'source.vtt'}
    if len(sources) != 1:
        raise IntakeError('saved handoff must contain exactly one original caption file')
    source_name = next(iter(sources))
    names = [source_name, 'transcript.json']
    episode_import = 'episode-import.json' in files
    if episode_import:
        names.append('episode-import.json')
    if set(files) != {*names, 'manifest.json'}:
        raise IntakeError('saved handoff contains missing or unexpected files')
    manifest = {'schema': 'caption-intake-bundle/v1', 'complete': True, 'files': {
        name: {'bytes': len(files[name]), 'sha256': hashlib.sha256(files[name]).hexdigest()}
        for name in names}}
    if files['manifest.json'] != json_bytes(manifest):
        raise IntakeError('saved handoff manifest does not match its retained files')
    retained = _document(files['transcript.json'])
    provenance = retained.get('provenance')
    if not isinstance(provenance, dict) or provenance.get('format') != source_name.split('.')[1]:
        raise IntakeError('saved handoff transcript has no matching source format')
    parsed = parse_captions(files[source_name], fmt=provenance.get('format'),
                            title=retained.get('title'), encoding=provenance.get('encoding'),
                            default_speaker=provenance.get('default_speaker'))
    if files['transcript.json'] != json_bytes(parsed):
        raise IntakeError('saved transcript does not match its original captions and options')
    duration, synthetic = None, False
    if episode_import:
        episode = _document(files['episode-import.json'])
        if type(episode.get('duration')) not in (int, float):
            raise IntakeError('saved episode import has no numeric recording duration')
        duration, synthetic = str(episode['duration']), episode.get('synthetic_demo')
        expected = canonical_episode(parsed, duration, synthetic_demo=synthetic)
        if files['episode-import.json'] != json_bytes(expected):
            raise IntakeError('saved episode import does not match its retained captions and options')
    restored = {'name': source_name, 'source_base64': base64.b64encode(files[source_name]).decode('ascii'),
                'title': parsed['title'], 'format': provenance['format'],
                'encoding': provenance['encoding'], 'speaker': provenance['default_speaker'],
                'duration_seconds': duration, 'synthetic_demo': synthetic, 'query': '', 'offset': 0}
    summary = {'title': parsed['title'], 'source_sha256': parsed['provenance']['source_sha256'],
               'source_bytes': len(files[source_name]), 'format': provenance['format'],
               'encoding': provenance['encoding'], 'cue_count': len(parsed['segments']),
               'episode_import': episode_import}
    return restored, summary


def reopen_handoff(raw: bytes, *, max_files: int, max_source_bytes: int, max_cues: int) -> list[dict]:
    """Recompile all retained artifacts, then return ordinary workbench upload rows.

    The checks bind the supplied files to each other. They do not authenticate
    the author, verify audio, or recover options absent from the saved format.
    """
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_ARCHIVE_BYTES:
        raise IntakeError(f'saved handoff must contain 1..{MAX_ARCHIVE_BYTES} bytes')
    try:
        budget = [MAX_EXPANDED_BYTES]
        # Inspect names without expanding a second copy of individual handoffs.
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            batch = 'batch-manifest.json' in archive.namelist()
        if not batch:
            row, summary = _single(raw, budget)
            rows, summaries = [row], [summary]
        else:
            files = _members(raw, budget, max_files + 1, MAX_ARCHIVE_BYTES)
            manifest = _document(files['batch-manifest.json'])
            retained_rows = manifest.get('files')
            if not isinstance(retained_rows, list) or not 1 <= len(retained_rows) <= max_files:
                raise IntakeError('saved batch must contain a bounded nonempty files list')
            rows, summaries, expected_rows, members = [], [], [], []
            for index, retained in enumerate(retained_rows):
                if not isinstance(retained, dict) or not isinstance(retained.get('bundle'), dict):
                    raise IntakeError('saved batch has an invalid handoff entry')
                member = retained['bundle'].get('path')
                if (not isinstance(member, str) or not re.fullmatch(r'[0-9]{2}-[A-Za-z0-9_-]{1,60}\.zip', member)
                        or not member.startswith(f'{index + 1:02d}-') or member in members or member not in files):
                    raise IntakeError('saved batch has a missing, repeated or invalid handoff member')
                row, summary = _single(files[member], budget)
                row['name'] = retained.get('name')
                expected_rows.append({'name': row['name'], **summary, 'bundle': {
                    'path': member, 'bytes': len(files[member]),
                    'sha256': hashlib.sha256(files[member]).hexdigest()}})
                members.append(member)
                rows.append(row)
                summaries.append(summary)
            expected = {'schema': 'caption-workbench-batch/v1', 'complete': True,
                        'media_verified': False, 'files': expected_rows}
            if set(files) != {*members, 'batch-manifest.json'} or files['batch-manifest.json'] != json_bytes(expected):
                raise IntakeError('saved batch manifest does not match its complete handoffs')
        if (sum(row['source_bytes'] for row in summaries) > max_source_bytes
                or sum(row['cue_count'] for row in summaries) > max_cues):
            raise IntakeError('saved handoff exceeds the workbench source-byte or cue limit; split the batch')
        return rows
    except IntakeError:
        raise
    except (OSError, ValueError, TypeError, KeyError, RecursionError, zipfile.BadZipFile,
            NotImplementedError, RuntimeError, zlib.error) as exc:
        raise IntakeError('unable to reopen a complete caption handoff ZIP') from exc
