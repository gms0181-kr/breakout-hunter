/* One validated, immutable server snapshot for Hunter and Analysis. No scoring. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else{root.SqueezeData=api;root.SqueezeStore=api.createStore({fetcher:root.fetch.bind(root),storage:root.localStorage})}})(typeof window!=='undefined'?window:globalThis,function(){
'use strict';
const WEIGHTS={short_pressure:30,capital_inflow:25,price_structure:20,dilution_gap:20,catalyst:5},TICKER=/^[A-Z][A-Z0-9.\-]{0,14}$/;
const finite=x=>typeof x==='number'&&Number.isFinite(x),time=x=>Date.parse(x||'');
function freeze(value){if(value&&typeof value==='object'&&!Object.isFrozen(value)){Object.freeze(value);Object.values(value).forEach(freeze)}return value}
function validateAnalysis(a,ticker,at){
 if(!a||a.ticker!==ticker||time(a.as_of)!==time(at))throw Error('종목 또는 점수 기준시각 불일치: '+ticker);
 if(!finite(a.coverage)||a.coverage<0||a.coverage>100)throw Error('확인 배점 오류: '+ticker);
 let covered=0,observed=0,known=false;
 for(const [k,max] of Object.entries(WEIGHTS)){const c=a.components?.[k];if(!c||c.max!==max||!finite(c.coverage)||c.coverage<0||c.coverage>max||c.score!==null&&(!finite(c.score)||c.score<0||c.score>c.coverage))throw Error('점수 스키마 오류: '+ticker);covered+=c.coverage;if(c.score!==null){known=true;observed+=c.score}}
 // Integrity checks only. Never substitute or recalculate the server's score.
 if(covered!==a.coverage||a.observed_score!==(known?observed:null)||a.total_score!==(covered===100?a.observed_score:null))throw Error('서버 점수 무결성 오류: '+ticker);
 if(!a.ctb||!a.market||!a.dilution||!a.official_interest)throw Error('검증 필드 누락: '+ticker);
}
function normalize(input,now=Date.now()){
 const d=structuredClone(input);
 if(d.engine!=='SHORT SQUEEZE HUNTER 1.0'||!Number.isFinite(time(d.updated_at))||time(d.updated_at)>now+60000||!Array.isArray(d.observations))throw Error('공통 수집본 형식·시각 검증 실패');
 const id=d.snapshot_id||d.updated_at;if(time(id)!==time(d.updated_at))throw Error('수집본 ID 불일치');
 const map=new Map();
 for(const r of d.observations){if(!TICKER.test(r.ticker)||map.has(r.ticker))throw Error('중복 또는 잘못된 티커');validateAnalysis(r.analysis,r.ticker,d.updated_at);map.set(r.ticker,r)}
 for(const group of ['top10','research_top10','high_risk']){if(!Array.isArray(d[group]))throw Error('후보 그룹 누락');const seen=new Set();d[group]=d[group].map(row=>{const r=map.get(row.ticker);if(!r||seen.has(row.ticker)||JSON.stringify(row.analysis)!==JSON.stringify(r.analysis))throw Error('후보·상세 점수 불일치: '+row.ticker);seen.add(row.ticker);return r})}
 d.snapshot_id=id;d.details=d.details||{};
 for(const [t,x] of Object.entries(d.details)){const r=map.get(t);if(!r)continue;if(x.analysis&&JSON.stringify(x.analysis)!==JSON.stringify(r.analysis))throw Error('상세 점수 불일치: '+t);if(x.stock?.ticker!==t)throw Error('상세 티커 불일치: '+t);if(r.analysis.ctb.valid&&x.observation?.borrow&&(x.observation.borrow.ctb!==r.analysis.ctb.current||x.observation.borrow.available!==r.analysis.ctb.available||time(x.observation.borrow.as_of)!==time(r.analysis.ctb.as_of)))throw Error('상세 대차 기준 불일치: '+t);x.analysis=r.analysis}
 if(d.monitor&&time(d.monitor.updated_at)!==time(d.updated_at))throw Error('경보 수집본 시각 불일치');
 return freeze(d);
}
function createStore({fetcher,storage,now=Date.now}={}){
 let snapshot=null,selected='',error='',loading=null,busy=false,generation=0;const listeners=new Set(),series=new Map(),inflight=new Map(),details=new Map();let favorites=[];
 try{const v=JSON.parse(storage?.getItem('bh-squeeze-favorites')||'[]');if(Array.isArray(v))favorites=v.filter(x=>TICKER.test(x))}catch(_){}
 const emit=type=>listeners.forEach(fn=>fn({type,snapshot_id:snapshot?.snapshot_id,ticker:selected,error}));
 function getRecord(t=selected){return snapshot?.observations.find(x=>x.ticker===t)||null}
 function select(t){if(!TICKER.test(t||''))return false;if(selected!==t){selected=t;emit('selection')}return !!getRecord(t)}
 function accept(input){const incoming=normalize(input,now());if(snapshot&&time(incoming.updated_at)<time(snapshot.updated_at))return false;if(snapshot&&incoming.snapshot_id===snapshot.snapshot_id){if(JSON.stringify(incoming)!==JSON.stringify(snapshot))throw Error('같은 수집본 ID의 내용 충돌');return true}snapshot=incoming;generation++;details.clear();series.clear();error='';if(!selected)selected=snapshot.research_top10[0]?.ticker||snapshot.observations[0]?.ticker||'';emit('snapshot');return true}
 async function refresh(){if(loading)return loading;busy=true;emit('loading');loading=(async()=>{try{const res=await fetcher('./squeeze-hunter.json?t='+now(),{cache:'no-store'});if(!res.ok)throw Error('공통 수집본 조회 실패: HTTP '+res.status);const incoming=await res.json();if(!incoming.monitor){try{const sr=await fetcher('./squeeze-state.json?t='+now(),{cache:'no-store'});const state=sr.ok?await sr.json():null;if(state&&time(state.updated_at)===time(incoming.updated_at))incoming.monitor=state;else incoming.monitor={updated_at:incoming.updated_at,history:[],alerts:[],status:'다른 기준시각의 경보는 병합하지 않음'}}catch(_){incoming.monitor={updated_at:incoming.updated_at,history:[],alerts:[],status:'경보 조회 실패'}}}return accept(incoming)}catch(e){error=e.message;emit('error');return false}finally{loading=null;busy=false;emit('ready')}})();return loading}
 async function getDetail(t=selected){const r=getRecord(t);if(!r)return null;const id=snapshot.snapshot_id,key=id+'|'+t;if(details.has(key))return details.get(key);if(snapshot.details[t])return snapshot.details[t];const version=generation,letter=t[0],chunkKey=id+'|'+letter;
  if(!series.has(chunkKey)&&!inflight.has(chunkKey))inflight.set(chunkKey,(async()=>{const response=await fetcher('./squeeze-series-'+encodeURIComponent(letter)+'.json?snapshot='+encodeURIComponent(id),{cache:'no-store'});if(!response.ok)throw Error('상세 일봉 조회 실패');const chunk=await response.json();if(chunk.snapshot_id!==id||!chunk.symbols)throw Error('차트 수집본이 다릅니다. 새 수집본 갱신 후 확인하세요.');if(version!==generation)throw Error('갱신 전 차트 응답 제외');series.set(chunkKey,chunk.symbols);return chunk.symbols})().finally(()=>inflight.delete(chunkKey)));
  const symbols=series.get(chunkKey)||await inflight.get(chunkKey);if(version!==generation||snapshot.snapshot_id!==id)throw Error('갱신 전 상세 응답 제외');const values=symbols[t];if(!Array.isArray(values))throw Error('같은 수집본의 종목 일봉 없음');const bars=values.map(v=>Object.fromEntries(['time','open','high','low','close','volume','vwap'].map((k,i)=>[k,v[i]])));const detail=freeze({stock:{...r,bars},observation:{float:r.float||{},short_volume:r.short_volume||{}},analysis:r.analysis,snapshot_id:id});details.set(key,detail);emit('detail');return detail;
 }
 return {accept,refresh,select,getRecord,getDetail,getSnapshot:()=>snapshot,getSelected:()=>selected,getError:()=>error,isLoading:()=>busy,subscribe(fn){listeners.add(fn);return()=>listeners.delete(fn)},getFavorites:()=>[...favorites],toggleFavorite(t){if(!TICKER.test(t||''))return;favorites=favorites.includes(t)?favorites.filter(x=>x!==t):[...favorites,t];try{storage?.setItem('bh-squeeze-favorites',JSON.stringify(favorites))}catch(_){}emit('favorites')}};
}
return {createStore,normalize,validateAnalysis};
});
