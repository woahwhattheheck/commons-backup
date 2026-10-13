from __future__ import annotations
import html
import posixpath
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from .codec import GuardError, loads, read_text, read_text_under_root
SCHEMA = 'commons.public-surface-link-guard/v1'
REPORT_SCHEMA = 'commons.public-surface-link-guard-report/v2'
PUBLIC_CLASSES = frozenset({'STOREFRONT', 'CUSTOMER_FACING', 'PUBLIC_PRODUCT', 'PUBLIC_COMPETITION', 'PUBLIC_DELIVERABLE'})
CLASSES = PUBLIC_CLASSES | frozenset({'INTERNAL'})
BLOCK_KINDS = frozenset({'COMMONS_PAD', 'COMMONS_BOARD', 'COMMONS_RECEIPT', 'COMMONS_ACTION', 'COMMONS_INTERNAL'})
BLOCK_MATCHES = frozenset({'EXACT', 'SUBTREE'})
MAX_SURFACES = 5000
MAX_RULES = 1000
MAX_FILE_BYTES = 2 * 1024 * 1024
REMEDIATION = 'Remove the Commons destination or replace it with a product-specific public URL; use only an exact owner-approved path+destination+expiry exception when required.'
URL = re.compile('(?i)https?:[\\\\/]{2,}[^\\s<>\'\\"`]+')
NET = re.compile('(?i)(?<![:\\\\/])[\\\\/]{2}[A-Za-z0-9.-]+(?::\\d+)?[\\\\/][^\\s<>\'\\"`]*')
MD = re.compile('\\[[^\\]]*\\]\\(([^)\\s]+)(?:\\s+[\'\\"][^\'\\"]*[\'\\"])?\\)')
HTML = re.compile('(?is)\\b(?:href|src|action)\\s*=\\s*([\'\\"])(.*?)\\1')
AUTO = re.compile('<((?:(?:https?:[\\\\/]{2,})|(?:[\\\\/]{2}))[^>]+)>', re.I)
_ASCII_ESCAPE = re.compile('\\\\u00(2[fF]|3[aA]|5[cC])')

def _text(value: Any, name: str, n: int=4096) -> str:
    if type(value) is not str or not value or len(value) > n:
        raise GuardError(f'{name} must be safe non-empty text')
    if any((ord(char) < 32 or ord(char) == 127 or 55296 <= ord(char) <= 57343 for char in value)):
        raise GuardError(f'{name} must be safe non-empty text')
    return value

def _path(value: Any, name: str, _text_fn: Callable[..., str]=_text) -> str:
    text = _text_fn(value, name, 1024).replace('\\', '/')
    path = Path(text)
    if path.is_absolute() or text.startswith('/') or any((part in {'', '.', '..'} for part in path.parts)):
        raise GuardError(f'{name} must be normalized relative path')
    return text

def _keys(obj: dict[str, Any], required: set[str], optional: set[str], name: str) -> None:
    missing = required - set(obj)
    extra = set(obj) - required - optional
    if missing:
        raise GuardError(f"{name} missing keys: {', '.join(sorted(missing))}")
    if extra:
        raise GuardError(f"{name} unknown keys: {', '.join(sorted(extra))}")

def _decode_ascii_escape(match: re.Match[str]) -> str:
    code = match.group(1).lower()
    return {'2f': '/', '3a': ':', '5c': '\\'}[code]

def _deescape(value: str, _html_unescape: Callable[[str], str]=html.unescape, _escape_re: re.Pattern[str]=_ASCII_ESCAPE, _escape_fn: Callable[[re.Match[str]], str]=_decode_ascii_escape) -> str:
    current = value
    for _ in range(4):
        nxt = _html_unescape(current)
        nxt = _escape_re.sub(_escape_fn, nxt)
        nxt = nxt.replace('\\/', '/')
        if nxt == current:
            break
        current = nxt
    return current

def _decode(value: str, _deescape_fn: Callable[[str], str]=_deescape, _unquote_fn: Callable[[str], str]=unquote) -> str:
    current = _deescape_fn(value.strip())
    for _ in range(3):
        nxt = _unquote_fn(current)
        if nxt == current:
            break
        current = nxt
    return current.strip().rstrip('.,;:!?)]}')

def _normalize_path(path: str, _decode_fn: Callable[[str], str]=_decode, _norm_fn: Callable[[str], str]=posixpath.normpath) -> str:
    path = _decode_fn(path or '/').replace('\\', '/')
    trailing = path.endswith('/')
    normalized = _norm_fn('/' + path.lstrip('/'))
    if trailing and normalized != '/':
        normalized += '/'
    return normalized

def _url(value: str, _decode_fn: Callable[[str], str]=_decode, _normalize_path_fn: Callable[[str], str]=_normalize_path, _split_fn: Callable[[str], Any]=urlsplit, _unsplit_fn: Callable[[tuple[str, str, str, str, str]], str]=urlunsplit, _sub_fn: Callable[..., str]=re.sub) -> str | None:
    candidate = _decode_fn(value).replace('\\', '/')
    if candidate.startswith('//'):
        candidate = 'https:' + candidate
    candidate = _sub_fn('(?i)^(https?):/+(?=[^/])', '\\1://', candidate)
    candidate = _sub_fn('(?i)^(https?):/{3,}', '\\1://', candidate)
    try:
        parsed = _split_fn(candidate)
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    if scheme not in {'http', 'https'} or not parsed.netloc:
        return None
    host = (parsed.hostname or '').lower().rstrip('.')
    if not host:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if scheme == 'http' and port == 80 or (scheme == 'https' and port == 443):
        port = None
    netloc = host if port is None else f'{host}:{port}'
    return _unsplit_fn((scheme, netloc, _normalize_path_fn(parsed.path), parsed.query, parsed.fragment))

def _target(value: Any, name: str, _url_fn: Callable[[str], str | None]=_url, _text_fn: Callable[..., str]=_text) -> str:
    url = _url_fn(_text_fn(value, name))
    if url is None:
        raise GuardError(f'{name} must be absolute http(s) URL')
    return url

def _origin_and_path(url: str, _split_fn: Callable[[str], Any]=urlsplit, _normalize_path_fn: Callable[[str], str]=_normalize_path) -> tuple[str, str, str]:
    parsed = _split_fn(url)
    return (parsed.scheme, parsed.netloc.lower(), _normalize_path_fn(parsed.path))

def _rule_match(url: str, rule: dict[str, str], _origin_fn: Callable[[str], tuple[str, str, str]]=_origin_and_path) -> bool:
    if rule['match'] == 'EXACT':
        return url == rule['destination']
    scheme, netloc, path = _origin_fn(url)
    rscheme, rnetloc, rpath = _origin_fn(rule['destination'])
    if (scheme, netloc) != (rscheme, rnetloc):
        return False
    base = rpath.rstrip('/') or '/'
    return path == base or path.startswith(base.rstrip('/') + '/')

def _banned(url: str, rules: list[dict[str, str]], _split_fn: Callable[[str], Any]=urlsplit, _normalize_path_fn: Callable[[str], str]=_normalize_path, _unquote_fn: Callable[[str], str]=unquote, _rule_match_fn: Callable[[str, dict[str, str]], bool]=_rule_match) -> str | None:
    parsed = _split_fn(url)
    host = (parsed.hostname or '').lower().rstrip('.')
    path = _normalize_path_fn(parsed.path).lower()
    if host == 'woahwhattheheck.github.io' and (path == '/commons' or path.startswith('/commons/')):
        return 'COMMONS_PAGES'
    segments = [_unquote_fn(part).lower() for part in _normalize_path_fn(parsed.path).split('/') if part]
    if host in {'github.com', 'www.github.com'} and len(segments) >= 2 and segments[0] == 'woahwhattheheck' and segments[1] in {'commons', 'commons.git'}:
        return 'COMMONS_GITHUB'
    if host == 'raw.githubusercontent.com' and len(segments) >= 2 and segments[:2] == ['woahwhattheheck', 'commons']:
        return 'COMMONS_GITHUB'
    if host == 'api.github.com' and len(segments) >= 3 and segments[:3] == ['repos', 'woahwhattheheck', 'commons']:
        return 'COMMONS_GITHUB'
    if host == 'codeload.github.com' and len(segments) >= 2 and segments[:2] == ['woahwhattheheck', 'commons']:
        return 'COMMONS_GITHUB'
    for rule in rules:
        if _rule_match_fn(url, rule):
            return rule['kind']
    return None

def _make_date_parser() -> Callable[[Any, str], Any]:
    from datetime import date as Date

    def parse(value: Any, name: str):
        text = _text(value, name, 10)
        try:
            parsed = Date.fromisoformat(text)
        except ValueError as exc:
            raise GuardError(f'{name} must be YYYY-MM-DD') from exc
        if parsed.isoformat() != text:
            raise GuardError(f'{name} must be canonical YYYY-MM-DD')
        return parsed
    return parse
_PARSE_DATE = _make_date_parser()

def _validate_impl(doc: Any, _keys_fn: Callable[..., None]=_keys, _text_fn: Callable[..., str]=_text, _path_fn: Callable[[Any, str], str]=_path, _target_fn: Callable[[Any, str], str]=_target, _banned_fn: Callable[[str, list[dict[str, str]]], str | None]=_banned, _parse_date_fn: Callable[[Any, str], Any]=_PARSE_DATE, _schema: str=SCHEMA, _classes: frozenset[str]=CLASSES, _public_classes: frozenset[str]=PUBLIC_CLASSES, _block_kinds: frozenset[str]=BLOCK_KINDS, _block_matches: frozenset[str]=BLOCK_MATCHES, _max_surfaces: int=MAX_SURFACES, _max_rules: int=MAX_RULES) -> dict[str, Any]:
    if type(doc) is not dict:
        raise GuardError('manifest must be object')
    _keys_fn(doc, {'schema', 'surfaces', 'exceptions', 'aliases', 'blocked_destinations'}, set(), 'manifest')
    if doc['schema'] != _schema:
        raise GuardError(f'manifest.schema must be {_schema}')
    for key, limit in (('surfaces', _max_surfaces), ('exceptions', _max_rules), ('aliases', _max_rules), ('blocked_destinations', _max_rules)):
        if type(doc[key]) is not list or len(doc[key]) > limit:
            raise GuardError(f'manifest.{key} must be bounded list')
    blocked: list[dict[str, str]] = []
    blocked_ids: set[str] = set()
    for index, row in enumerate(doc['blocked_destinations']):
        if type(row) is not dict:
            raise GuardError(f'blocked_destination[{index}] must be object')
        _keys_fn(row, {'id', 'kind', 'destination', 'match'}, set(), f'blocked_destination[{index}]')
        ident = _text_fn(row['id'], f'blocked_destination[{index}].id', 128)
        kind = _text_fn(row['kind'], f'blocked_destination[{index}].kind', 64)
        match = _text_fn(row['match'], f'blocked_destination[{index}].match', 16)
        if kind not in _block_kinds:
            raise GuardError(f'blocked_destination[{index}].kind invalid')
        if match not in _block_matches:
            raise GuardError(f'blocked_destination[{index}].match invalid')
        if ident in blocked_ids:
            raise GuardError(f'duplicate blocked destination id: {ident}')
        blocked_ids.add(ident)
        blocked.append({'id': ident, 'kind': kind, 'destination': _target_fn(row['destination'], f'blocked_destination[{index}].destination'), 'match': match})
    blocked.sort(key=lambda row: row['id'])
    surfaces: list[dict[str, Any]] = []
    paths: set[str] = set()
    public_paths: set[str] = set()
    for index, row in enumerate(doc['surfaces']):
        if type(row) is not dict:
            raise GuardError(f'surface[{index}] must be object')
        _keys_fn(row, {'path', 'class'}, {'public_base_url'}, f'surface[{index}]')
        path = _path_fn(row['path'], f'surface[{index}].path')
        classification = _text_fn(row['class'], f'surface[{index}].class', 64)
        if classification not in _classes:
            raise GuardError(f'surface[{index}].class invalid')
        if path in paths:
            raise GuardError(f'duplicate surface path: {path}')
        paths.add(path)
        if classification == 'INTERNAL' and 'public_base_url' in row:
            raise GuardError(f'surface[{index}] INTERNAL must not declare public_base_url')
        base = _target_fn(row['public_base_url'], f'surface[{index}].public_base_url') if 'public_base_url' in row else None
        if classification in _public_classes:
            public_paths.add(path)
        normalized_surface = {'path': path, 'class': classification}
        if base is not None:
            normalized_surface['public_base_url'] = base
        surfaces.append(normalized_surface)
    surfaces.sort(key=lambda row: row['path'])
    exceptions: list[dict[str, str]] = []
    seen_exceptions: set[tuple[str, str]] = set()
    for index, row in enumerate(doc['exceptions']):
        if type(row) is not dict:
            raise GuardError(f'exception[{index}] must be object')
        _keys_fn(row, {'path', 'destination', 'expires_on', 'reason'}, set(), f'exception[{index}]')
        path = _path_fn(row['path'], f'exception[{index}].path')
        if path not in public_paths:
            raise GuardError(f'exception[{index}] path is not a declared public surface')
        destination = _target_fn(row['destination'], f'exception[{index}].destination')
        if not _banned_fn(destination, blocked):
            raise GuardError(f'exception[{index}] destination is not blocked Commons target')
        expires = _parse_date_fn(row['expires_on'], f'exception[{index}].expires_on').isoformat()
        reason = _text_fn(row['reason'], f'exception[{index}].reason', 512)
        key = (path, destination)
        if key in seen_exceptions:
            raise GuardError(f'duplicate exception for {path}')
        seen_exceptions.add(key)
        exceptions.append({'path': path, 'destination': destination, 'expires_on': expires, 'reason': reason})
    exceptions.sort(key=lambda row: (row['path'], row['destination']))
    aliases: list[dict[str, str]] = []
    seen_aliases: set[str] = set()
    for index, row in enumerate(doc['aliases']):
        if type(row) is not dict:
            raise GuardError(f'alias[{index}] must be object')
        _keys_fn(row, {'alias', 'target'}, set(), f'alias[{index}]')
        alias = _target_fn(row['alias'], f'alias[{index}].alias')
        target = _target_fn(row['target'], f'alias[{index}].target')
        if not _banned_fn(target, blocked):
            raise GuardError(f'alias[{index}] target must be blocked Commons target')
        if alias in seen_aliases:
            raise GuardError(f'duplicate alias: {alias}')
        seen_aliases.add(alias)
        aliases.append({'alias': alias, 'target': target})
    aliases.sort(key=lambda row: row['alias'])
    return {'schema': _schema, 'surfaces': surfaces, 'exceptions': exceptions, 'aliases': aliases, 'blocked_destinations': blocked}

def validate(doc: Any, _validate_fn: Callable[[Any], dict[str, Any]]=_validate_impl) -> dict[str, Any]:
    return _validate_fn(doc)
