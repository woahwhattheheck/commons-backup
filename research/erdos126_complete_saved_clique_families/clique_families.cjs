'use strict';
const copy=x=>JSON.parse(JSON.stringify(x));
const hex=x=>x.toString(16);
const bits=x=>{const a=[];for(let i=0;x;i++,x>>=1n)if(x&1n)a.push(i);return a;};
const parse=(s,n)=>{if(typeof s!=='string'||!/^(0|[1-9a-f][0-9a-f]*)$/.test(s))throw new TypeError('canonical hexadecimal mask required');const x=BigInt('0x'+s);if(x>=(1n<<BigInt(n)))throw new RangeError('mask outside universe');return x;};
const plus=(a,b,work)=>{const z=Array(Math.max(a.length,b.length+1)).fill(0n);for(let k=0;k<a.length;k++){z[k]+=a[k];work.coefficientAdds++;}for(let k=0;k<b.length;k++){z[k+1]+=b[k];work.coefficientAdds++;}while(z.length>1&&z.at(-1)===0n)z.pop();return z;};
function compile(input){
 const n=input.vertices.length;if(n<1||n>128||input.vertices.some((v,i)=>v!==i))throw new TypeError('vertices must be 0 through n-1, n<=128');
 const work={adjacencyCopies:0,statesBuilt:0,memoHits:0,candidateIntersections:0,coefficientAdds:0,newFactorDivisions:0,newPairRows:0,newGraphViews:0,oldSearchNodes:0,oldColorBounds:0};
 const views=[];
 for(const g of input.graphs){
  if(g.adjacency_masks_hex.length!==n)throw new TypeError('adjacency length');
  const adjacency=g.adjacency_masks_hex.map(s=>{work.adjacencyCopies++;return parse(s,n);});
  const nodes=[{mask:'0',vertex:null,exclude:null,include:null,coefficients:['1']}],memo=new Map([['0',0]]),polys=[[1n]];
  function visit(c){
   const key=hex(c);if(memo.has(key)){work.memoHits++;return memo.get(key);}
   const low=c&-c,v=low.toString(2).length-1,rest=c^low;
   const ex=visit(rest);work.candidateIntersections++;const inc=visit(rest&adjacency[v]);
   const poly=plus(polys[ex],polys[inc],work),id=nodes.length;
   nodes.push({mask:key,vertex:v,exclude:ex,include:inc,coefficients:poly.map(String)});polys.push(poly);memo.set(key,id);work.statesBuilt++;return id;
  }
  const root=visit((1n<<BigInt(n))-1n);
  views.push({key:g.key,allowed_primes:g.allowed_primes,edge_count:g.edge_count,inherited_maximum:g.inherited_maximum,root,nodes,coefficients:nodes[root].coefficients,total:nodes[root].coefficients.reduce((s,x)=>s+BigInt(x),0n).toString()});
 }
 return {format:'saved-smooth-sum-clique-families/v1',input:copy(input),order:'membership vector at vertices 0..n-1, absent before present',views,work};
}
function createReader(certificate){
 const n=certificate.input.vertices.length,all=(1n<<BigInt(n))-1n;
 const views=new Map(certificate.views.map(v=>[v.key,{saved:v,masks:v.nodes.map(x=>BigInt('0x'+x.mask)),base:v.nodes.map(x=>x.coefficients.map(BigInt)),pools:new Map()}]));
 const cache=new Map(),work={conditionsBuilt:0,conditionHits:0,filteredPoolsBuilt:0,basePolynomialReferences:0,filteredNodeVisits:0,coefficientAdds:0,countCoefficientReads:0,selectionSteps:0,rankSteps:0,materializedSets:0,marginalNodeVisits:0,marginalProducts:0,newFamilyStates:0,newFactorDivisions:0,newAdjacency:0,oldSearchNodes:0};
 const listMask=(a=[])=>{if(!Array.isArray(a))throw new TypeError('vertex list');let m=0n;for(const v of a){if(!Number.isInteger(v)||v<0||v>=n)throw new RangeError('vertex outside universe');const b=1n<<BigInt(v);if(m&b)throw new TypeError('duplicate vertex');m|=b;}return m;};
 function normalized(q){
  const v=views.get(q.graph);if(!v)throw new RangeError('unknown saved graph');
  const r=listMask(q.require),f=listMask(q.forbid);
  let lo=q.min_size===undefined?0:q.min_size,hi=q.max_size===undefined?n:q.max_size;
  if(!Number.isSafeInteger(lo)||!Number.isSafeInteger(hi))throw new TypeError('integer cardinality bounds');
  return {v,r,f,lo:Math.max(0,lo),hi:Math.min(n,hi)};
 }
 function pool(v,r,f){
  const k=hex(r)+'/'+hex(f);if(v.pools.has(k))return v.pools.get(k);
  let p,lo,hi;
  if(r===0n&&f===0n){p=v.base;lo=v.saved.nodes.map(()=>true);hi=lo.slice();work.basePolynomialReferences+=p.length;}
  else {
   work.filteredPoolsBuilt++;p=[[r&f?0n:1n]];lo=[false];hi=[false];
   for(let id=1;id<v.saved.nodes.length;id++){
    work.filteredNodeVisits++;const nd=v.saved.nodes[id],b=1n<<BigInt(nd.vertex),rest=v.masks[id]^b;
    const l=!(r&f)&&!(r&b),h=!(r&f)&&!(f&b)&&!(r&rest&~v.masks[nd.include]);
    lo[id]=Boolean(l);hi[id]=Boolean(h);p[id]=plus(l?p[nd.exclude]:[0n],h?p[nd.include]:[0n],work);
   }
  }
  const z={key:k,required_mask:hex(r),forbidden_mask:hex(f),polys:p,lo,hi,base:r===0n&&f===0n};v.pools.set(k,z);return z;
 }
 function intervalSum(poly,lo,hi){let z=0n;for(let j=Math.max(0,lo);j<=Math.min(hi,poly.length-1);j++){z+=poly[j];work.countCoefficientReads++;}return z;}
 function condition(q){
  const z=normalized(q),key=[q.graph,hex(z.r),hex(z.f),z.lo,z.hi].join('|');
  if(cache.has(key)){work.conditionHits++;return cache.get(key);}
  const p=pool(z.v,z.r,z.f),coeff=p.polys[z.v.saved.root],total=z.lo<=z.hi?intervalSum(coeff,z.lo,z.hi):0n;
  const o={key,graph:q.graph,require:bits(z.r),forbid:bits(z.f),min_size:z.lo,max_size:z.hi,coefficients:coeff.map(String),count:String(total)};
  const c={...z,p,public:o,total};cache.set(key,c);work.conditionsBuilt++;return c;
 }
 const branchCount=(c,id,prefix)=>intervalSum(c.p.polys[id],c.lo-prefix,c.hi-prefix);
 function materialize(mask){work.materializedSets++;return {mask:hex(mask),vertices:bits(mask),size:bits(mask).length};}
 function select(q,rank){
  if(typeof rank!=='string'||!/^(0|[1-9][0-9]*)$/.test(rank)||rank.length>64)throw new TypeError('nonnegative decimal rank string');
  const c=condition(q);let k=BigInt(rank);if(k>=c.total)return {status:'OUT_OF_RANGE',count:String(c.total),rank};
  let id=c.v.saved.root,prefix=0,m=0n;
  while(id){work.selectionSteps++;const nd=c.v.saved.nodes[id],a=c.p.lo[id]?branchCount(c,nd.exclude,prefix):0n;
   if(k<a)id=nd.exclude;else{k-=a;if(!c.p.hi[id])throw new Error('invalid retained branch count');m|=1n<<BigInt(nd.vertex);prefix++;id=nd.include;}
  }
  return {status:'OK',rank,count:String(c.total),...materialize(m)};
 }
 function rank(q,vertices){
  const target=listMask(vertices),c=condition(q);if((target&c.r)!==c.r||(target&c.f)||vertices.length<c.lo||vertices.length>c.hi||c.total===0n)return {status:'NOT_IN_CONDITION'};
  let id=c.v.saved.root,left=target,prefix=0,k=0n;
  while(id){work.rankSteps++;const nd=c.v.saved.nodes[id],b=1n<<BigInt(nd.vertex);
   if(left&b){if(!c.p.hi[id])return {status:'NOT_IN_CONDITION'};if(c.p.lo[id])k+=branchCount(c,nd.exclude,prefix);left^=b;if(left&~c.v.masks[nd.include])return {status:'NOT_IN_FAMILY'};prefix++;id=nd.include;}
   else{if(!c.p.lo[id])return {status:'NOT_IN_CONDITION'};id=nd.exclude;}
  }
  if(left)return {status:'NOT_IN_FAMILY'};return {status:'OK',rank:String(k),count:String(c.total),mask:hex(target)};
 }
 function page(q,offset,limit){
  if(typeof offset!=='string'||!/^(0|[1-9][0-9]*)$/.test(offset)||offset.length>64||!Number.isInteger(limit)||limit<1||limit>256)throw new TypeError('page offset/limit');
  const c=condition(q),o=BigInt(offset);if(o>c.total)return {status:'OUT_OF_RANGE',count:String(c.total),offset};
  const items=[];for(let j=o;j<c.total&&items.length<limit;j++)items.push(select(q,String(j)));
  return {status:'OK',count:String(c.total),offset,items,next_offset:o+BigInt(items.length)<c.total?String(o+BigInt(items.length)):null};
 }
 function marginals(q){
  const c=condition(q),v=c.v,root=v.saved.root,forward=Array(v.saved.nodes.length).fill(null),m=Array(n).fill(0n);forward[root]=[1n];
  const add=(id,poly,shift)=>{if(!forward[id])forward[id]=[];for(let k=0;k<poly.length;k++)forward[id][k+shift]=(forward[id][k+shift]||0n)+(poly[k]||0n);};
  if(c.total>0n)for(let id=root;id>0;id--){
   const a=forward[id];if(!a)continue;work.marginalNodeVisits++;const nd=v.saved.nodes[id];
   if(c.p.lo[id])add(nd.exclude,a,0);
   if(c.p.hi[id]){
    const b=c.p.polys[nd.include];for(let i=0;i<a.length;i++)if(a[i])for(let j=0;j<b.length;j++)if(i+j+1>=c.lo&&i+j+1<=c.hi){m[nd.vertex]+=a[i]*b[j];work.marginalProducts++;}
    add(nd.include,a,1);
   }
  }
  return {count:String(c.total),vertices:m.map((count,vertex)=>({vertex,count:String(count)}))};
 }
 return Object.freeze({
  summary:()=>({order:certificate.order,views:certificate.views.map(v=>({graph:v.key,coefficients:v.coefficients,total:v.total,inherited_maximum:v.inherited_maximum,nodes:v.nodes.length}))}),
  condition:q=>copy(condition(q).public),select,rank,page,marginals,
  snapshot:()=>({format:'smooth-sum-family-reader/v1',conditions:Array.from(cache.values(),c=>c.public),pools:Array.from(views.values()).flatMap(v=>Array.from(v.pools.values(),p=>({graph:v.saved.key,key:p.key,base:p.base,required_mask:p.required_mask,forbidden_mask:p.forbidden_mask,polynomials:p.base?null:p.polys.map(a=>a.map(String)),exclude_allowed:p.base?null:p.lo,include_allowed:p.base?null:p.hi}))),work:copy(work)}),
  work:()=>copy(work)
 });
}
module.exports={compile,createReader};
