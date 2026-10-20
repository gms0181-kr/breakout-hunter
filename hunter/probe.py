"""Log only provider status and record counts, never credentials or response bodies."""
import asyncio, json, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import aiohttp

async def probe():
    now=datetime.now(timezone.utc)
    report={"tested_at":now.isoformat(),"providers":{}}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        cases=[
            ("alpaca","https://data.alpaca.markets/v2/stocks/bars",{"APCA-API-KEY-ID":os.getenv("ALPACA_API_KEY",""),"APCA-API-SECRET-KEY":os.getenv("ALPACA_API_SECRET","")},{"symbols":"SPY","timeframe":"1Day","start":(now-timedelta(days=10)).strftime("%Y-%m-%d"),"end":(now-timedelta(minutes=20)).isoformat(),"feed":"iex","limit":20}),
            ("sec_submissions","https://data.sec.gov/submissions/CIK0000320193.json",{"User-Agent":os.getenv("SEC_USER_AGENT","")},None),
            ("sec_tickers","https://www.sec.gov/files/company_tickers.json",{"User-Agent":os.getenv("SEC_USER_AGENT","")},None)]
        for name,url,headers,params in cases:
            if not all(headers.values()):
                report["providers"][name]={"status":"missing_configuration"}; continue
            try:
                async with session.get(url,headers=headers,params=params) as response:
                    item={"http_status":response.status,"status":"ok" if response.status==200 else "denied"}
                    if response.status==200:
                        data=await response.json(content_type=None)
                        item["records"]=sum(len(v) for v in data.get("bars",{}).values()) if name=="alpaca" else len(data.get("filings",{}).get("recent",{}).get("form",[])) if name=="sec_submissions" else len(data)
                    report["providers"][name]=item
            except Exception as exc:
                report["providers"][name]={"status":"network_error","error_type":type(exc).__name__}
            await asyncio.sleep(.4)
    Path("public").mkdir(exist_ok=True)
    Path("public/connections.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report))
    return report

if __name__=="__main__": asyncio.run(probe())
