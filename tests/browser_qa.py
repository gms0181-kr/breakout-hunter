"""Post-deployment QA. No API credentials are present in this job."""
import asyncio,json,os,shutil
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    url=os.environ["SITE_URL"]
    Path("qa").mkdir(exist_ok=True)
    evidence=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium') or None)
        for name,width,height in (("desktop",1440,1000),("mobile",390,844),("small-mobile",320,740),("tablet",768,1024),("wide-desktop",1920,1080)):
            print("viewport_start "+name,flush=True)
            page=await browser.new_page(viewport={"width":width,"height":height})
            page.set_default_timeout(15000)
            errors=[]
            page.on("pageerror",lambda err: errors.append(type(err).__name__))
            response=await page.goto(url,wait_until="networkidle",timeout=60000)
            print("viewport_loaded "+name,flush=True)
            assert response and response.status==200
            await page.wait_for_function("report !== null",timeout=30000)
            assert await page.title()=="BREAKOUT HUNTER 1.0"
            await page.locator("#scan-now").click()
            assert await page.locator("#manual-dialog").is_visible()
            assert await page.locator("#manual-launch").get_attribute("href")=="https://github.com/gms0181-kr/breakout-hunter/actions/workflows/scan.yml"
            await page.locator("#manual-close").click()
            assert not await page.locator("#manual-dialog").is_visible()
            refresh_verified=False
            if name=="desktop":
                async with page.expect_response(lambda r: "/data.json?t=" in r.url,timeout=75000) as refreshed:
                    await page.wait_for_timeout(62000)
                refresh_response=await refreshed.value
                assert refresh_response.status==200
                refresh_verified=True
            await page.locator("#verified").click()
            valid=await page.evaluate("activeTop10().length")
            shown=await page.locator("#rows [data-ticker]").count()
            stored=await page.evaluate("storedTop10().length")
            assert shown==stored, (shown,stored)
            # Expired evidence must stay visibly historical, never silently disappear
            # or count as a current actionable signal.
            await page.evaluate("""() => {
                window.originalReport=report;
                report=JSON.parse(JSON.stringify(report));
                for(const s of storedTop10()) if(s.halt_check) s.halt_check.expires_at='2000-01-01T00:00:00Z';
                draw();
            }""")
            assert await page.evaluate("activeTop10().length")==0
            assert await page.locator("#rows [data-ticker]").count()==stored
            if stored:
                assert "재확인" in await page.locator("#tabletitle").inner_text()
            await page.evaluate("report=window.originalReport;delete window.originalReport;draw()")
            if valid:
                assert await page.locator("#rows").inner_text()
            float_cells=await page.locator("#rows [data-float-value=yes]").count()
            ctb_cells=await page.locator("#rows [data-ctb-value=yes]").count()
            cache_symbols=await page.evaluate("Object.keys(enrichment.symbols||{}).length")
            if cache_symbols and stored:
                expected_float=await page.evaluate("storedTop10().filter(s=>sourceObservation(s)?.float?.display_value!=null).length")
                expected_ctb=await page.evaluate("storedTop10().filter(s=>sourceObservation(s)?.borrow?.ctb!=null).length")
                assert float_cells==expected_float
                assert ctb_cells==expected_ctb
            await page.locator("#triple").click()
            assert "3중 검증 후보" in await page.locator("#tabletitle").inner_text()
            expected=await page.evaluate("(report.verification_candidates||[]).filter(s=>s.market_cap==null||s.market_cap<=Number(document.getElementById('cap').value)).length")
            assert await page.locator("#rows [data-ticker]").count()==expected
            await page.locator("#research").click()
            if await page.evaluate("!!report.verification_summary"):
                assert await page.locator("#rows .verification-badge").count()==await page.locator("#rows [data-ticker]").count()
            await page.locator("#inlf-validation summary").click()
            assert await page.locator("#inlf-case").is_visible()
            print("viewport_screenshot "+name,flush=True)
            await page.screenshot(path=f"qa/{name}.png",full_page=False,timeout=20000)
            buttons=page.locator("[data-ticker]")
            if await buttons.count():
                await buttons.first.click()
                assert await page.locator("#detail").is_visible()
                await page.locator("#close").click()
            await page.locator('a[href="#short-squeeze"]').click()
            await page.wait_for_function("document.body.classList.contains('sq-mode')",timeout=15000)
            await page.wait_for_function("window.SqueezeStore?.getSnapshot() && !SqueezeStore.isLoading()",timeout=60000)
            squeeze_count=await page.locator('[data-sq-select]').count()
            if squeeze_count:
                buttons_sq=page.locator('[data-sq-select]')
                ticker=await buttons_sq.nth(min(1,squeeze_count-1)).get_attribute('data-sq-select')
                await buttons_sq.nth(min(1,squeeze_count-1)).click()
                assert ticker in await page.locator('#sq-detail h2').inner_text()
                await page.locator('[data-sq-period="5D"]').click()
                assert await page.locator('[data-sq-period="5D"]').get_attribute('aria-pressed')=='true'
                assert await page.locator('#sq-price svg').count()==1
                await page.locator('#sq-search').fill('__NO_MATCH_TERMINAL_QA__')
                assert await page.locator('[data-sq-select]').count()==0
                await page.locator('#sq-search').fill('')
                await page.locator('#sq-sort').select_option('ticker')
                assert await page.locator('[data-sq-select]').count()==squeeze_count
                assert await page.locator('.sq-grid5 .sq-panel').count()==5
            await page.screenshot(path=f"qa/squeeze-{name}.png",full_page=False,timeout=20000)
            assert not await page.evaluate("document.documentElement.scrollWidth > innerWidth"),'terminal horizontal overflow'
            await page.locator('a[href="#scan"]').click()
            await page.wait_for_function("!document.body.classList.contains('sq-mode')",timeout=15000)
            await page.locator('a[href="#squeeze-hunter"]').first.click()
            await page.wait_for_function("document.body.classList.contains('sh-mode')",timeout=15000)
            await page.wait_for_function("!document.getElementById('sh-refresh').disabled",timeout=60000)
            assert await page.locator('#squeeze-hunter').is_visible()
            independent_count=await page.locator('#sh-list [data-sh-select]').count()
            if independent_count:
                await page.locator('#sh-search').fill('__NO_MATCH_INDEPENDENT__')
                assert await page.locator('#sh-list [data-sh-select]').count()==0
                await page.locator('#sh-search').fill('')
                assert await page.locator('#sh-list [data-sh-select]').count()==independent_count
                assert await page.locator('#sh-top10 tbody tr').count()<=10
                assert await page.locator('#sh-research tbody tr').count()<=10
                ranking=page.locator('#sh-research [data-sh-select]')
                chosen=ranking.first if await ranking.count() else page.locator('#sh-list [data-sh-select]').first
                selected_hunter=await chosen.get_attribute('data-sh-select')
                expected=await page.evaluate("t=>{const s=SqueezeStore.getSnapshot(),r=SqueezeStore.getRecord(t);return {id:s.snapshot_id,score:String(r.analysis.observed_score),coverage:String(r.analysis.coverage)}}",selected_hunter)
                await chosen.click()
                await page.wait_for_function("document.body.classList.contains('sq-mode') && !document.body.classList.contains('sh-mode')",timeout=15000)
                assert selected_hunter in await page.locator('#sq-detail h2').inner_text()
                assert await page.locator('#sq-detail').get_attribute('data-ticker')==selected_hunter
                assert await page.locator('#sq-detail').get_attribute('data-observed-score')==expected['score']
                assert await page.locator('#sq-detail').get_attribute('data-coverage')==expected['coverage']
                assert await page.locator('#sq-detail').get_attribute('data-snapshot-id')==expected['id']
                assert await page.locator('#sq-detail .sh-stage-track>div').count()==5
                assert await page.locator('#sq-detail .sq-core-data .sq-panel').count()==5
                assert await page.locator('#sq-detail .sq-score-grid .sq-panel').count()==5
                await page.locator('[data-sq-period="5D"]').click()
                assert await page.locator('[data-sq-period="5D"]').get_attribute('aria-pressed')=='true'
                assert await page.locator('#sq-price svg').count()==1
                if name=='desktop':
                    await page.reload(wait_until='networkidle',timeout=60000)
                    await page.wait_for_function("window.SqueezeStore?.getSnapshot() && !SqueezeStore.isLoading()",timeout=60000)
                    assert selected_hunter in await page.locator('#sq-detail h2').inner_text()
                    assert await page.locator('#sq-detail').get_attribute('data-observed-score')==await page.evaluate('String(SqueezeStore.getRecord().analysis.observed_score)')
                await page.locator('#sq-search').fill(selected_hunter)
                star=page.locator('[data-sq-star="'+selected_hunter+'"]')
                if await star.get_attribute('aria-pressed')!='true':await star.click()
                await page.locator('#sq-search').fill('')
                await page.locator('#sq-back-hunter').click()
                await page.wait_for_function("document.body.classList.contains('sh-mode')",timeout=15000)
                await page.locator('#sh-filter').select_option('favorites')
                assert await page.locator('#sh-list [data-sh-select="'+selected_hunter+'"]').count()==1
                await page.locator('#sh-filter').select_option('all')
                assert await page.evaluate('SqueezeStore.getSelected()')==selected_hunter
                assert await page.locator('#squeeze-hunter').get_attribute('data-snapshot-id')==await page.evaluate('SqueezeStore.getSnapshot().snapshot_id')
                print('shared_snapshot_score_verified '+name,flush=True)
            else:
                assert '수집' in await page.locator('#sh-status').inner_text()
            await page.screenshot(path=f"qa/hunter-{name}.png",full_page=False,timeout=20000)
            assert not await page.evaluate("document.documentElement.scrollWidth > innerWidth"),'independent hunter horizontal overflow'
            await page.locator('a[href="#scan"]').click()
            await page.wait_for_function("!document.body.classList.contains('sh-mode')",timeout=15000)
            if width<768 and await page.locator("#rows [data-ticker]").count():
                assert await page.locator("#rows tr").first.evaluate("el=>getComputedStyle(el).display")=="grid"
                assert await page.locator("#rows tr").first.locator("td").nth(5).get_attribute("data-label")=="Float"
            assert not errors,errors
            overflow=await page.evaluate("document.documentElement.scrollWidth > innerWidth")
            assert not overflow,"page horizontal overflow"
            evidence.append({"viewport":name,"http":response.status,"javascript_errors":errors,"passed":True,"automatic_refresh_verified":refresh_verified,"active_candidates":valid,"float_cells":float_cells,"ctb_cells":ctb_cells,"halt_checked_at":await page.evaluate("report.halt_check?.checked_at || null")})
            print("viewport_passed "+name,flush=True)
            await page.close()
        await browser.close()
    Path("qa/result.json").write_text(json.dumps(evidence,indent=2))
    print(json.dumps(evidence))
async def bounded():
    await asyncio.wait_for(main(),timeout=480)
asyncio.run(bounded())

