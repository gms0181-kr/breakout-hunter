/* Display-only stage translations. Engine identifiers and stored data stay unchanged. */
(function(root){
'use strict';
const stages=Object.freeze([
 Object.freeze({id:'DORMANT',number:1,label:'공매도 압박 잠복'}),
 Object.freeze({id:'FUEL_BUILDING',number:2,label:'숏 압박 축적'}),
 Object.freeze({id:'SETUP',number:3,label:'상승 준비'}),
 Object.freeze({id:'IGNITION',number:4,label:'상승 점화'}),
 Object.freeze({id:'EXPANSION',number:5,label:'상승 가속'})
]);
const get=value=>stages.find(s=>s.id===String(value||'').trim().replace(/ /g,'_'));
const label=value=>{const s=get(value);return s?s.number+'단계 '+s.label:'단계 미확정'};
function text(value){return String(value??'').replace(/(?:STAGE\s+[1-5]\s*[/:-]?\s*)?\b(DORMANT|FUEL[ _]BUILDING|SETUP|IGNITION|EXPANSION)\b/g,(_,id)=>label(id))}
root.SqueezeLabels=Object.freeze({stages,get,label,text});
})(window);
