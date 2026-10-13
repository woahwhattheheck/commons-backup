'use strict';
// Fixed explicit five-piece right-triangle substitution; exact integer arithmetic.
const SCHEMA='commons.five_piece_triangle/v1';
const T=[[0,0],[2,0],[0,1]],A=[[2,-1],[1,2]],H=[[2,1],[-1,2]];
const CHILDREN=[
 {R:[[0,-1],[-1,0]],t:[0,2],quarter:3,reflection:1},
 {R:[[1,0],[0,-1]],t:[0,1],quarter:0,reflection:1},
 {R:[[1,0],[0,-1]],t:[2,2],quarter:0,reflection:1},
 {R:[[1,0],[0,1]],t:[0,1],quarter:0,reflection:0},
 {R:[[-1,0],[0,-1]],t:[2,2],quarter:2,reflection:0}
];
const clone=x=>JSON.parse(JSON.stringify(x));
const mod4=n=>((n%4)+4)%4;
const key=o=>o.join(',');
function compose(u,v){const s=u[2]?-1:1;return [u[0]+s*v[0],mod4(u[1]+s*v[1]),u[2]^v[2]];}
function residual(prefix,target){const s=prefix[2]?-1:1;return [s*(target[0]-prefix[0]),mod4(s*(target[1]-prefix[1])),prefix[2]^target[2]];}
function int(x,lo,hi){if(!Number.isSafeInteger(x)||x<lo||x>hi)throw new RangeError('integer range');return x;}
function nat(x){if(typeof x!=='string'||!/^(0|[1-9][0-9]*)$/.test(x)||x.length>1024)throw new TypeError('nonnegative decimal string');return BigInt(x);}
function signed(x){if(typeof x!=='string'||!/^(-?[1-9][0-9]*|0)$/.test(x)||x.length>1024)throw new TypeError('signed decimal string');return BigInt(x);}
function mm(a,b){return [[a[0][0]*b[0][0]+a[0][1]*b[1][0],a[0][0]*b[0][1]+a[0][1]*b[1][1]],[a[1][0]*b[0][0]+a[1][1]*b[1][0],a[1][0]*b[0][1]+a[1][1]*b[1][1]]];}
function mv(a,x){return [a[0][0]*x[0]+a[0][1]*x[1],a[1][0]*x[0]+a[1][1]*x[1]];}
function buildIndex(input){
 const depth=int(input.depth,0,128);if(!input.parameter_source)throw new TypeError('identified parameter source');
 if(JSON.stringify(input.triangle)!==JSON.stringify(T)||JSON.stringify(input.inflation)!==JSON.stringify(A)||JSON.stringify(input.children)!==JSON.stringify(CHILDREN))throw new TypeError('fixed explicit template required');
 const base=CHILDREN.map((c,id)=>{
  const Rt=[[c.R[0][0],c.R[1][0]],[c.R[0][1],c.R[1][1]]],B=mm(H,c.R),b=mv(H,c.t),C=mm(Rt,A),d=mv(Rt,c.t).map(x=>-x);
  const gram=mm([[B[0][0],B[1][0]],[B[0][1],B[1][1]]],B),det=B[0][0]*B[1][1]-B[0][1]*B[1][0];
  if(JSON.stringify(gram)!=='[[5,0],[0,5]]'||det!==(c.reflection?-5:5))throw new Error('template similarity');
  const expanded=T.map(p=>mv(c.R,p).map((x,i)=>x+c.t[i])),vertices=T.map(p=>mv(B,p).map((x,i)=>x+b[i]));
  for(const [x,y] of vertices)if(x<0||y<0||x+2*y>10)throw new Error('template containment');
  return {id,B,b,inverse_C:C,inverse_d:d,orientation_step:[-1,c.quarter,c.reflection],expanded_vertices:expanded,vertices_numerator:vertices,denominator:'5',gram,determinant:det};
 });
 const layers=[[[0,0,0,'1']]],powers=['1'];let map=new Map([['0,0,0',1n]]);
 const work={orientation_cells:1,transition_updates:0,base_similarity_rows:5,leaf_triangles_enumerated:0};
 for(let n=1;n<=depth;n++){
  const next=new Map();for(const [k,c] of map){const o=k.split(',').map(Number);for(const b of base){const z=key(compose(o,b.orientation_step));next.set(z,(next.get(z)||0n)+c);work.transition_updates++;}}
  const rows=[...next].map(([k,c])=>[...k.split(',').map(Number),String(c)]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]||a[2]-b[2]);
  powers.push(String(BigInt(powers[n-1])*5n));if(rows.reduce((s,r)=>s+BigInt(r[3]),0n)!==BigInt(powers[n]))throw new Error('count partition');
  layers.push(rows);work.orientation_cells+=rows.length;map=next;
 }
 return {schema:SCHEMA,input:clone(input),base,powers,layers,work,ordering:'lexicographic child addresses over digits 0..4',orientation:'k*atan(1/2)+j*pi/2, with reflection parity e'};
}
function openIndex(saved){
 const r=clone(saved);if(r.schema!==SCHEMA)throw new TypeError('schema');const depth=int(r.input.depth,0,128);if(r.base.length!==5||r.layers.length!==depth+1||r.powers.length!==depth+1)throw new TypeError('shape');
 const powers=r.powers.map(nat),maps=r.layers.map((rows,n)=>{const m=new Map();for(const c of rows){if(c.length!==4)throw new TypeError('orientation row');int(c[0],-n,n);int(c[1],0,3);int(c[2],0,1);const k=key(c.slice(0,3));if(m.has(k))throw new TypeError('duplicate orientation');m.set(k,nat(c[3]));}return m;});
 const base=r.base.map(b=>({...b,B:b.B.map(row=>row.map(BigInt)),b:b.b.map(BigInt),C:b.inverse_C.map(row=>row.map(BigInt)),d:b.inverse_d.map(BigInt)}));
 const work={indexed_orientation_cells:r.layers.reduce((s,x)=>s+x.length,0),orientation_lookups:0,orientation_steps:0,affine_steps:0,point_nodes_visited:0,point_child_tests:0,orientation_recurrence_updates:0,base_template_reconstructions:0};
 function dep(n){return int(n,0,depth);}
 function address(a){if(typeof a!=='string'||!/^[0-4]*$/.test(a)||a.length>depth)throw new TypeError('address');return a;}
 function target(t){if(!Array.isArray(t)||t.length!==3)throw new TypeError('orientation');int(t[0],-depth,depth);int(t[1],0,3);int(t[2],0,1);return t;}
 function orientation(a){address(a);let o=[0,0,0];for(const c of a){o=compose(o,base[Number(c)].orientation_step);work.orientation_steps++;}return o;}
 function rankAddress(a){address(a);let v=0n;for(const c of a)v=5n*v+BigInt(c);return String(v);}
 function selectAddress(n,k){dep(n);let q=nat(k);if(q>=powers[n])throw new RangeError('rank');let a='';for(let i=0;i<n;i++){a=String(q%5n)+a;q/=5n;}return a;}
 function lookup(n,prefix,t){work.orientation_lookups++;return maps[n].get(key(residual(prefix,t)))||0n;}
 function geometry(a){
  address(a);let M=[[1n,0n],[0n,1n]],v=[0n,0n],D=1n;const trace=[];
  for(const c of a){const b=base[Number(c)],w=mv(M,b.b);v=[w[0]+5n*v[0],w[1]+5n*v[1]];M=mm(M,b.B);D*=5n;work.affine_steps++;
   trace.push({child:Number(c),matrix:M.map(row=>row.map(String)),translation:v.map(String),denominator:String(D)});}
  const vertices=[v,[v[0]+2n*M[0][0],v[1]+2n*M[1][0]],[v[0]+M[0][1],v[1]+M[1][1]]].map(p=>p.map(String));
  return {address:a,rank:rankAddress(a),depth:a.length,matrix:M.map(row=>row.map(String)),translation:v.map(String),vertices_numerator:vertices,denominator:String(D),orientation:orientation(a),area:{numerator:'1',denominator:String(D)},squared_sides:{short_numerator:'1',long_numerator:'4',hypotenuse_numerator:'5',denominator:String(D)},trace};
 }
 function selectOrientation(n,t,k){
  dep(n);target(t);let z=nat(k),o=[0,0,0],a='';const total=lookup(n,o,t);if(z>=total)throw new RangeError('orientation rank');const trace=[];
  for(let i=0;i<n;i++){let found=false;for(let c=0;c<5;c++){const next=compose(o,base[c].orientation_step),count=lookup(n-i-1,next,t);
    if(z<count){trace.push({position:i,child:c,count:String(count),remaining_rank:String(z)});a+=String(c);o=next;found=true;break;}z-=count;}
   if(!found)throw new Error('saved count inconsistency');}
  return {depth:n,target:t.slice(),rank:k,count:String(total),address:a,global_rank:rankAddress(a),trace};
 }
 function rankOrientation(a){
  address(a);const t=orientation(a);let o=[0,0,0],rank=0n;const trace=[];
  for(let i=0;i<a.length;i++){const chosen=Number(a[i]);let skipped=0n;for(let c=0;c<chosen;c++)skipped+=lookup(a.length-i-1,compose(o,base[c].orientation_step),t);rank+=skipped;trace.push({position:i,child:chosen,skipped:String(skipped)});o=compose(o,base[chosen].orientation_step);}
  return {address:a,target:t,rank:String(rank),count:String(lookup(a.length,[0,0,0],t)),global_rank:rankAddress(a),trace};
 }
 function countPrefix(n,t,prefix){dep(n);target(t);address(prefix);if(prefix.length>n)throw new RangeError('prefix length');const remaining=n-prefix.length;return {depth:n,target:t.slice(),prefix,count:String(lookup(remaining,orientation(prefix),t)),global_start:String(BigInt(rankAddress(prefix))*powers[remaining]),global_end_exclusive:String((BigInt(rankAddress(prefix))+1n)*powers[remaining])};}
 function locate(n,point,limit=20000){
  dep(n);int(limit,1,100000);const q=nat(point.den),x=signed(point.x),y=signed(point.y);if(q===0n)throw new RangeError('positive denominator');
  const inside=p=>p[0]>=0n&&p[1]>=0n&&p[0]+2n*p[1]<=2n*q;
  const stack=inside([x,y])?[{address:'',p:[x,y]}]:[],matches=[];let visited=0,tests=0;
  while(stack.length){if(visited===limit)return {depth:n,point:clone(point),complete:false,reason:'visit_cap',visited,child_tests:tests,matches,frontier:stack.map(z=>({address:z.address,local_numerators:z.p.map(String)}))};
   const z=stack.pop();visited++;work.point_nodes_visited++;
   if(z.address.length===n){matches.push({address:z.address,rank:rankAddress(z.address),local_numerators:z.p.map(String),denominator:String(q),boundary:{short_axis:z.p[0]===0n,long_axis:z.p[1]===0n,hypotenuse:z.p[0]+2n*z.p[1]===2n*q}});continue;}
   for(let c=4;c>=0;c--){const b=base[c],v=mv(b.C,z.p).map((x,i)=>x+b.d[i]*q);tests++;work.point_child_tests++;if(inside(v))stack.push({address:z.address+String(c),p:v});}
  }
  return {depth:n,point:clone(point),complete:true,visited,child_tests:tests,matches};
 }
 return {summary:()=>({depth,triangles:r.powers[depth],orientation_classes:r.layers[depth].length,work:clone(r.work)}),
  histogram:n=>{dep(n);return {depth:n,total:r.powers[n],rows:clone(r.layers[n])};},
  selectAddress,rankAddress,orientation,geometry,selectOrientation,rankOrientation,countPrefix,locate,
  work:()=>clone(work),snapshot:()=>clone(r)};
}
module.exports={SCHEMA,buildIndex,openIndex};
