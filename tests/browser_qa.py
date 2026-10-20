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
        for name,width,height in (("desktop",1440,1000),("mobile",390,844)):
            page=await browser.new_page(viewport={"width":width,"height":height})
            errors=[]
            page.on("pageerror",lambda err: errors.append(type(err).__name__))
            response=await page.goto(url,wait_until="networkidle",timeout=60000)
            assert response and response.status==200
            await page.wait_for_function("report !== null",timeout=30000)
            assert await page.title()=="BREAKOUT HUNTER 1.0"
            await page.locator("#research").click()
            await page.screenshot(path=f"qa/{name}.png",full_page=True)
            buttons=page.locator("[data-ticker]")
            if await buttons.count():
                await buttons.first.click()
                assert await page.locator("#detail").is_visible()
                await page.locator("#close").click()
            assert not errors,errors
            overflow=await page.evaluate("document.documentElement.scrollWidth > innerWidth")
            assert not overflow,"page horizontal overflow"
            evidence.append({"viewport":name,"http":response.status,"javascript_errors":errors,"passed":True})
            await page.close()
        await browser.close()
    Path("qa/result.json").write_text(json.dumps(evidence,indent=2))
    print(json.dumps(evidence))
asyncio.run(main())
