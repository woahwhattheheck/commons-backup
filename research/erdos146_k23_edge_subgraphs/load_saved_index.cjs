'use strict';
function assemble(manifest, shards) {
  if(manifest.schema!=='erdos146-k23-manifest-v1'||shards.length!==4)throw new TypeError('manifest/shards');
  const rows=shards.flat(),m=manifest.metadata;
  if(rows.length!==32768)throw new RangeError('row count');
  return {schema:m.schema,input:m.input,edges:m.edges,patterns:m.patterns,rows,
    free_masks:m.free_masks,profiles:m.profiles,summary:m.summary,work:m.work};
}
module.exports={assemble};
