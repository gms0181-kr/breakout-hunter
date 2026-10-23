"""Exercise the actual WASM Python path, not a JavaScript score imitation."""
import asyncio,json,threading,shutil,hashlib
from datetime import datetime,timedelta
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

class CachedHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        if self.path.split('?')[0].endswith(('.py','.json','.js')):self.send_header('Cache-Control','public, max-age=3600')
        super().end_headers()

async def main():
    server=ThreadingHTTPServer(('127.0.0.1',8765),partial(CachedHandler,directory='public'))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    index=json.loads(Path('public/time-machine/index.json').read_text());date=(datetime.fromisoformat(next(e for e in index['snapshots'] if e['status']=='PARTIAL REPLAY')['available_at'].replace('Z','+00:00'))+timedelta(minutes=1)).astimezone(ZoneInfo('America/New_York'))
    Path('qa').mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium') or None)
        page=await browser.new_page(viewport={'width':1440,'height':1000});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto('http://127.0.0.1:8765/time-machine.html')
        await page.locator('#tm-run').wait_for()
        await page.wait_for_function("!document.getElementById('tm-run').disabled")
        await page.locator('#tm-date').fill(date.strftime('%Y-%m-%d'));await page.locator('#tm-time').fill(date.strftime('%H:%M'))
        await page.locator('#tm-run').click()
        await page.wait_for_function("!document.getElementById('tm-run').disabled",timeout=240000)
        text=await page.locator('#tm-status').inner_text()
        assert 'PARTIAL REPLAY' in text,text
        # Simulate deployment while the browser retains hour-long source caches.
        engine_path=Path('public/time-machine/engine/time_machine.py');index_path=Path('public/time-machine/index.json')
        original_engine=engine_path.read_bytes();original_index=index_path.read_bytes()
        try:
            revised=original_engine+b'\n';engine_path.write_bytes(revised)
            updated=json.loads(original_index);updated['engine_hashes']['time_machine']=hashlib.sha256(revised).hexdigest()
            updated['built_at']=datetime.now(ZoneInfo('UTC')).isoformat();index_path.write_text(json.dumps(updated))
            await page.reload();await page.wait_for_function("!document.getElementById('tm-run').disabled")
            await page.locator('#tm-date').fill(date.strftime('%Y-%m-%d'));await page.locator('#tm-time').fill(date.strftime('%H:%M'))
            await page.locator('#tm-run').click();await page.wait_for_function("!document.getElementById('tm-run').disabled",timeout=240000)
            refreshed=await page.locator('#tm-status').inner_text()
            assert 'PARTIAL REPLAY' in refreshed,refreshed
        finally:
            engine_path.write_bytes(original_engine);index_path.write_bytes(original_index)
        await page.screenshot(path='qa/time-machine-desktop.png',full_page=True)
        if await page.locator('#tm-evaluate').is_enabled():
            await page.locator('#tm-evaluate').click();await page.wait_for_function("!document.getElementById('tm-evaluate').disabled",timeout=30000)
            result_text=await page.locator('#tm-results').inner_text()
            assert '검증 성공률 산출 불가' in result_text,result_text
        await page.locator('#tm-date').fill('2026-10-15');await page.locator('#tm-time').fill('09:30');await page.locator('#tm-run').click()
        await page.wait_for_function("!document.getElementById('tm-run').disabled",timeout=30000)
        assert 'NOT REPRODUCIBLE' in await page.locator('#tm-status').inner_text()
        # Reconstruction requests cannot silently fall back to saved rows.
        await page.locator('#tm-acquisition').select_option('historical')
        assert await page.locator('#tm-reconstruction').is_visible()
        fixture={'retrieved_at':'2026-10-23T17:40:58.788786+00:00','as_of':'2026-10-15T16:00:00+00:00','result':{'mode':'all','acquisition_mode':'HISTORICAL RECONSTRUCTION','status':'PARTIAL REPLAY','reason':'External reconstruction browser fixture','requested_et':'2026-10-15T12:00 ET','examined':2,'candidate_count':0,'top20':[],'usable_price_stocks':2,'coverage_report':{'requested_symbols':3,'with_historical_prices':2},'missing':['historical eligibility unverified'],'frozen':{'selection_hash':'test'}}}
        await page.route('**/time-machine/reconstruction-latest.json',lambda route:route.fulfill(json=fixture))
        await page.locator('#tm-time').fill('12:00')
        assert '2026-10-15T12:00 ET' in await page.locator('#tm-request').inner_text()
        await page.locator('#tm-run').click()
        await page.wait_for_function("!document.getElementById('tm-run').disabled")
        assert 'HISTORICAL RECONSTRUCTION' in await page.locator('#tm-status').inner_text()
        assert '적격 검증 0종목' in await page.locator('#tm-detection-title').inner_text()
        assert '외부 조회 시각' in await page.locator('#tm-summary').inner_text()
        assert '이후 성과 자료 미연결' in await page.locator('#tm-results').inner_text()
        await page.set_viewport_size({'width':320,'height':740})
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'external retrieval timestamp overflow'
        await page.set_viewport_size({'width':1440,'height':1000})
        assert await page.locator('#tm-evaluate').is_disabled()
        await page.locator('#tm-time').fill('12:01');await page.locator('#tm-run').click()
        await page.wait_for_function("!document.getElementById('tm-run').disabled")
        assert '선택한 시각·범위의 TIME MACHINE 실행' in await page.locator('#tm-status').inner_text()
        assert '이전 요청의 후보를 표시하지 않음' in await page.locator('#tm-candidates').inner_text()
        assert await page.locator('#tm-evaluate').is_disabled()
        # Transport fixtures validate the popup bridge only, not live GitHub dispatch.
        await page.wait_for_function("!document.getElementById('tm-execute').disabled")
        await page.evaluate("window.__requests=[];window.__popup={closed:false};window.open=(url)=>{window.__requests.push(url);return window.__popup}")
        await page.locator('#tm-time').fill('12:00');await page.locator('#tm-execute').click()
        assert await page.locator('#tm-date').is_disabled()
        first=await page.evaluate('window.__requests[0]')
        assert 'et=2026-10-15T12%3A00' in first,first
        report=json.loads(json.dumps(fixture));report['job']={'id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','et':'2026-10-15T12:00','scope':'all'}
        report['result']['engine_hash']='dce175439f954828ef814510b6c1db3d2a21cf36b8b5797b642dfc72a2820ec7'
        payload={'report':report,'job_id':report['job']['id'],'type':'result','channel':'breakout-time-machine'}
        await page.evaluate("""data=>{data.nonce=new URL(window.__requests[0]).searchParams.get('request_key');window.__reply=data;window.dispatchEvent(new MessageEvent('message',{origin:'https://attacker.invalid',source:window,data}));}""",payload)
        assert '결과 미확정' in await page.locator('#tm-candidates').inner_text()
        # A real Window proxy is needed as MessageEvent.source. This owned child
        # remains local; only the bridge origin value is simulated.
        await page.evaluate("window.__popup=window;window.open=(url)=>{window.__requests.push(url);return window}")
        await page.evaluate("window.dispatchEvent(new MessageEvent('message',{origin:'https://breakout-time-machine-runner.rockymite64.chatgpt.site',source:window.__popup,data:{...window.__reply,type:'error',message:'fixture reset'}}))")
        # Previous attempt's source is deliberately different, so it is ignored.
        assert await page.locator('#tm-execute').is_disabled()
        await page.reload();await page.wait_for_function("!document.getElementById('tm-execute').disabled && !document.getElementById('tm-run').disabled")
        await page.locator('#tm-date').fill('2026-10-15');await page.locator('#tm-time').fill('12:00')
        await page.evaluate("window.__requests=[];window.open=url=>{window.__requests.push(url);return window}")
        await page.locator('#tm-execute').click()
        await page.evaluate("""data=>{data.nonce=new URL(window.__requests[0]).searchParams.get('request_key');window.dispatchEvent(new MessageEvent('message',{origin:'https://breakout-time-machine-runner.rockymite64.chatgpt.site',source:window,data}));}""",payload)
        assert 'PARTIAL REPLAY' in await page.locator('#tm-status').inner_text()
        assert '외부 수집·분석 완료' in await page.locator('#tm-service-state').inner_text()
        assert await page.locator('#tm-evaluate').is_disabled()
        await page.locator('#tm-date').fill('2026-10-12');await page.locator('#tm-time').fill('14:00');await page.locator('#tm-execute').click()
        second=await page.evaluate('window.__requests[1]')
        assert 'et=2026-10-12T14%3A00' in second and first!=second
        await page.evaluate("""data=>{data.nonce=new URL(window.__requests[1]).searchParams.get('request_key');window.dispatchEvent(new MessageEvent('message',{origin:'https://breakout-time-machine-runner.rockymite64.chatgpt.site',source:window,data}));}""",payload)
        assert '일치하지 않는 결과를 차단' in await page.locator('#tm-status').inner_text()
        assert '결과 미확정' in await page.locator('#tm-candidates').inner_text()
        await page.evaluate("window.dispatchEvent(new MessageEvent('message',{origin:'https://breakout-time-machine-runner.rockymite64.chatgpt.site',source:window,data:{channel:'breakout-time-machine',nonce:new URL(window.__requests[1]).searchParams.get('request_key'),type:'error',message:'503 서버 실행 자격증명 미설정'}}))")
        assert '503' in await page.locator('#tm-status').inner_text()
        assert await page.locator('#tm-execute').is_enabled()
        await page.set_viewport_size({'width':390,'height':844});await page.screenshot(path='qa/time-machine-mobile.png',full_page=True)
        assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'mobile overflow'
        assert not errors,errors
        await browser.close()
    server.shutdown();print('Actual browser Python replay, deployment cache refresh, missing-history guard, future panel and mobile checks passed')
if __name__=='__main__':asyncio.run(main())
