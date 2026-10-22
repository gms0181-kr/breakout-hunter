/* Independent observed-score engine. No probability or short entry-price inference. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ShortPressure=api})(typeof globalThis!=='undefined'?globalThis:this,function(){
'use strict';
const finite=v=>typeof v==='number'&&Number.isFinite(v);
const mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:null;
const stamp=x=>Date.parse(x||'');
function validBars(stock,now=Date.now()){return (stock.bars||[]).filter(b=>stamp(b.time)<=now&&b.complete!==false&&['open','high','low','close','volume'].every(k=>finite(b[k]))&&b.low>0&&b.high>=b.low&&b.open>=b.low&&b.open<=b.high&&b.close>=b.low&&b.close<=b.high&&b.volume>=0).sort((a,b)=>stamp(a.time)-stamp(b.time))}
function analyze(stock,obs={},now=Date.now()){
 const components={ctb:null,availability:null,interest:null,capital:null,structure:null};let coverage=0;const notes=[],evidence=[];
 const b=obs.borrow||{},t=stamp(b.as_of),borrowFresh=finite(t)&&t<=now&&now-t<=48*3600000&&!b.stale&&b.lender==='Interactive Brokers'&&typeof b.source==='string'&&b.source.startsWith('https://chartexchange.com/');
 const history=[...(obs.borrow_history||[]),b].filter(x=>stamp(x.as_of)<=now&&stamp(x.as_of)>=now-24*3600000&&!x.stale&&x.lender===b.lender).sort((x,y)=>stamp(x.as_of)-stamp(y.as_of));
 const h=[...new Map(history.map(x=>[x.as_of,x])).values()];
 const prior=h.filter(x=>stamp(x.as_of)<t).at(-1);
 let ctbDelta=null,availableDelta=null;
 if(borrowFresh&&finite(b.ctb)&&b.ctb>=0){components.ctb=b.ctb>=100?15:b.ctb>=30?10:b.ctb>=10?5:0;coverage+=15;evidence.push('CTB 수준 '+b.ctb+'%');if(prior&&finite(prior.ctb)){ctbDelta=b.ctb-prior.ctb;components.ctb+=ctbDelta>=20?10:ctbDelta>=5?5:0;coverage+=10}}
 if(borrowFresh&&finite(b.available)&&b.available>=0){components.availability=b.available===0?10:b.available<=10000?7:b.available<=100000?3:0;coverage+=10;if(prior&&finite(prior.available))availableDelta=b.available-prior.available;if(prior&&finite(prior.available)&&prior.available>0){availableDelta=b.available-prior.available;const fall=(prior.available-b.available)/prior.available;components.availability+=fall>=.8?10:fall>=.5?7:fall>=.2?3:0;coverage+=10}if(b.available===0)notes.push('IBKR 잔량 0(주): 전체 시장 대차 소진 또는 숏커버 확정이 아님')}
 if(!borrowFresh)notes.push('대차 자료 미확인·48시간 초과·갱신 실패: 점수 제외');
 const si=obs.short_interest||{},siDate=stamp(si.settlement_date),siFresh=finite(siDate)&&siDate<=now&&now-siDate<=45*86400000&&!si.stale&&si.status==='source_reported_official'&&si.official_origin==='FINRA';
 const interveningSplit=(stock.split_check?.events||[]).some(e=>stamp(e.ex_date)>siDate&&stamp(e.ex_date)<=now)||(obs.float?.flags||[]).some(x=>x.includes('병합'));
 if(siFresh&&finite(si.float_pct)&&si.float_pct>=0&&!interveningSplit&&si.float_pct<=100){components.interest=si.float_pct>=20?12:si.float_pct>=10?7:si.float_pct>=5?3:0;coverage+=12;if(finite(si.change_pct)&&si.previous?.settlement_date&&stamp(si.previous.settlement_date)<siDate){components.interest+=si.change_pct>=20?8:si.change_pct>0?4:0;coverage+=8}}
 else notes.push('공식 잔고 미확인·오래됨·수량 기준 주의: 점수 제외');
 if(finite(si.float_pct)&&si.float_pct>100)notes.push('출처 Short/Float 100% 초과: 분모·병합 조정 확인 전 잔고 점수 보류');
 const bars=validBars(stock,now),last=bars.at(-1),previous=bars.at(-2);let turnoverRatio=null,reclaim=null,breakout=null,support=null,resistance=null;
 const marketFresh=last&&now-stamp(last.time)<=7*86400000;
 if(marketFresh&&bars.length>=21){const past=bars.slice(-21,-1),avg=mean(past.map(x=>x.close*x.volume));turnoverRatio=avg>0?last.close*last.volume/avg:null;if(finite(turnoverRatio)){components.capital=turnoverRatio>=5?12:turnoverRatio>=3?9:turnoverRatio>=2?6:0;components.capital+=last.close>=previous.close&&last.close>=last.low+(last.high-last.low)*.6?8:last.close>=previous.close?4:0;coverage+=20}support=Math.min(...past.map(x=>x.low));resistance=Math.max(...past.map(x=>x.high));breakout=last.close>resistance;components.structure=breakout?7:0;coverage+=7;if(finite(last.vwap)&&last.vwap>0&&finite(previous.vwap)&&previous.vwap>0){reclaim=previous.close<=previous.vwap&&last.close>last.vwap;components.structure+=reclaim?8:last.close>last.vwap?4:0;coverage+=8}}
 const observed=Object.values(components).filter(finite).reduce((a,x)=>a+x,0),total=coverage===100?observed:null;
 const alert=coverage<40?'자료 부족':observed>=70&&coverage>=80?'높은 압박 관찰':observed>=40?'압박 관찰':'일반 관찰';
 return {components,weights:{ctb:25,availability:20,interest:20,capital:20,structure:15},observed_score:coverage?observed:null,coverage,total_score:total,alert,notes,evidence,prior,ctbDelta,availableDelta,history:h,bars,metrics:{turnoverRatio,reclaim,breakout,support,resistance},method:'관측 점수/100과 확인 배점 구분. 미확인은 null, 확인된 낮은 수준만 0. 대차 단일 출처; 확률·강제청산 확정 지표 아님'};
}
function zones(bars,current){
 const data=bars.slice(-60);if(data.length<5||!finite(current)||current<=0)return [];
 const low=Math.min(...data.map(x=>x.low)),high=Math.max(...data.map(x=>x.high));if(high<=low)return [];
 const width=(high-low)/3;
 return [0,1,2].map(i=>{const from=low+i*width,to=low+(i+1)*width;const members=data.filter(b=>{const typical=(b.high+b.low+b.close)/3;return typical>=from&&(i===2?typical<=to:typical<to)});const v=members.reduce((a,b)=>a+b.volume,0),last=members.at(-1);return {index:i,from,to,distance_pct:(from/current-1)*100,volume_proxy:v,samples:members.length,breakout:current>to,reaction_pct:last?(last.close/last.open-1)*100:null,volume_change_pct:members.length>=2&&members.at(-2).volume>0?(last.volume/members.at(-2).volume-1)*100:null,confidence:members.length>=10?'표본 보통 · 방법 한계 있음':'낮음',note:'일봉 대표가격에 해당 일봉 전체 거래량을 배정한 근사치. 실제 가격별 체결량·숏 진입가 아님'}});
}
return {analyze,zones,validBars,finite};
});
