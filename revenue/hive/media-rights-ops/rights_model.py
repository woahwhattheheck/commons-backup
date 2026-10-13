"""Strict schemas and canonicalization for the media-rights operations desk."""
from __future__ import annotations
import hashlib,json,re
from datetime import date,datetime,timezone
from pathlib import Path
SCHEMA='media-rights-ops/v1'; EXPORT_SCHEMA='media-rights-ops-export/v1'; RECEIPT_SCHEMA='media-rights-ops-receipt/v1'; MAX_INPUT_BYTES=8*1024*1024
ID_RE=re.compile(r'^[a-z0-9][a-z0-9._-]{1,79}$'); CHANNEL_RE=re.compile(r'^[a-z0-9][a-z0-9._-]{1,63}$'); TERRITORY_RE=re.compile(r'^[A-Z][A-Z0-9-]{1,15}$'); SHA256_RE=re.compile(r'^[0-9a-f]{64}$')
class RightsError(ValueError): pass
def require(ok,msg):
    if not ok: raise RightsError(msg)
def canonical_bytes(v): return (json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
def _fraction_groups(text):
    """Yield non-separator fractional digit groups accepted by fromisoformat.

    A dot/comma immediately after a complete ISO date may be the legal single
    date/time separator. Everything else is a numeric fractional component.
    """
    for match in re.finditer(r'[.,]([0-9]+)',text):
        prefix=text[:match.start()]
        try:
            date.fromisoformat(prefix)
            datetime.fromisoformat(prefix+'T00:00:00')
        except ValueError:
            yield match
def parse_time(v,at):
    """Parse an offset-aware ISO instant without silently discarding precision.

    V1 accepts whole seconds and microsecond precision (1..6 supplied digits).
    CPython accepts some >6-digit and zero-offset fractional forms by silently
    dropping digits. Detect every numeric fraction in the original text and
    fail closed unless it is exactly representable by datetime.
    """
    require(isinstance(v,str) and v,f'{at} must be an offset-aware timestamp')
    text=v[:-1]+'+00:00' if v.endswith('Z') else v
    try: dt=datetime.fromisoformat(text)
    except ValueError as e: raise RightsError(f'{at} must be an ISO-8601 timestamp') from e
    require(dt.tzinfo is not None and dt.utcoffset() is not None,f'{at} must include an offset')
    for match in _fraction_groups(text):
        digits=match.group(1)
        nonzero=any(digit!='0' for digit in digits)
        require(len(digits)<=6 or not nonzero,f'{at} supports at most 6 nonzero fractional digits')
        if nonzero:
            offset_sign=max(text.rfind('+',10,match.start()),text.rfind('-',10,match.start()))
            require(offset_sign<0,f'{at} fractional UTC offsets are unsupported')
            zeroed=text[:match.start()+1]+('0'*len(digits))+text[match.end():]
            try: zero_dt=datetime.fromisoformat(zeroed)
            except ValueError as e: raise RightsError(f'{at} must be an ISO-8601 timestamp') from e
            require(zero_dt!=dt,f'{at} contains fractional precision that the runtime discards')
    try: utc=dt.astimezone(timezone.utc)
    except (ValueError,OverflowError) as e: raise RightsError(f'{at} is outside the supported UTC range') from e
    return utc
def norm_time(v,at):
    utc=parse_time(v,at)
    timespec='microseconds' if utc.microsecond else 'seconds'
    return utc.isoformat(timespec=timespec).replace('+00:00','Z')
def strict_object(v,keys,at): require(isinstance(v,dict),f'{at} must be an object'); require(set(v)==keys,f'{at} keys invalid: expected {sorted(keys)}'); return v
def strict_id(v,at): require(isinstance(v,str) and ID_RE.fullmatch(v) is not None,f'{at} invalid'); return v
def strict_text(v,at,max_len=300):
    require(isinstance(v,str) and v.strip(),f'{at} must be nonempty text'); v=v.strip(); require(len(v.encode())<=max_len,f'{at} too long'); require('\x00' not in v,f'{at} contains NUL'); return v
def strict_channel(v,at): require(isinstance(v,str) and CHANNEL_RE.fullmatch(v) is not None,f'{at} invalid'); return v
def strict_territory(v,at): require(isinstance(v,str) and TERRITORY_RE.fullmatch(v) is not None,f'{at} invalid'); return v
def _no_float(_): raise RightsError('floating-point JSON numbers are not accepted')
def _no_constant(v): raise RightsError(f'non-finite JSON constant is not accepted: {v}')
def _pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise RightsError(f'duplicate JSON key: {k}')
        out[k]=v
    return out
def loads_strict(raw):
    require(len(raw)<=MAX_INPUT_BYTES,'input exceeds 8 MiB')
    try: text=raw.decode('utf-8')
    except UnicodeDecodeError as e: raise RightsError('input must be UTF-8') from e
    try: return json.loads(text,object_pairs_hook=_pairs,parse_float=_no_float,parse_constant=_no_constant)
    except json.JSONDecodeError as e: raise RightsError(f'invalid JSON: {e.msg}') from e
def read_strict_json(path:Path): require(path.is_file() and not path.is_symlink(),f'input must be a regular non-symlink file: {path}'); return loads_strict(path.read_bytes())
def normalize_manifest(doc):
    root=strict_object(doc,{'schema','assets','grants'},'document'); require(root['schema']==SCHEMA,'schema mismatch'); require(isinstance(root['assets'],list) and root['assets'],'assets must be a nonempty list'); require(isinstance(root['grants'],list) and root['grants'],'grants must be a nonempty list')
    assets=[]; ids=set()
    for i,raw in enumerate(root['assets']):
        at=f'assets[{i}]'; x=strict_object(raw,{'asset_id','sha256','parent_asset_id'},at); aid=strict_id(x['asset_id'],f'{at}.asset_id'); require(aid not in ids,f'duplicate asset_id: {aid}'); ids.add(aid); require(isinstance(x['sha256'],str) and SHA256_RE.fullmatch(x['sha256']),f'{at}.sha256 invalid'); parent=x['parent_asset_id']
        if parent is not None: parent=strict_id(parent,f'{at}.parent_asset_id'); require(parent!=aid,f'{at} cannot parent itself')
        assets.append({'asset_id':aid,'sha256':x['sha256'],'parent_asset_id':parent})
    for x in assets: require(x['parent_asset_id'] is None or x['parent_asset_id'] in ids,f"unknown parent_asset_id: {x['parent_asset_id']}")
    parents={x['asset_id']:x['parent_asset_id'] for x in assets}
    for aid in sorted(ids):
        seen=set(); cur=aid
        while cur is not None: require(cur not in seen,f'asset lineage cycle at {aid}'); seen.add(cur); cur=parents[cur]
    grants=[]; gids=set()
    for i,raw in enumerate(root['grants']):
        at=f'grants[{i}]'; x=strict_object(raw,{'grant_id','asset_id','authority_ref','valid_from','valid_until','channels','territories'},at); gid=strict_id(x['grant_id'],f'{at}.grant_id'); require(gid not in gids,f'duplicate grant_id: {gid}'); gids.add(gid); aid=strict_id(x['asset_id'],f'{at}.asset_id'); require(aid in ids,f'{at}.asset_id not in assets'); start=norm_time(x['valid_from'],f'{at}.valid_from'); end=norm_time(x['valid_until'],f'{at}.valid_until'); require(parse_time(start,'start')<parse_time(end,'end'),f'{at} validity window must be increasing'); require(isinstance(x['channels'],list) and x['channels'],f'{at}.channels required'); require(isinstance(x['territories'],list) and x['territories'],f'{at}.territories required'); channels=sorted({strict_channel(v,f'{at}.channels') for v in x['channels']}); territories=sorted({strict_territory(v,f'{at}.territories') for v in x['territories']}); require(len(channels)==len(x['channels']),f'{at}.channels duplicates not allowed'); require(len(territories)==len(x['territories']),f'{at}.territories duplicates not allowed'); grants.append({'grant_id':gid,'asset_id':aid,'authority_ref':strict_text(x['authority_ref'],f'{at}.authority_ref'),'valid_from':start,'valid_until':end,'channels':channels,'territories':territories})
    return {'schema':SCHEMA,'assets':sorted(assets,key=lambda x:x['asset_id']),'grants':sorted(grants,key=lambda x:x['grant_id'])}
def normalize_intent(doc,require_request_id=False):
    keys={'asset_id','channel','territory','starts_at','ends_at'}|({'request_id'} if require_request_id else set()); x=strict_object(doc,keys,'intent'); out={'asset_id':strict_id(x['asset_id'],'intent.asset_id'),'channel':strict_channel(x['channel'],'intent.channel'),'territory':strict_territory(x['territory'],'intent.territory'),'starts_at':norm_time(x['starts_at'],'intent.starts_at'),'ends_at':norm_time(x['ends_at'],'intent.ends_at')}; require(parse_time(out['starts_at'],'starts_at')<parse_time(out['ends_at'],'ends_at'),'intent window must be increasing')
    if require_request_id: out['request_id']=strict_id(x['request_id'],'intent.request_id')
    return out
