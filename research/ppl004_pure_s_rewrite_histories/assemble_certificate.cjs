"use strict";
// Caller supplies the manifest and complete raw part strings in its stated order.
// Length/ASCII checks protect this fixed serialization; no SHA or mathematical audit.
function assembleCertificate(manifest,texts){
  if(!manifest||manifest.schema!=="ppl004.lossless-certificate-parts/v1"||
     !Array.isArray(texts)||texts.length!==manifest.parts.length)throw new TypeError("parts shape");
  for(let i=0;i<texts.length;i++)if(typeof texts[i]!=="string"||
     /[^\x00-\x7f]/.test(texts[i])||texts[i].length!==manifest.parts[i].bytes)throw new RangeError("part length or encoding");
  const joined=texts.join("");
  if(joined.length!==manifest.whole.bytes)throw new RangeError("whole length");
  return JSON.parse(joined);
}
module.exports={assembleCertificate};
