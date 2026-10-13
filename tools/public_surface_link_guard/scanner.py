from __future__ import annotations
import html
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
from .codec import GuardError, loads, read_text, read_text_under_root
from .policy import MAX_FILE_BYTES, REMEDIATION, REPORT_SCHEMA, _PARSE_DATE, _banned, _decode, _deescape, _normalize_path, _url, _validate_impl
from .policy import URL, NET, MD, HTML, AUTO

def _text_variants(text: str, _deescape_fn: Callable[[str], str]=_deescape, _html_unescape: Callable[[str], str]=html.unescape) -> list[str]:
    variants = [text]
    current = text
    for _ in range(4):
        nxt = _deescape_fn(current)
        if nxt == current:
            break
        variants.append(nxt)
        current = nxt
    entity = _html_unescape(current)
    if entity not in variants:
        variants.append(entity)
    return variants

def _links(text: str, _variants_fn: Callable[[str], list[str]]=_text_variants, _regexes=((URL, 0), (NET, 0), (MD, 1), (HTML, 2), (AUTO, 1))) -> list[tuple[int, str]]:
    out: dict[tuple[int, str], tuple[int, str]] = {}
    for variant in _variants_fn(text):
        for regex, group in _regexes:
            for match in regex.finditer(variant):
                raw = match.group(group).strip()
                line = variant.count('\n', 0, match.start(group)) + 1
                if raw:
                    out[line, raw] = (line, raw)
    return [out[key] for key in sorted(out)]

def _candidate(raw: str, base: str | None, _url_fn: Callable[[str], str | None]=_url, _join_fn: Callable[[str, str], str]=urljoin, _decode_fn: Callable[[str], str]=_decode) -> str | None:
    direct = _url_fn(raw)
    if direct:
        return direct
    if base:
        return _url_fn(_join_fn(base, _decode_fn(raw)))
    return None

def _resolve_alias(url: str, aliases: list[dict[str, str]], _url_fn: Callable[[str], str | None]=_url, _split_fn: Callable[[str], Any]=urlsplit, _normalize_path_fn: Callable[[str], str]=_normalize_path, _unsplit_fn: Callable[[tuple[str, str, str, str, str]], str]=urlunsplit) -> tuple[str, str | None]:
    source = _split_fn(url)
    source_path = _normalize_path_fn(source.path)
    for row in aliases:
        alias = _split_fn(row['alias'])
        alias_path = _normalize_path_fn(alias.path)
        if (source.scheme, source.netloc.lower()) != (alias.scheme, alias.netloc.lower()):
            continue
        base = alias_path.rstrip('/') or '/'
        if source_path != base and (not source_path.startswith(base.rstrip('/') + '/')):
            continue
        suffix = source_path[len(base):] if base != '/' else source_path
        target = _split_fn(row['target'])
        target_path = _normalize_path_fn(target.path).rstrip('/')
        mapped_path = target_path + suffix
        mapped = _unsplit_fn((target.scheme, target.netloc, mapped_path or '/', source.query, source.fragment))
        return (_url_fn(mapped) or row['target'], row['alias'])
    return (url, None)

def _scan_impl(*, root: Path, manifest: dict[str, Any], as_of: Any, evaluation_mode: str, _validate_fn: Callable[[Any], dict[str, Any]]=_validate_impl, _read_fn: Callable[[Path, str, int], str]=read_text_under_root, _links_fn: Callable[[str], list[tuple[int, str]]]=_links, _candidate_fn: Callable[[str, str | None], str | None]=_candidate, _resolve_alias_fn: Callable[[str, list[dict[str, str]]], tuple[str, str | None]]=_resolve_alias, _banned_fn: Callable[[str, list[dict[str, str]]], str | None]=_banned, _parse_date_fn: Callable[[Any, str], Any]=_PARSE_DATE, _max_file_bytes: int=MAX_FILE_BYTES, _remediation: str=REMEDIATION, _report_schema: str=REPORT_SCHEMA) -> dict[str, Any]:
    from datetime import date as Date
    if type(as_of) is not Date:
        raise GuardError('as_of must be exact date')
    normalized = _validate_fn(manifest)
    exception_map = {(row['path'], row['destination']): row for row in normalized['exceptions']}
    violations: list[dict[str, Any]] = []
    exemptions: list[dict[str, Any]] = []
    scanned: list[dict[str, Any]] = []
    for surface in normalized['surfaces']:
        text = _read_fn(root, surface['path'], _max_file_bytes)
        if surface['class'] == 'INTERNAL':
            scanned.append({'path': surface['path'], 'class': 'INTERNAL', 'candidate_links': 0, 'enforcement': 'EXPLICIT_INTERNAL'})
            continue
        links = _links_fn(text)
        scanned.append({'path': surface['path'], 'class': surface['class'], 'candidate_links': len(links), 'enforcement': 'PUBLIC_BACKLINK_SCAN'})
        seen_candidates: set[tuple[int, str, str | None]] = set()
        for line, raw in links:
            url = _candidate_fn(raw, surface.get('public_base_url'))
            if not url:
                continue
            destination, alias = _resolve_alias_fn(url, normalized['aliases'])
            reason = _banned_fn(destination, normalized['blocked_destinations'])
            if not reason:
                continue
            candidate_key = (line, destination, alias)
            if candidate_key in seen_candidates:
                continue
            seen_candidates.add(candidate_key)
            exception = exception_map.get((surface['path'], destination))
            row = {'path': surface['path'], 'line': line, 'raw': raw, 'destination': destination, 'via_alias': alias}
            if exception and as_of <= _parse_date_fn(exception['expires_on'], 'exception expires_on'):
                exemptions.append(row | {'expires_on': exception['expires_on'], 'reason': exception['reason']})
                continue
            violations.append(row | {'class': surface['class'], 'reason': 'EXPIRED_EXCEPTION' if exception else reason, 'remediation': _remediation})
    key = lambda row: (row['path'], row['line'], row['destination'], row['raw'])
    violations.sort(key=key)
    exemptions.sort(key=key)
    scanned.sort(key=lambda row: row['path'])
    return {'schema': _report_schema, 'evaluated_on': as_of.isoformat(), 'evaluation_mode': evaluation_mode, 'state': 'HOLD_PUBLIC_COMMONS_BACKLINK' if violations else 'PASS_NO_PUBLIC_COMMONS_BACKLINK', 'scanned_surfaces': scanned, 'violations': violations, 'active_exemptions': exemptions, 'authority': {'network_access_performed': False, 'external_send_authorized': False, 'deployment_authorized': False, 'owner_exception_inferred': False}}

def scan_manifest(*, root: Path, manifest: dict[str, Any], as_of: Any, _scan_fn: Callable[..., dict[str, Any]]=_scan_impl) -> dict[str, Any]:
    """Historical/testing seam. This result is never labeled PROCESS_CURRENT."""
    return _scan_fn(root=root, manifest=manifest, as_of=as_of, evaluation_mode='HISTORICAL_EXPLICIT')

def load_manifest(path: Path, _validate_fn: Callable[[Any], dict[str, Any]]=_validate_impl, _loads_fn: Callable[[str], Any]=loads, _read_fn: Callable[[Path, int], str]=read_text) -> dict[str, Any]:
    return _validate_fn(_loads_fn(_read_fn(path, 256 * 1024)))

def _make_process_current_scan(load_fn: Callable[[Path], dict[str, Any]], scan_fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    from datetime import datetime as DateTime, timezone as Timezone

    def process_date():
        return DateTime.now(Timezone.utc).date()

    def current_scan(*, root: Path, manifest_path: Path) -> dict[str, Any]:
        manifest = load_fn(manifest_path)
        return scan_fn(root=root, manifest=manifest, as_of=process_date(), evaluation_mode='PROCESS_CURRENT')
    return current_scan
scan_paths = _make_process_current_scan(load_manifest, _scan_impl)
