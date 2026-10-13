"use strict";
// Exact distance classes of a finite rectangular integer grid; no pair enumeration.
const SCHEMA="commons.rectangle_distance_fibers/v1";
const LIMITS=Object.freeze({side:1000000,points:100000,page:64,digits:128,json_chars:16000000});
function fail(x){throw new Error(x);}
function nat(x,max,name){if(!Number.isSafeInteger(x)||x<0||x>max)fail(name+" out of range");return x;}
function dimensions(width,height){nat(width,LIMITS.side,"width");nat(height,LIMITS.side,"height");if(!width||!height||width*height>LIMITS.points)fail("grid size");return width*height;}
function copy(x){return JSON.parse(JSON.stringify(x));}
function decimal(x,digits=LIMITS.digits){if(typeof x==="number"){if(!Number.isSafeInteger(x))fail("safe integer");x=String(x);}
 if(typeof x!=="string"||! /^-?(0|[1-9][0-9]*)$/.test(x)||x.replace("-","").length>digits)fail("bounded decimal");return BigInt(x);}
function transform(a={}){
 if(!a||typeof a!=="object"||Array.isArray(a)||Object.keys(a).some(k=>!["x0","y0","scale"].includes(k)))fail("transform");
 const x0=decimal(a.x0===undefined?"0":a.x0),y0=decimal(a.y0===undefined?"0":a.y0),scale=decimal(a.scale===undefined?"1":a.scale);if(scale<=0n)fail("positive scale");return {x0,y0,scale};
}
function compile(width,height){
 const n=dimensions(width,height),blocks=[],map=new Map();
 const stats={displacement_blocks:0,squared_distance_evaluations:0,point_pairs_enumerated:0};
 for(let dx=0;dx<width;dx++)for(let dy=0;dy<height;dy++){
  if(dx===0&&dy===0)continue;
  const q=dx*dx+dy*dy,base=(width-dx)*(height-dy),orientations=dx&&dy?2:1,weight=base*orientations,id=blocks.length;
  stats.squared_distance_evaluations++;
  blocks.push([dx,dy,q,base,orientations,weight,-1]);if(!map.has(q))map.set(q,[]);map.get(q).push(id);
 }
 const groups=[],pairPrefix=[0],multiplicityMap=new Map();
 for(const q of [...map.keys()].sort((a,b)=>a-b)){
  const ids=map.get(q),prefix=[0],id=groups.length;
  for(const b of ids){blocks[b][6]=id;prefix.push(prefix[prefix.length-1]+blocks[b][5]);}
  const count=prefix[prefix.length-1];groups.push({squared_distance:q,pair_count:count,block_ids:ids,block_prefix:prefix});
  pairPrefix.push(pairPrefix[pairPrefix.length-1]+count);
  if(!multiplicityMap.has(count))multiplicityMap.set(count,[]);multiplicityMap.get(count).push(id);
 }
 stats.displacement_blocks=blocks.length;
 const histogram=[...multiplicityMap].sort((a,b)=>a[0]-b[0]).map(([multiplicity,ids])=>({multiplicity,distance_ids:ids}));
 const low=groups.map((g,i)=>g.pair_count<=n?i:-1).filter(i=>i>=0),diameter=groups.length?groups.length-1:null;
 return {schema:SCHEMA,width,height,point_count:n,unordered_pair_count:n*(n-1)/2,
  point_order:"x-major then y; coordinates start at zero",
  block_columns:["dx","dy","squared_distance","translation_count","orientations","pair_count","distance_id"],
  blocks,groups,pair_prefix:pairPrefix,multiplicity_histogram:histogram,
  low_multiplicity:{threshold:n,distance_ids:low,non_diameter_ids:low.filter(i=>i!==diameter)},diameter_id:diameter,stats};
}
function open(saved){
 const text=typeof saved==="string"?saved:JSON.stringify(saved);if(text.length>LIMITS.json_chars)fail("snapshot size");const s=JSON.parse(text);
 if(!s||s.schema!==SCHEMA)fail("schema");const n=dimensions(s.width,s.height),w=s.width,h=s.height,total=n*(n-1)/2,maxQ=(w-1)*(w-1)+(h-1)*(h-1);
 if(s.point_count!==n||s.unordered_pair_count!==total||!Array.isArray(s.blocks)||s.blocks.length!==n-1||!Array.isArray(s.groups)||s.groups.length>n-1)fail("dimensions");
 const blockLookup=new Map();let at=0;
 for(let dx=0;dx<w;dx++)for(let dy=0;dy<h;dy++){
  if(!dx&&!dy)continue;const b=s.blocks[at];
  if(!Array.isArray(b)||b.length!==7||b[0]!==dx||b[1]!==dy)fail("block layout");
  nat(b[2],maxQ,"distance");if(!b[2])fail("positive distance");nat(b[3],n,"translation count");if(!b[3]||![1,2].includes(b[4]))fail("block count");
  nat(b[5],total,"block weight");nat(b[6],s.groups.length-1,"distance id");blockLookup.set(dx+","+dy,at++);
 }
 const qMap=new Map(),seen=new Set();
 function prefix(a,size,end){if(!Array.isArray(a)||a.length!==size+1||a[0]!==0||a[size]!==end)fail("prefix dimensions");for(let i=1;i<a.length;i++){nat(a[i],total,"prefix");if(a[i]<=a[i-1])fail("positive prefix");}}
 let previousQ=0;
 for(let id=0;id<s.groups.length;id++){
  const g=s.groups[id];nat(g.squared_distance,maxQ,"distance");if(g.squared_distance<=previousQ)fail("distance order");previousQ=g.squared_distance;
  nat(g.pair_count,total,"multiplicity");if(!g.pair_count||!Array.isArray(g.block_ids)||!g.block_ids.length)fail("group");
  prefix(g.block_prefix,g.block_ids.length,g.pair_count);let prev=-1;
  for(const b of g.block_ids){nat(b,s.blocks.length-1,"block id");if(b<=prev||seen.has(b)||s.blocks[b][6]!==id||s.blocks[b][2]!==g.squared_distance)fail("group block link");prev=b;seen.add(b);}
  qMap.set(g.squared_distance,id);
 }
 if(seen.size!==s.blocks.length)fail("block partition");prefix(s.pair_prefix,s.groups.length,total);
 if(s.diameter_id!==(s.groups.length?s.groups.length-1:null))fail("diameter id");
 function ids(a){if(!Array.isArray(a)||a.length>s.groups.length)fail("distance ids");let p=-1;for(const i of a){nat(i,s.groups.length-1,"distance id");if(i<=p)fail("id order");p=i;}}
 if(s.low_multiplicity.threshold!==n)fail("threshold");ids(s.low_multiplicity.distance_ids);ids(s.low_multiplicity.non_diameter_ids);
 if(!Array.isArray(s.multiplicity_histogram)||s.multiplicity_histogram.length>s.groups.length)fail("histogram");let prev=0,histTotal=0;
 for(const row of s.multiplicity_histogram){nat(row.multiplicity,total,"multiplicity");if(row.multiplicity<=prev)fail("histogram order");prev=row.multiplicity;ids(row.distance_ids);histTotal+=row.distance_ids.length;}
 if(histTotal!==s.groups.length)fail("histogram partition size");
 const stats={queries:0,groups_indexed:s.groups.length,blocks_indexed:s.blocks.length,groups_scanned:0,binary_steps:0,pairs_selected:0,pairs_ranked:0,displacement_compilations:0,squared_distance_evaluations:0,point_pairs_enumerated:0};
 function locate(p,rank){let lo=0,hi=p.length-1;while(lo<hi){stats.binary_steps++;const m=(lo+hi)>>1;if(p[m+1]<=rank)lo=m+1;else hi=m;}return lo;}
 function groupRecord(id){nat(id,s.groups.length-1,"distance id");const g=s.groups[id];return {distance_id:id,squared_distance:g.squared_distance,pair_count:g.pair_count,block_count:g.block_ids.length,is_diameter:id===s.diameter_id,low_multiplicity:g.pair_count<=n};}
 function physical(p,a){return [(a.x0+a.scale*BigInt(p[0])).toString(),(a.y0+a.scale*BigInt(p[1])).toString()];}
 function pairAt(id,rank,a){
  const g=s.groups[id];nat(rank,g.pair_count-1,"distance pair rank");const pos=locate(g.block_prefix,rank),bid=g.block_ids[pos],b=s.blocks[bid];
  const local=rank-g.block_prefix[pos],orientation=Math.floor(local/b[3]),translation=local%b[3],height=h-b[1];
  const x=Math.floor(translation/height),y=translation%height;
  const first=orientation===0?[x,y]:[x,y+b[1]],second=orientation===0?[x+b[0],y+b[1]]:[x+b[0],y];
  stats.pairs_selected++;
  return {global_rank:s.pair_prefix[id]+rank,distance_id:id,distance_rank:rank,block_id:bid,block_rank:local,orientation:orientation===0?"nonnegative-dy":"negative-dy",
   grid_points:[first,second],point_ids:[first[0]*h+first[1],second[0]*h+second[1]],
   points:[physical(first,a),physical(second,a)],squared_distance:g.squared_distance,transformed_squared_distance:(BigInt(g.squared_distance)*a.scale*a.scale).toString()};
 }
 function rankPair(points,a){
  if(!Array.isArray(points)||points.length!==2||points.some(p=>!Array.isArray(p)||p.length!==2))fail("pair coordinates");
  const grid=points.map(p=>p.map((v,i)=>{const diff=decimal(v,LIMITS.digits+7)-(i?a.y0:a.x0);if(diff%a.scale!==0n)fail("point outside scaled lattice");const x=diff/a.scale;if(x<0n||x>=BigInt(i?h:w))fail("point outside grid");return Number(x);}));
  if(grid[0][0]>grid[1][0]||(grid[0][0]===grid[1][0]&&grid[0][1]>grid[1][1]))grid.reverse();
  const dx=grid[1][0]-grid[0][0],signedDy=grid[1][1]-grid[0][1],dy=Math.abs(signedDy);
  if(!dx&&!dy)fail("distinct points required");const bid=blockLookup.get(dx+","+dy),b=s.blocks[bid],id=b[6],g=s.groups[id];
  const orientation=dx&&signedDy<0?1:0,x=grid[0][0],y=Math.min(grid[0][1],grid[1][1]);
  const local=orientation*b[3]+x*(h-dy)+y;
  let lo=0,hi=g.block_ids.length;while(lo<hi){stats.binary_steps++;const m=(lo+hi)>>1;if(g.block_ids[m]<bid)lo=m+1;else hi=m;}
  const rank=g.block_prefix[lo]+local;stats.pairs_ranked++;
  return {global_rank:s.pair_prefix[id]+rank,distance_id:id,distance_rank:rank,block_id:bid,block_rank:local};
 }
 function slice(ids,criteria){const p=[0];for(const id of ids)p.push(p[p.length-1]+s.groups[id].pair_count);
  return {schema:"commons.rectangle_distance_slice/v1",width:w,height:h,criteria:copy(criteria),distance_ids:ids,pair_prefix:p};}
 function openSlice(raw){
  const a=copy(raw);if(a.schema!=="commons.rectangle_distance_slice/v1"||a.width!==w||a.height!==h)fail("slice binding");ids(a.distance_ids);
  prefix(a.pair_prefix,a.distance_ids.length,a.pair_prefix[a.pair_prefix.length-1]);
  return {
   summary(){stats.queries++;return {criteria:copy(a.criteria),distances:a.distance_ids.length,pairs:a.pair_prefix[a.pair_prefix.length-1]};},
   page(start=0,limit=64){stats.queries++;nat(start,a.distance_ids.length,"start");nat(limit,LIMITS.page,"page size");return {total:a.distance_ids.length,start,items:a.distance_ids.slice(start,start+limit).map(groupRecord),next:start+limit<a.distance_ids.length?start+limit:null};},
   selectDistance(rank){stats.queries++;nat(rank,a.distance_ids.length-1,"slice rank");return {slice_rank:rank,...groupRecord(a.distance_ids[rank])};},
   selectPair(rank,options={}){stats.queries++;nat(rank,a.pair_prefix[a.pair_prefix.length-1]-1,"slice pair rank");const i=locate(a.pair_prefix,rank);return {slice_pair_rank:rank,...pairAt(a.distance_ids[i],rank-a.pair_prefix[i],transform(options))};},
   rankPair(points,options={}){stats.queries++;const r=rankPair(points,transform(options));let lo=0,hi=a.distance_ids.length;while(lo<hi){stats.binary_steps++;const m=(lo+hi)>>1;if(a.distance_ids[m]<r.distance_id)lo=m+1;else hi=m;}return lo<a.distance_ids.length&&a.distance_ids[lo]===r.distance_id?a.pair_prefix[lo]+r.distance_rank:null;},
   snapshot(){return copy(a);}
  };
 }
 return {
  summary(){stats.queries++;return {width:w,height:h,points:n,unordered_pairs:total,displacement_blocks:s.blocks.length,distances:s.groups.length,diameter:s.diameter_id===null?null:groupRecord(s.diameter_id),low_multiplicity_distances:s.low_multiplicity.distance_ids.length,low_non_diameter_distances:s.low_multiplicity.non_diameter_ids.length,histogram_rows:s.multiplicity_histogram.length,constructor_stats:copy(s.stats)};},
  distance(squared){stats.queries++;nat(squared,Number.MAX_SAFE_INTEGER,"squared distance");const id=qMap.get(squared);return id===undefined?null:groupRecord(id);},
  distancePage(start=0,limit=64){stats.queries++;nat(start,s.groups.length,"start");nat(limit,LIMITS.page,"page size");return {total:s.groups.length,start,items:s.groups.slice(start,start+limit).map((_,i)=>groupRecord(start+i)),next:start+limit<s.groups.length?start+limit:null};},
  fiber(squared){stats.queries++;nat(squared,Number.MAX_SAFE_INTEGER,"squared distance");const id=qMap.get(squared);if(id===undefined)return null;const g=s.groups[id];return {...groupRecord(id),blocks:g.block_ids.map((bid,i)=>({block_id:bid,record:s.blocks[bid].slice(),pair_rank_start:g.block_prefix[i]}))};},
  selectPair(rank,options={}){stats.queries++;nat(rank,total-1,"global pair rank");const id=locate(s.pair_prefix,rank);return pairAt(id,rank-s.pair_prefix[id],transform(options));},
  distancePair(squared,rank,options={}){stats.queries++;nat(squared,Number.MAX_SAFE_INTEGER,"squared distance");const id=qMap.get(squared);if(id===undefined)fail("unrealized distance");return pairAt(id,rank,transform(options));},
  rankPair(points,options={}){stats.queries++;return rankPair(points,transform(options));},
  lowMultiplicity(excludeDiameter=false){stats.queries++;if(typeof excludeDiameter!=="boolean")fail("diameter flag");return slice((excludeDiameter?s.low_multiplicity.non_diameter_ids:s.low_multiplicity.distance_ids).slice(),{max_multiplicity:n,exclude_diameter:excludeDiameter});},
  filter(criteria={}){
   stats.queries++;if(!criteria||typeof criteria!=="object"||Array.isArray(criteria)||Object.keys(criteria).some(x=>!["min_multiplicity","max_multiplicity","min_squared","max_squared","exclude_diameter"].includes(x)))fail("filter");
   const c=copy(criteria);for(const k of ["min_multiplicity","max_multiplicity"])if(c[k]!==undefined)nat(c[k],total,k);for(const k of ["min_squared","max_squared"])if(c[k]!==undefined)nat(c[k],Number.MAX_SAFE_INTEGER,k);if(c.exclude_diameter!==undefined&&typeof c.exclude_diameter!=="boolean")fail("diameter flag");
   const a=[];for(let id=0;id<s.groups.length;id++){stats.groups_scanned++;const g=s.groups[id];
    if(c.min_multiplicity!==undefined&&g.pair_count<c.min_multiplicity||c.max_multiplicity!==undefined&&g.pair_count>c.max_multiplicity||c.min_squared!==undefined&&g.squared_distance<c.min_squared||c.max_squared!==undefined&&g.squared_distance>c.max_squared||c.exclude_diameter&&id===s.diameter_id)continue;a.push(id);}
   return slice(a,c);
  },
  openSlice,
  histogram(start=0,limit=64){stats.queries++;nat(start,s.multiplicity_histogram.length,"start");nat(limit,LIMITS.page,"page size");return {total:s.multiplicity_histogram.length,start,rows:copy(s.multiplicity_histogram.slice(start,start+limit)),next:start+limit<s.multiplicity_histogram.length?start+limit:null};},
  blockPage(start=0,limit=64){stats.queries++;nat(start,s.blocks.length,"start");nat(limit,LIMITS.page,"page size");return {total:s.blocks.length,start,rows:copy(s.blocks.slice(start,start+limit)),next:start+limit<s.blocks.length?start+limit:null};},
  stats(){return copy(stats);},snapshot(){return copy(s);}
 };
}
module.exports={compile,open,LIMITS,SCHEMA};
