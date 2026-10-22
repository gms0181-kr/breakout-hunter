"""Post-deployment QA. No API credentials are present in this job."""
import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    url=os.environ["SITE_URL"]
    Path("qa").mkdir(exist_ok=True)
    evidence=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        for name,width,height in (("desktop",1440,1000),("mobile",390,844),("small-mobile",320,740),("tablet",768,1024),("wide-desktop",1920,1080)):
            page=await browser.new_page(viewport={"width":width,"height":height})
            errors=[]
            page.on("pageerror",lambda err: errors.append(type(err).__name__))
            response=await page.goto(url,wait_until="networkidle",timeout=60000)
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
            await page.screenshot(path=f"qa/{name}.png",full_page=True)
            buttons=page.locator("[data-ticker]")
            if await buttons.count():
                await buttons.first.click()
                assert await page.locator("#detail").is_visible()
                await page.locator("#close").click()
            if width<768 and await page.locator("#rows [data-ticker]").count():
                assert await page.locator("#rows tr").first.evaluate("el=>getComputedStyle(el).display")=="grid"
                assert await page.locator("#rows tr").first.locator("td").nth(5).get_attribute("data-label")=="Float"
            assert not errors,errors
            overflow=await page.evaluate("document.documentElement.scrollWidth > innerWidth")
            assert not overflow,"page horizontal overflow"
            evidence.append({"viewport":name,"http":response.status,"javascript_errors":errors,"passed":True,"automatic_refresh_verified":refresh_verified,"active_candidates":valid,"float_cells":float_cells,"ctb_cells":ctb_cells,"halt_checked_at":await page.evaluate("report.halt_check?.checked_at || null")})
            await page.close()
        await browser.close()
    Path("qa/result.json").write_text(json.dumps(evidence,indent=2))
    print(json.dumps(evidence))
asyncio.run(main())

