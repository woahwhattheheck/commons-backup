"use strict";
function gcd(a,b){a=a<0n?-a:a;b=b<0n?-b:b;while(b){const t=a%b;a=b;b=t;}return a;}
function R(a,b=1n){if(!b)throw new RangeError("zero denominator");if(b<0n){a=-a;b=-b;}const g=gcd(a,b);return[a/g,b/g];}
const fmt=a=>a[1]===1n?String(a[0]):a[0]+"/"+a[1];
function parse(s){if(typeof s!=="string"||s.length>2048||! /^(0|-?[1-9][0-9]*)(\/[1-9][0-9]*)?$/.test(s))throw new TypeError("rational string");const a=s.split("/");return R(BigInt(a[0]),a[1]?BigInt(a[1]):1n);}
const add=(a,b)=>R(a[0]*b[1]+b[0]*a[1],a[1]*b[1]);
const sub=(a,b)=>R(a[0]*b[1]-b[0]*a[1],a[1]*b[1]);
const mul=(a,b)=>R(a[0]*b[0],a[1]*b[1]);
const div=(a,b)=>R(a[0]*b[1],a[1]*b[0]);
const cmp=(a,b)=>{const z=a[0]*b[1]-b[0]*a[1];return z<0n?-1:z>0n?1:0;};
const mid=(a,b)=>div(add(a,b),R(2n));
function trim(p){while(p.length>1&&p[p.length-1]===0n)p.pop();return p;}
function primitive(p){trim(p);let g=0n;for(const c of p)g=gcd(g,c);if(g===0n)return[0n];return p.map(c=>c/g);}
function derivative(p){return p.length<2?[0n]:p.slice(1).map((c,i)=>c*BigInt(i+1));}
function convolution(a,b){const c=Array(a.length+b.length-1).fill(0n);a.forEach((x,i)=>b.forEach((y,j)=>c[i+j]+=x*y));return trim(c);}
function combine(a,b,sign=1n){const c=Array(Math.max(a.length,b.length)).fill(0n);for(let i=0;i<c.length;i++)c[i]=(a[i]||0n)+sign*(b[i]||0n);return trim(c);}
function remainder(a,b,work){
 const r=a.map(x=>R(x)),degree=b.length-1;
 while(r.length>=b.length&&!(r.length===1&&r[0][0]===0n)){
  const k=r.length-b.length,f=div(r[r.length-1],R(b[degree]));work.rational_division_steps++;
  for(let i=0;i<b.length;i++)r[k+i]=sub(r[k+i],mul(f,R(b[i])));
  while(r.length>1&&r[r.length-1][0]===0n)r.pop();
 }
 let l=1n;for(const c of r)l=l/gcd(l,c[1])*c[1];return primitive(r.map(c=>-c[0]*(l/c[1])));
}
function variations(signs){let v=0;for(let i=1;i<signs.length;i++)if(signs[i]!==signs[i-1])v++;return v;}
function evaluateSign(p,x,work){let c=p[p.length-1],power=x[1];work.polynomial_evaluations++;for(let j=p.length-2;j>=0;j--){c=c*x[0]+p[j]*power;power*=x[1];work.horner_steps++;}return c<0n?-1:c>0n?1:0;}
function endpoint(chain,x,work){
 const left=[],right=[],orders=[];let fsign=null;
 for(let i=0;i<chain.length;i++){
  let p=chain[i],s=evaluateSign(p,x,work),order=0;if(i===0)fsign=s;
  while(s===0){p=derivative(p);order++;work.derivative_fallbacks++;s=evaluateSign(p,x,work);if(p.length===1&&p[0]===0n)throw new Error("zero chain member");}
  right.push(s);left.push(order%2?-s:s);orders.push(order);
 }
 return{at:fmt(x),f_sign:fsign,taylor_orders:orders,signs_left:left,signs_right:right,Vleft:variations(left),Vright:variations(right)};
}
function buildIndex(input){
 const roots=input.roots.slice(),n=roots.length,q=BigInt(input.q),precision=input.precision;
 if(n<2||n>8||roots.some((x,i)=>!Number.isSafeInteger(x)||Math.abs(x)>1000000||(i&&x<=roots[i-1])))throw new RangeError("2..8 sorted distinct bounded integer roots");
 if(typeof input.q!=="string"||! /^[1-9][0-9]*$/.test(input.q)||input.q.length>50||q<1n)throw new RangeError("positive q");
 if(!Number.isInteger(precision)||precision<8||precision>128)throw new RangeError("precision8..128");
 const work={factor_products:0,rational_division_steps:0,polynomial_evaluations:0,horner_steps:0,derivative_fallbacks:0,unique_endpoints:0,isolation_nodes:0};
 let re=[1n],im=[0n];
 for(const root of roots){const factor=[-q*BigInt(root),q],nr=combine(convolution(re,factor),im,-1n),ni=combine(convolution(im,factor),re);re=nr;im=ni;work.factor_products++;}
 const original=combine(convolution(re,re),convolution(im,im));original[0]-=q**BigInt(2*n);trim(original);
 const f=primitive(original),chain=[f,primitive(derivative(f))];
 while(chain[chain.length-1].length>1){
  const rem=remainder(chain[chain.length-2],chain[chain.length-1],work);if(rem.length===1&&rem[0]===0n)throw new RangeError("section polynomial must be squarefree");
  chain.push(rem);
 }
 const endpoints=[],cache=new Map();
 function at(x){const key=fmt(x);if(cache.has(key))return cache.get(key);const e=endpoint(chain,x,work),id=endpoints.length;endpoints.push({...e,id});cache.set(key,id);work.unique_endpoints++;return id;}
 const lo=R(BigInt(roots[0]-1)),hi=R(BigInt(roots[n-1]+1)),a=at(lo),b=at(hi);
 if(endpoints[a].f_sign!==1||endpoints[b].f_sign!==1)throw new Error("bounding sign");
 const total=endpoints[a].Vright-endpoints[b].Vleft;if(total<0||total>2*n||total%2)throw new Error("root count");
 const tree=[],isolated=[],stack=[{left:a,right:b,parent:null,depth:0}],target=R(1n,1n<<BigInt(precision));
 while(stack.length){
  if(tree.length>=10000)throw new RangeError("isolation node cap");
  const x=stack.pop(),L=endpoints[x.left],H=endpoints[x.right],l=parse(L.at),h=parse(H.at),count=L.Vright-H.Vleft,id=tree.length,node={id,...x,count};
  tree.push(node);work.isolation_nodes++;
  if(count===0){node.status="empty";continue;}
  if(count===1&&cmp(sub(h,l),target)<=0){node.status="isolated";isolated.push({kind:"interval",left:L.at,right:H.at,node:id,left_endpoint:x.left,right_endpoint:x.right});continue;}
  if(x.depth>=256)throw new RangeError("isolation depth cap");
  const center=mid(l,h),e=at(center),E=endpoints[e];node.status="split";node.midpoint=e;
  if(E.f_sign===0){if(E.Vleft-E.Vright!==1)throw new Error("simple root jump");isolated.push({kind:"point",at:E.at,left:E.at,right:E.at,endpoint:e,node:id});node.exact_midpoint_root=true;}
  stack.push({left:e,right:x.right,parent:id,depth:x.depth+1},{left:x.left,right:e,parent:id,depth:x.depth+1});
 }
 isolated.sort((a,b)=>cmp(parse(a.left),parse(b.left)));isolated.forEach((r,i)=>r.rank=i);
 if(isolated.length!==total)throw new Error("isolation coverage");
 const components=[];for(let i=0;i<total;i+=2)components.push({id:components.length,left_root:i,right_root:i+1,left_closed:true,right_closed:true});
 return{format:"polynomial-lemniscate-section-v1",input:JSON.parse(JSON.stringify(input)),scaled_real:re.map(String),scaled_imaginary:im.map(String),section_polynomial:original.map(String),primitive_section:f.map(String),sturm_chain:chain.map(p=>p.map(String)),bounds:{left:fmt(lo),right:fmt(hi),left_endpoint:a,right_endpoint:b},endpoint_certificates:endpoints,isolation_tree:tree,roots:isolated,filled_components:components,summary:{degree:n,section_degree:f.length-1,sturm_length:chain.length,real_roots:total,filled_components:components.length,precision_bits:precision,exact_point_roots:isolated.filter(r=>r.kind==="point").length},work};
}
function openIndex(s){
 if(!s||s.format!=="polynomial-lemniscate-section-v1"||s.roots.length!==s.summary.real_roots)throw new TypeError("snapshot shape");
 const chain=s.sturm_chain.map(p=>p.map(BigInt)),work={queries:0,polynomial_evaluations:0,horner_steps:0,derivative_fallbacks:0};
 const copy=x=>JSON.parse(JSON.stringify(x));
 function ep(x){return endpoint(chain,parse(x),work);}
 function idx(i,n){if(!Number.isInteger(i)||i<0||i>=n)throw new RangeError("index");return i;}
 function query(q){work.queries++;switch(q.op){
  case"summary":return copy(s.summary);
  case"root":return copy(s.roots[idx(q.rank,s.roots.length)]);
  case"rootsPage":{if(!Number.isInteger(q.start)||q.start<0||q.start>s.roots.length||!Number.isInteger(q.limit)||q.limit<0||q.limit>1000)throw new RangeError("page");return copy(s.roots.slice(q.start,q.start+q.limit));}
  case"component":return copy(s.filled_components[idx(q.id,s.filled_components.length)]);
  case"savedEndpoint":return copy(s.endpoint_certificates[idx(q.id,s.endpoint_certificates.length)]);
  case"treeNode":return copy(s.isolation_tree[idx(q.id,s.isolation_tree.length)]);
  case"polynomial":return copy({scaled_real:s.scaled_real,scaled_imaginary:s.scaled_imaginary,section:s.section_polynomial,primitive:s.primitive_section});
  case"chain":return copy(s.sturm_chain);
  case"point":{const e=ep(q.x),base=s.endpoint_certificates[s.bounds.left_endpoint];return{...e,roots_strictly_less:base.Vright-e.Vleft,on_boundary:e.f_sign===0,in_filled_section:e.f_sign<=0};}
  case"count":{const a=parse(q.left),b=parse(q.right);if(cmp(a,b)>=0)throw new RangeError("left<right");const l=endpoint(chain,a,work),r=endpoint(chain,b,work);return{left:l,right:r,open_root_count:l.Vright-r.Vleft};}
  default:throw new TypeError("query op");
 }}
 return{query,stats:()=>copy(work)};
}
module.exports={buildIndex,openIndex};
