'use strict';
const SCHEMA='erdos593-weak-color-partitions-v1';
function integer(x,a,b,name){if(!Number.isSafeInteger(x)||x<a||x>b)throw new RangeError(name);return x;}
function natural(x,name){if(typeof x==='number'&&!Number.isSafeInteger(x))throw new RangeError(name+' requires a safe integer or decimal string');let v;try{v=BigInt(x);}catch{throw new TypeError(name);}if(v<0n)throw new RangeError(name);return v;}
function compile(input){
  const n=integer(input.vertices,1,8,'vertices'),edges=input.edges;
  if(!Array.isArray(edges)||edges.length>16)throw new RangeError('at most sixteen edges');
  const seen=new Set();
  for(const e of edges){if(!Array.isArray(e)||e.length!==3)throw new TypeError('three-uniform edge');
    e.forEach(v=>integer(v,0,n-1,'vertex'));if(!(e[0]<e[1]&&e[1]<e[2]))throw new RangeError('increasing triple');
    const k=e.join(',');if(seen.has(k))throw new TypeError('duplicate edge');seen.add(k);}
  const m=edges.length,total=1<<m,full=total-1,partitions=[];
  const coefficients=Array.from({length:total},()=>Array(n+1).fill(0));
  const work={partition_leaves:0,edge_monochromatic_checks:0,initial_coefficient_additions:0,
    coefficient_cells:total*(n+1),superset_zeta_additions:0,size_recurrences:0,old_edge_color_calls:0};
  const a=Array(n).fill(0);
  function visit(pos,maximum){
    if(pos===n){
      const blocks=Array.from({length:maximum+1},()=>[]);a.forEach((v,i)=>blocks[v].push(i));
      let bad=0;for(let i=0;i<m;i++){const e=edges[i];work.edge_monochromatic_checks++;
        if(a[e[0]]===a[e[1]]&&a[e[1]]===a[e[2]])bad|=1<<i;}
      const allowed=full^bad,id=partitions.length,k=blocks.length;
      partitions.push({id,rgs:a.slice(),blocks,k,bad,allowed});coefficients[allowed][k]++;
      work.partition_leaves++;work.initial_coefficient_additions++;return;
    }
    for(let c=0;c<=maximum+1;c++){a[pos]=c;visit(pos+1,Math.max(maximum,c));}
  }
  visit(1,0);
  for(let bit=1;bit<total;bit<<=1)for(let s=0;s<total;s++)if(!(s&bit))
    for(let k=0;k<=n;k++){coefficients[s][k]+=coefficients[s|bit][k];work.superset_zeta_additions++;}
  const sizes=Array(total).fill(0),rows=[],profiles=new Map();
  for(let s=0;s<total;s++){
    if(s){sizes[s]=sizes[s&(s-1)]+1;work.size_recurrences++;}
    let chi=1;while(chi<=n&&coefficients[s][chi]===0)chi++;
    const two=2*((coefficients[s][1]||0)+(coefficients[s][2]||0));
    rows.push({mask:s,size:sizes[s],chromatic:chi,two_colorings:two,coefficients:coefficients[s]});
    const key=sizes[s]+':'+chi;if(!profiles.has(key))profiles.set(key,[]);profiles.get(key).push(s);
  }
  return {schema:SCHEMA,input,partitions,rows,profiles:Array.from(profiles,([key,masks])=>({key,masks})),
    summary:{vertices:n,edge_labels:m,subhosts:total,unrestricted_vertex_partitions:partitions.length,
      full_host:rows[full],property_b_subhosts:rows.filter(r=>r.chromatic<=2).length},work};
}
function openIndex(data){
  if(!data||data.schema!==SCHEMA||!Array.isArray(data.rows)||!Array.isArray(data.partitions))
    throw new TypeError('saved index');
  const n=data.input.vertices,m=data.input.edges.length,full=(1<<m)-1;
  if(data.rows.length!==full+1)throw new TypeError('row count');
  const byRgs=new Map(data.partitions.map(p=>[p.rgs.join(','),p.id]));
  const conditions=new Map(),subhosts=new Map(),falling=new Map();
  const work={structural_rows_read:data.rows.length,partition_scans:0,pair_constraint_checks:0,
    saved_row_lookups:0,subhost_scans:0,falling_multiplications:0,palette_products:0,
    palette_additions:0,rank_comparisons:0,injection_steps:0,selected_records:0,
    new_partition_generation:0,new_monochromatic_checks:0,new_zeta_additions:0};
  function mask(x){return integer(x,0,full,'edge mask');}
  function row(s){work.saved_row_lookups++;return data.rows[mask(s)];}
  function falls(q){
    const Q=natural(q,'palette'),key=Q.toString();
    if(!falling.has(key)){const a=[1n];for(let k=1;k<=n;k++){a.push(Q<BigInt(k)?0n:a[k-1]*(Q-BigInt(k-1)));work.falling_multiplications++;}
      falling.set(key,a);}
    return {Q,a:falling.get(key)};
  }
  function count(available,q){
    const r=row(available),f=falls(q);let total=0n;
    for(let k=1;k<=n;k++){total+=BigInt(r.coefficients[k])*f.a[k];work.palette_products++;work.palette_additions++;}
    return {available:r.mask,palette:f.Q.toString(),count:total.toString(),coefficients:r.coefficients.slice()};
  }
  function pairs(value){if(value===undefined)return [];if(!Array.isArray(value))throw new TypeError('pairs');
    return value.map(e=>{if(!Array.isArray(e)||e.length!==2)throw new TypeError('pair');
      return [integer(e[0],0,n-1,'vertex'),integer(e[1],0,n-1,'vertex')];});}
  function condition(filter={}){
    const f={available:mask(filter.available===undefined?full:filter.available),
      blocks:filter.blocks===undefined||filter.blocks===null?null:integer(filter.blocks,1,n,'blocks'),
      together:pairs(filter.together),apart:pairs(filter.apart)};
    const key=JSON.stringify(f);
    if(!conditions.has(key)){const ids=[],by_blocks=Array.from({length:n+1},()=>[]);
      for(const p of data.partitions){work.partition_scans++;if((p.bad&f.available)!==0||(f.blocks!==null&&p.k!==f.blocks))continue;
        let ok=true;for(const [u,v] of f.together){work.pair_constraint_checks++;if(p.rgs[u]!==p.rgs[v]){ok=false;break;}}
        if(ok)for(const [u,v] of f.apart){work.pair_constraint_checks++;if(p.rgs[u]===p.rgs[v]){ok=false;break;}}
        if(ok){ids.push(p.id);by_blocks[p.k].push(p.id);}}
      conditions.set(key,{key,filter:f,ids,by_blocks});}
    const c=conditions.get(key);return {key,filter:c.filter,count:c.ids.length,by_blocks:c.by_blocks.map(x=>x.length)};
  }
  function cached(key){if(!conditions.has(key))throw new RangeError('unknown condition');return conditions.get(key);}
  function partitionSelect(key,rank){const c=cached(key);integer(rank,0,c.ids.length-1,'rank');work.selected_records++;
    return {rank,...JSON.parse(JSON.stringify(data.partitions[c.ids[rank]]))};}
  function search(a,x){let lo=0,hi=a.length;while(lo<hi){let mid=(lo+hi)>>1;work.rank_comparisons++;
    if(a[mid]<x)lo=mid+1;else hi=mid;}return lo<a.length&&a[lo]===x?lo:null;}
  function partitionRank(key,rgs){if(!Array.isArray(rgs)||rgs.length!==n)throw new TypeError('rgs');
    rgs.forEach(x=>integer(x,0,n-1,'rgs entry'));const id=byRgs.get(rgs.join(','));return id===undefined?null:search(cached(key).ids,id);}
  function conditionedCount(key,q){const c=cached(key),f=falls(q);let total=0n;
    for(let k=1;k<=n;k++){total+=BigInt(c.by_blocks[k].length)*f.a[k];work.palette_products++;work.palette_additions++;}
    return {key,palette:f.Q.toString(),count:total.toString()};}
  function injectionSelect(Q,k,rank){
    const used=[],labels=[];
    for(let i=0;i<k;i++){let block=1n;for(let j=i+1;j<k;j++){block*=Q-BigInt(j);work.falling_multiplications++;}
      const digit=rank/block;rank%=block;let label=digit;
      for(const x of used)if(x<=label)label++;
      labels.push(label);used.push(label);used.sort((a,b)=>a<b?-1:a>b?1:0);work.injection_steps++;}
    return labels;
  }
  function injectionRank(Q,labels){
    let rank=0n;const used=[];
    for(let i=0;i<labels.length;i++){const label=labels[i];let digit=label;
      for(const x of used)if(x<label)digit--;
      let block=1n;for(let j=i+1;j<labels.length;j++){block*=Q-BigInt(j);work.falling_multiplications++;}
      rank+=digit*block;used.push(label);work.injection_steps++;}
    return rank;
  }
  function coloringSelect(key,q,rankValue){
    const c=cached(key),f=falls(q),rank=natural(rankValue,'rank');let remaining=rank;
    for(let k=1;k<=n;k++){
      const size=BigInt(c.by_blocks[k].length)*f.a[k];work.palette_products++;
      if(remaining>=size){remaining-=size;continue;}
      const index=Number(remaining/f.a[k]),p=data.partitions[c.by_blocks[k][index]];
      const labels=injectionSelect(f.Q,k,remaining%f.a[k]);work.selected_records++;
      return {key,palette:f.Q.toString(),rank:rank.toString(),partition_id:p.id,
        block_labels:labels.map(String),colors:p.rgs.map(i=>labels[i].toString())};
    }
    throw new RangeError('rank');
  }
  function coloringRank(key,q,colors){
    const c=cached(key),f=falls(q);
    if(!Array.isArray(colors)||colors.length!==n)throw new TypeError('colors');
    const labels=[],seen=new Map(),rgs=[];
    for(const x of colors){const v=natural(x,'color');if(v>=f.Q)throw new RangeError('color outside palette');
      const s=v.toString();if(!seen.has(s)){seen.set(s,labels.length);labels.push(v);}rgs.push(seen.get(s));}
    const id=byRgs.get(rgs.join(',')),k=labels.length;if(id===undefined)return null;
    const pi=search(c.by_blocks[k],id);if(pi===null)return null;
    let rank=0n;for(let j=1;j<k;j++){rank+=BigInt(c.by_blocks[j].length)*f.a[j];work.palette_products++;work.palette_additions++;}
    rank+=BigInt(pi)*f.a[k]+injectionRank(f.Q,labels);work.palette_products++;work.palette_additions+=2;
    return rank.toString();
  }
  function subhostCondition(filter={}){
    const f={available:mask(filter.available===undefined?full:filter.available),
      include:mask(filter.include===undefined?0:filter.include),exclude:mask(filter.exclude===undefined?0:filter.exclude),
      size:filter.size===undefined||filter.size===null?null:integer(filter.size,0,m,'size'),
      max_chromatic:integer(filter.max_chromatic===undefined?n:filter.max_chromatic,0,n,'chromatic bound')};
    if((f.include&f.available)!==f.include||(f.exclude&f.available)!==f.exclude||(f.include&f.exclude))
      throw new RangeError('edge restrictions');
    const key=JSON.stringify(f);if(!subhosts.has(key)){const masks=[];
      for(const r of data.rows){work.subhost_scans++;if((r.mask&f.available)!==r.mask||
        (r.mask&f.include)!==f.include||(r.mask&f.exclude)||r.chromatic>f.max_chromatic||
        (f.size!==null&&r.size!==f.size))continue;masks.push(r.mask);}
      subhosts.set(key,{key,filter:f,masks});}
    const c=subhosts.get(key);return {key,filter:f,count:c.masks.length};
  }
  function subhostSelect(key,rank){const c=subhosts.get(key);if(!c)throw new RangeError('condition');
    integer(rank,0,c.masks.length-1,'rank');work.selected_records++;return JSON.parse(JSON.stringify(row(c.masks[rank])));}
  function subhostRank(key,s){mask(s);const c=subhosts.get(key);if(!c)throw new RangeError('condition');return search(c.masks,s);}
  return {summary:()=>JSON.parse(JSON.stringify(data.summary)),row:s=>JSON.parse(JSON.stringify(row(s))),
    count,condition,partitionSelect,partitionRank,conditionedCount,coloringSelect,coloringRank,
    subhostCondition,subhostSelect,subhostRank,
    exportCaches:()=>({conditions:Array.from(conditions.values()),subhosts:Array.from(subhosts.values()),
      falling:Array.from(falling,([q,values])=>({q,values:values.map(String)}))}),
    work:()=>({...work})};
}
module.exports={compile,openIndex};
