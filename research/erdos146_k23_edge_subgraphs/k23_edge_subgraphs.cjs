'use strict';
// Exact fixed-host K_{2,3}-free edge-subgraph compiler and saved reader.
const SCHEMA = 'erdos146-k23-certificate-v1';
function integer(x, lo, hi, name) {
  if (!Number.isSafeInteger(x) || x < lo || x > hi) throw new RangeError(name);
  return x;
}
function compile(input) {
  if (!input || input.vertices !== 6 || !Array.isArray(input.edges) || input.edges.length !== 15 ||
      JSON.stringify(input.parts) !== '[2,3]') throw new TypeError('six vertices, fifteen edges, parts [2,3] required');
  const edges = input.edges.map(e => {
    if (!Array.isArray(e) || e.length !== 2) throw new TypeError('edge pair');
    const u=integer(e[0],0,5,'endpoint'), v=integer(e[1],0,5,'endpoint');
    if (u>=v) throw new RangeError('increasing endpoints');
    return [u,v];
  });
  const lookup = new Map(edges.map((e,i)=>[e.join(','),i]));
  if (lookup.size !== 15) throw new TypeError('duplicate edge');
  const patterns=[], work={pattern_masks:0,pattern_edge_lookups:0,classifications:0,pattern_tests:0,
    size_recurrences:0,coefficient_cells:32768*16,zeta_additions:0,profile_rows:0,
    old_graph_property_calls:0,subgraph_family_enumeration:0};
  for(let u=0;u<6;u++) for(let v=u+1;v<6;v++) {
    const rest=[0,1,2,3,4,5].filter(x=>x!==u&&x!==v);
    for(let omitted=0;omitted<4;omitted++) {
      const right=rest.filter((_,i)=>i!==omitted); let mask=0;
      for(const a of [u,v]) for(const b of right) {
        const key=a<b ? a+','+b : b+','+a;
        mask |= 1 << lookup.get(key); work.pattern_edge_lookups++;
      }
      patterns.push({left:[u,v],right,mask}); work.pattern_masks++;
    }
  }
  const sizes=new Uint8Array(32768), first=new Int16Array(32768); first.fill(-1);
  const co=Array.from({length:32768},()=>new Uint32Array(16));
  const free=[], histogram=Array(16).fill(0);
  for(let h=0;h<32768;h++) {
    if(h){ sizes[h]=sizes[h&(h-1)]+1; work.size_recurrences++; }
    for(let j=0;j<patterns.length;j++) {
      work.pattern_tests++;
      if((h&patterns[j].mask)===patterns[j].mask){first[h]=j;break;}
    }
    work.classifications++;
    if(first[h]===-1){free.push(h);histogram[sizes[h]]++;co[h][sizes[h]]=1;}
  }
  // Ranked subset zeta transform: co[H][k] counts free T subset H of size k.
  for(let bit=1;bit<32768;bit<<=1) for(let h=0;h<32768;h++) if(h&bit) {
    const a=co[h], b=co[h^bit];
    for(let k=0;k<16;k++){a[k]+=b[k];work.zeta_additions++;}
  }
  const rows=[], profileMap=new Map();
  for(let h=0;h<32768;h++){
    let maximum=15;while(maximum>0&&co[h][maximum]===0)maximum--;
    rows.push([sizes[h],first[h],maximum,Array.from(co[h])]);
    const key=sizes[h]+':'+maximum;
    if(!profileMap.has(key))profileMap.set(key,[]);
    profileMap.get(key).push(h);work.profile_rows++;
  }
  const profiles=Array.from(profileMap,([key,hosts])=>({key,hosts})).sort((a,b)=>{
    const x=a.key.split(':').map(Number),y=b.key.split(':').map(Number);
    return x[0]-y[0]||x[1]-y[1];
  });
  return {schema:SCHEMA,input,edges,patterns,rows,free_masks:free,profiles,
    summary:{vertices:6,edge_labels:15,host_graphs:32768,forbidden_copies:patterns.length,
      free_graphs:free.length,free_by_size:histogram,maximum_free_edges:rows[32767][2],
      maximum_free_graphs:co[32767][rows[32767][2]],profile_buckets:profiles.length},
    work};
}
function openIndex(data) {
  if(!data||data.schema!==SCHEMA||!Array.isArray(data.rows)||data.rows.length!==32768||
     !Array.isArray(data.free_masks)||!Array.isArray(data.edges)||data.edges.length!==15)
    throw new TypeError('saved certificate shape');
  let previous=-1;
  for(const m of data.free_masks) {
    integer(m,0,32767,'free mask');
    if(m<=previous)throw new TypeError('free masks must increase'); previous=m;
  }
  for(const row of data.rows) if(!Array.isArray(row)||row.length!==4||
    !Array.isArray(row[3])||row[3].length!==16)throw new TypeError('saved row shape');
  const conditions=new Map(), minimals=new Map();
  const work={structural_rows_read:32768,saved_row_lookups:0,saved_free_scans:0,
    conditional_coefficient_additions:0,extension_flag_lookups:0,rank_comparisons:0,
    edge_label_lookups:0,selected_records:0,new_pattern_tests:0,new_zeta_additions:0};
  function mask(x){return integer(x,0,32767,'edge mask');}
  function row(h){work.saved_row_lookups++;return data.rows[mask(h)];}
  function decode(h){
    const list=[]; for(let i=0;i<15;i++){work.edge_label_lookups++;if(h&(1<<i))list.push({id:i,vertices:data.edges[i].slice()});}
    return list;
  }
  function condition(filter={}) {
    const host=mask(filter.host===undefined?32767:filter.host);
    const include=mask(filter.include===undefined?0:filter.include);
    const exclude=mask(filter.exclude===undefined?0:filter.exclude);
    const size=filter.size===undefined||filter.size===null ? null : integer(filter.size,0,15,'size');
    if((include&host)!==include||(exclude&host)!==exclude||(include&exclude)!==0)
      throw new RangeError('conditions must be disjoint subsets of host');
    const f={host,include,exclude,size}, key=JSON.stringify(f);
    if(!conditions.has(key)){
      const masks=[],coefficients=Array(16).fill(0);
      for(const t of data.free_masks){
        work.saved_free_scans++;
        if((t&host)!==t||(t&include)!==include||(t&exclude)!==0)continue;
        const k=row(t)[0];if(size!==null&&k!==size)continue;
        masks.push(t);coefficients[k]++;work.conditional_coefficient_additions++;
      }
      conditions.set(key,{key,filter:f,masks,coefficients});
    }
    const c=conditions.get(key);
    return {key,filter:c.filter,count:c.masks.length,coefficients:c.coefficients.slice()};
  }
  function get(key){if(!conditions.has(key))throw new RangeError('unknown condition');return conditions.get(key);}
  function select(key,rank){
    const c=get(key);integer(rank,0,c.masks.length-1,'rank');
    const h=c.masks[rank];work.selected_records++;
    return {rank,mask:h,size:row(h)[0],edges:decode(h)};
  }
  function rank(key,h){
    mask(h);const a=get(key).masks;let lo=0,hi=a.length;
    while(lo<hi){const mid=(lo+hi)>>1;work.rank_comparisons++;if(a[mid]<h)lo=mid+1;else hi=mid;}
    return lo<a.length&&a[lo]===h?lo:null;
  }
  function minimum(host){
    const h=mask(host),r=row(h);return {host:h,host_edges:r[0],minimum_deletions:r[0]-r[2],
      maximum_kept:r[2],optimal_count:r[3][r[2]],coefficients:r[3].slice()};
  }
  function optimal(host){const r=minimum(host);return condition({host:r.host,size:r.maximum_kept});}
  function deletion(host,rankValue){
    const h=mask(host),c=optimal(h),s=select(c.key,rankValue),removed=h^s.mask;
    return {rank:rankValue,host:h,kept:s.mask,removed,kept_edges:s.edges,
      removed_edges:decode(removed),minimum:minimum(h).minimum_deletions};
  }
  function deletionRank(host,removed){
    const h=mask(host),d=mask(removed);if((d&h)!==d)throw new RangeError('deletions outside host');
    return rank(optimal(h).key,h^d);
  }
  function minimal(host){
    const h=mask(host);
    if(!minimals.has(h)){
      const kept=[],by_deleted=Array(16).fill(0),hostSize=row(h)[0];
      for(const t of data.free_masks){
        work.saved_free_scans++;if((t&h)!==t)continue;
        let remaining=h^t, maximal=true;
        while(remaining){const bit=remaining&-remaining;remaining^=bit;work.extension_flag_lookups++;
          if(row(t|bit)[1]===-1){maximal=false;break;}}
        if(maximal){kept.push(t);by_deleted[hostSize-row(t)[0]]++;}
      }
      minimals.set(h,{host:h,kept,by_deleted});
    }
    const x=minimals.get(h);return {host:h,count:x.kept.length,by_deleted:x.by_deleted.slice()};
  }
  function minimalSelect(host,rankValue){
    const h=mask(host);minimal(h);const x=minimals.get(h);
    integer(rankValue,0,x.kept.length-1,'rank');
    const t=x.kept[rankValue];work.selected_records++;
    return {rank:rankValue,host:h,kept:t,removed:h^t,removed_edges:decode(h^t)};
  }
  function witness(host){
    const h=mask(host),r=row(h);
    return {host:h,free:r[1]===-1,first_pattern:r[1]===-1?null:JSON.parse(JSON.stringify(data.patterns[r[1]]))};
  }
  function profile(size,maximum){
    integer(size,0,15,'host size');integer(maximum,0,15,'maximum kept');
    const key=size+':'+maximum,p=data.profiles.find(x=>x.key===key);
    return {key,count:p?p.hosts.length:0};
  }
  function hostSelect(size,maximum,rankValue){
    const p=profile(size,maximum),x=data.profiles.find(x=>x.key===p.key);
    integer(rankValue,0,p.count-1,'rank');return minimum(x.hosts[rankValue]);
  }
  return {summary:()=>JSON.parse(JSON.stringify(data.summary)),minimum,condition,select,rank,optimal,
    deletion,deletionRank,minimal,minimalSelect,witness,profile,hostSelect,
    patterns:()=>JSON.parse(JSON.stringify(data.patterns)),
    page:(key,start,limit)=>{integer(limit,0,1000,'limit');const c=get(key);
      integer(start,0,c.masks.length,'start');const out=[];
      for(let i=start;i<Math.min(start+limit,c.masks.length);i++)out.push(select(key,i));return out;},
    exportCaches:()=>({conditions:Array.from(conditions.values()),minimal_families:Array.from(minimals.values())}),
    work:()=>({...work})};
}
module.exports={compile,openIndex};
