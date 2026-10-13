"use strict";
// Labelled binary linear codes, exact finite RREF atlas and saved coset reader.
function integer(x,name,a,b){if(!Number.isSafeInteger(x)||x<a||x>b)throw new RangeError(name);return x;}
function compile(input){
 const L=input.limits||{},n=integer(input.dimension,"dimension",1,Math.min(8,L.max_dimension||8)),N=1<<n;
 const bin=input.binomial_row,bc=input.binomial_cumulative;
 if(!Array.isArray(bin)||bin.length!==n+1||!Array.isArray(bc)||bc.length!==n+2||bc[0]!=="0")throw new Error("inherited binomial row shape");
 for(const v of bin.concat(bc))if(typeof v!=="string"||!/^(0|[1-9][0-9]*)$/.test(v))throw new TypeError("inherited coefficient");
 const volumes=bc.slice(1).map(Number);if(volumes.some(v=>!Number.isSafeInteger(v)))throw new RangeError("ball volume");
 const weights=Array(N).fill(0),work={weight_recurrence_steps:0,pivot_masks:0,rref_free_bit_probes:0,rref_free_bit_assignments:0,subspaces:0,ambient_assignments:0,reduction_bit_probes:0,reduction_xors:0,coset_histogram_increments:0,coset_cumulative_additions:0,coset_cells:0,profile_insertions:0,optimum_code_scans:0,binomial_recurrence_steps:0};
 for(let x=1;x<N;x++){weights[x]=weights[x>>1]+(x&1);work.weight_recurrence_steps++;}
 const weightOrder=Array.from({length:N},(_,x)=>x).sort((a,b)=>weights[a]-weights[b]||a-b);
 const codes=[],profiles=new Map();
 for(let pivotMask=0;pivotMask<N;pivotMask++){
  work.pivot_masks++;const pivots=[],free=[];
  for(let j=0;j<n;j++)((pivotMask>>j)&1?pivots:free).push(j);
  const positions=[];for(let i=0;i<pivots.length;i++)for(const j of free)if(j>pivots[i])positions.push([i,j]);
  const variants=1<<positions.length;
  for(let assignment=0;assignment<variants;assignment++){
   if(codes.length>=(L.max_subspaces||10000))throw new RangeError("subspace cap");
   if(work.ambient_assignments+N>(L.max_ambient_assignments||1000000))throw new RangeError("assignment cap");
   const k=pivots.length,cosetCount=1<<(n-k),cells=2*(n+1)*cosetCount;
   if(work.coset_cells+cells>(L.max_coset_cells||2000000))throw new RangeError("coset cell cap");
   const basis=pivots.map(j=>1<<j);
   for(let a=0;a<positions.length;a++){work.rref_free_bit_probes++;if((assignment>>a)&1){const[i,j]=positions[a];basis[i]|=1<<j;work.rref_free_bit_assignments++;}}
   const remainderToCoset=Array(N).fill(-1),cosets=[];
   for(let s=0;s<cosetCount;s++){
    let representative=0;for(let j=0;j<free.length;j++)if((s>>j)&1)representative|=1<<free[j];
    remainderToCoset[representative]=s;
    cosets.push({representative,error_vectors:[],histogram:Array(n+1).fill(0),cumulative:[],minimum_weight:null,minimum_count:0});
   }
   const syndromeMap=Array(N);
   for(const x of weightOrder){
    let rem=x;for(let i=0;i<k;i++){work.reduction_bit_probes++;if((rem>>pivots[i])&1){rem^=basis[i];work.reduction_xors++;}}
    const s=remainderToCoset[rem];if(s<0)throw new Error("invalid RREF remainder");
    syndromeMap[x]=s;const c=cosets[s];c.error_vectors.push(x);c.histogram[weights[x]]++;work.coset_histogram_increments++;work.ambient_assignments++;
   }
   let radius=0;
   for(const c of cosets){
    if(!c.error_vectors.length)throw new Error("empty coset");
    c.minimum_weight=weights[c.error_vectors[0]];c.minimum_count=c.histogram[c.minimum_weight];radius=Math.max(radius,c.minimum_weight);
    let total=0;for(const v of c.histogram){total+=v;c.cumulative.push(total);work.coset_cumulative_additions++;}
   }
   work.coset_cells+=cells;
   const id=codes.length,minimum=cosets[0].error_vectors.length===1?null:weights[cosets[0].error_vectors[1]];
   const code={id,pivot_mask:pivotMask,free_assignment:assignment,pivots,basis,dimension:k,size:1<<k,covering_radius:radius,minimum_nonzero_distance:minimum,syndrome_map:syndromeMap,cosets};
   codes.push(code);work.subspaces++;
   const key=k+","+radius+","+(minimum===null?"infinity":minimum);
   if(!profiles.has(key))profiles.set(key,{key,dimension:k,covering_radius:radius,minimum_nonzero_distance:minimum,code_ids:[]});
   profiles.get(key).code_ids.push(id);work.profile_insertions++;
  }
 }
 const optima=[];
 for(let r=0;r<=n;r++){
  let d=n+1,ids=[];for(const c of codes){work.optimum_code_scans++;if(c.covering_radius<=r){if(c.dimension<d){d=c.dimension;ids=[];}if(c.dimension===d)ids.push(c.id);}}
  if(!ids.length)throw new Error("missing full-space cover");
  let numerator=(1<<d)*volumes[r],denominator=N;while(numerator%2===0&&denominator%2===0){numerator/=2;denominator/=2;}
  optima.push({radius:r,minimum_dimension:d,minimum_size:1<<d,ball_volume:volumes[r],density_numerator:numerator,density_denominator:denominator,code_ids:ids});
 }
 const dimensionCounts=Array(n+1).fill(0),radiusCounts=Array(n+1).fill(0);
 for(const c of codes){dimensionCounts[c.dimension]++;radiusCounts[c.covering_radius]++;}
 return {format:"binary-linear-cover-v1",dimension:n,ambient_size:N,provenance:input.provenance,binomial_row:bin.slice(),ball_volumes:volumes,weights,weight_order:weightOrder,codes,profiles:Array.from(profiles.values()),optima,summary:{dimension:n,ambient_size:N,subspaces:codes.length,cosets:work.coset_cells/(2*(n+1)),profile_count:profiles.size,dimension_counts:dimensionCounts,covering_radius_counts:radiusCounts,optima:optima.map(o=>({radius:o.radius,dimension:o.minimum_dimension,size:o.minimum_size,density:[o.density_numerator,o.density_denominator],count:o.code_ids.length}))},construction_work:work};
}
function openIndex(data){
 if(data.format!=="binary-linear-cover-v1"||data.ambient_size!==1<<data.dimension||!Array.isArray(data.codes))throw new Error("snapshot shape");
 const n=data.dimension,N=data.ambient_size,caches=[],memo=new Map();
 const work={family_code_scans:0,syndrome_lookups:0,code_lookups:0,coefficient_lookups:0,error_entries_returned:0,codeword_xors:0,neighbor_rank_probes:0,family_rank_probes:0,rref_enumerations:0,basis_reductions:0,weight_computations:0,histogram_rebuilds:0};
 const vec=x=>integer(x,"ambient vector",0,N-1);
 function code(id){integer(id,"code id",0,data.codes.length-1);work.code_lookups++;return data.codes[id];}
 function brief(c){return {id:c.id,dimension:c.dimension,size:c.size,covering_radius:c.covering_radius,minimum_nonzero_distance:c.minimum_nonzero_distance,basis:c.basis,pivots:c.pivots};}
 function condition(o={}){
  const a={min_dimension:o.min_dimension===undefined?0:integer(o.min_dimension,"min_dimension",0,n),max_dimension:o.max_dimension===undefined?n:integer(o.max_dimension,"max_dimension",0,n),max_radius:o.max_radius===undefined?n:integer(o.max_radius,"max_radius",0,n),min_distance:o.min_distance===undefined?0:integer(o.min_distance,"min_distance",0,n+1),allow_zero_dimension:o.allow_zero_dimension===undefined?true:o.allow_zero_dimension};
  if(typeof a.allow_zero_dimension!=="boolean"||a.min_dimension>a.max_dimension)throw new RangeError("condition");
  for(const key of ["contains","excludes"]){if(o[key]!==undefined&&!Array.isArray(o[key]))throw new TypeError(key);a[key]=Array.from(new Set((o[key]||[]).map(vec))).sort((x,y)=>x-y);}
  return a;
 }
 function family(o={}){
  const a=condition(o),key=JSON.stringify(a);if(memo.has(key))return caches[memo.get(key)];
  const ids=[];
  for(const c of data.codes){
   work.family_code_scans++;
   if(c.dimension<a.min_dimension||c.dimension>a.max_dimension||c.covering_radius>a.max_radius||(!a.allow_zero_dimension&&c.dimension===0)||(c.minimum_nonzero_distance!==null&&c.minimum_nonzero_distance<a.min_distance))continue;
   let ok=true;
   for(const x of a.contains){work.syndrome_lookups++;if(c.syndrome_map[x]!==0){ok=false;break;}}
   if(ok)for(const x of a.excludes){work.syndrome_lookups++;if(c.syndrome_map[x]===0){ok=false;break;}}
   if(ok)ids.push(c.id);
  }
  const entry={id:caches.length,condition:a,count:ids.length,code_ids:ids};memo.set(key,entry.id);caches.push(entry);return entry;
 }
 function selectFamily(o,rank){const f=family(o);integer(rank,"family rank",0,f.count-1);return {cache_id:f.id,rank,total:f.count,code:brief(code(f.code_ids[rank]))};}
 function rankFamily(o,id){code(id);const f=family(o);let lo=0,hi=f.count;while(lo<hi){const mid=(lo+hi)>>1;work.family_rank_probes++;if(f.code_ids[mid]<id)lo=mid+1;else hi=mid;}return {cache_id:f.id,id,member:lo<f.count&&f.code_ids[lo]===id,rank:lo<f.count&&f.code_ids[lo]===id?lo:null,total:f.count};}
 function coset(id,x){const c=code(id);vec(x);work.syndrome_lookups++;const s=c.syndrome_map[x];return {code:c,syndrome:s,coset:c.cosets[s]};}
 function neighbors(id,x,r,start=0,limit=1000){
  integer(r,"radius",0,n);integer(limit,"limit",0,10000);const z=coset(id,x);work.coefficient_lookups++;const total=z.coset.cumulative[r];integer(start,"start",0,total);
  const items=[];for(let rank=start;rank<Math.min(total,start+limit);rank++){const e=z.coset.error_vectors[rank];items.push({rank,error:e,distance:data.weights[e],codeword:x^e});work.error_entries_returned++;work.codeword_xors++;}
  return {id,received:x,radius:r,syndrome:z.syndrome,minimum_distance:z.coset.minimum_weight,nearest_count:z.coset.minimum_count,start,next:start+items.length,total,items};
 }
 return {
  summary:()=>data.summary,profiles:()=>data.profiles,optima:()=>data.optima,
  code:id=>code(id),
  family:o=>{const f=family(o);return {cache_id:f.id,condition:f.condition,count:f.count};},
  familyPage:(o,start=0,limit=100)=>{const f=family(o);integer(start,"start",0,f.count);integer(limit,"limit",0,10000);return {cache_id:f.id,start,next:Math.min(f.count,start+limit),total:f.count,items:f.code_ids.slice(start,start+limit).map((id,i)=>({rank:start+i,code:brief(code(id))}))};},
  selectFamily,rankFamily,
  coset:(id,x)=>{const z=coset(id,x);return {id,received:x,syndrome:z.syndrome,...z.coset};},
  neighbors,
  nearest:(id,x)=>{const z=coset(id,x);return neighbors(id,x,z.coset.minimum_weight,0,z.coset.minimum_count);},
  rankNeighbor:(id,x,r,cw)=>{vec(cw);integer(r,"radius",0,n);const z=coset(id,x),e=x^cw;work.codeword_xors++;work.coefficient_lookups++;const total=z.coset.cumulative[r];let rank=-1;for(let j=0;j<total;j++){work.neighbor_rank_probes++;if(z.coset.error_vectors[j]===e){rank=j;break;}}return {id,received:x,radius:r,codeword:cw,error:e,member:rank>=0,rank:rank<0?null:rank,total};},
  density:(id,r)=>{integer(r,"radius",0,n);const c=code(id);return {id,radius:r,covers:c.covering_radius<=r,numerator:c.size*data.ball_volumes[r],denominator:N,ball_volume:data.ball_volumes[r]};},
  caches:()=>caches,work:()=>({...work})
 };
}
module.exports={compile,openIndex};
