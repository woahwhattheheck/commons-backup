#!/usr/bin/env python3
"""Offline, non-mutating local-link and explicit-locator verification.

Only the supplied bundle is inspected. A successful check establishes a local
file/locator match, not evidence quality, factual findings or external reachability.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, dataclass, field
import difflib
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import unquote, urlsplit

MAX_BYTES = 4 * 1024 * 1024
TEXT_SUFFIXES = {'.txt', '.md', '.csv', '.json', '.html', '.htm', '.xml', '.log'}


@dataclass
class Result:
    id: str
    source: str
    target: str
    status: str
    detail: str
    source_line: int | None = None
    resolved_path: str | None = None
    suggestions: list[str] = field(default_factory=list)


class HTMLIndex(HTMLParser):
    """Collect literal destination IDs and links; never run scripts or fetch URLs."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: Counter[str] = Counter()
        self.links: list[tuple[int, str]] = []
        self.has_base = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == 'base' and 'href' in values:
            self.has_base = True
        # An <a id="x" name="x"> is one destination, not two.
        names = {values.get('id')}
        if tag == 'a':
            names.add(values.get('name'))
        self.anchors.update(value for value in names if value is not None)
        for key in ('href', 'src'):
            if tag != 'base' and values.get(key) is not None:
                self.links.append((self.getpos()[0], values[key]))

    handle_startendtag = handle_starttag


def normalized(value: str) -> str:
    return unicodedata.normalize('NFC', value).casefold()


def markdown_anchors(text: str) -> Counter[str]:
    """Conservative ATX-heading anchors plus literal HTML IDs.

    Complex inline markup/setext headings require explicit HTML IDs instead of
    guessing a renderer's slug. Repeated simple headings receive -1, -2, ... .
    """
    anchors: Counter[str] = Counter()
    seen: Counter[str] = Counter()
    visible: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        match = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if match:
            marker = match[1]
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            continue
        if fence:
            continue
        visible.append(line)
        heading = re.match(r'^ {0,3}#{1,6}[ \t]+(.+?)\s*#*\s*$', line)
        if not heading or any(c in heading[1] for c in '[]<>*_`\\'):
            continue
        title = heading[1].lower()
        slug = ''.join(c for c in title if c.isalnum() or c in '-_ ')
        slug = slug.replace(' ', '-')
        candidate = slug
        while candidate in anchors:
            seen[slug] += 1
            candidate = f'{slug}-{seen[slug]}'
        anchors[candidate] += 1
    parser = HTMLIndex()
    parser.feed('\n'.join(visible))
    anchors.update(parser.anchors)
    return anchors


class Bundle:
    def __init__(self, root: Path, max_bytes: int = MAX_BYTES) -> None:
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('bundle root must be a directory')
        if max_bytes < 1:
            raise ValueError('max_bytes must be positive')
        self.max_bytes = max_bytes
        self.files = sorted(p.relative_to(self.root).as_posix()
                            for p in self.root.rglob('*') if p.is_file())
        self.portable: dict[str, list[str]] = {}
        for name in self.files:
            self.portable.setdefault(normalized(name), []).append(name)

    def local_path(self, value: str) -> Path:
        path = (self.root / value).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('destination is outside the supplied bundle')
        return path

    def read(self, path: Path) -> bytes:
        # Read at most limit + 1 bytes, including a file that grows during a check.
        with path.open('rb') as handle:
            data = handle.read(self.max_bytes + 1)
        if len(data) > self.max_bytes:
            raise ValueError(f'content exceeds inspection limit {self.max_bytes} bytes')
        return data

    def alternatives(self, wanted: str, expected_sha: str | None) -> list[str]:
        if expected_sha:
            matches = []
            for name in self.files:
                try:
                    data = self.read(self.local_path(name))
                    if hashlib.sha256(data).hexdigest() == expected_sha:
                        matches.append(name)
                except (OSError, ValueError):
                    continue
            if matches:
                return matches
        basename = Path(wanted).name
        exact_name = [p for p in self.files if normalized(Path(p).name) == normalized(basename)]
        return exact_name or difflib.get_close_matches(wanted, self.files, n=5, cutoff=0.6)

    def verify(self, ref: dict) -> Result:
        if not isinstance(ref, dict):
            return Result('', '', '', 'INVALID_REFERENCE', 'reference must be an object')
        result = Result(str(ref.get('id', '')), str(ref.get('source', '')),
                        str(ref.get('target', '')), 'INVALID_REFERENCE', '')
        def finish(status: str, detail: str, suggestions: list[str] | None = None) -> Result:
            result.status, result.detail = status, detail
            result.suggestions = suggestions or []
            return result
        if not all(isinstance(ref.get(key), str) and ref[key]
                   for key in ('id', 'source', 'target')):
            return finish('INVALID_REFERENCE', 'id, source and target must be nonempty strings')
        if 'source_line' in ref:
            line = ref['source_line']
            if type(line) is not int or line < 1:
                return finish('INVALID_REFERENCE', 'source_line must be a positive integer')
            result.source_line = line
        expected_sha = ref.get('sha256')
        if expected_sha is not None and not (isinstance(expected_sha, str) and
                                             re.fullmatch('[0-9a-f]{64}', expected_sha)):
            return finish('INVALID_REFERENCE', 'sha256 must be 64 lowercase hexadecimal characters')
        target = ref['target']
        if '\\' in target or any(ord(c) < 32 or ord(c) == 127 for c in target):
            return finish('NONPORTABLE_TARGET', 'use URL-style relative paths without control characters')
        try:
            source = self.local_path(ref['source'])
            if not source.is_file():
                return finish('MISSING_SOURCE', 'the citing source file does not exist')
            if result.source_line and result.source_line > len(self.read(source).decode('utf-8-sig').splitlines()):
                return finish('MISSING_SOURCE_LINE', 'the declared citing line is beyond the source')
            if source.suffix.lower() in ('.html', '.htm'):
                source_index = HTMLIndex()
                source_index.feed(self.read(source).decode('utf-8-sig'))
                if source_index.has_base:
                    return finish('UNSUPPORTED_BASE', 'citing HTML uses <base href>; its navigation is not evaluated')
            parts = urlsplit(target)
            if parts.scheme or parts.netloc:
                return finish('EXTERNAL_UNCHECKED', 'external or scheme-bearing destination; no network request made')
            if parts.query:
                return finish('UNSUPPORTED_QUERY', 'query-dependent local navigation is not evaluated')
            if re.search(r'%(?![0-9a-fA-F]{2})', target):
                return finish('INVALID_URL_ENCODING', 'percent escapes require two hexadecimal digits')
            path_part = unquote(parts.path, encoding='utf-8', errors='strict')
            fragment = unquote(parts.fragment, encoding='utf-8', errors='strict')
            if '\\' in path_part or '\x00' in path_part or '\x00' in fragment:
                return finish('NONPORTABLE_TARGET', 'decoded path or fragment contains an unsupported character')
            if path_part.startswith('/') or re.match(r'^[a-zA-Z]:', path_part):
                return finish('NONPORTABLE_TARGET', 'absolute paths do not travel with an exported bundle')
            candidate = source.parent / path_part if path_part else source
            path = candidate.resolve()
            if not path.is_relative_to(self.root):
                return finish('OUTSIDE_BUNDLE', 'destination is outside the supplied bundle; not inspected')
            relative = path.relative_to(self.root).as_posix()
            result.resolved_path = relative
            portable = self.portable.get(normalized(relative), [])
            if len(portable) > 1:
                return finish('AMBIGUOUS_PATH', 'case/Unicode-equivalent file names are not portable', portable)
            if not path.is_file():
                if portable:
                    return finish('PATH_SPELLING_MISMATCH', 'case or Unicode spelling differs from the bundle', portable)
                return finish('MISSING_TARGET', 'destination is missing; suggestions are not automatic redirects',
                              self.alternatives(relative, expected_sha))
            if not fragment and ref.get('locator') is None and expected_sha is None:
                return finish('VERIFIED', 'local file exists; no internal locator was requested')
            data = self.read(path)
            if expected_sha and hashlib.sha256(data).hexdigest() != expected_sha:
                return finish('CONTENT_CHANGED', 'file bytes differ from the cited SHA-256 snapshot')
            locator = ref.get('locator')
            if locator is not None and (not isinstance(locator, dict) or not locator):
                return finish('INVALID_LOCATOR', 'locator must be a nonempty object')
            if fragment or locator:
                if path.suffix.lower() not in TEXT_SUFFIXES:
                    return finish('UNSUPPORTED_LOCATOR', 'binary/document page locators need a format-aware adapter')
                text = data.decode('utf-8-sig')
                if fragment:
                    if path.suffix.lower() in ('.html', '.htm'):
                        parser = HTMLIndex()
                        parser.feed(text)
                        anchors = parser.anchors
                    elif path.suffix.lower() == '.md':
                        anchors = markdown_anchors(text)
                    else:
                        return finish('UNSUPPORTED_LOCATOR', 'fragments supported only for HTML and simple Markdown anchors')
                    count = anchors[fragment]
                    if count == 0:
                        return finish('MISSING_ANCHOR', f'no exact destination ID/heading anchor {fragment!r}',
                                      difflib.get_close_matches(fragment, sorted(anchors), n=5))
                    if count > 1:
                        return finish('AMBIGUOUS_ANCHOR', f'{count} destinations share anchor {fragment!r}')
                if locator:
                    kind = locator.get('kind')
                    if kind == 'lines':
                        first, last = locator.get('start'), locator.get('end', locator.get('start'))
                        if type(first) is not int or type(last) is not int or not 1 <= first <= last:
                            return finish('INVALID_LOCATOR', 'line bounds must be positive integers with start <= end')
                        if last > len(text.splitlines()):
                            return finish('MISSING_LINES', f'requested ending line {last} exceeds file length')
                    elif kind == 'quote':
                        quote = locator.get('text')
                        if not isinstance(quote, str) or not quote:
                            return finish('INVALID_LOCATOR', 'quote text must be nonempty')
                        # Include overlapping occurrences; count() would miss ambiguity in "aaa" / "aa".
                        count = sum(text.startswith(quote, i) for i in range(len(text)))
                        if count != 1:
                            return finish('MISSING_QUOTE' if not count else 'AMBIGUOUS_QUOTE',
                                          f'exact quotation occurs {count} times')
                    elif kind == 'csv':
                        if path.suffix.lower() != '.csv':
                            return finish('UNSUPPORTED_LOCATOR', 'CSV row locators require a .csv destination')
                        reader = csv.DictReader(io.StringIO(text, newline=''), strict=True)
                        column, value = locator.get('column'), locator.get('value')
                        if not isinstance(column, str) or not isinstance(value, str):
                            return finish('INVALID_LOCATOR', 'CSV column and value must be strings')
                        headers = reader.fieldnames or []
                        if headers.count(column) != 1:
                            return finish('INVALID_CSV_COLUMN', 'CSV key column is missing or duplicated')
                        records = list(reader)
                        if any(None in row or any(v is None for v in row.values()) for row in records):
                            return finish('MALFORMED_CSV', 'CSV record width does not match its headers')
                        matches = [row for row in records if row.get(column) == value]
                        if len(matches) != 1:
                            return finish('MISSING_RECORD' if not matches else 'AMBIGUOUS_RECORD',
                                          f'{len(matches)} CSV records match {column}={value!r}')
                    else:
                        return finish('UNSUPPORTED_LOCATOR', f'locator kind {kind!r} is not implemented')
            return finish('VERIFIED', 'all requested file, byte-identity and locator checks passed')
        except UnicodeError as error:
            return finish('UNREADABLE_TEXT', str(error))
        except (OSError, ValueError, csv.Error) as error:
            return finish('INSPECTION_ERROR', str(error))

    def scan_html(self, source: str) -> list[Result]:
        try:
            text = self.read(self.local_path(source)).decode('utf-8-sig')
            parser = HTMLIndex()
            parser.feed(text)
            if parser.has_base:
                return [Result(f'{source}:base', source, '', 'UNSUPPORTED_BASE',
                               'HTML <base href> changes link resolution; supply a resolved export')]
            return [self.verify({'id': f'{source}:{line}:{index}', 'source': source,
                                 'source_line': line, 'target': target})
                    for index, (line, target) in enumerate(parser.links, 1)]
        except (OSError, ValueError, UnicodeError) as error:
            return [Result(source, source, '', 'INSPECTION_ERROR', str(error))]


def check(root: Path, manifest: dict) -> dict:
    if not isinstance(manifest, dict) or type(manifest.get('version')) is not int or manifest['version'] != 1:
        raise ValueError('manifest version must be integer 1')
    references, sources = manifest.get('citations', []), manifest.get('scan_html', [])
    if not isinstance(references, list) or not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
        raise ValueError('citations and scan_html must be arrays; scan_html entries must be strings')
    bundle = Bundle(root)
    results = [bundle.verify(ref) for ref in references]
    for source in sorted(set(sources)):
        results.extend(bundle.scan_html(source))
    ids = Counter(result.id for result in results if result.id)
    for result in results:
        if ids[result.id] > 1:
            result.status = 'DUPLICATE_CITATION_ID'
            result.detail = 'citation IDs must identify one source reference unambiguously'
    counts = dict(sorted(Counter(result.status for result in results).items()))
    unresolved = len(results) - counts.get('VERIFIED', 0)
    return {'version': 1, 'verdict': 'VERIFIED' if results and not unresolved else 'UNRESOLVED',
            'total': len(results), 'verified': counts.get('VERIFIED', 0), 'unresolved': unresolved,
            'coverage': 'declared citations and links in explicitly selected HTML files only',
            'counts': counts, 'results': [asdict(result) for result in results]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('manifest', type=Path, help='JSON manifest read independently of the bundle')
    args = parser.parse_args(argv)
    try:
        report = check(args.bundle, json.loads(args.manifest.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError) as error:
        print(json.dumps({'verdict': 'INVALID_INPUT', 'detail': str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['verdict'] == 'VERIFIED' else 1


if __name__ == '__main__':
    sys.exit(main())
