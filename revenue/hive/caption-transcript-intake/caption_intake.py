#!/usr/bin/env python3
"""Offline, source-preserving SRT/WebVTT intake. See README for supported subset."""
from __future__ import annotations

import argparse
import codecs
from decimal import Decimal, InvalidOperation
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile

MAX_BYTES = 2_000_000
MAX_CUES = 10_000
TIMESTAMP = re.compile(r"(?:(?P<h>[0-9]{2,9}):)?(?P<m>[0-5][0-9]):(?P<s>[0-5][0-9])(?P<sep>[.,])(?P<ms>[0-9]{3})\Z")
TIMING = re.compile(r"(?P<start>\S+)[ \t]+-->[ \t]+(?P<end>\S+)(?:[ \t]+(?P<settings>.*))?\Z")
TAGS = re.compile(r"<[^<>]*>")


class IntakeError(ValueError):
    """Invalid or unsupported input; no source file is modified."""


def _label(value: str, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise IntakeError(f"{field} must contain 1..{limit} characters")
    if any(ord(c) < 32 or c == '\x7f' for c in value):
        raise IntakeError(f"{field} contains control characters")
    return value.strip()


def timestamp_ms(value: str, fmt: str) -> int:
    m = TIMESTAMP.fullmatch(value)
    if not m or m['sep'] != (',' if fmt == 'srt' else '.') or (fmt == 'srt' and m['h'] is None):
        raise IntakeError(f"invalid {fmt.upper()} timestamp: {value!r}")
    return ((int(m['h'] or 0) * 60 + int(m['m'])) * 60 + int(m['s'])) * 1000 + int(m['ms'])


def plain_payload(raw: str, fmt: str, default_speaker: str) -> tuple[str, str]:
    """A single explicit VTT voice may wrap the entire cue; never infer voices."""
    speaker = default_speaker
    voice = re.fullmatch(r"[ \t\n]*<v(?:\.[^\s<>.]+)*[ \t]+([^<>\n]+)>(.*)", raw, re.S) if fmt == 'vtt' else None
    if voice:
        speaker = _label(html.unescape(voice[1]), 'voice annotation', 200)
        raw = voice[2]
        close = re.search(r"</v>[ \t\n]*\Z", raw)
        if close:
            raw = raw[:close.start()]
    stack: list[str] = []
    pieces: list[str] = []
    offset = 0
    for tag in TAGS.finditer(raw):
        literal = raw[offset:tag.start()]
        if '<' in literal:
            raise IntakeError('unclosed or nested markup; escape a literal < as &lt;')
        pieces.append(literal)
        token = tag[0][1:-1]
        if token.startswith('/'):
            name = token[1:]
            if not stack or stack.pop() != name:
                raise IntakeError(f'unmatched or unsupported closing tag: {tag[0]}')
        else:
            match = re.fullmatch(r"(b|i|u)(?:\.[^\s<>.]+)*", token)
            if fmt == 'vtt':
                match = match or re.fullmatch(r"(c)(?:\.[^\s<>.]+)*", token)
            if not match:
                raise IntakeError(f'unsupported markup: {tag[0]}; split multi-voice cues before import')
            stack.append(match[1])
        offset = tag.end()
    tail = raw[offset:]
    if '<' in tail:
        raise IntakeError('unclosed markup; escape a literal < as &lt;')
    pieces.append(tail)
    if stack:
        raise IntakeError('unclosed formatting span')
    text = html.unescape(''.join(pieces)).strip()
    if not text or any(ord(c) < 32 and c not in '\t\n' for c in text) or '\x7f' in text:
        raise IntakeError('cue text is empty or contains control characters')
    return speaker, text


def parse_captions(source: bytes, *, fmt: str, title: str, encoding: str = 'utf-8-sig',
                   default_speaker: str = 'Unspecified') -> dict:
    title = _label(title, 'title', 300)
    default_speaker = _label(default_speaker, 'default speaker', 200)
    if fmt not in ('srt', 'vtt'):
        raise IntakeError('format must be srt or vtt')
    if not isinstance(source, bytes) or not 0 < len(source) <= MAX_BYTES:
        raise IntakeError(f'source must contain 1..{MAX_BYTES} bytes')
    try:
        codec = codecs.lookup(encoding).name
        if fmt == 'vtt' and codec not in ('utf-8', 'utf-8-sig'):
            raise IntakeError('WebVTT requires UTF-8; explicit legacy encoding is SRT-only')
        text = source.decode(encoding).removeprefix('\ufeff')
    except (LookupError, UnicodeError) as exc:
        raise IntakeError(f'cannot decode source with {encoding!r}') from exc
    if any(ord(c) < 32 and c not in '\r\n\t' for c in text) or '\x7f' in text:
        raise IntakeError('source contains control characters')
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    blocks: list[tuple[int, list[str]]] = []
    start, block = 1, []
    for number, line in enumerate(lines, 1):
        if not line.strip(' \t'):
            if block:
                blocks.append((start, block))
                block = []
        else:
            if not block:
                start = number
            block.append(line)
    if block:
        blocks.append((start, block))
    metadata: list[dict] = []
    if fmt == 'vtt':
        if not blocks or blocks[0][0] != 1 or not re.fullmatch(r'WEBVTT(?:[ \t].*)?', blocks[0][1][0]):
            raise IntakeError('WebVTT must begin with WEBVTT')
        number, header = blocks.pop(0)
        if any('-->' in line for line in header):
            raise IntakeError('WebVTT header must end with a blank line before cues')
        if any('X-TIMESTAMP-MAP' in line.upper() for line in header):
            raise IntakeError('X-TIMESTAMP-MAP needs media-timeline mapping; not supported')
        metadata.append({'kind': 'header', 'line': number, 'raw': '\n'.join(header)})
    cues: list[dict] = []
    segments: list[dict] = []
    identifiers: set[str] = set()
    previous_start = -1
    for number, block in blocks:
        first = block[0]
        if fmt == 'vtt' and (re.match(r'NOTE(?:[ \t]|$)', first) or first in ('STYLE', 'REGION')):
            kind = first.split()[0]
            if kind != 'NOTE' and cues:
                raise IntakeError(f'line {number}: {kind} must precede cues')
            metadata.append({'kind': kind, 'line': number, 'raw': '\n'.join(block)})
            continue
        identifier = None
        index = 0
        if '-->' not in first:
            identifier, index = first, 1
        try:
            if fmt == 'srt' and (identifier is None or not re.fullmatch(r'[0-9]+', identifier)):
                raise IntakeError('SRT cue requires a numeric counter')
            if identifier is not None and identifier in identifiers:
                raise IntakeError(f'duplicate source cue identifier: {identifier!r}')
            if identifier is not None:
                identifiers.add(identifier)
            timing = TIMING.fullmatch(block[index]) if len(block) > index else None
            if not timing:
                raise IntakeError('missing or malformed timing line')
            begin, end = timestamp_ms(timing['start'], fmt), timestamp_ms(timing['end'], fmt)
            if end <= begin or begin < previous_start:
                raise IntakeError('end must exceed start; cues must be ordered by start time')
            settings = timing['settings'] or ''
            if fmt == 'srt' and settings:
                raise IntakeError('SRT coordinate/timing extensions are not supported')
            if settings and any(':' not in s or s.startswith(':') or s.endswith(':') for s in settings.split()):
                raise IntakeError('invalid WebVTT setting token')
            raw = '\n'.join(block[index + 1:])
            if '-->' in raw:
                raise IntakeError('cue payload contains -->; separate cues with blank lines')
            speaker, plain = plain_payload(raw, fmt, default_speaker)
        except IntakeError as exc:
            raise IntakeError(f'line {number}, cue {len(cues) + 1}: {exc}') from exc
        segment_id = f'c{len(cues) + 1:05d}'
        segments.append({'id': segment_id, 'start_ms': begin, 'end_ms': end, 'speaker': speaker, 'text': plain})
        cues.append({'segment_id': segment_id, 'source_id': identifier, 'line': number,
                     'timing': block[index], 'settings': settings, 'raw_payload': raw})
        previous_start = begin
        if len(cues) > MAX_CUES:
            raise IntakeError(f'input exceeds {MAX_CUES} cues')
    if not cues:
        raise IntakeError('no caption cues found')
    return {'schema': 'caption-intake/v1', 'title': title, 'segments': segments,
            'provenance': {'format': fmt, 'encoding': codec, 'source_sha256': hashlib.sha256(source).hexdigest(),
                           'source_bytes': len(source), 'default_speaker': default_speaker,
                           'media_verified': False, 'metadata': metadata, 'cues': cues}}


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')


def canonical_episode(parsed: dict, duration_seconds: str, *, synthetic_demo: bool = False) -> dict:
    """Map to KESTREL's Hive004 import contract; never infer recording duration."""
    if not isinstance(duration_seconds, str) or not 0 < len(duration_seconds) <= 64:
        raise IntakeError('recording duration must be a decimal string of at most 64 characters')
    try:
        duration = Decimal(duration_seconds)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise IntakeError('recording duration must be an explicit decimal number of seconds') from exc
    if not duration.is_finite() or not 0 < duration <= 86400:
        raise IntakeError('recording duration must be finite, positive, and at most 86400 seconds')
    if type(synthetic_demo) is not bool:
        raise IntakeError('synthetic_demo must be a boolean')
    # These limits belong to the optional consumer, not generic caption intake.
    if len(parsed['title']) > 200:
        raise IntakeError('canonical title exceeds 200 characters; retain the generic transcript or edit the title')
    if len(parsed['segments']) > 2000:
        raise IntakeError('canonical import supports at most 2000 segments; retain the generic transcript')
    rows = []
    previous_end = 0
    for row in parsed['segments']:
        if len(row['speaker']) > 120:
            raise IntakeError(f"canonical speaker exceeds 120 characters at {row['id']}; retain the generic transcript")
        if len(row['text']) > 12000:
            raise IntakeError(f"canonical text exceeds 12000 characters at {row['id']}; retain the generic transcript")
        if row['start_ms'] < previous_end:
            raise IntakeError(f"canonical import cannot represent overlap at {row['id']}; "
                              'export without --duration-seconds to preserve overlapping captions')
        if Decimal(row['end_ms']) / 1000 > duration:
            raise IntakeError(f"caption {row['id']} exceeds the supplied recording duration")
        rows.append({'id': row['id'], 'start': row['start_ms'] / 1000,
                     'end': row['end_ms'] / 1000, 'speaker': row['speaker'],
                     'text': row['text'], 'verified': False})
        previous_end = row['end_ms']
    return {'title': parsed['title'], 'duration': float(duration), 'synthetic_demo': synthetic_demo,
            'description': 'Imported supplied captions; recording and transcript require human review. '
                           + 'Original SHA-256: ' + parsed['provenance']['source_sha256'],
            'segments': rows, 'chapters': []}


def create_bundle(source: bytes, parsed: dict, *, duration_seconds: str | None = None,
                  synthetic_demo: bool = False) -> bytes:
    """Build deterministic ZIP bytes without touching caller paths."""
    if hashlib.sha256(source).hexdigest() != parsed['provenance']['source_sha256']:
        raise IntakeError('source bytes no longer match the parsed provenance')
    files = {f"source.{parsed['provenance']['format']}": source, 'transcript.json': json_bytes(parsed)}
    if duration_seconds is not None:
        files['episode-import.json'] = json_bytes(canonical_episode(parsed, duration_seconds, synthetic_demo=synthetic_demo))
    files['manifest.json'] = json_bytes({'schema': 'caption-intake-bundle/v1', 'complete': True,
        'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in files.items()}})
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return output.getvalue()


def publish_bundle(destination: Path, payload: bytes) -> None:
    """Publish a complete staged file exclusively; existing targets are never replaced."""
    staging = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.caption-intake-', dir=destination.parent, delete=False) as file:
            staging = Path(file.name)
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        # Atomic no-replace publication, including when another importer wins a race.
        os.link(staging, destination)
    except OSError as exc:
        raise IntakeError(f'cannot publish {destination}: {exc.strerror}; target was not replaced') from exc
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--format', choices=('srt', 'vtt'))
    parser.add_argument('--title', required=True)
    parser.add_argument('--speaker', default='Unspecified', help='explicit label for cues without a voice annotation')
    parser.add_argument('--encoding', default='utf-8-sig', help='SRT encoding override; no guessing')
    parser.add_argument('--duration-seconds', help='actual recording duration supplied by the editor; adds Hive004 import JSON')
    parser.add_argument('--synthetic-demo', action='store_true', help='label the optional episode import as synthetic')
    parser.add_argument('--output', type=Path, required=True, help='new ZIP path; parent must exist')
    args = parser.parse_args(argv)
    try:
        with args.source.open('rb') as file:
            source = file.read(MAX_BYTES + 1)
        fmt = args.format or args.source.suffix.lower().removeprefix('.')
        parsed = parse_captions(source, fmt=fmt, title=args.title, encoding=args.encoding, default_speaker=args.speaker)
        publish_bundle(args.output, create_bundle(source, parsed, duration_seconds=args.duration_seconds,
                                                  synthetic_demo=args.synthetic_demo))
        print(json.dumps({'output': str(args.output), 'cues': len(parsed['segments']),
                          'source_sha256': parsed['provenance']['source_sha256'], 'media_verified': False,
                          'episode_import': args.duration_seconds is not None}))
        return 0
    except (OSError, IntakeError) as exc:
        print(f'caption-intake: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
