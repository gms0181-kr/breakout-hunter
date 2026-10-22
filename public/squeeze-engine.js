/* Chart geometry only. The sole scoring engine is hunter/squeeze_signals.py. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.SqueezeGeometry=api})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const finite=v=>typeof v==='number'&&Number.isFinite(v);
const mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:null;
const stamp=x=>Date.parse(x||'');
function validBars(stock,now=Date.now()){return (stock.bars||[]).filter(b=>stamp(b.time)<=now&&(!b.available_at||stamp(b.available_at)<=now)&&b.complete!==false&&['open','high','low','close','volume'].every(k=>finite(b[k]))&&b.low>0&&b.high>=b.low&&b.open>=b.low&&b.open<=b.high&&b.close>=b.low&&b.close<=b.high&&b.volume>=0).sort((a,b)=>stamp(a.time)-stamp(b.time))}
function zones(bars,current){
 const data=bars.slice(-60);if(data.length<5||!finite(current)||current<=0)return [];
 const low=Math.min(...data.map(x=>x.low)),high=Math.max(...data.map(x=>x.high));if(high<=low)return [];
 const width=(high-low)/3;
 return [0,1,2].map(i=>{const from=low+i*width,to=low+(i+1)*width;const members=data.filter(b=>{const typical=(b.high+b.low+b.close)/3;return typical>=from&&(i===2?typical<=to:typical<to)});const v=members.reduce((a,b)=>a+b.volume,0),last=members.at(-1);return {index:i,from,to,distance_pct:(from/current-1)*100,volume_proxy:v,samples:members.length,breakout:current>to,reaction_pct:last?(last.close/last.open-1)*100:null,volume_change_pct:members.length>=2&&members.at(-2).volume>0?(last.volume/members.at(-2).volume-1)*100:null,confidence:members.length>=10?'표본 보통 · 방법 한계 있음':'낮음',note:'일봉 대표가격에 해당 일봉 전체 거래량을 배정한 근사치. 실제 가격별 체결량·숏 진입가 아님'}});
}
return {zones,validBars,finite};
});
