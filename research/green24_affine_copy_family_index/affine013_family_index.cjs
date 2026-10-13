"use strict";
const SCHEMA="commons.affine013_host_families/v1";
const copy=x=>JSON.parse(JSON.stringify(x));
function integer(x,label) {
  if(typeof x==="number"&&!Number.isSafeInteger(x))throw Error(label);
  try{return BigInt(x);}catch(_){throw Error(label);}
}
function compile(input) {
  const host=input.host.map(x=>integer(x,"host integer")),n=host.length;
  if(n<1||n>20||host.some((x,i)=>i>0&&x<=host[i-1]))throw Error("strictly increasing host, size 1..20");
  if(!Array.isArray(input.expected_size_counts)||input.expected_size_counts.length!==n+1)throw Error("supplied size-count row");
  const lookup=new Map(host.map((x,i)=>[x.toString(),i])),patterns=[],byMax=Array.from({length:n},()=>[]);
  const work={ordered_pair_checks:0,integer_pattern_values:0,patterns:0,subset_rows:0,new_pattern_membership_checks:0,score_additions:0,size_additions:0,bucket_insertions:0,binomial_accounting_checks:0,old_graphs:0,old_Pascal:0,old_AP:0};
  for(let i=0;i<n;i++)for(let j=0;j<n;j++)if(i!==j) {
    work.ordered_pair_checks++;const z=3n*host[j]-2n*host[i];work.integer_pattern_values++;
    const k=lookup.get(z.toString());if(k===undefined)continue;
    const ids=[i,j,k],max=Math.max(...ids),mask=ids.reduce((s,v)=>s+2**v,0);
    const p={id:patterns.length,x_index:i,y_index:j,z_index:k,a:host[i].toString(),d:(host[j]-host[i]).toString(),z:z.toString(),mask,max_index:max,lower_pair_mask:mask-2**max};
    patterns.push(p);byMax[max].push(p);work.patterns++;
  }
  const total=2**n,scores=new Uint16Array(total),sizes=new Uint8Array(total),groups=Array.from({length:n+1},()=>new Map());
  groups[0].set(0,[0]);work.subset_rows++;work.bucket_insertions++;
  for(let mask=1;mask<total;mask++) {
    const hi=31-Math.clz32(mask),parent=mask-2**hi;let score=scores[parent];
    for(const p of byMax[hi]){work.new_pattern_membership_checks++;if((parent&p.lower_pair_mask)===p.lower_pair_mask){score++;work.score_additions++;}}
    scores[mask]=score;sizes[mask]=sizes[parent]+1;work.size_additions++;work.subset_rows++;
    const g=groups[sizes[mask]];if(!g.has(score))g.set(score,[]);g.get(score).push(mask);work.bucket_insertions++;
  }
  const buckets=[],summary=[];
  for(let size=0;size<=n;size++) {
    const rows=[...groups[size]].sort((a,b)=>a[0]-b[0]),actual=rows.reduce((s,x)=>s+x[1].length,0);
    work.binomial_accounting_checks++;if(BigInt(actual)!==BigInt(input.expected_size_counts[size]))throw Error("size accounting mismatch");
    for(const [copies,masks] of rows)buckets.push({id:buckets.length,size,copies,count:masks.length,masks});
    summary.push({size,total:actual,minimum_copies:rows[0][0],minimum_count:rows[0][1].length,maximum_copies:rows[rows.length-1][0],maximum_count:rows[rows.length-1][1].length,profiles:rows.length});
  }
  return {schema:SCHEMA,input:copy(input),order:"size, then copy count, then increasing numerical host mask",patterns,buckets,summary,work};
}
function openIndex(data,retainedCaches=[]) {
  if(data.schema!==SCHEMA||!Array.isArray(data.buckets)||!Array.isArray(data.patterns))throw Error("saved index");
  const n=data.input.host.length,full=2**n-1,host=data.input.host.map(x=>integer(x,"host")),B=data.buckets,P=data.patterns,caches=new Map(retainedCaches.map(x=>[x.key,x]));
  const work={families_built:0,saved_bucket_scans:0,saved_mask_scans:0,condition_bit_checks:0,cumulative_additions:0,cache_hits:0,binary_steps:0,lookup_bucket_probes:0,popcount_steps:0,materialized_values:0,pattern_scans:0,affine_multiplications:0,affine_additions:0,new_pattern_values:0,new_subset_scores:0,new_histogram:0};
  function maskValue(x){if(!Number.isSafeInteger(x)||x<0||x>full)throw RangeError("host mask");return x;}
  function ids(a){if(a===undefined)return[];if(!Array.isArray(a))throw Error("index list");const r=[...a].sort((a,b)=>a-b);if(r.some((x,i)=>!Number.isInteger(x)||x<0||x>=n||(i>0&&x===r[i-1])))throw Error("distinct host indices");return r;}
  function normalize(o={}) {
    const size=o.size===undefined?null:o.size,min=o.min_copies===undefined?0:o.min_copies,max=o.max_copies===undefined?P.length:o.max_copies;
    if(size!==null&&(!Number.isInteger(size)||size<0||size>n))throw Error("size");
    if(!Number.isInteger(min)||!Number.isInteger(max)||min<0||max<0)throw Error("copy bounds");
    return {size,min_copies:min,max_copies:max,require:ids(o.require),forbid:ids(o.forbid)};
  }
  function family(o={}) {
    const q=normalize(o),key=JSON.stringify(q);if(caches.has(key)){work.cache_hits++;return caches.get(key);}
    work.families_built++;const require=q.require.reduce((s,i)=>s+2**i,0),forbid=q.forbid.reduce((s,i)=>s+2**i,0),segments=[];let total=0;
    if((require&forbid)===0&&q.min_copies<=q.max_copies)for(const b of B) {
      work.saved_bucket_scans++;if((q.size!==null&&b.size!==q.size)||b.copies<q.min_copies||b.copies>q.max_copies)continue;
      let indices=null,count=b.count;
      if(require||forbid){indices=[];for(let i=0;i<b.masks.length;i++){const mask=b.masks[i];work.saved_mask_scans++;work.condition_bit_checks+=2;if((mask&require)===require&&(mask&forbid)===0)indices.push(i);}count=indices.length;}
      if(count){segments.push({bucket:b.id,start:total,count,indices});total+=count;work.cumulative_additions++;}
    }
    const f={key,options:q,count:total,segments};caches.set(key,f);return f;
  }
  function lower(a,x){let lo=0,hi=a.length;while(lo<hi){work.binary_steps++;const mid=(lo+hi)>>1;if(a[mid]<x)lo=mid+1;else hi=mid;}return lo;}
  function locate(mask){maskValue(mask);let v=mask,size=0;for(;v;v&=v-1){size++;work.popcount_steps++;}
    for(const b of B)if(b.size===size){work.lookup_bucket_probes++;const i=lower(b.masks,mask);if(b.masks[i]===mask)return{bucket:b.id,index:i,size,copies:b.copies};}
    throw Error("missing saved mask");
  }
  function values(mask){const indices=[],result=[];for(let i=0;i<n;i++)if(mask&2**i){indices.push(i);result.push(host[i].toString());work.materialized_values++;}return {indices,values:result};}
  function count(o={}){const f=family(o);return{options:f.options,count:f.count,buckets:f.segments.length};}
  function select(rank,o={}) {
    const r=integer(rank,"rank"),f=family(o);if(r<0n||r>=BigInt(f.count))throw RangeError("rank");const v=Number(r);
    let lo=0,hi=f.segments.length;while(lo+1<hi){work.binary_steps++;const mid=(lo+hi)>>1;if(f.segments[mid].start<=v)lo=mid;else hi=mid;}
    const seg=f.segments[lo],b=B[seg.bucket],local=v-seg.start,index=seg.indices?seg.indices[local]:local,mask=b.masks[index];
    return {rank:v,total:f.count,options:f.options,bucket:b.id,bucket_index:index,mask,size:b.size,copies:b.copies,...values(mask)};
  }
  function rank(mask,o={}) {
    maskValue(mask);const loc=locate(mask),f=family(o),s=f.segments.find(s=>s.bucket===loc.bucket);
    if(!s)return{member:false,mask,reason:"excluded score/size bucket"};
    const i=s.indices?lower(s.indices,loc.index):loc.index;
    if(s.indices&&s.indices[i]!==loc.index)return{member:false,mask,reason:"required/forbidden condition"};
    return {member:true,mask,rank:s.start+i,total:f.count,options:f.options,...loc};
  }
  function page(start,limit,o={}) {
    const s=integer(start,"page start"),f=family(o);if(s<0n||s>BigInt(f.count)||!Number.isInteger(limit)||limit<0||limit>1000)throw RangeError("page");
    const records=[];for(let i=Number(s);i<f.count&&records.length<limit;i++)records.push(select(i,o));
    return {start:Number(s),count:f.count,records,next:Number(s)+records.length<f.count?Number(s)+records.length:null};
  }
  function occurrences(mask) {
    maskValue(mask);const rows=[];for(const p of P){work.pattern_scans++;if((mask&p.mask)===p.mask)rows.push(copy(p));}
    return {mask,patterns:rows};
  }
  function affine(mask,scale,shift) {
    maskValue(mask);const a=integer(scale,"scale"),b=integer(shift,"shift");if(a===0n)throw Error("nonzero scale");
    const selected=values(mask),images=new Map();for(const i of selected.indices){images.set(i,(a*host[i]+b).toString());work.affine_multiplications++;work.affine_additions++;}
    const rows=occurrences(mask).patterns.map(p=>({pattern:p.id,x:images.get(p.x_index),y:images.get(p.y_index),z:images.get(p.z_index),d:(a*BigInt(p.d)).toString()}));work.affine_multiplications+=rows.length;
    return {mask,scale:a.toString(),shift:b.toString(),count:rows.length,points:selected.indices.map(i=>({index:i,value:images.get(i)})),patterns:rows};
  }
  return {summary:()=>copy(data.summary),count,select,rank,page,occurrences,affine,
    profile:mask=>({mask,...locate(mask)}),
    bucket:id=>{if(!Number.isInteger(id)||!B[id])throw RangeError("bucket");return copy(B[id]);},
    pattern:id=>{if(!Number.isInteger(id)||!P[id])throw RangeError("pattern");return copy(P[id]);},
    caches:()=>copy([...caches.values()]),work:()=>copy(work)};
}
module.exports={compile,openIndex};
