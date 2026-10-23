'use strict';
(()=>{
const $=id=>document.getElementById(id),button=$('tm-execute'),resume=$('tm-resume');
const ENGINE='dce175439f954828ef814510b6c1db3d2a21cf36b8b5797b642dfc72a2820ec7';
let origin,active,popup,closedTimer;
button.disabled=true;
const say=text=>{$('tm-status').textContent=text;if($('tm-service-state'))$('tm-service-state').textContent=text};
function lock(value){for(const id of ['tm-date','tm-time','tm-mode','tm-acquisition','tm-run'])$(id).disabled=value;button.disabled=value||!origin;}
function openRequest(request){
 popup=window.open(request.url,'breakout-time-machine-execution','popup,width=1050,height=900');
 if(!popup){say('실행 창이 차단됐습니다. 팝업 허용 후 다시 실행하세요. 수집 시작은 확인되지 않았습니다.');lock(false);return;}
 active=request;lock(true);resume.hidden=true;window.dispatchEvent(new CustomEvent('tm:external-start'));say('소유자 인증 확인 및 TIME MACHINE 실행 요청 중…');
 clearInterval(closedTimer);closedTimer=setInterval(()=>{if(popup?.closed){clearInterval(closedTimer);lock(false);resume.hidden=false;say('실행 창이 닫혔습니다. 서버에 접수된 작업은 취소되지 않습니다. 기존 작업 이어보기를 사용할 수 있습니다.')}},1000);
}
button.onclick=()=>{
 if(!origin)return;const date=$('tm-date').value,time=$('tm-time').value;if(!date||!time){say('과거 ET 날짜와 시각을 선택하세요');return;}
 $('tm-acquisition').value='historical';$('tm-acquisition').onchange();const nonce=crypto.randomUUID(),et=date+'T'+time,scope=$('tm-mode').value;
 const url=new URL('/',origin);url.search=new URLSearchParams({et,scope,request_key:nonce}).toString();openRequest({nonce,et,scope,url:url.href});
};
resume.onclick=()=>{if(active)openRequest(active)};
window.addEventListener('message',event=>{
 if(!active||event.origin!==origin||event.source!==popup)return;const data=event.data;
 if(!data||data.channel!=='breakout-time-machine'||data.nonce!==active.nonce)return;
 if(data.type==='status')say(data.message+(data.job_id?' · 작업 ID '+data.job_id:''));
 if(data.type==='error'){clearInterval(closedTimer);say('실행 중단: '+data.message);lock(false);resume.hidden=false;}
 if(data.type==='result'){
  const report=data.report;
  if(report?.job?.et!==active.et||report?.job?.scope!==active.scope||report.job.id!==data.job_id||report.result?.engine_hash!==ENGINE||report.result?.acquisition_mode!=='HISTORICAL RECONSTRUCTION'||!Array.isArray(report.result?.top20)||report.result.top20.length>20){say('선택한 날짜·작업 ID·엔진과 일치하지 않는 결과를 차단했습니다');return;}
  clearInterval(closedTimer);lock(false);resume.hidden=true;window.dispatchEvent(new CustomEvent('tm:external-result',{detail:report}));
  $('tm-service-state').textContent='외부 수집·분석 완료 · 작업 ID '+data.job_id+' · 새 수집 결과 (캐시 재사용 없음)';
 }
 if(data.type==='status'&&['failed','cancelled'].includes(data.state)){clearInterval(closedTimer);lock(false);resume.hidden=false;}
});
fetch('./time-machine-service.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('실행 서버 주소 미설정');return r.json()}).then(config=>{
 const u=new URL(config.origin);if(u.protocol!=='https:'||u.pathname!=='/'||u.search||u.hash||u.origin!=='https://breakout-time-machine-runner.rockymite64.chatgpt.site')throw Error('허용되지 않은 실행 서버');origin=u.origin;button.disabled=false;
}).catch(e=>say('TIME MACHINE 실행 연결 준비 상태: '+e.message));
})();
