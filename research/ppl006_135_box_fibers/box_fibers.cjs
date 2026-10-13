"use strict";
const FIELDS=["x","y","z","w","n","t"];
const copy=x=>JSON.parse(JSON.stringify(x));
function int(x,name){if(!Number.isSafeInteger(x))throw new TypeError(name+" must be a safe integer");return x;}
function compile(input){
 const B=int(input.coordinateMax,"coordinateMax");if(B<0||B>63)throw new RangeError("coordinateMax 0..63");
 const work={squareProducts:0,tripleCandidates:0,acceptedTriples:0,jointCoefficientIncrements:0,explicitQuadrupleRows:0};
 const squares=Array.from({length:B+1},(_,i)=>{work.squareProducts++;return i*i;});
 const roots=[];for(let t=0;t*t<=9*B;t++){work.squareProducts++;roots.push([t,t*t]);}
 const triples=[];
 for(let y=0;y<=B;y++)for(let z=0;z<=B;z++)for(const [t,tt]of roots){
  work.tripleCandidates++;const x=tt-3*y-5*z;
  if(x>=0&&x<=B){triples.push([x,y,z,t,squares[x]+squares[y]+squares[z]]);work.acceptedTriples++;}
 }
 triples.sort((a,b)=>a[0]-b[0]||a[1]-b[1]||a[2]-b[2]);
 const joint=new Map(),nt=new Map(),rt=new Map();
 for(const a of triples)for(let w=0;w<=B;w++){
  const n=a[4]+squares[w],t=a[3],key=n+","+t;work.jointCoefficientIncrements++;
  joint.set(key,(joint.get(key)||0)+1);nt.set(n,(nt.get(n)||0)+1);rt.set(t,(rt.get(t)||0)+1);
 }
 const sorted=m=>Array.from(m).sort((a,b)=>a[0]-b[0]);
 const fibers=Array.from(joint,([k,count])=>k.split(",").map(Number).concat(count)).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
 return {schema:"ppl006.box-fibers/v1",input,squares,triples,joint:fibers,nProfile:sorted(nt),tProfile:sorted(rt),
  summary:{triples:triples.length,quadruples:triples.length*(B+1),jointFibers:fibers.length,distinctTargets:nt.size,
   targetMin:nt.size?Math.min(...nt.keys()):null,targetMax:nt.size?Math.max(...nt.keys()):null,
   squareRoots:sorted(rt).map(x=>x[0])},constructionWork:work};
}
function createReader(saved){
 if(!saved||saved.schema!=="ppl006.box-fibers/v1")throw new TypeError("saved schema");
 const B=saved.input.coordinateMax,triples=saved.triples,squares=saved.squares;
 const lookup=new Map(triples.map((a,i)=>[a.slice(0,3).join(","),i]));
 const fiberLookup=new Map(saved.joint.map(a=>[a[0]+","+a[1],a[2]])),cache=new Map(),images=new Map();
 const work={lookupRows:triples.length+saved.joint.length,conditionBuilds:0,conditionHits:0,tripleChecks:0,
  squareLookups:0,selectBlockReads:0,rankBlockReads:0,tupleMaterializations:0,fiberReads:0,
  imageBuilds:0,imageHits:0,imageTupleVisits:0,profileCellsRead:0,newTripleCandidates:0,newBaseCoefficients:0};
 const physical=[[0,B],[0,B],[0,B],[0,B],[0,4*B*B],[0,Math.floor(Math.sqrt(9*B))]];
 function normalize(filter={}){
  if(!filter||typeof filter!=="object"||Array.isArray(filter))throw new TypeError("filter object");
  for(const k of Object.keys(filter))if(!FIELDS.includes(k))throw new RangeError("unknown filter "+k);
  return FIELDS.map((f,i)=>{const a=filter[f]===undefined?physical[i]:filter[f];
   if(!Array.isArray(a)||a.length!==2)throw new TypeError("inclusive range "+f);
   return [Math.max(physical[i][0],int(a[0],f)),Math.min(physical[i][1],int(a[1],f))];});
 }
 function bound(value,upper){
  let lo=0,hi=squares.length;while(lo<hi){const m=Math.floor((lo+hi)/2);work.squareLookups++;
   if(squares[m]<value||(upper&&squares[m]===value))lo=m+1;else hi=m;}return lo;
 }
 function context(filter){
  const ranges=normalize(filter),key=JSON.stringify(ranges);
  if(cache.has(key)){work.conditionHits++;return cache.get(key);}
  work.conditionBuilds++;const blocks=[];let count=0,nMin=null,nMax=null;const tCounts=new Map();
  if(ranges.every(a=>a[0]<=a[1]))for(let id=0;id<triples.length;id++){
   work.tripleChecks++;const a=triples[id];
   if(a[0]<ranges[0][0]||a[0]>ranges[0][1]||a[1]<ranges[1][0]||a[1]>ranges[1][1]||
    a[2]<ranges[2][0]||a[2]>ranges[2][1]||a[3]<ranges[5][0]||a[3]>ranges[5][1])continue;
   const lo=Math.max(ranges[3][0],bound(ranges[4][0]-a[4],false));
   const hi=Math.min(ranges[3][1],bound(ranges[4][1]-a[4],true)-1);
   if(lo>hi)continue;
   const c=hi-lo+1;blocks.push([id,lo,hi,count]);count+=c;
   work.squareLookups+=2;const l=a[4]+squares[lo],h=a[4]+squares[hi];
   nMin=nMin===null?l:Math.min(nMin,l);nMax=nMax===null?h:Math.max(nMax,h);
   tCounts.set(a[3],(tCounts.get(a[3])||0)+c);
  }
  const c={key,ranges,blocks,count,nMin,nMax,tProfile:Array.from(tCounts).sort((a,b)=>a[0]-b[0])};
  cache.set(key,c);return c;
 }
 function materialize(id,w){
  work.tupleMaterializations++;work.squareLookups++;const a=triples[id];
  return {tuple:a.slice(0,3).concat(w),n:a[4]+squares[w],t:a[3],tripleId:id,globalRank:id*(B+1)+w};
 }
 function select(filter,rank){
  const c=context(filter);int(rank,"rank");if(rank<0||rank>=c.count)throw new RangeError("rank outside family");
  let lo=0,hi=c.blocks.length;while(lo<hi){const m=Math.floor((lo+hi)/2),a=c.blocks[m];work.selectBlockReads++;
   if(rank>=a[3]+a[2]-a[1]+1)lo=m+1;else hi=m;}
  const a=c.blocks[lo];return {...materialize(a[0],a[1]+rank-a[3]),rank,condition:c.key};
 }
 function rank(filter,tuple){
  if(!Array.isArray(tuple)||tuple.length!==4)throw new TypeError("tuple");tuple.forEach((v,i)=>int(v,FIELDS[i]));
  const c=context(filter),id=lookup.get(tuple.slice(0,3).join(",")),w=tuple[3];
  if(id===undefined)throw new RangeError("triple outside saved family");
  let lo=0,hi=c.blocks.length;while(lo<hi){const m=Math.floor((lo+hi)/2);work.rankBlockReads++;
   if(c.blocks[m][0]<id)lo=m+1;else hi=m;}
  const a=c.blocks[lo];if(!a||a[0]!==id||w<a[1]||w>a[2])throw new RangeError("tuple outside condition");
  return {...materialize(id,w),rank:a[3]+w-a[1],condition:c.key};
 }
 function image(filter={}){
  const c=context(filter);if(images.has(c.key)){work.imageHits++;return copy(images.get(c.key));}
  work.imageBuilds++;const counts=new Map();
  for(const [id,lo,hi]of c.blocks)for(let w=lo;w<=hi;w++){
   work.imageTupleVisits++;work.squareLookups++;const n=triples[id][4]+squares[w];counts.set(n,(counts.get(n)||0)+1);}
  const r={condition:c.key,quadruples:c.count,distinctTargets:counts.size,nProfile:Array.from(counts).sort((a,b)=>a[0]-b[0])};
  images.set(c.key,r);return copy(r);
 }
 return {summary:()=>copy({summary:saved.summary,constructionWork:saved.constructionWork}),
  profiles:()=>{work.profileCellsRead+=saved.joint.length+saved.nProfile.length+saved.tProfile.length;
   return copy({joint:saved.joint,nProfile:saved.nProfile,tProfile:saved.tProfile});},
  condition:filter=>{const c=context(filter);return copy({key:c.key,ranges:c.ranges,count:c.count,blocks:c.blocks.length,nMin:c.nMin,nMax:c.nMax,tProfile:c.tProfile});},
  blocks:filter=>copy(context(filter)),
  count:filter=>({condition:context(filter).key,count:context(filter).count}),
  select,rank,image,
  fiber:(n,t)=>{int(n,"n");int(t,"t");work.fiberReads++;return {n,t,count:fiberLookup.get(n+","+t)||0};},
  page:(filter,start,limit)=>{const c=context(filter);int(start,"start");int(limit,"limit");
   if(start<0||start>c.count||limit<0||limit>1000)throw new RangeError("page");
   return {start,total:c.count,rows:Array.from({length:Math.min(limit,c.count-start)},(_,i)=>select(filter,start+i))};},
  work:()=>copy(work),caches:()=>copy({conditions:Array.from(cache.values()),images:Array.from(images.values())})};
}
module.exports={compile,createReader};
