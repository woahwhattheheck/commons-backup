#!/usr/bin/env python3
"""Generate review-only promotion assets from one canonical offer list."""
import argparse, csv, hashlib, html, json, re, shutil, tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

SLUG=re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*$")

def gf_mul(x,y):
    z=0
    while y:
        if y&1:z^=x
        y>>=1;x=(x<<1)^(0x11D if x&0x80 else 0)
    return z

def rs_divisor(n):
    r=[0]*(n-1)+[1];root=1
    for _ in range(n):
        r=[gf_mul(v,root)^(r[i+1] if i+1<n else 0) for i,v in enumerate(r)]
        root=gf_mul(root,2)
    return r

def qr_words(text):
    raw=text.encode()
    if len(raw)>106: raise ValueError("landing URL exceeds QR version 5-L capacity")
    bits=[0,1,0,0]+[(len(raw)>>i)&1 for i in range(7,-1,-1)]
    for b in raw: bits += [(b>>i)&1 for i in range(7,-1,-1)]
    bits += [0]*min(4,864-len(bits));bits += [0]*(-len(bits)%8)
    data=bytearray(sum(bits[j+i]<<(7-i) for i in range(8)) for j in range(0,len(bits),8))
    toggle=0
    while len(data)<108:data.append((0xEC,0x11)[toggle]);toggle^=1
    div=rs_divisor(26);rem=[0]*26
    for b in data:
        f=b^rem.pop(0);rem.append(0)
        rem=[v^gf_mul(div[i],f) for i,v in enumerate(rem)]
    return bytes(data+bytearray(rem))

def qr_matrix(text):
    size=37;m=[[None]*size for _ in range(size)];fn=[[False]*size for _ in range(size)]
    def put(x,y,v):m[y][x]=v;fn[y][x]=True
    for cx,cy in ((3,3),(33,3),(3,33)):
        for dy in range(-4,5):
            for dx in range(-4,5):
                x,y=cx+dx,cy+dy
                if 0<=x<size and 0<=y<size:put(x,y,max(abs(dx),abs(dy)) not in (2,4))
    for i in range(8,29):put(6,i,i%2==0);put(i,6,i%2==0)
    for dy in range(-2,3):
        for dx in range(-2,3):put(30+dx,30+dy,max(abs(dx),abs(dy))!=1)
    a=[(8,i) for i in range(6)]+[(8,7),(8,8),(7,8)]+[(14-i,8) for i in range(9,15)]
    b=[(36-i,8) for i in range(8)]+[(8,22+i) for i in range(8,15)]
    for x,y in a+b:put(x,y,False)
    put(8,29,True)
    words=qr_words(text);k=0;right=36
    while right>=1:
        if right==6:right-=1
        up=((right+1)&2)==0
        for v in range(size):
            y=36-v if up else v
            for x in (right,right-1):
                if not fn[y][x]:
                    bit=(words[k>>3]>>(7-(k&7)))&1 if k<len(words)*8 else 0
                    m[y][x]=bool(bit^((x+y)%2==0));k+=1
        right-=2
    if k!=1079:raise AssertionError(k)  # 134 codewords plus seven version-5 remainder bits.
    data=8;rem=data
    for _ in range(10):rem=(rem<<1)^(0x537 if rem>>9 else 0)
    fmt=((data<<10)|rem)^0x5412
    for i,(p,q) in enumerate(zip(a,b)):put(*p,bool((fmt>>i)&1));put(*q,bool((fmt>>i)&1))
    put(8,29,True)
    return m

def qr_svg(url):
    m=qr_matrix(url);d=[]
    for y,row in enumerate(m):
        for x,v in enumerate(row):
            if v:d.append(f"M{x+4} {y+4}h1v1h-1z")
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 45 45" shape-rendering="crispEdges"><rect width="45" height="45" fill="white"/><path d="'+"".join(d)+'" fill="black"/></svg>\n'

def load(brand_path,offers_path):
    brand=json.loads(brand_path.read_text())
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}",brand.get("primary_color","")):raise ValueError("invalid primary_color")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}",brand.get("secondary_color","")):raise ValueError("invalid secondary_color")
    rows=json.loads(offers_path.read_text());out=[];ids=set();slugs=set()
    for row in rows:
        if row["offer_id"] in ids or row["slug"] in slugs:raise ValueError("duplicate offer id or slug")
        if not SLUG.fullmatch(row["slug"]):raise ValueError("invalid slug")
        start,end=date.fromisoformat(row["starts_on"]),date.fromisoformat(row["expires_on"])
        price=Decimal(str(row["price"]))
        if end<start or price<0 or price.as_tuple().exponent<-2:raise ValueError("invalid date range or price")
        row=dict(row,price=price,starts_on=start,expires_on=end);out.append(row)
        ids.add(row["offer_id"]);slugs.add(row["slug"])
    return brand,out

def status(o,day):
    return "UPCOMING" if day<o["starts_on"] else ("EXPIRED_REMOVED" if day>o["expires_on"] else "ACTIVE")

def money(o):return ("$" if o.get("currency")=="USD" else o.get("currency","")+" ")+f'{o["price"]:.2f}'

def card(brand,o,w,h,qr):
    esc=html.escape
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><rect width="100%" height="100%" fill="{brand["primary_color"]}"/><rect x="4%" y="4%" width="92%" height="92%" rx="24" fill="{brand["secondary_color"]}"/><text x="8%" y="15%" font-family="sans-serif" font-size="42">{esc(brand["business_name"])}</text><text x="8%" y="31%" font-family="sans-serif" font-size="58">{esc(o["headline"])}</text><text x="8%" y="43%" font-family="sans-serif" font-size="36">{esc(o["detail"])}</text><text x="8%" y="58%" font-family="sans-serif" font-size="74">{money(o)}</text><text x="8%" y="68%" font-family="sans-serif" font-size="26">Valid through {o["expires_on"]}</text><text x="8%" y="75%" font-family="sans-serif" font-size="20">{esc(o["terms"])}</text><image href="{qr}" x="72%" y="66%" width="22%" height="22%"/></svg>\n'''

def build(brand_path,offers_path,day,base_url,out):
    brand,offers=load(brand_path,offers_path);out=out.resolve();out.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix="promotion-",dir=out.parent))
    try:
        for d in ("site/offers","social","print","qr"):(stage/d).mkdir(parents=True)
        assets=[];items=[]
        for o in offers:
            if status(o,day)!="ACTIVE":continue
            oid,slug=o["offer_id"],o["slug"];url=f'{base_url.rstrip("/")}/offers/{slug}.html'
            (stage/f"qr/{oid}.svg").write_text(qr_svg(url))
            landing=f'''<!doctype html><meta charset="utf-8"><title>{html.escape(o["headline"])}</title><h1>{html.escape(o["headline"])}</h1><p>{html.escape(o["detail"])}</p><strong>{money(o)}</strong><p>Valid through {o["expires_on"]}</p><small>{html.escape(o["terms"])}</small>\n'''
            (stage/f"site/offers/{slug}.html").write_text(landing)
            (stage/f"social/{oid}.svg").write_text(card(brand,o,1080,1080,f"../qr/{oid}.svg"))
            (stage/f"print/{oid}.svg").write_text(card(brand,o,816,1056,f"../qr/{oid}.svg"))
            items.append(f'<li><a href="offers/{slug}.html">{html.escape(o["headline"])} — {money(o)}</a> (through {o["expires_on"]})</li>')
            assets.append({"offer_id":oid,"landing_url":url,"web":f"site/offers/{slug}.html","social":f"social/{oid}.svg","print":f"print/{oid}.svg","qr":f"qr/{oid}.svg"})
        (stage/"site/index.html").write_text(f'<!doctype html><meta charset="utf-8"><h1>{html.escape(brand["business_name"])} offers</h1><ul>{"".join(items)}</ul>\n')
        with (stage/"expiry-calendar.csv").open("w",newline="") as f:
            w=csv.writer(f);w.writerow(("offer_id","starts_on","expires_on","status"))
            for o in offers:w.writerow((o["offer_id"],o["starts_on"],o["expires_on"],status(o,day)))
        sources=[{"path":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for p in (brand_path,offers_path)]
        manifest={"as_of":str(day),"mode":"LOCAL_EXPORT_ONLY_UNSENT","sources":sources,"assets":assets}
        (stage/"build-manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
        if out.exists():shutil.rmtree(out)
        stage.rename(out);stage=None
        return manifest
    finally:
        if stage and stage.exists():shutil.rmtree(stage)

def main():
    p=argparse.ArgumentParser();p.add_argument("--brand",type=Path,required=True);p.add_argument("--offers",type=Path,required=True);p.add_argument("--as-of",type=date.fromisoformat,required=True);p.add_argument("--base-url",required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    print(json.dumps(build(a.brand,a.offers,a.as_of,a.base_url,a.out),indent=2))
if __name__=="__main__":main()
