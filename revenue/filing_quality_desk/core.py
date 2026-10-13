from __future__ import annotations
import hashlib,json,re
from datetime import date
from decimal import Decimal,InvalidOperation

class FilingQualityError(ValueError): pass
MAX_BYTES=8_000_000; MAX_DEPTH=40; MAX_SCALARS=300_000
ID=re.compile(r'^[A-Za-z0-9_.:-]{1,120}$')
UNIT=re.compile(r'^[A-Za-z0-9_.:/-]{1,120}$')

def _pairs(pairs):
    d={}
    for k,v in pairs:
        if k in d: raise FilingQualityError(f'duplicate JSON key: {k}')
        d[k]=v
    return d

def _constant(x): raise FilingQualityError(f'non-finite JSON number: {x}')
def load(raw:bytes,limit=MAX_BYTES):
    if len(raw)>limit: raise FilingQualityError('input too large')
    try:v=json.loads(raw.decode(),object_pairs_hook=_pairs,parse_int=str,parse_float=str,parse_constant=_constant)
    except (UnicodeDecodeError,json.JSONDecodeError,RecursionError) as e: raise FilingQualityError(f'invalid JSON: {e}') from e
    stack=[(v,0)];n=0
    while stack:
        x,d=stack.pop()
        if d>MAX_DEPTH: raise FilingQualityError('JSON nesting too deep')
        if isinstance(x,dict):stack.extend((c,d+1) for c in x.values())
        elif isinstance(x,list):stack.extend((c,d+1) for c in x)
        elif x is None or isinstance(x,(str,bool)):n+=1
        else:raise FilingQualityError('unsupported decoded type')
        if n>MAX_SCALARS: raise FilingQualityError('too many scalars')
    return v

def text(x,name):
    if not isinstance(x,str) or not x: raise FilingQualityError(f'{name} must be nonempty string')
    return x
def ident(x,name):
    x=text(x,name)
    if not ID.fullmatch(x): raise FilingQualityError(f'{name} has unsafe characters')
    return x
def unit(x,name):
    x=text(x,name)
    if not UNIT.fullmatch(x): raise FilingQualityError(f'{name} has unsafe characters')
    return x
def day(x,name):
    x=text(x,name)
    try:parsed=date.fromisoformat(x)
    except ValueError as e:raise FilingQualityError(f'{name} must be ISO date') from e
    if parsed.isoformat()!=x:raise FilingQualityError(f'{name} must be canonical ISO date')
    return x
def dec(x,name):
    if isinstance(x,bool) or not isinstance(x,str):raise FilingQualityError(f'{name} must be numeric')
    try:d=Decimal(x)
    except InvalidOperation as e:raise FilingQualityError(f'{name} invalid decimal') from e
    if not d.is_finite() or len(d.as_tuple().digits)>256 or abs(d.adjusted())>256:raise FilingQualityError(f'{name} out of bounds')
    return d
def dec_text(d):
    if d==0:return '0'
    t=format(d,'f');return t.rstrip('0').rstrip('.') if '.' in t else t
def sha(b):return hashlib.sha256(b).hexdigest()
def canon(x):return (json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
