"""Creator reward campaign desk. Python standard library; local handoff only; no provider calls."""
import argparse
import csv
import hashlib
import io
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import stat
import sys
import threading
import uuid
import zipfile
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlsplit

ROOT = Path(__file__).resolve().parent
INDEX_HTML = (ROOT / 'index.html').read_bytes()  # read once: the desk opens no other file while serving
PLATFORMS = ('TIKTOK', 'INSTAGRAM', 'YOUTUBE', 'X', 'OTHER')
RULE_KINDS = ('FIXED_PER_APPROVED', 'PER_THOUSAND_VIEWS')
CAMPAIGN_STATES = ('DRAFT', 'OPEN', 'CLOSED')
REVIEWABLE = 'SUBMITTED'
ADMIN_FEE_BPS = 500  # proposed 5% administration fee; PROPOSED_NOT_ACCEPTED
HANDOFF_MODE = 'LOCAL_HANDOFF_ONLY_NOT_PAID'
MAX_MINOR = 10**12
MAX_BODY_BYTES = 5_000_000
REGULAR_FILE_MESSAGE = 'database path must be a regular file (existing or new), never a link or a special file'
NOT_A_DATABASE_MESSAGE = 'database path does not hold a desk SQLite database'
SUBSTITUTED_MESSAGE = 'database identity changed since the desk opened it; no operation runs against a substituted database'
UNSUPPORTED_MESSAGE = ('database custody cannot be proven on this platform (no readable descriptor table and no exclusive '
                       'file handles); the desk does not start here')
# Custody proof per platform. Where the process descriptor table is readable, every connection's own
# descriptor is checked against the pinned file before any statement runs. On Windows the pinned handle
# keeps the database from being renamed, replaced or deleted while the desk lives. Elsewhere the desk
# does not start.
DESCRIPTOR_TABLE = next((table for table in ('/proc/self/fd', '/dev/fd') if os.path.isdir(table)), None)
CUSTODY_PROOF = 'descriptor' if DESCRIPTOR_TABLE else ('handle' if os.name == 'nt' else None)
_DESK_LOCK = threading.Lock()  # one desk operation at a time per process, held from the open until the session closes


def _descriptors():
    try:
        return {int(name) for name in os.listdir(DESCRIPTOR_TABLE) if name.isdigit()}
    except (OSError, TypeError):
        return set()


def _descriptor_proof(before, after, pinned):
    """True when the open just performed is bound to the pinned file.

    A descriptor that appeared during the open and refers to the pinned file proves it. When no
    regular-file descriptor appeared at all, SQLite reused one of its own parked descriptors, and
    those only ever refer to the pinned file (a refused open is closed before anything else can hold
    a lock on the other file). A regular-file descriptor that appeared and refers elsewhere is the
    connection opening some other file.
    """
    on_pinned = elsewhere = False
    for descriptor in after - before:
        try:
            found = os.fstat(descriptor)
        except OSError:
            continue  # closed again already (the listing's own directory handle)
        if not stat.S_ISREG(found.st_mode):
            continue
        if (found.st_dev, found.st_ino) == pinned:
            on_pinned = True
        else:
            elsewhere = True
    return on_pinned or not elsewhere


class _Session:
    """A proven connection; closing it also releases the desk lock held since the open."""
    __slots__ = ('_db', '_live')

    def __init__(self, db):
        self._db = db
        self._live = True

    def __getattr__(self, name):
        return getattr(self._db, name)

    def close(self):
        if self._live:
            self._live = False
            try:
                self._db.close()
            finally:
                _DESK_LOCK.release()

    def __del__(self):
        self.close()
# Known tracking/share parameters are dropped from content URLs; any other query material is refused
# unless a code-owned projection below names it as the content identity.
TRACKING_QUERY_KEYS = frozenset((
    'fbclid', 'gclid', 'gbraid', 'wbraid', 'msclkid', 'yclid', 'twclid', 'ttclid', 'li_fat_id', 'igshid', 'igsh', 'si', 'feature',
    'ref', 'ref_src', 'ref_url', 'source', 'mc_cid', 'mc_eid', 's', 't', '_t', '_r', '_d', 'is_from_webapp', 'is_copy_url',
    'sender_device', 'sender_web_id', 'web_id', 'share_app_id', 'share_link_id', 'share_item_id', 'tt_from', 'u_code', 'ug_btm',
    'lang', 'app', 'checksum', 'timestamp', 'sec_uid', 'sec_user_id', 'ab_channel', 'pp', 'spm', 'from', 'cxt', 'ncid', 'trk',
    'context', 'sfnsn', 'mibextid', 'rdid', 'share_url', 'utm',
))
YOUTUBE_HOSTS = frozenset(('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtube-nocookie.com', 'www.youtube-nocookie.com'))
YOUTUBE_ID = re.compile(r'[A-Za-z0-9_-]{11}')
YOUTUBE_PATH_ID = re.compile(r'/(?:shorts|live|embed|v)/([A-Za-z0-9_-]{11})$')
HANDLE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9 ._-]{0,119}')
ASSET_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.(md|txt)')
# Opaque-reference grammar for payout route and settlement references. It is a
# shape filter owned by this module, not a detector: it refuses obvious contact,
# URL/host, phone, SSN, card/account/IBAN digit shapes, credential keywords,
# well-known secret prefixes and token-shaped runs, so those values never reach
# SQLite, state, handoff records or exports. Operators supply references issued
# by their payout system of record.
OPAQUE_REF = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}')
REF_FORBIDDEN_TEXT = re.compile(
    r'(?:@|://|(?<![A-Za-z0-9])www\.|(?<![A-Za-z0-9])(?:mailto|tel|sms|http|https|ftp):|'
    r'(?<![A-Za-z0-9])(?:password|passwd|pwd|secret|api[_-]?key|apikey|token|bearer|auth|oauth|otp|cvv|cvc|pin|'
    r'iban|swift|bic|routing|aba|card|pan|ssn|sin|ein|tin|tax[_-]?id)(?![A-Za-z]))', re.I)
REF_SECRET_PREFIX = re.compile(
    r'(?<![A-Za-z0-9])(?:(?:sk|pk|rk)[_-](?:live|test)[_-]|whsec[_-]|ghp_|gho_|ghu_|ghs_|github_pat_|xox[abpr]-|'
    r'AKIA[0-9A-Z]{12,}|ASIA[0-9A-Z]{12,}|ya29\.|eyJ[A-Za-z0-9_-]{10,}|sq0[a-z]{3}-|SG\.[A-Za-z0-9_-]{10,}|glpat-|npm_)', re.I)
REF_HOST_SHAPE = re.compile(r'[A-Za-z0-9-]+\.[A-Za-z]{2,24}(?:$|[/:.])')
# Phone, SSN and EIN shapes with every separator the identifier grammar admits.
REF_PHONE_OR_SSN_SHAPE = re.compile(r'(?<!\d)(?:\d{3}[-.:/]\d{3}[-.:/]\d{4}|\d{3}[-.:/]\d{2}[-.:/]\d{4}|\d{2}[-.:/]\d{7})(?!\d)')
REF_CARD_GROUP_SHAPE = re.compile(r'(?<!\d)\d{4}(?:[-.:/]\d{4}){2,4}(?!\d)')
REF_DIGIT_ONLY_MINIMUM = 9  # a value with no letters and this many digits is a number, not a reference
OPERATION_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}')
METRIC_KEYS = ('views', 'likes', 'comments', 'shares', 'saves')
# Exact field sets per operation: a payload with any other field is refused rather than partially applied.
OPERATION_FIELDS = {
    'brand/create': frozenset(('name',)),
    'creator/create': frozenset(('handle', 'consent_on', 'payout_route_ref')),
    'campaign/create': frozenset(('brand_id', 'title', 'brief', 'rights_terms', 'currency', 'budget_minor', 'rule', 'eligibility')),
    'campaign/action': frozenset(('id', 'version', 'action', 'name', 'license', 'content')),
    'submission/create': frozenset(('campaign_id', 'creator_id', 'platform', 'url', 'posted_on', 'disclosure_present', 'rights_accepted')),
    'submission/review': frozenset(('id', 'version', 'decision', 'note', 'metrics')),
    'payable/handoff': frozenset(('campaign_id',)),
    'payable/settle': frozenset(('id', 'version', 'settlement_ref')),
}
PERCENT_ESCAPE = re.compile(r'%([0-9A-Fa-f]{2})')
UNRESERVED = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~')
PATH_SAFE = "%-._~!$&'()*+,;=:@"
REF_DIGIT_RUN = re.compile(r'\d{13,}')
REF_DIGIT_TOKEN = re.compile(r'(?<![A-Za-z0-9])\d{9,}(?![A-Za-z0-9])')
REF_IBAN_SHAPE = re.compile(r'(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}[A-Za-z0-9]{11,30}(?![A-Za-z0-9])')
REF_TOKEN_SHAPE = re.compile(r'[A-Za-z0-9]{32,}')


class DeskError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def text(value, name, maximum=100000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise DeskError(f'{name} must be nonempty text (maximum {maximum} characters)')
    if any((ord(ch) < 32 and ch not in '\n\r\t') or ord(ch) == 127 for ch in value):
        raise DeskError(f'{name} must not contain control characters')
    return value


def integer(value, name, minimum=0, maximum=MAX_MINOR):
    if type(value) is not int or not minimum <= value <= maximum:
        raise DeskError(f'{name} must be an integer from {minimum} to {maximum}')
    return value


def boolean(value, name):
    if type(value) is not bool:
        raise DeskError(f'{name} must be true or false')
    return value


def day(value, name):
    if not isinstance(value, str):
        raise DeskError(f'{name} must be a YYYY-MM-DD date')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DeskError(f'{name} must be a YYYY-MM-DD date') from exc
    if parsed.isoformat() != value:
        raise DeskError(f'{name} must be a canonical YYYY-MM-DD date')
    return value


def numeric_identity_shape(value):
    """True when a value carries a phone, SSN, EIN, card, account or IBAN digit shape under any admitted separator."""
    return bool(REF_PHONE_OR_SSN_SHAPE.search(value) or REF_CARD_GROUP_SHAPE.search(value) or REF_DIGIT_RUN.search(value)
                or REF_DIGIT_TOKEN.search(value) or REF_IBAN_SHAPE.search(value)
                or (sum(ch.isdigit() for ch in value) >= REF_DIGIT_ONLY_MINIMUM and not any(ch.isalpha() for ch in value)))


def opaque_ref(value, name):
    """Validate an opaque reference: ASCII identifier grammar minus contact, URL, account, card and secret shapes."""
    reference = text(value, name, 80)
    if not OPAQUE_REF.fullmatch(reference):
        raise DeskError(f'{name} must be an opaque reference of up to 80 ASCII letters, digits, dots, underscores, colons, slashes or hyphens')
    if (REF_FORBIDDEN_TEXT.search(reference) or REF_SECRET_PREFIX.search(reference) or REF_HOST_SHAPE.search(reference)
            or REF_TOKEN_SHAPE.search(reference) or numeric_identity_shape(reference)):
        raise DeskError(f'{name} must be an opaque reference: no email, link, host, phone, account, card, IBAN, credential or token shapes')
    return reference


def operation_key(value):
    """Validate the client idempotency key and return the digest under which it is retained."""
    key = text(value, 'operation_id', 200)
    if not OPERATION_ID.fullmatch(key):
        raise DeskError('operation_id must be an identifier of up to 200 ASCII letters, digits, dots, underscores, colons, slashes or hyphens')
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def metrics_block(value):
    """Owner-entered metrics: a fixed allow-list of non-negative integer counts, nothing else."""
    if not isinstance(value, dict):
        raise DeskError('metrics must be an object')
    if set(value) - set(METRIC_KEYS):
        raise DeskError(f'metrics accepts only {list(METRIC_KEYS)}')
    return {key: integer(value[key], f'metrics.{key}', 0) for key in METRIC_KEYS if key in value}


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DeskError(f'duplicate JSON key {key!r}')
        result[key] = value
    return result


def _no_non_finite(constant):
    raise DeskError(f'non-finite JSON constant {constant} is not accepted')


def _scalar_strings(value):
    """Refuse strings that are not valid Unicode scalar sequences (lone surrogates) anywhere in a parsed document."""
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            try:
                item.encode('utf-8')
            except UnicodeEncodeError as exc:
                raise DeskError('JSON strings must be valid Unicode scalar values') from exc
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return value


def strict_json(text_value):
    """Parse request JSON strictly: duplicate keys, NaN/Infinity, lone surrogates and nesting bombs are refused, never silently resolved."""
    try:
        parsed = json.loads(text_value, object_pairs_hook=_no_duplicate_keys, parse_constant=_no_non_finite)
    except DeskError:
        raise
    except (ValueError, RecursionError) as exc:
        raise DeskError('Request body must be a JSON object') from exc
    return _scalar_strings(parsed)


def encoded(value):
    try:
        text_value = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        text_value.encode('utf-8')  # a lone surrogate must fail here as a DeskError, never later as an unhandled encode error
    except (ValueError, TypeError, RecursionError) as exc:
        raise DeskError('Payload must contain finite JSON values and valid Unicode scalar strings') from exc
    return text_value


def now():
    return datetime.now(timezone.utc).isoformat()


def normalize_url(value):
    """Return the canonical public content URL, the only URL form the desk retains.

    Scheme, lowercased host and path are kept; userinfo is refused; fragments and known tracking
    parameters are dropped. Query material is retained only where a code-owned projection names it as
    the content identity: YouTube video ids, which are normalized to https://www.youtube.com/watch?v=ID
    from watch, youtu.be, shorts, live and embed forms. Any other query material is refused rather than
    silently stripped, so a signed or tokenized link never enters the desk and a content identity is
    never lost. The duplicate key is the retained value.
    """
    raw = text(value, 'url', 2000).strip()
    parts = urlsplit(raw)
    if parts.scheme.lower() not in ('http', 'https') or not parts.netloc or '@' in parts.netloc:
        raise DeskError('url must be an http(s) content link with a host and no credentials')
    host = (parts.hostname or '').lower()
    if not host or not host.isascii() or any(ord(ch) < 0x21 for ch in host):
        raise DeskError('url host must be a non-empty ASCII host name (use the punycode form for internationalized hosts)')
    try:
        port = parts.port  # raises for non-numeric or out-of-range ports instead of silently dropping them
    except ValueError as exc:
        raise DeskError('url port must be a number from 1 to 65535') from exc
    if port == 0:
        raise DeskError('url port must be a number from 1 to 65535')
    scheme = parts.scheme.lower()
    authority = f'[{host}]' if ':' in host else host
    if port is not None and port != {'http': 80, 'https': 443}[scheme]:
        authority = f'{authority}:{port}'  # an explicit non-default port is part of the content identity
    path = canonical_path(parts.path)
    query = {}
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in TRACKING_QUERY_KEYS or lowered.startswith('utm_'):
            continue
        query.setdefault(lowered, []).append(item)
    if host == 'youtu.be' or host in YOUTUBE_HOSTS:
        if port not in (None, 443, 80):
            raise DeskError('YouTube links must use the default port')
        if host == 'youtu.be':
            video = path.strip('/')
            if not YOUTUBE_ID.fullmatch(video):
                raise DeskError('youtu.be links must be https://youtu.be/<11-character video id>')
        elif path == '/watch':
            values = query.pop('v', [])
            if len(values) != 1 or not YOUTUBE_ID.fullmatch(values[0]):
                raise DeskError('YouTube watch links must carry exactly one 11-character v= video id')
            video = values[0]
        else:
            match = YOUTUBE_PATH_ID.fullmatch(path)
            if not match:
                raise DeskError('YouTube links must be a watch, youtu.be, shorts, live or embed video link')
            video = match.group(1)
        if query:
            raise DeskError(f'url carries unsupported query material {sorted(query)}; supply the canonical video link')
        return f'https://www.youtube.com/watch?v={video}'
    if query:
        raise DeskError(f'url carries query material that is not a supported content identity {sorted(query)}; supply the canonical content link')
    return f'{scheme}://{authority}{path}'


def canonical_path(raw_path):
    """One spelling per path: dot and empty segments are refused, percent-escapes are uppercase, unreserved octets are literal."""
    if not raw_path:
        return '/'
    if not raw_path.startswith('/'):
        raise DeskError('url path must start with /')
    segments = raw_path[1:].split('/')
    if segments and segments[-1] == '':
        segments = segments[:-1]  # a trailing slash is not part of the identity
    canonical = []
    for segment in segments:
        if segment in ('', '.', '..'):
            raise DeskError('url path must not contain empty or dot segments')
        if len(PERCENT_ESCAPE.findall(segment)) != segment.count('%'):
            raise DeskError('url path percent-escapes must be well formed')

        def _escape(match):
            octet = int(match.group(1), 16)
            char = chr(octet)
            return char if char in UNRESERVED else f'%{octet:02X}'

        canonical.append(quote(PERCENT_ESCAPE.sub(_escape, segment), safe=PATH_SAFE))
    return '/' + '/'.join(canonical) if canonical else '/'


def loopback_host(value):
    """Accept only loopback bind targets; this desk has no remote authentication and is never served elsewhere."""
    host = text(value, 'host', 253).strip()
    candidate = host[1:-1] if host.startswith('[') and host.endswith(']') else host
    if candidate.lower() == 'localhost':
        return host
    try:
        if ipaddress.ip_address(candidate).is_loopback:
            return host
    except ValueError:
        pass
    raise DeskError('host must be a loopback address (127.0.0.1, ::1 or localhost); this desk has no remote authentication and is not served on other interfaces')


def reward_rule(data):
    if not isinstance(data, dict):
        raise DeskError('rule must be an object')
    kind = data.get('kind')
    if kind not in RULE_KINDS:
        raise DeskError(f'rule.kind must be one of {list(RULE_KINDS)}')
    rule = {'kind': kind, 'allow_partial': boolean(data.get('allow_partial', False), 'rule.allow_partial')}
    if kind == 'FIXED_PER_APPROVED':
        rule['amount_minor'] = integer(data.get('amount_minor'), 'rule.amount_minor', 1)
        allowed = {'kind', 'allow_partial', 'amount_minor'}
    else:
        rule['rate_minor_per_thousand'] = integer(data.get('rate_minor_per_thousand'), 'rule.rate_minor_per_thousand', 1)
        rule['cap_minor'] = integer(data.get('cap_minor'), 'rule.cap_minor', 1)
        rule['minimum_views'] = integer(data.get('minimum_views', 0), 'rule.minimum_views', 0)
        allowed = {'kind', 'allow_partial', 'rate_minor_per_thousand', 'cap_minor', 'minimum_views'}
    if set(data) - allowed:
        raise DeskError(f'rule has unknown fields {sorted(set(data) - allowed)}')
    return rule


def eligibility(data):
    if not isinstance(data, dict):
        raise DeskError('eligibility must be an object')
    platforms = data.get('platforms')
    if not isinstance(platforms, list) or not platforms or any(p not in PLATFORMS for p in platforms) or len(set(platforms)) != len(platforms):
        raise DeskError(f'eligibility.platforms must list distinct values from {list(PLATFORMS)}')
    rules = {
        'platforms': sorted(platforms),
        'disclosure_tag': text(data.get('disclosure_tag', '#ad'), 'eligibility.disclosure_tag', 40),
        'requires_disclosure': boolean(data.get('requires_disclosure', True), 'eligibility.requires_disclosure'),
        'requires_rights_acceptance': boolean(data.get('requires_rights_acceptance', True), 'eligibility.requires_rights_acceptance'),
        'window_start': day(data.get('window_start'), 'eligibility.window_start'),
        'window_end': day(data.get('window_end'), 'eligibility.window_end'),
    }
    if rules['window_end'] < rules['window_start']:
        raise DeskError('eligibility.window_end precedes window_start')
    allowed = {'platforms', 'disclosure_tag', 'requires_disclosure', 'requires_rights_acceptance', 'window_start', 'window_end'}
    if set(data) - allowed:
        raise DeskError(f'eligibility has unknown fields {sorted(set(data) - allowed)}')
    return rules


def compute_reward(rule, metrics):
    """Deterministic integer reward from the campaign rule and owner-entered metrics."""
    if rule['kind'] == 'FIXED_PER_APPROVED':
        return rule['amount_minor'], {'kind': rule['kind'], 'amount_minor': rule['amount_minor']}
    views = integer(metrics.get('views') if isinstance(metrics, dict) else None, 'metrics.views', 0)
    if views < rule['minimum_views']:
        return 0, {'kind': rule['kind'], 'views': views, 'below_minimum_views': True}
    amount = min(rule['cap_minor'], views * rule['rate_minor_per_thousand'] // 1000)
    return amount, {'kind': rule['kind'], 'views': views, 'rate_minor_per_thousand': rule['rate_minor_per_thousand'], 'cap_minor': rule['cap_minor']}


def admin_fee(amount_minor):
    """Proposed administration fee in minor units, round half up at 5%."""
    return (amount_minor * ADMIN_FEE_BPS + 5000) // 10000


class Desk:
    """One SQLite database, bound to this desk for its whole life.

    Startup opens the path itself (links refused) and keeps that handle open. Every connection,
    the first one included, is proven before any statement runs: where the process descriptor
    table is readable, the descriptor the connection opened must refer to the pinned file
    itself, so a copy carrying the same header identity that is swapped in for the open and
    swapped out again is refused and receives nothing; on Windows the pinned handle keeps the
    database from being renamed, replaced or deleted while the desk lives; on any other platform
    the desk does not start. The header identity (minted for a new database, kept for an existing
    desk database, adopted once for a database written before identities existed) additionally
    refuses a pinned file whose bytes were replaced in place by another database.
    """

    def __init__(self, path):
        self._handle = None
        self.path = str(path)
        target = Path(self.path)
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise DeskError(REGULAR_FILE_MESSAGE)
        target.parent.mkdir(parents=True, exist_ok=True)
        if CUSTODY_PROOF is None:
            raise DeskError(UNSUPPORTED_MESSAGE)
        with _DESK_LOCK:  # no other open of this path in the process while the handle is taken
            self.pinned = self._pin()
        self.identity = None
        try:
            db = self._open()
        except BaseException:
            self.close()
            raise
        try:
            identity = self._adopt(db)
            db.executescript('''
                CREATE TABLE IF NOT EXISTS brands (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS campaigns (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    brand_id TEXT NOT NULL REFERENCES brands(id), title TEXT NOT NULL, brief TEXT NOT NULL,
                    rights_terms TEXT NOT NULL, currency TEXT NOT NULL, budget_minor INTEGER NOT NULL,
                    rule TEXT NOT NULL, eligibility TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'DRAFT',
                    version INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id), name TEXT NOT NULL,
                    license TEXT NOT NULL, content TEXT NOT NULL, created TEXT NOT NULL,
                    UNIQUE(campaign_id, name));
                CREATE TABLE IF NOT EXISTS creators (
                    id TEXT PRIMARY KEY, handle TEXT UNIQUE NOT NULL, consent_on TEXT NOT NULL,
                    payout_route_ref TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS submissions (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    campaign_id TEXT NOT NULL REFERENCES campaigns(id), creator_id TEXT NOT NULL REFERENCES creators(id),
                    platform TEXT NOT NULL, url TEXT NOT NULL, url_key TEXT NOT NULL, posted_on TEXT NOT NULL,
                    disclosure_present INTEGER NOT NULL, rights_accepted INTEGER NOT NULL,
                    metrics TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'SUBMITTED',
                    review_note TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL,
                    UNIQUE(campaign_id, url_key));
                CREATE TABLE IF NOT EXISTS payables (
                    id TEXT PRIMARY KEY, submission_id TEXT UNIQUE NOT NULL REFERENCES submissions(id),
                    campaign_id TEXT NOT NULL REFERENCES campaigns(id), creator_id TEXT NOT NULL REFERENCES creators(id),
                    amount_minor INTEGER NOT NULL, admin_fee_minor INTEGER NOT NULL, basis TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'CALCULATED', handoff_id TEXT NOT NULL DEFAULT '',
                    settlement_ref TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS handoffs (
                    id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
                    payload TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS operations (
                    id_sha256 TEXT PRIMARY KEY, payload_sha256 TEXT NOT NULL, result TEXT NOT NULL);
            ''')
            # Custody proof: the header read through the pinned handle and the identity the connection
            # reports must both be the adopted identity, so the connection wrote to and read from the
            # very file this desk holds, whatever the path pointed at between the check and the open.
            if self._header_identity() != identity or self._connection_identity(db) != identity:
                raise DeskError(SUBSTITUTED_MESSAGE, 503)
        except BaseException:
            db.close()
            self.close()
            raise
        db.close()
        self.identity = identity

    def _pin(self):
        """Open the database path itself, never a link, and keep the handle for the desk's whole life."""
        flags = os.O_RDWR | os.O_CREAT
        for name in ('O_NOFOLLOW', 'O_CLOEXEC', 'O_BINARY', 'O_NOINHERIT'):
            flags |= getattr(os, name, 0)
        try:
            self._handle = os.open(self.path, flags, 0o600)
            opened = os.fstat(self._handle)
            unfollowed = os.lstat(self.path)
        except OSError as exc:
            self.close()
            raise DeskError(REGULAR_FILE_MESSAGE) from exc
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (unfollowed.st_dev, unfollowed.st_ino):
            self.close()
            raise DeskError(REGULAR_FILE_MESSAGE)
        return (opened.st_dev, opened.st_ino)

    def _open(self):
        """Take the desk lock, open a connection and prove, before any statement runs, that it opened the pinned file itself.

        The lock is held until the returned session is closed, so one desk operation runs at a time in
        this process: the descriptor that appears during the open belongs to this open, and no other desk
        transaction exists while it is proven.
        """
        _DESK_LOCK.acquire()
        try:
            before = _descriptors()
            db = sqlite3.connect(self.path, timeout=10)
        except BaseException:
            _DESK_LOCK.release()
            raise
        try:
            if CUSTODY_PROOF == 'descriptor':
                # The descriptor this open created must refer to the pinned file. A copy carrying the same
                # header identity, swapped in for the open and swapped out again, is a different file.
                if not _descriptor_proof(before, _descriptors(), self.pinned):
                    raise DeskError(SUBSTITUTED_MESSAGE, 503)
            else:
                # The pinned handle keeps the path from being renamed, replaced or deleted while the desk lives.
                try:
                    current = os.stat(self.path)
                except OSError as exc:
                    raise DeskError(SUBSTITUTED_MESSAGE, 503) from exc
                if (current.st_dev, current.st_ino) != self.pinned:
                    raise DeskError(SUBSTITUTED_MESSAGE, 503)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
        except BaseException:
            db.close()
            _DESK_LOCK.release()
            raise
        return _Session(db)

    def _header_identity(self):
        """Identity (application id, user version) read from the SQLite header through the pinned handle; None while the file is empty."""
        os.lseek(self._handle, 0, os.SEEK_SET)
        header = os.read(self._handle, 100)
        if not header:
            return None
        if len(header) < 100 or header[:16] != b'SQLite format 3\x00':
            raise DeskError(NOT_A_DATABASE_MESSAGE, 503)
        return (int.from_bytes(header[68:72], 'big', signed=True), int.from_bytes(header[60:64], 'big', signed=True))

    @staticmethod
    def _connection_identity(db):
        """The same identity as the connection itself reports it, from the file the connection actually opened."""
        try:
            return (int(db.execute('PRAGMA application_id').fetchone()[0]), int(db.execute('PRAGMA user_version').fetchone()[0]))
        except sqlite3.DatabaseError as exc:
            raise DeskError(NOT_A_DATABASE_MESSAGE, 503) from exc

    def _adopt(self, db):
        """Choose the identity this desk binds to: minted for a new database, kept for an existing one, minted once for a pre-identity desk database."""
        seen = self._connection_identity(db)
        header = self._header_identity()
        if header is None:
            if seen != (0, 0) or int(db.execute('PRAGMA page_count').fetchone()[0]) != 0:
                raise DeskError(SUBSTITUTED_MESSAGE, 503)  # the pinned file is empty; the connection opened something else
        elif seen == (0, 0):
            if header != (0, 0):
                raise DeskError(SUBSTITUTED_MESSAGE, 503)  # the pinned file carries an identity; the connection sees none
            is_desk = db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='brands'").fetchone()[0]
            if int(is_desk) != 1:
                raise DeskError(NOT_A_DATABASE_MESSAGE, 503)
        elif seen != header:
            raise DeskError(SUBSTITUTED_MESSAGE, 503)
        else:
            return header
        identity = (secrets.randbits(31) | 1, secrets.randbits(31) | 1)  # never the unset pair
        db.execute('PRAGMA application_id=%d' % identity[0])
        db.execute('PRAGMA user_version=%d' % identity[1])
        return identity

    def close(self):
        """Release the pinned handle; a closed desk opens no further connections."""
        handle, self._handle = self._handle, None
        if handle is not None:
            os.close(handle)

    def __del__(self):
        self.close()

    def connect(self):
        if self._handle is None:
            raise DeskError('desk is closed', 503)
        db = self._open()
        try:
            # _open proved the descriptor; the header identity additionally refuses a pinned file whose
            # bytes were replaced in place by another database.
            if self._connection_identity(db) != self.identity:
                raise DeskError(SUBSTITUTED_MESSAGE, 503)
        except BaseException:
            db.close()
            raise
        return db

    @staticmethod
    def row(db, table, identifier):
        # Table names originate only from this module, never from request data.
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise DeskError('Item not found', 404)
        return dict(row)

    @staticmethod
    def expected(row, data):
        version = integer(data.get('version'), 'version', 1, 2**53 - 1)
        if version != row['version']:
            raise DeskError('This item changed. Refresh before editing.', 409)

    @staticmethod
    def committed(db, campaign_id):
        value = db.execute('SELECT COALESCE(SUM(amount_minor),0) FROM payables WHERE campaign_id=?', (campaign_id,)).fetchone()[0]
        return int(value)

    def snapshot(self):
        db = self.connect()
        try:
            db.execute('BEGIN')
            brands = [dict(r) for r in db.execute('SELECT * FROM brands ORDER BY name,id')]
            creators = [dict(r) for r in db.execute('SELECT * FROM creators ORDER BY handle')]
            campaigns = [dict(r) for r in db.execute('SELECT * FROM campaigns ORDER BY seq')]
            submissions = [dict(r) for r in db.execute('SELECT * FROM submissions ORDER BY seq')]
            payables = [dict(r) for r in db.execute('SELECT * FROM payables ORDER BY created,id')]
            assets = [dict(r) for r in db.execute('SELECT id,campaign_id,name,license,created,length(content) AS bytes FROM assets ORDER BY campaign_id,name')]
            for campaign in campaigns:
                campaign['rule'] = json.loads(campaign['rule'])
                campaign['eligibility'] = json.loads(campaign['eligibility'])
                committed = sum(p['amount_minor'] for p in payables if p['campaign_id'] == campaign['id'])
                campaign['budget'] = {
                    'budget_minor': campaign['budget_minor'],
                    'committed_minor': committed,
                    'remaining_minor': campaign['budget_minor'] - committed,
                    'payable_count': sum(1 for p in payables if p['campaign_id'] == campaign['id']),
                }
            for submission in submissions:
                submission['metrics'] = json.loads(submission['metrics'])
                submission['disclosure_present'] = bool(submission['disclosure_present'])
                submission['rights_accepted'] = bool(submission['rights_accepted'])
            for payable in payables:
                payable['basis'] = json.loads(payable['basis'])
            return {'brands': brands, 'creators': creators, 'campaigns': campaigns, 'submissions': submissions,
                    'payables': payables, 'assets': assets, 'handoff_mode': HANDOFF_MODE,
                    'admin_fee_bps': ADMIN_FEE_BPS, 'commercial_status': 'PROPOSED_NOT_ACCEPTED'}
        finally:
            db.close()

    def write(self, operation, data):
        if not isinstance(data, dict):
            raise DeskError('Payload must be an object')
        key_digest = operation_key(data.get('operation_id'))
        allowed = OPERATION_FIELDS.get(operation)
        if allowed is None:
            raise DeskError('Unknown operation', 404)
        unknown = sorted(set(data) - allowed - {'operation_id'})
        if unknown:
            raise DeskError(f'{operation} does not accept fields {unknown}')
        # Write receipts keep only digests of the idempotency key and the request payload: exact replay
        # still matches and a different payload is still refused, but no raw request text is retained.
        payload_digest = hashlib.sha256(encoded({'operation': operation, 'data': data}).encode('utf-8')).hexdigest()
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT * FROM operations WHERE id_sha256=?', (key_digest,)).fetchone()
            if previous:
                if previous['payload_sha256'] != payload_digest:
                    raise DeskError('operation_id already belongs to a different edit', 409)
                return json.loads(previous['result'])
            result = self._apply(db, operation, data)
            db.execute('INSERT INTO operations VALUES (?,?,?)', (key_digest, payload_digest, encoded(result)))
            db.commit()
            return result
        except sqlite3.IntegrityError as exc:
            db.rollback()
            raise DeskError('This record already exists (duplicate handle, asset name, content URL, or payable).', 409) from exc
        finally:
            db.close()

    def _apply(self, db, operation, data):
        if operation == 'brand/create':
            name = text(data.get('name'), 'name', 120)
            if not NAME.fullmatch(name):
                raise DeskError('name uses letters, digits, spaces, dots, underscores or hyphens')
            identifier = uuid.uuid4().hex
            db.execute('INSERT INTO brands(id,name) VALUES (?,?)', (identifier, name))
            return {'id': identifier}
        if operation == 'creator/create':
            handle = text(data.get('handle'), 'handle', 64)
            if not HANDLE.fullmatch(handle):
                raise DeskError('handle uses letters, digits, dots, underscores or hyphens')
            handle = handle.lower()  # platform handles are case-insensitive; one spelling per creator
            if numeric_identity_shape(handle):
                raise DeskError('handle must be a creator handle, not a phone, SSN, card, account or IBAN number')
            consent_on = day(data.get('consent_on'), 'consent_on')
            route = opaque_ref(data.get('payout_route_ref'), 'payout_route_ref')
            identifier = uuid.uuid4().hex
            db.execute('INSERT INTO creators(id,handle,consent_on,payout_route_ref) VALUES (?,?,?,?)', (identifier, handle, consent_on, route))
            return {'id': identifier}
        if operation == 'campaign/create':
            brand_id = text(data.get('brand_id'), 'brand_id', 100)
            self.row(db, 'brands', brand_id)
            title = text(data.get('title'), 'title', 200)
            brief = text(data.get('brief'), 'brief', 20000)
            rights = text(data.get('rights_terms'), 'rights_terms', 20000)
            currency = text(data.get('currency', 'USD'), 'currency', 3)
            if not re.fullmatch(r'[A-Z]{3}', currency):
                raise DeskError('currency must be a three-letter uppercase code')
            budget = integer(data.get('budget_minor'), 'budget_minor', 1)
            rule = reward_rule(data.get('rule'))
            rules = eligibility(data.get('eligibility'))
            identifier = uuid.uuid4().hex
            db.execute('INSERT INTO campaigns(id,brand_id,title,brief,rights_terms,currency,budget_minor,rule,eligibility,created) VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (identifier, brand_id, title, brief, rights, currency, budget, encoded(rule), encoded(rules), now()))
            return {'id': identifier}
        if operation == 'campaign/action':
            identifier = text(data.get('id'), 'id', 100)
            campaign = self.row(db, 'campaigns', identifier)
            self.expected(campaign, data)
            action = data.get('action')
            if action == 'open' and campaign['status'] == 'DRAFT':
                db.execute("UPDATE campaigns SET status='OPEN',version=version+1 WHERE id=?", (identifier,))
            elif action == 'close' and campaign['status'] == 'OPEN':
                db.execute("UPDATE campaigns SET status='CLOSED',version=version+1 WHERE id=?", (identifier,))
            elif action == 'asset' and campaign['status'] in ('DRAFT', 'OPEN'):
                name = text(data.get('name'), 'name', 84)
                if not ASSET_NAME.fullmatch(name):
                    raise DeskError('asset names use letters, digits, underscores or hyphens and end in .md or .txt')
                db.execute('INSERT INTO assets(id,campaign_id,name,license,content,created) VALUES (?,?,?,?,?,?)',
                           (uuid.uuid4().hex, identifier, name, text(data.get('license'), 'license', 2000), text(data.get('content'), 'content'), now()))
                db.execute('UPDATE campaigns SET version=version+1 WHERE id=?', (identifier,))
            else:
                raise DeskError(f'Action {action!r} is not available while the campaign is {campaign["status"]}', 409)
            return {'id': identifier}
        if operation == 'submission/create':
            campaign = self.row(db, 'campaigns', text(data.get('campaign_id'), 'campaign_id', 100))
            creator = self.row(db, 'creators', text(data.get('creator_id'), 'creator_id', 100))
            if campaign['status'] != 'OPEN':
                raise DeskError('Submissions are accepted only while the campaign is OPEN', 409)
            rules = json.loads(campaign['eligibility'])
            platform = data.get('platform')
            if platform not in rules['platforms']:
                raise DeskError(f'platform must be one of the campaign platforms {rules["platforms"]}')
            url = normalize_url(data.get('url'))  # canonical public form is the only URL the desk retains
            posted_on = day(data.get('posted_on'), 'posted_on')
            if posted_on < creator['consent_on']:
                raise DeskError('posted_on precedes the recorded creator consent date')
            identifier = uuid.uuid4().hex
            db.execute('INSERT INTO submissions(id,campaign_id,creator_id,platform,url,url_key,posted_on,disclosure_present,rights_accepted,created) VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (identifier, campaign['id'], creator['id'], platform, url, url, posted_on,
                        int(boolean(data.get('disclosure_present'), 'disclosure_present')),
                        int(boolean(data.get('rights_accepted'), 'rights_accepted')), now()))
            return {'id': identifier, 'url': url}
        if operation == 'submission/review':
            identifier = text(data.get('id'), 'id', 100)
            submission = self.row(db, 'submissions', identifier)
            self.expected(submission, data)
            if submission['status'] != REVIEWABLE:
                raise DeskError('This submission was already reviewed; one review and at most one payable per submission.', 409)
            note = text(data.get('note', 'reviewed'), 'note', 5000)
            decision = data.get('decision')
            campaign = self.row(db, 'campaigns', submission['campaign_id'])
            if decision == 'reject':
                db.execute("UPDATE submissions SET status='REJECTED',review_note=?,version=version+1 WHERE id=?", (note, identifier))
                return {'id': identifier, 'status': 'REJECTED', 'payable_id': None}
            if decision != 'approve':
                raise DeskError('decision must be approve or reject')
            if campaign['status'] != 'OPEN':
                raise DeskError('Approvals are recorded only while the campaign is OPEN', 409)
            rules = json.loads(campaign['eligibility'])
            problems = []
            if rules['requires_disclosure'] and not submission['disclosure_present']:
                problems.append(f'missing required disclosure {rules["disclosure_tag"]}')
            if rules['requires_rights_acceptance'] and not submission['rights_accepted']:
                problems.append('creator has not accepted the campaign rights/usage terms')
            if not rules['window_start'] <= submission['posted_on'] <= rules['window_end']:
                problems.append('posted outside the campaign window')
            if problems:
                raise DeskError('Not eligible for approval: ' + '; '.join(problems), 409)
            metrics = metrics_block(data.get('metrics', {}))
            rule = json.loads(campaign['rule'])
            reward, basis = compute_reward(rule, metrics)
            remaining = campaign['budget_minor'] - self.committed(db, campaign['id'])
            status, payable_id, amount = 'APPROVED', None, 0
            if reward <= 0:
                status = 'APPROVED_NO_REWARD'
            elif reward <= remaining:
                amount = reward
            elif rule['allow_partial'] and remaining > 0:
                amount, status = remaining, 'APPROVED_PARTIAL_BUDGET'
            else:
                status = 'APPROVED_BUDGET_EXHAUSTED'
            if amount > 0:
                payable_id = uuid.uuid4().hex
                basis = dict(basis, computed_reward_minor=reward, budget_remaining_before_minor=remaining)
                db.execute('INSERT INTO payables(id,submission_id,campaign_id,creator_id,amount_minor,admin_fee_minor,basis,created) VALUES (?,?,?,?,?,?,?,?)',
                           (payable_id, identifier, campaign['id'], submission['creator_id'], amount, admin_fee(amount), encoded(basis), now()))
            db.execute('UPDATE submissions SET status=?,review_note=?,metrics=?,version=version+1 WHERE id=?',
                       (status, note, encoded(metrics), identifier))
            return {'id': identifier, 'status': status, 'payable_id': payable_id, 'amount_minor': amount,
                    'admin_fee_minor': admin_fee(amount) if amount else 0}
        if operation == 'payable/handoff':
            campaign = self.row(db, 'campaigns', text(data.get('campaign_id'), 'campaign_id', 100))
            rows = [dict(r) for r in db.execute("SELECT p.*, c.handle, c.payout_route_ref FROM payables p JOIN creators c ON c.id=p.creator_id WHERE p.campaign_id=? AND p.status='CALCULATED' ORDER BY p.created,p.id", (campaign['id'],))]
            if not rows:
                raise DeskError('No calculated payables are waiting for handoff', 409)
            handoff_id = uuid.uuid4().hex
            requests = [{
                'request_id': f'{handoff_id}-{index:04d}', 'payable_id': r['id'], 'creator_handle': r['handle'],
                'payout_route_ref': r['payout_route_ref'], 'amount_minor': r['amount_minor'], 'currency': campaign['currency'],
                'proposed_admin_fee_minor': r['admin_fee_minor'], 'memo': f'{campaign["title"]} / {r["submission_id"]}',
                'idempotency_key': r['id'],
            } for index, r in enumerate(rows, start=1)]
            payload = {'mode': HANDOFF_MODE, 'campaign_id': campaign['id'], 'handoff_id': handoff_id, 'created': now(),
                       'provider': 'ADAPTER_CONTRACT_ONLY', 'requests': requests,
                       'total_amount_minor': sum(r['amount_minor'] for r in requests),
                       'note': 'No transfer was executed. A separately authorized operator submits these requests to the payout provider; settlement is recorded here afterwards by reference.'}
            db.execute('INSERT INTO handoffs VALUES (?,?,?,?)', (handoff_id, campaign['id'], encoded(payload), payload['created']))
            for r in rows:
                db.execute("UPDATE payables SET status='HANDED_OFF',handoff_id=?,version=version+1 WHERE id=?", (handoff_id, r['id']))
            return {'handoff_id': handoff_id, 'count': len(requests), 'total_amount_minor': payload['total_amount_minor'], 'mode': HANDOFF_MODE}
        if operation == 'payable/settle':
            identifier = text(data.get('id'), 'id', 100)
            payable = self.row(db, 'payables', identifier)
            self.expected(payable, data)
            if payable['status'] != 'HANDED_OFF':
                raise DeskError('Only handed-off payables can record an external settlement reference', 409)
            reference = opaque_ref(data.get('settlement_ref'), 'settlement_ref')
            db.execute("UPDATE payables SET status='SETTLEMENT_RECORDED',settlement_ref=?,version=version+1 WHERE id=?", (reference, identifier))
            return {'id': identifier, 'status': 'SETTLEMENT_RECORDED'}
        raise DeskError('Unknown operation', 404)

    def export(self, campaign_id):
        db = self.connect()
        try:
            db.execute('BEGIN')
            campaign = self.row(db, 'campaigns', campaign_id)
            campaign['rule'] = json.loads(campaign['rule'])
            campaign['eligibility'] = json.loads(campaign['eligibility'])
            submissions = [dict(r) for r in db.execute('SELECT s.*, c.handle FROM submissions s JOIN creators c ON c.id=s.creator_id WHERE s.campaign_id=? ORDER BY s.seq', (campaign_id,))]
            payables = [dict(r) for r in db.execute('SELECT p.*, c.handle FROM payables p JOIN creators c ON c.id=p.creator_id WHERE p.campaign_id=? ORDER BY p.created,p.id', (campaign_id,))]
            assets = [dict(r) for r in db.execute('SELECT * FROM assets WHERE campaign_id=? ORDER BY name', (campaign_id,))]
            handoff = db.execute('SELECT payload FROM handoffs WHERE campaign_id=? ORDER BY created DESC,id DESC LIMIT 1', (campaign_id,)).fetchone()
        finally:
            db.close()
        committed = sum(p['amount_minor'] for p in payables)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('campaign.json', encoded({**campaign, 'budget': {'budget_minor': campaign['budget_minor'], 'committed_minor': committed, 'remaining_minor': campaign['budget_minor'] - committed}}))
            archive.writestr('submissions.csv', self._csv(['id', 'handle', 'platform', 'url', 'posted_on', 'disclosure_present', 'rights_accepted', 'status', 'metrics', 'review_note'], submissions))
            archive.writestr('payables.csv', self._csv(['id', 'submission_id', 'handle', 'amount_minor', 'admin_fee_minor', 'status', 'handoff_id', 'settlement_ref', 'basis'], payables))
            archive.writestr('payout_handoff.json', handoff['payload'] if handoff else encoded({'mode': HANDOFF_MODE, 'requests': []}))
            for asset in assets:
                archive.writestr(f'assets/{asset["name"]}', asset['content'])
                archive.writestr(f'assets/{asset["name"]}.license.txt', asset['license'])
            archive.writestr('README.txt', 'Local campaign export. ' + HANDOFF_MODE + '. Payables are calculated rewards under the campaign rule and budget cap; '
                             'the proposed administration fee is PROPOSED_NOT_ACCEPTED; no transfer, invoice, or platform action was performed.\n')
        return buffer.getvalue()

    @staticmethod
    def _csv(fields, rows):
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(fields)
        for row in rows:
            record = []
            for field in fields:
                value = row.get(field, '')
                if isinstance(value, str) and value[:1] in ('=', '+', '-', '@'):
                    value = "'" + value
                record.append(value)
            writer.writerow(record)
        return stream.getvalue()


def load_example(desk, path=ROOT / 'example.json'):
    """Replay the recorded synthetic operations. Re-running with the same database is idempotent."""
    with open(path, encoding='utf-8') as handle:
        script = strict_json(handle.read())
    results = {}

    def resolve(value):
        if isinstance(value, dict):
            if set(value) == {'$ref'}:
                return results[value['$ref']]['id']
            return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v) for v in value]
        return value

    for step in script['operations']:
        data = resolve(step['data'])
        if 'version' in data and isinstance(data['version'], dict) and set(data['version']) == {'$current'}:
            table = data['version']['$current']
            state = desk.snapshot()
            current = next(item for item in state[table] if item['id'] == data['id'])
            data['version'] = current['version']
        results[step['operation_id']] = desk.write(step['operation'], {'operation_id': step['operation_id'], **data})
    return results


class Handler(BaseHTTPRequestHandler):
    desk = None
    routes = {
        '/api/brand/create': 'brand/create', '/api/creator/create': 'creator/create',
        '/api/campaign/create': 'campaign/create', '/api/campaign/action': 'campaign/action',
        '/api/submission/create': 'submission/create', '/api/submission/review': 'submission/review',
        '/api/payable/handoff': 'payable/handoff', '/api/payable/settle': 'payable/settle',
    }

    def log_message(self, *args):
        return

    def reply(self, status, body, content_type='application/json; charset=utf-8'):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        if self.close_connection:
            self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            if path == '/':
                self.reply(200, INDEX_HTML, 'text/html; charset=utf-8')
            elif path == '/api/state':
                self.reply(200, encoded(self.desk.snapshot()))
            elif path.startswith('/api/export/'):
                campaign_id = path[len('/api/export/'):]
                if not re.fullmatch(r'[0-9a-f]{32}', campaign_id):
                    raise DeskError('Item not found', 404)
                self.reply(200, self.desk.export(campaign_id), 'application/zip')
            else:
                raise DeskError('Not found', 404)
        except DeskError as exc:
            self.reply(exc.status, encoded({'error': str(exc)}))

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            header = (self.headers.get('Content-Length') or '').strip()
            length = int(header) if header.isdigit() else -1
            if length < 0:
                self.close_connection = True  # nothing can be drained without a valid length; the reply closes the connection
                raise DeskError('Content-Length must be a non-negative integer')
            if length == 0:
                raise DeskError('Request body must be a JSON object')
            if length > MAX_BODY_BYTES:
                self.close_connection = True  # refused without reading; the reply closes the connection instead of draining megabytes
                raise DeskError('Request body must be JSON up to 5 MB', 413)
            body = self.rfile.read(length)  # bounded drain before any reply so a refused route never aborts the client socket
            if len(body) != length:
                self.close_connection = True
                raise DeskError('Request body was shorter than Content-Length')
            operation = self.routes.get(path)
            if operation is None:
                raise DeskError('Not found', 404)
            try:
                data = strict_json(body.decode('utf-8'))
            except UnicodeDecodeError as exc:
                raise DeskError('Request body must be UTF-8 JSON') from exc
            self.reply(200, encoded(self.desk.write(operation, data)))
        except DeskError as exc:
            self.reply(exc.status, encoded({'error': str(exc)}))


def make_server(desk, host='127.0.0.1', port=0):
    handler = type('BoundHandler', (Handler,), {'desk': desk})
    return ThreadingHTTPServer((loopback_host(host), port), handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Creator reward campaign desk (local, standard library).')
    parser.add_argument('--db', default=str(ROOT / 'creator-reward.sqlite3'))
    parser.add_argument('--host', default='127.0.0.1', help='loopback only (127.0.0.1, ::1 or localhost); the desk has no remote authentication')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--demo', action='store_true', help='load the recorded synthetic campaign (idempotent)')
    args = parser.parse_args(argv)
    try:
        bind_host = loopback_host(args.host)
        desk = Desk(args.db)
    except DeskError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    if args.demo:
        load_example(desk)
    server = make_server(desk, bind_host, args.port)
    print(f'Creator reward campaign desk on http://{args.host}:{server.server_address[1]} ({HANDOFF_MODE})')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        desk.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
