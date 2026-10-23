const REPO='gms0181-kr/breakout-hunter';
const WORKFLOW='time-machine-reconstruct.yml';
const PARENT='https://gms0181-kr.github.io';
const ENGINE='dce175439f954828ef814510b6c1db3d2a21cf36b8b5797b642dfc72a2820ec7';
const ACTIVE=['dispatching','dispatch_unknown','queued','collecting','analyzing','publishing'];
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'private, no-store','x-content-type-options':'nosniff','referrer-policy':'no-referrer'}});
class Failure extends Error{constructor(status,message){super(message);this.status=status}}
export function etUTC(et){
 if(typeof et!=='string'||!/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(et))throw new Failure(400,'ET 날짜·시각 형식 오류');
 const naive=Date.parse(et+'Z');if(!Number.isFinite(naive))throw new Failure(400,'유효하지 않은 날짜');
 const fmt=new Intl.DateTimeFormat('sv-SE',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
 const matches=[4,5].map(h=>new Date(naive+h*3600000)).filter(d=>fmt.format(d).replace(' ','T')===et);
 if(matches.length!==1)throw new Failure(400,'존재하지 않거나 중복되는 ET 시각');
 return matches[0].toISOString();
}
export function validate(body,now=Date.now()){
 const asOf=etUTC(body.et);if(Date.parse(asOf)>=now)throw new Failure(400,'완료된 과거 시각을 선택하세요');
 if(!['all','china'].includes(body.scope)||!UUID.test(body.idempotency_key||''))throw new Failure(400,'범위 또는 요청 키 오류');
 return {et:body.et,scope:body.scope,asOf,idem:body.idempotency_key};
}
function principal(req,env){
 // The Site is confirmed owner-private; dispatch authenticates service access
 // before this Worker. Never make this Site public without redesigning auth.
 if(env.OWNER_PRIVATE_CONFIRMED!=='true')throw new Failure(401,'사이트 인증 설정을 확인하세요');
 const id=req.headers.get('oai-authenticated-user-id');
 const email=req.headers.get('oai-authenticated-user-email');
 if(email&&env.OWNER_EMAIL&&email.toLowerCase()!==env.OWNER_EMAIL.toLowerCase())throw new Failure(403,'소유자 전용 기능입니다');
 if(!id && (req.method!=='GET'||new URL(req.url).pathname.startsWith('/api/jobs')))throw new Failure(401,'소유자 브라우저 로그인이 필요합니다');
 return id||'owner-private-service';
}
async function bodyJSON(req){
 if(!req.headers.get('content-type')?.startsWith('application/json'))throw new Failure(415,'JSON 요청이 필요합니다');
 const text=await req.text();if(text.length>2048)throw new Failure(413,'요청이 너무 큽니다');
 try{return JSON.parse(text)}catch{throw new Failure(400,'요청 JSON 오류')}
}
async function gh(env,path,options={}){
 const response=await fetch('https://api.github.com/repos/'+REPO+path,{...options,redirect:'error',signal:AbortSignal.timeout(20000),headers:{accept:'application/vnd.github+json','user-agent':'Breakout-Time-Machine','x-github-api-version':'2026-03-10',authorization:'Bearer '+env.GITHUB_ACTIONS_TOKEN,'content-type':'application/json'}});
 return response;
}
const publicJob=j=>({job_id:j.id,et:j.et,scope:j.scope,as_of:j.as_of,state:j.state,error:j.error||null,run_id:j.run_id||null,cache_reused:false,poll_after_ms:10000,...(j.result?{report:JSON.parse(j.result)}:{})});
async function update(env,id,values){
 const keys=Object.keys(values);await env.DB.prepare('UPDATE tm_jobs SET '+keys.map(k=>k+'=?').join(',')+' WHERE id=?').bind(...keys.map(k=>values[k]),id).run();
}
export async function submit(req,env,owner){
 const input=validate(await bodyJSON(req));
 let row=await env.DB.prepare('SELECT * FROM tm_jobs WHERE owner=? AND idem=?').bind(owner,input.idem).first();
 if(row){if(row.et!==input.et||row.scope!==input.scope)throw new Failure(409,'같은 요청 키에 다른 날짜를 사용할 수 없습니다');return json({...publicJob(row),resumed:true})}
 if(!env.GITHUB_ACTIONS_TOKEN)throw new Failure(503,'서버 실행 자격증명 미설정: GITHUB_ACTIONS_TOKEN · 실제 수집을 시작하지 않았습니다');
 const id=crypto.randomUUID(),now=Date.now();
 const inserted=await env.DB.prepare(`INSERT INTO tm_jobs(id,owner,idem,et,scope,as_of,state,created,updated,last_poll)
 SELECT ?,?,?,?,?,?,'dispatching',?,?,0
 WHERE (SELECT COUNT(*) FROM tm_jobs WHERE state IN ('dispatching','dispatch_unknown','queued','collecting','analyzing','publishing') AND updated>?)<2
 AND (SELECT COUNT(*) FROM tm_jobs WHERE owner=? AND created>?)<3
 AND (SELECT COUNT(*) FROM tm_jobs WHERE created>?)<6`).bind(id,owner,input.idem,input.et,input.scope,input.asOf,now,now,now-3600000,owner,now-3600000,now-86400000).run();
 if(!inserted.meta?.changes)throw new Failure(429,'실행 한도: 동시 2건 · 사용자 시간당 3건 · 전체 하루 6건');
 try{
  const r=await gh(env,'/actions/workflows/'+WORKFLOW+'/dispatches',{method:'POST',body:JSON.stringify({ref:'main',inputs:{et:input.et,scope:input.scope,request_id:id}})});
  if(!r.ok){await update(env,id,{state:'failed',error:'GitHub 실행 요청 거부 (HTTP '+r.status+') · 서버 Actions 권한을 확인하세요',updated:Date.now()})}
  else{let data={};if(r.status!==204){try{data=await r.json()}catch{}}
   await update(env,id,{state:'queued',run_id:Number.isSafeInteger(data.workflow_run_id)?data.workflow_run_id:null,updated:Date.now()});
  }
 }catch{await update(env,id,{state:'dispatch_unknown',error:'실행 요청의 접수 여부 확인 중 · 자동 재발송하지 않습니다',updated:Date.now()})}
 row=await env.DB.prepare('SELECT * FROM tm_jobs WHERE id=? AND owner=?').bind(id,owner).first();return json(publicJob(row),202);
}
export function verifyReport(report,row){
 if(report.job?.id!==row.id||report.job?.et!==row.et||report.job?.scope!==row.scope||Date.parse(report.as_of)!==Date.parse(row.as_of)||report.result?.engine_hash!==ENGINE||!Array.isArray(report.result?.top20)||report.result.top20.length>20||report.result.acquisition_mode!=='HISTORICAL RECONSTRUCTION')throw new Failure(502,'날짜·작업 ID·엔진 버전이 일치하지 않는 결과를 차단했습니다');
 return report;
}
async function poll(env,row){
 const now=Date.now();if(!ACTIVE.includes(row.state)||now-row.last_poll<10000)return row;
 // Atomic poll lease prevents repeated browser refreshes from flooding GitHub.
 const lease=await env.DB.prepare('UPDATE tm_jobs SET last_poll=? WHERE id=? AND last_poll=?').bind(now,row.id,row.last_poll).run();
 if(!lease.meta?.changes)return row;
 try{
  let id=row.run_id;
  if(!id){
   const r=await gh(env,'/actions/workflows/'+WORKFLOW+'/runs?event=workflow_dispatch&branch=main&per_page=30');if(!r.ok)throw new Failure(502,'GitHub 작업 상태 조회 실패 (HTTP '+r.status+')');
   const match=(await r.json()).workflow_runs?.find(x=>x.display_title==='TIME MACHINE '+row.id);id=match?.id;
   if(id)await update(env,row.id,{run_id:id,error:null});
   else if(now-row.created>600000)await update(env,row.id,{state:'failed',error:'10분 내 실행 접수를 확인하지 못했습니다 · 자동 재발송 없음',updated:now});
  }
  if(id){
   const r=await gh(env,'/actions/runs/'+id);if(!r.ok)throw new Failure(502,'GitHub 실행 상태 확인 실패');const run=await r.json();
   if(run.status==='completed'){
    if(run.conclusion!=='success')await update(env,row.id,{state:run.conclusion==='cancelled'?'cancelled':'failed',error:'수집 워크플로 종료: '+String(run.conclusion),updated:now});
    else{
     const response=await fetch('https://raw.githubusercontent.com/'+REPO+'/main/public/time-machine/jobs/'+row.id+'.json',{cache:'no-store',signal:AbortSignal.timeout(20000),redirect:'error'});
     if(response.status===404){await update(env,row.id,{state:'publishing',updated:now});}
     else if(!response.ok)throw new Failure(502,'수집 결과 조회 실패');
     else{const report=verifyReport(await response.json(),row);await update(env,row.id,{state:'completed',result:JSON.stringify(report),error:null,updated:now});}
    }
   }else if(run.status==='queued'||run.status==='waiting'||run.status==='pending')await update(env,row.id,{state:'queued',updated:now});
   else{
    const jr=await gh(env,'/actions/runs/'+id+'/jobs?per_page=10');let state='collecting';
    if(jr.ok){const jobs=(await jr.json()).jobs||[];const step=jobs.flatMap(j=>j.steps||[]).find(s=>s.status==='in_progress')?.name||'';
     if(/analy|분석/i.test(step))state='analyzing';if(/Publish|Persist|upload-artifact/i.test(step))state='publishing';}
    await update(env,row.id,{state,error:null,updated:now});
   }
  }
  if(now-row.created>7200000)await update(env,row.id,{state:'failed',error:'2시간 실행 제한 초과 · GitHub 상태를 확인하세요',updated:now});
 }catch(error){await update(env,row.id,{error:error instanceof Failure?error.message:'상태 연결 일시 오류 · 기존 작업은 유지됩니다'});}
 return await env.DB.prepare('SELECT * FROM tm_jobs WHERE id=?').bind(row.id).first();
}
const PAGE=`<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BREAKOUT HUNTER — TIME MACHINE 실행</title><style>:root{color-scheme:dark;font:14px system-ui;background:#061326;color:#F4F7FC}body{margin:0;padding:24px}main{max-width:1000px;margin:auto}h1,b,a{color:#F4BE55}.panel{background:#0D2039;border:1px solid #304766;border-radius:12px;padding:20px;margin:18px 0}button{background:#F4BE55;color:#061326;padding:12px;border:0;border-radius:7px;font-weight:bold}p{line-height:1.7}td,th{padding:12px;border-bottom:1px solid #304766;text-align:left}.scroll{overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}small{color:#9EB0C8}</style><main><small>NAVY & GOLD · OWNER AUTHENTICATED</small><h1>TIME MACHINE 실행</h1><div class="panel"><b id="request"></b><p id="status" role="status">서버 연결 확인 중…</p><p id="job"></p><button id="retry" hidden>실행 재시도</button></div><div id="results"></div><details class="panel"><summary>실행 방식과 데이터 한계</summary><p>기존 GitHub Actions와 Alpaca Secrets를 사용합니다. 원본 엔진 계산은 유지하며, 과거 상장·CTB·SEC 확인이 부족하면 PARTIAL REPLAY로 표시합니다. 정기 스캔과 텔레그램은 실행하지 않습니다.</p></details></main><script>
(()=>{const p=new URLSearchParams(location.search),et=p.get('et'),scope=p.get('scope')||'all',key=p.get('request_key');const nonce=key;const $=id=>document.getElementById(id),esc=v=>String(v??'미확인').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let running=false;
function notify(type,payload){if(window.opener)window.opener.postMessage({channel:'breakout-time-machine',nonce,type,...payload},'${PARENT}');}
async function api(path,options){const r=await fetch(path,{...options,cache:'no-store'});let data;try{data=await r.json()}catch{throw Error('인증 또는 서버 응답 오류')};if(!r.ok)throw Error(data.error||'요청 실패 (HTTP '+r.status+')');return data;}
const states={dispatching:'실행 요청 중',dispatch_unknown:'실행 접수 여부 확인 중',queued:'GitHub 실행 대기',collecting:'외부 과거 데이터 수집 중',analyzing:'기존 엔진 분석 중',publishing:'결과 저장 중',completed:'분석 완료',failed:'실행 실패',cancelled:'작업 취소됨'};
function show(job){$('job').textContent='작업 ID: '+job.job_id;$('status').textContent=(states[job.state]||job.state)+(job.error?' · '+job.error:'');notify('status',{job_id:job.job_id,state:job.state,message:$('status').textContent});if(job.report){const r=job.report.result,c=r.coverage_report||{};$('results').innerHTML='<div class="panel"><h2>'+esc(r.status)+'</h2><p>요청 '+esc(c.requested_symbols)+'종목 · 과거 가격 확보 '+esc(r.examined)+'종목 · 당시 소형주 적격 검증 '+esc(c.historical_smallcap_verified)+'종목 · 적격 미검증 신호 '+esc(r.candidate_count)+'종목</p><p>'+esc(r.reason)+'</p><div class="scroll"><table><tr><th>순위</th><th>티커</th><th>점수 / 확인 배점</th><th>근거</th></tr>'+r.top20.map((x,i)=>'<tr><td>'+(i+1)+'</td><td>'+esc(x.ticker)+'</td><td>'+esc(x.analysis.observed_score)+' / '+esc(x.analysis.coverage)+'</td><td>'+esc(x.analysis.early_signal?.basis||x.analysis.stage_reason)+'</td></tr>').join('')+'</table></div></div>';notify('result',{report:job.report,job_id:job.job_id});}}
async function start(){if(running)return;running=true;$('retry').hidden=true;try{if(!et||!key)throw Error('기존 BREAKOUT HUNTER 화면에서 날짜를 선택하고 TIME MACHINE 실행을 눌러 주세요');$('request').textContent=et+' ET · '+scope;let job=await api('/api/jobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({et,scope,idempotency_key:key})});show(job);while(!['completed','failed','cancelled'].includes(job.state)){await new Promise(r=>setTimeout(r,job.poll_after_ms||10000));try{job=await api('/api/jobs/'+job.job_id);show(job)}catch(e){$('status').textContent=e.message+' · 기존 작업 상태 재조회 중';notify('status',{state:'connection_error',message:$('status').textContent});}}}catch(e){$('status').textContent=e.message;notify('error',{message:e.message});$('retry').hidden=false}finally{running=false}}
$('retry').onclick=start;if(et&&key)start();else{$('status').textContent='BREAKOUT HUNTER의 TIME MACHINE 실행 버튼으로 시작하세요.';}
})();</script></html>`;
export default{async fetch(req,env){
 try{
  const url=new URL(req.url);const owner=principal(req,env);
  if(req.method==='GET'&&url.pathname==='/')return new Response(PAGE,{headers:{'content-type':'text/html; charset=utf-8','cache-control':'private, no-store','x-content-type-options':'nosniff','referrer-policy':'no-referrer','content-security-policy':"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors https://gms0181-kr.github.io"}});
  if(req.method==='GET'&&url.pathname==='/api/health')return json({authenticated:true,configured:!!env.GITHUB_ACTIONS_TOKEN,engine:ENGINE,rate_limits:{concurrent:2,per_user_hour:3,global_day:6}});
  if(req.method==='POST'&&url.pathname==='/api/jobs'){
   if(req.headers.get('origin')!==url.origin)throw new Failure(403,'다른 출처의 실행 요청을 차단했습니다');
   if(!env.DB)throw new Failure(503,'실행 기록 저장소 미설정');return await submit(req,env,owner);
  }
  const match=url.pathname.match(/^\/api\/jobs\/([0-9a-f-]{36})$/i);
  if(req.method==='GET'&&match&&UUID.test(match[1])){if(!env.DB)throw new Failure(503,'실행 기록 저장소 미설정');const row=await env.DB.prepare('SELECT * FROM tm_jobs WHERE id=? AND owner=?').bind(match[1],owner).first();if(!row)throw new Failure(404,'이 사용자의 작업이 없습니다');return json(publicJob(await poll(env,row)));}
  return json({error:'찾을 수 없는 경로'},404);
 }catch(error){return json({error:error instanceof Failure?error.message:'서버 처리 오류 · 작업을 자동 재발송하지 않습니다'},error instanceof Failure?error.status:500)}
}};
