#!/usr/bin/env python3
"""Local batch caption workbench over the existing source-preserving parser."""
from __future__ import annotations

import argparse
import base64
import binascii
from collections import Counter
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
from pathlib import Path
import re
import sys
import traceback
from urllib.parse import urlsplit
import zipfile

from caption_intake import (MAX_BYTES, MAX_CUES, IntakeError, canonical_episode,
                            create_bundle, json_bytes, parse_captions)
from saved_handoff import MAX_ARCHIVE_BYTES, reopen_handoff

MAX_FILES = 20
MAX_BATCH_BYTES = 20_000_000
MAX_REQUEST_BYTES = 28_000_000  # Includes base64 expansion and request metadata.
MAX_BATCH_CUES = 50_000
PAGE_SIZE = 100
PREVIEW_CHARS = 4_000
ROOT = Path(__file__).resolve().parent


def text_field(row: dict, key: str, default: str, limit: int) -> str:
    value = row.get(key, default)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise IntakeError(f'{key} must contain 1..{limit} characters')
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise IntakeError(f'{key} contains control characters')
    return value.strip()


def read_upload(row: object) -> tuple[str, bytes, dict]:
    if not isinstance(row, dict):
        raise IntakeError('each file must be an object')
    name = text_field(row, 'name', 'captions', 500)
    encoded = row.get('source_base64')
    if not isinstance(encoded, str) or not 0 < len(encoded) <= 4 * ((MAX_BYTES + 2) // 3):
        raise IntakeError(f'source must contain 1..{MAX_BYTES} bytes')
    try:
        source = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise IntakeError('source_base64 must encode the original caption bytes') from exc
    if not 0 < len(source) <= MAX_BYTES:
        raise IntakeError(f'source must contain 1..{MAX_BYTES} bytes')
    settings = {
        'fmt': text_field(row, 'format', Path(name).suffix.lower().lstrip('.'), 8),
        'title': text_field(row, 'title', Path(name).stem, 300),
        'encoding': text_field(row, 'encoding', 'utf-8-sig', 80),
        'default_speaker': text_field(row, 'speaker', 'Unspecified', 200),
    }
    return name, source, settings


def describe(parsed: dict, row: dict) -> dict:
    segments = parsed['segments']
    provenance = parsed['provenance']
    overlaps, end = 0, 0
    for cue in segments:
        overlaps += cue['start_ms'] < end
        end = max(end, cue['end_ms'])
    voices = Counter(cue['speaker'] for cue in segments)
    query = row.get('query', '')
    offset = row.get('offset', 0)
    if not isinstance(query, str) or len(query) > 256:
        raise IntakeError('preview query must be text of at most 256 characters')
    if type(offset) is not int or not 0 <= offset <= MAX_CUES:
        raise IntakeError(f'preview offset must be an integer from 0 to {MAX_CUES}')
    needle = query.casefold()
    indices = [i for i, cue in enumerate(segments)
               if not needle or any(needle in str(value).casefold() for value in
                                    (cue['id'], cue['text'], cue['speaker'],
                                     provenance['cues'][i]['source_id']))]
    offset = min(offset, max(0, ((len(indices) - 1) // PAGE_SIZE) * PAGE_SIZE))
    preview = []
    for i in indices[offset:offset + PAGE_SIZE]:
        cue, original = segments[i], provenance['cues'][i]
        preview.append({**cue, 'text': cue['text'][:PREVIEW_CHARS],
                        'text_truncated': len(cue['text']) > PREVIEW_CHARS,
                        'source_id': original['source_id'], 'line': original['line'],
                        'timing': original['timing'], 'settings': original['settings'],
                        'raw_payload': original['raw_payload'][:PREVIEW_CHARS],
                        'raw_truncated': len(original['raw_payload']) > PREVIEW_CHARS})
    return {
        'title': parsed['title'], 'cue_count': len(segments),
        'first_caption_ms': segments[0]['start_ms'], 'last_caption_ms': end,
        'overlapping_cues': overlaps, 'speaker_count': len(voices),
        'speakers': [{'name': name, 'cues': count} for name, count in voices.most_common(100)],
        'source_sha256': provenance['source_sha256'], 'source_bytes': provenance['source_bytes'],
        'format': provenance['format'], 'encoding': provenance['encoding'],
        'media_verified': False,
        'preview': {'offset': offset, 'page_size': PAGE_SIZE, 'matched': len(indices),
                    'query': query, 'cues': preview},
    }


def process_files(document: object, *, build: bool = False) -> tuple[list[dict], list[tuple[str, bytes]]]:
    if not isinstance(document, dict) or not isinstance(document.get('files'), list):
        raise IntakeError('request must contain a files array')
    files = document['files']
    if not 1 <= len(files) <= MAX_FILES:
        raise IntakeError(f'select 1..{MAX_FILES} files')
    results: list[dict] = []
    bundles: list[tuple[str, bytes]] = []
    source_total = cue_total = 0
    for index, row in enumerate(files):
        result = {'index': index, 'name': f'File {index + 1}', 'ok': False, 'parsed': False}
        results.append(result)
        try:
            name, source, settings = read_upload(row)
            result['name'] = name
            source_total += len(source)
            if source_total > MAX_BATCH_BYTES:
                raise IntakeError(f'selected originals exceed {MAX_BATCH_BYTES} bytes; split the batch')
            parsed = parse_captions(source, **settings)
            cue_total += len(parsed['segments'])
            if cue_total > MAX_BATCH_CUES:
                raise IntakeError(f'selected captions exceed {MAX_BATCH_CUES} cues; split the batch')
            result.update(describe(parsed, row))
            result['parsed'] = True
            duration = row.get('duration_seconds')
            if duration == '':
                duration = None
            synthetic = row.get('synthetic_demo', False)
            if type(synthetic) is not bool:
                raise IntakeError('synthetic_demo must be a boolean')
            result['episode_import'] = duration is not None
            if build:
                payload = create_bundle(source, parsed, duration_seconds=duration, synthetic_demo=synthetic)
                stem = re.sub(r'[^a-zA-Z0-9_-]+', '-', Path(name).stem).strip('-')[:60] or 'captions'
                member = f'{index + 1:02d}-{stem}.zip'
                bundles.append((member, payload))
                result['bundle'] = {'path': member, 'bytes': len(payload),
                                    'sha256': hashlib.sha256(payload).hexdigest()}
            elif duration is not None:
                canonical_episode(parsed, duration, synthetic_demo=synthetic)
            result['ok'] = True
        except IntakeError as exc:
            result['error'] = str(exc)
    return results, bundles


def batch_archive(results: list[dict], bundles: list[tuple[str, bytes]]) -> bytes:
    """Wrap the existing handoff ZIPs; no partial export or path from an upload."""
    if not results or not all(row['ok'] for row in results) or len(bundles) != len(results):
        raise IntakeError('fix or deselect every invalid file before exporting this batch')
    manifest = {'schema': 'caption-workbench-batch/v1', 'complete': True,
                'media_verified': False, 'files': [
                    {key: row[key] for key in ('name', 'title', 'source_sha256', 'source_bytes',
                                               'format', 'encoding', 'cue_count', 'episode_import', 'bundle')}
                    for row in results]}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, payload in [*bundles, ('batch-manifest.json', json_bytes(manifest))]:
            archive.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), payload)
    return output.getvalue()


def reject_constant(value: str) -> None:
    raise IntakeError(f'JSON constant {value} is not supported')


class WorkbenchServer(HTTPServer):
    """One request at a time bounds concurrent in-memory conversion work."""
    def __init__(self, port: int):
        self.assets = {
            '/': ((ROOT / 'workbench.html').read_bytes(), 'text/html; charset=utf-8'),
            '/workbench.js': ((ROOT / 'workbench.js').read_bytes(), 'text/javascript; charset=utf-8'),
        }
        super().__init__(('127.0.0.1', port), WorkbenchHandler)


class WorkbenchHandler(BaseHTTPRequestHandler):
    server: WorkbenchServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, format: str, *args: object) -> None:
        # Do not echo uploaded names, captions, query strings, or request headers.
        pass

    def reply(self, status: int, payload: bytes, kind: str = 'application/json; charset=utf-8',
              filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; "
                         "style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in self.server.assets:
            payload, kind = self.server.assets[path]
            self.reply(200, payload, kind)
        elif path == '/api/info':
            self.reply(200, json_bytes({'service': 'caption-workbench', 'max_files': MAX_FILES,
                                       'max_file_bytes': MAX_BYTES, 'max_batch_bytes': MAX_BATCH_BYTES,
                                       'max_batch_cues': MAX_BATCH_CUES, 'max_archive_bytes': MAX_ARCHIVE_BYTES,
                                       'page_size': PAGE_SIZE}))
        elif path == '/favicon.ico':
            self.reply(204, b'')
        else:
            self.reply(404, json_bytes({'error': 'route not found'}))

    def read_body(self, content_type: str, maximum: int) -> bytes:
        if self.headers.get('Transfer-Encoding'):
            raise IntakeError('send a Content-Length request; chunked bodies are not supported')
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != content_type:
            raise IntakeError(f'Content-Type must be {content_type}')
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 9:
            raise IntakeError('one integer Content-Length is required')
        length = int(lengths[0])
        if not 0 < length <= maximum:
            raise IntakeError(f'request exceeds {maximum} bytes or is empty')
        payload = self.rfile.read(length)
        if len(payload) != length:
            raise IntakeError('incomplete request; original files were not stored')
        return payload

    def read_document(self) -> object:
        payload = self.read_body('application/json', MAX_REQUEST_BYTES)
        try:
            return json.loads(payload.decode('utf-8'), parse_constant=reject_constant)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise IntakeError('invalid UTF-8 JSON request') from exc

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path not in ('/api/preview', '/api/export', '/api/batch', '/api/reopen'):
            self.reply(404, json_bytes({'error': 'route not found'}))
            return
        try:
            if path == '/api/reopen':
                files = reopen_handoff(self.read_body('application/zip', MAX_ARCHIVE_BYTES),
                                       max_files=MAX_FILES, max_source_bytes=MAX_BATCH_BYTES,
                                       max_cues=MAX_BATCH_CUES)
                results, _ = process_files({'files': files})
                if not all(row['ok'] for row in results):
                    raise IntakeError('saved handoff options cannot be restored by this workbench')
                self.reply(200, json_bytes({'ok': True, 'files': files, 'results': results,
                                           'media_verified': False}))
                return
            document = self.read_document()
            if path == '/api/export' and (not isinstance(document, dict)
                                         or not isinstance(document.get('files'), list)
                                         or len(document['files']) != 1):
                raise IntakeError('individual export requires exactly one file')
            results, bundles = process_files(document, build=path != '/api/preview')
            ok = all(row['ok'] for row in results)
            if path == '/api/preview' or not ok:
                self.reply(200 if path == '/api/preview' else 422,
                           json_bytes({'ok': ok, 'results': results}))
            elif path == '/api/export':
                self.reply(200, bundles[0][1], 'application/zip', bundles[0][0])
            else:
                self.reply(200, batch_archive(results, bundles), 'application/zip', 'caption-batch.zip')
        except IntakeError as exc:
            self.reply(400, json_bytes({'error': str(exc)}))
        except (TimeoutError, ConnectionError):
            self.close_connection = True
        except Exception:
            # Genuine programming failures stay visible; never turn them into a successful export.
            traceback.print_exc(file=sys.stderr)
            self.reply(500, json_bytes({'error': 'conversion failed unexpectedly; see the server terminal'}))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766, help='loopback port (0 selects an available port)')
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error('--port must be from 0 to 65535')
    try:
        with WorkbenchServer(args.port) as server:
            print(f'Caption workbench: http://127.0.0.1:{server.server_port}/', flush=True)
            print('Originals are processed in memory. Close the tab to clear its selection; Ctrl+C stops the server.', flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f'caption-workbench: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
