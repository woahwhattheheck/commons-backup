"use strict";
/*
 * Finite cyclic dilate-gap index.
 * The caller supplies a prime modulus and an identified residue palette.
 * No primality certificate or asymptotic theorem is computed here.
 */
function safe(n,name,min=0){if(!Number.isSafeInteger(n)||n<min)throw new TypeError(name);return n;}
function integer(x,name){if(typeof x==="number"){if(!Number.isSafeInteger(x))throw new TypeError(name);return BigInt(x);}if(typeof x!=="string"||!/^-?\d+$/.test(x))throw new TypeError(name);return BigInt(x);}
function modulo(x,p){return ((x%p)+p)%p;}
function gapRow(c,selected,p,work){
  const gaps=[];
  for(let j=0;j<selected.length;j++){
    const left=selected[j],right=selected[(j+1)%selected.length];
    const distance=j+1<selected.length?right.residue-left.residue:right.residue+p-left.residue;
    gaps.push({start:(left.residue+1)%p,length:distance-1,left_index:left.index,right_index:right.index});
    work.gap_calculations++;
  }
  return {c,gaps,maximum:gaps.reduce((m,g)=>Math.max(m,g.length),0)};
}
function summarize(mask,size,rows,unbounded){
  if(unbounded)return {mask:String(mask),size,unbounded:true,maximum:null,maximizing_multipliers:rows.map(r=>r.c),maximum_gap_records:null,histogram:[],rows};
  let maximum=0;const counts=new Map();
  for(const r of rows){maximum=Math.max(maximum,r.maximum);counts.set(r.maximum,(counts.get(r.maximum)||0)+1);}
  return {mask:String(mask),size,unbounded:false,maximum,maximizing_multipliers:rows.filter(r=>r.maximum===maximum).map(r=>r.c),maximum_gap_records:rows.reduce((n,r)=>n+r.gaps.filter(g=>g.length===maximum).length,0),histogram:[...counts].sort((a,b)=>a[0]-b[0]).map(([maximum,count])=>({maximum,count})),rows};
}
function compile(input){
  const p=safe(input.modulus,"prime modulus",2),palette=input.palette;
  if(!Array.isArray(palette)||palette.length<1||palette.length>input.limits.max_palette||p>input.limits.max_modulus||p-1>input.limits.max_condition_rows||(p-1)*palette.length>input.limits.max_image_cells)throw new RangeError("input cap");
  if(new Set(palette).size!==palette.length||palette.some(x=>!Number.isSafeInteger(x)||x<0||x>=p))throw new TypeError("palette");
  const primes=input.prime_premise;
  if(!Array.isArray(primes)||new Set(primes).size!==primes.length)throw new TypeError("prime premise");
  const primeIndex=new Map(primes.map((v,i)=>[v,i])),saved=new Map();
  for(const q of input.retained_products){
    safe(q.i,"retained i");safe(q.j,"retained j");
    if(q.i>q.j||q.j>=primes.length||!Number.isSafeInteger(q.target)||q.target<0||q.target>=p)throw new TypeError("retained product shape");
    const key=q.i+","+q.j;if(saved.has(key))throw new Error("duplicate retained pair");saved.set(key,q);
  }
  const work={retained_product_records:input.retained_products.length,copied_image_cells:0,new_multiplications:0,new_remainders:0,sort_comparisons:0,gap_calculations:0,prime_tests:0,old_product_recomputations:0};
  const rows=[],fullRows=[];
  for(let c=1;c<p;c++){
    const ci=primeIndex.get(c),images=palette.map(a=>{
      const ai=primeIndex.get(a);
      if(ci!==undefined&&ai!==undefined){
        const q=saved.get(Math.min(ci,ai)+","+Math.max(ci,ai));if(!q)throw new Error("missing retained product");
        work.copied_image_cells++;return q.target;
      }
      work.new_multiplications++;work.new_remainders++;return c*a%p;
    });
    const order=palette.map((_,i)=>i).sort((a,b)=>{work.sort_comparisons++;return images[a]-images[b];});
    if(order.some((a,j)=>j>0&&images[a]===images[order[j-1]]))throw new Error("dilation not injective; prime premise or input invalid");
    rows.push({c,images,order});
    fullRows.push(gapRow(c,order.map(index=>({index,residue:images[index]})),p,work));
  }
  const fullMask=2**palette.length-1;
  return {format:"cyclic-dilate-gap-index-v1",modulus:p,palette:palette.slice(),full_mask:String(fullMask),limits:{...input.limits},provenance:input.provenance,rows,full_condition:summarize(fullMask,palette.length,fullRows,false),construction_work:work};
}
function openIndex(data,caches){
  if(data.format!=="cyclic-dilate-gap-index-v1")throw new TypeError("format");
  const p=data.modulus,n=data.palette.length,full=2**n-1;
  if(!Number.isSafeInteger(p)||p<2||n<1||n>24||data.rows.length!==p-1)throw new TypeError("shape");
  const conditions=new Map([[String(full),data.full_condition]]),families=new Map();
  const work={condition_cache_hits:0,condition_builds:0,condition_mask_probes:0,saved_image_lookups:0,gap_calculations:0,family_cache_hits:0,family_builds:0,gap_scans:0,interval_segments:0,rank_row_scans:0,rank_segment_scans:0,selection_row_probes:0,selection_segment_probes:0,bigint_remainders:0,selected_residue_lookups:0,membership_lookups:0,dilation_multiplications:0,dilation_sorts:0,prime_tests:0};
  function maskValue(value){const m=integer(value,"mask");if(m<0n||m>BigInt(full))throw new RangeError("mask");return Number(m);}
  if(caches){
    if(caches.format!=="cyclic-dilate-gap-caches-v1"||caches.modulus!==p||caches.full_mask!==String(full)||JSON.stringify(caches.palette)!==JSON.stringify(data.palette))throw new TypeError("cache binding");
    for(const c of caches.conditions){maskValue(c.mask);if(c.rows.length!==p-1)throw new TypeError("condition rows");conditions.set(c.mask,c);}
    for(const f of caches.families)families.set(f.key,f);
  }
  function condition(value){
    const mask=maskValue(value),key=String(mask);
    if(conditions.has(key)){work.condition_cache_hits++;return conditions.get(key);}
    work.condition_builds++;let size=0;for(let i=0;i<n;i++)if(mask&(1<<i))size++;
    const rows=[];
    if(size===0){for(let c=1;c<p;c++)rows.push({c,gaps:[],maximum:null});}
    else for(const row of data.rows){
      const selected=[];
      for(const index of row.order){work.condition_mask_probes++;if(mask&(1<<index)){work.saved_image_lookups++;selected.push({index,residue:row.images[index]});}}
      rows.push(gapRow(row.c,selected,p,work));
    }
    const c=summarize(mask,size,rows,size===0);conditions.set(key,c);return c;
  }
  function conditionSummary(mask){
    const c=condition(mask);return {mask:c.mask,size:c.size,unbounded:c.unbounded,maximum:c.maximum,maximizing_multipliers:c.maximizing_multipliers,maximum_gap_records:c.maximum_gap_records,histogram:c.histogram};
  }
  function family(value,length,shift="0"){
    const mask=maskValue(value),L=integer(length,"length"),t=integer(shift,"shift");
    if(L<0n)throw new RangeError("negative gap length");
    work.bigint_remainders++;const s=Number(modulo(t,BigInt(p))),key=mask+":"+L+":"+s;
    if(families.has(key)){work.family_cache_hits++;return families.get(key);}
    work.family_builds++;
    const con=condition(mask),rows=[];let total=0;
    for(const row of con.rows){
      const segments=[];
      if(L===0n||con.unbounded){segments.push({lo:0,hi:p-1,gap_index:null});work.interval_segments++;}
      else if(L<BigInt(p)){
        const len=Number(L);
        row.gaps.forEach((g,gi)=>{
          work.gap_scans++;if(g.length<len)return;
          const start=(g.start+s)%p,span=g.length-len,end=start+span;
          if(end<p){segments.push({lo:start,hi:end,gap_index:gi});work.interval_segments++;}
          else {segments.push({lo:start,hi:p-1,gap_index:gi},{lo:0,hi:end-p,gap_index:gi});work.interval_segments+=2;}
        });
      }
      segments.sort((a,b)=>a.lo-b.lo);let count=0;
      for(const seg of segments){count+=seg.hi-seg.lo+1;seg.cumulative=count;}
      total+=count;rows.push({c:row.c,segments,count,cumulative:total});
    }
    const f={key,mask:String(mask),length:String(L),shift_mod:s,total,rows};
    families.set(key,f);return f;
  }
  function familySummary(mask,length,shift="0"){
    const f=family(mask,length,shift);return {key:f.key,mask:f.mask,length:f.length,shift_mod:f.shift_mod,total:f.total,nonempty_multipliers:f.rows.filter(r=>r.count>0).length,counts:f.rows.map(r=>r.count)};
  }
  function select(value,length,rank,shift="0"){
    const f=family(value,length,shift);safe(rank,"rank");
    if(rank>=f.total)throw new RangeError("rank outside family");
    let lo=0,hi=f.rows.length-1;
    while(lo<hi){work.selection_row_probes++;const mid=(lo+hi)>>1;if(rank<f.rows[mid].cumulative)hi=mid;else lo=mid+1;}
    const row=f.rows[lo],before=lo?f.rows[lo-1].cumulative:0,local=rank-before;let prev=0,segment;
    for(const seg of row.segments){work.selection_segment_probes++;if(local<seg.cumulative){segment=seg;break;}prev=seg.cumulative;}
    const start=segment.lo+local-prev,L=BigInt(f.length),con=conditions.get(f.mask);
    let container=null;
    if(segment.gap_index!==null){
      const g=con.rows[lo].gaps[segment.gap_index],r=data.rows[lo];
      work.selected_residue_lookups+=2;
      container={start:(g.start+f.shift_mod)%p,length:g.length,left_palette_index:g.left_index,right_palette_index:g.right_index,left_occupied:(r.images[g.left_index]+f.shift_mod)%p,right_occupied:(r.images[g.right_index]+f.shift_mod)%p};
    }
    return {rank,multiplier:row.c,start,length:f.length,shift_mod:f.shift_mod,last:L===0n?null:Number((BigInt(start)+L-1n)%BigInt(p)),wraps:L===0n?"0":String((BigInt(start)+L-1n)/BigInt(p)),container};
  }
  function rank(value,length,multiplier,start,shift="0"){
    const f=family(value,length,shift);safe(multiplier,"multiplier",1);safe(start,"start");
    if(multiplier>=p||start>=p)throw new RangeError("residue range");
    const row=f.rows[multiplier-1];let local=0;
    for(const seg of row.segments){work.rank_segment_scans++;if(start>=seg.lo&&start<=seg.hi)return{member:true,rank:(multiplier===1?0:f.rows[multiplier-2].cumulative)+local+start-seg.lo};local=seg.cumulative;}
    return {member:false,rank:null};
  }
  function page(mask,length,offset=0,limit=20,shift="0"){
    safe(offset,"offset");safe(limit,"limit");if(limit>data.limits.max_page)throw new RangeError("page cap");
    const f=family(mask,length,shift),items=[];
    for(let r=offset;r<Math.min(f.total,offset+limit);r++)items.push(select(mask,length,r,shift));
    return {total:f.total,offset,items};
  }
  function membership(value,multiplier,start,length,shift="0"){
    const mask=maskValue(value),L=integer(length,"length"),t=integer(shift,"shift");
    safe(multiplier,"multiplier",1);safe(start,"start");if(multiplier>=p||start>=p||L<0n)throw new RangeError("membership arguments");
    work.bigint_remainders++;const s=Number(modulo(t,BigInt(p))),row=data.rows[multiplier-1];
    if(L===0n||mask===0)return {valid:true,witness:null};
    for(let i=0;i<n;i++)if(mask&(1<<i)){
      work.membership_lookups++;const residue=(row.images[i]+s)%p,offset=(residue-start+p)%p;
      if(BigInt(offset)<L)return {valid:false,witness:{palette_index:i,palette_value:data.palette[i],occupied_residue:residue,offset}};
    }
    return {valid:true,witness:null};
  }
  return {
    summary:()=>({modulus:p,palette:data.palette,subpalettes:String(1n<<BigInt(n)),multipliers:p-1,full_condition:conditionSummary(full),construction_work:data.construction_work}),
    condition:conditionSummary,
    conditionRows:mask=>condition(mask),
    family:familySummary,select,rank,page,membership,
    dilation:c=>{safe(c,"multiplier",1);if(c>=p)throw new RangeError("multiplier");return data.rows[c-1];},
    caches:()=>({format:"cyclic-dilate-gap-caches-v1",modulus:p,palette:data.palette.slice(),full_mask:String(full),conditions:[...conditions].filter(([k])=>k!==String(full)).map(([,v])=>v),families:[...families.values()]}),
    work:()=>({...work})
  };
}
module.exports={compile,openIndex};
