'use strict';
// Lossless structural decoder. No determinant or prefix-family computation.
function unpack(manifest,readShard) {
 if(manifest.schema!=='integer-hankel-prefix-manifest-v1'||typeof readShard!=='function')throw new TypeError('Manifest/reader');
 function collect(descriptors){const rows=[];for(const s of descriptors){if(s.start!==rows.length)throw new Error('Shard order');const part=readShard(s.path);if(!Array.isArray(part)||part.length!==s.count)throw new Error('Shard count');rows.push(...part);}return rows;}
 const encodedNodes=collect(manifest.node_shards),encodedDeterminants=collect(manifest.determinant_shards);
 const nodes=encodedNodes.map(row=>({code:row[0],branches:row[2].map((b,symbol)=>({symbol,target:b[0],checked:b[1],zero:b[2]===null?null:{record:b[2][0],order:b[2][1],shift:b[2][2]}})),completions:row[1]}));
 const determinants=encodedDeterminants.map(row=>({code:row[0],order:row[1],value:row[2],parents:row[3]}));
 return{...manifest.snapshot,nodes,determinants};
}
module.exports={unpack};
