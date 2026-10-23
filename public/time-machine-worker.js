'use strict';
let runtime,initialized;
async function initialize(index){
 if(initialized)return initialized;
 initialized=(async()=>{
  importScripts('https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js');
  runtime=await loadPyodide({indexURL:'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/'});
  runtime.FS.mkdirTree('/app/hunter');runtime.FS.writeFile('/app/hunter/__init__.py','');
  for(const name of index.engine_modules){const response=await fetch('./time-machine/engine/'+name+'.py');if(!response.ok)throw Error('엔진 소스 누락');const bytes=new Uint8Array(await response.arrayBuffer());const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');if(hash!==index.engine_hashes[name])throw Error('엔진 버전 해시 불일치');runtime.FS.writeFile('/app/hunter/'+name+'.py',bytes)}
  const zones=await(await fetch('./time-machine/tzdata.json')).json();for(const [name,b64] of Object.entries(zones)){runtime.FS.mkdirTree('/tz/'+name.split('/').slice(0,-1).join('/'));runtime.FS.writeFile('/tz/'+name,Uint8Array.from(atob(b64),c=>c.charCodeAt(0)))}
  await runtime.runPythonAsync("import sys, zoneinfo, json\nsys.path.insert(0,'/app')\nzoneinfo.reset_tzpath(['/tz'])\nfrom hunter.time_machine import et_instant, run_detection\n");
 })();return initialized;
}
self.onmessage=async({data})=>{try{
 if(data.type==='detect'){
  await initialize(data.index);runtime.globals.set('requested_et',data.date);const cutoff=runtime.runPython('et_instant(requested_et).isoformat()');const eligible=data.index.snapshots.filter(s=>Date.parse(s.available_at)<=Date.parse(cutoff));
  let bundle={};if(eligible.length){const record=eligible.at(-1),response=await fetch('./time-machine/'+record.file);if(!response.ok)throw Error('과거 스냅샷 누락');const bytes=new Uint8Array(await response.arrayBuffer());const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');if(hash!==record.sha256)throw Error('스냅샷 해시 불일치');bundle=JSON.parse(new TextDecoder().decode(bytes))}
  runtime.globals.set('bundle_json',JSON.stringify(bundle));runtime.globals.set('cutoff',cutoff);runtime.globals.set('scope_mode',data.mode);
  const result=JSON.parse(await runtime.runPythonAsync("detection_result=run_detection(json.loads(bundle_json),cutoff,scope_mode)\n_frozen_selection=detection_result['frozen']\njson.dumps(detection_result,ensure_ascii=False)"));result.requested_et=data.date+' ET';postMessage({id:data.id,result});
 }else if(data.type==='evaluate'){
  if(!runtime)throw Error('먼저 후보를 확정하세요');runtime.globals.set('expected_selection_hash',data.selection_hash);runtime.globals.set('outcomes_json',JSON.stringify(data.outcomes));runtime.globals.set('stop',data.stop);runtime.globals.set('slip',data.slip);
  const result=JSON.parse(await runtime.runPythonAsync("from hunter.time_machine_evaluate import evaluate\nif _frozen_selection['selection_hash'] != expected_selection_hash: raise ValueError('후보 확정 해시 불일치')\njson.dumps(evaluate(_frozen_selection,json.loads(outcomes_json),stop,slip),ensure_ascii=False)"));postMessage({id:data.id,result});
 }
}catch(e){postMessage({id:data.id,error:e.message||String(e)})}};
