"""Public reference adapters + authenticated Alpaca IEX daily bars.
No paid-page scraping, invented float, or fabricated borrow data.
"""
import asyncio
import csv
import io
import os
import re
import aiohttp
from datetime import datetime, timedelta, timezone
from .core import scan_order

NASDAQ_ROOT="https://www.nasdaqtrader.com/dynamic/SymDir/"
EXCLUDED=re.compile(r"\b(warrants?|rights?|preferred|debentures?|notes?|units?|exchange.traded|ETN|ETF|acquisition corp)\b",re.I)

async def fetch(session,url,headers=None,params=None,text=False):
    error=None
    for attempt in range(3):
        try:
            async with session.get(url,headers=headers,params=params,timeout=aiohttp.ClientTimeout(total=35)) as response:
                if response.status==429 or response.status>=500:
                    await asyncio.sleep(min(8,2**attempt)); continue
                response.raise_for_status()
                return await response.text() if text else await response.json(content_type=None)
        except (aiohttp.ClientError,asyncio.TimeoutError,ValueError) as exc:
            error=exc
            await asyncio.sleep(2**attempt)
    raise RuntimeError(str(error or "provider rate limit"))

async def universe(session):
    results=await asyncio.gather(*[fetch(session,NASDAQ_ROOT+name,text=True) for name in ("nasdaqlisted.txt","otherlisted.txt")],return_exceptions=True)
    stocks={}
    errors=[]
    for i,result in enumerate(results):
        if isinstance(result,Exception):
            errors.append({"source":("NASDAQ","NYSE/NYSE American")[i],"error":str(result)})
            continue
        for row in csv.DictReader(io.StringIO(result),delimiter="|"):
            symbol=row.get("Symbol") if i==0 else row.get("ACT Symbol")
            name=row.get("Security Name","")
            exchange="NASDAQ" if i==0 else {"N":"NYSE","A":"NYSE American"}.get(row.get("Exchange"))
            if not symbol or not exchange or row.get("ETF")!="N" or row.get("Test Issue")!="N" or EXCLUDED.search(name): continue
            if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}",symbol): continue
            stocks[symbol]={"ticker":symbol,"name":name,"exchange":exchange,"universe_source":NASDAQ_ROOT+("nasdaqlisted.txt" if i==0 else "otherlisted.txt"),"security_type_status":"name/ETF filter; manual exceptions pending","halt_status":"unverified"}
    return stocks,errors

async def bars(session,symbols):
    key=os.getenv("ALPACA_API_KEY")
    secret=os.getenv("ALPACA_API_SECRET")
    if not key or not secret:
        return {},[{"provider":"Alpaca","error":"연결 필요: ALPACA_API_KEY / ALPACA_API_SECRET"}]
    headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret}
    output={}
    errors=[]
    today=datetime.now(timezone.utc)
    for offset in range(0,len(symbols),100):
        group=symbols[offset:offset+100]
        params={"symbols":",".join(group),"timeframe":"1Day","start":(today-timedelta(days=400)).strftime("%Y-%m-%d"),"end":today.isoformat(),"limit":10000,"adjustment":"split","feed":"iex","sort":"asc"}
        try:
            while True:
                data=await fetch(session,"https://data.alpaca.markets/v2/stocks/bars",headers=headers,params=params)
                for ticker,items in data.get("bars",{}).items():
                    output.setdefault(ticker,[]).extend({"time":b["t"],"open":b["o"],"high":b["h"],"low":b["l"],"close":b["c"],"volume":b["v"]} for b in items)
                token=data.get("next_page_token")
                if not token: break
                params["page_token"]=token
            await asyncio.sleep(.4)
        except RuntimeError as exc: errors.extend({"ticker":s,"error":str(exc)} for s in group)
    return output,errors

async def sec_index(session):
    agent=os.getenv("SEC_USER_AGENT")
    if not agent: return {},[{"provider":"SEC","error":"연결 필요: SEC_USER_AGENT (organization contact-email)"}]
    try:
        data=await fetch(session,"https://www.sec.gov/files/company_tickers.json",headers={"User-Agent":agent})
        return {v["ticker"]:v["cik_str"] for v in data.values()},[]
    except RuntimeError as exc: return {},[{"provider":"SEC","error":str(exc)}]

async def sec_timeline(session,cik):
    agent=os.getenv("SEC_USER_AGENT")
    if not agent: return {"status":"연결 필요","reviewed":False}
    url="https://data.sec.gov/submissions/CIK"+str(cik).zfill(10)+".json"
    try:
        data=await fetch(session,url,headers={"User-Agent":agent})
        recent=data["filings"]["recent"]
        timeline=[]
        relevant={"S-1","S-1/A","S-3","S-3/A","F-1","F-1/A","F-3","F-3/A","EFFECT","424B3","424B5","8-K","6-K","10-Q","10-K","20-F"}
        for i,form in enumerate(recent.get("form",[])):
            if form not in relevant: continue
            accession=recent["accessionNumber"][i]
            document=recent["primaryDocument"][i]
            timeline.append({"form":form,"filed":recent["filingDate"][i],"accepted":recent.get("acceptanceDateTime",recent["filingDate"])[i],"source":f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-','')}/{document}","status":"원문·첨부계약 검토 필요; 공급 상태 미확인"})
            if len(timeline)>=30: break
        return {"status":"공시 목록 수집; 원문/계약 분석 미완료","reviewed":False,"source":url,"timeline":timeline,"evidence":[]}
    except RuntimeError as exc: return {"status":str(exc),"reviewed":False}

async def collect(config):
    async with aiohttp.ClientSession() as session:
        stocks,failures=await universe(session)
        symbols=scan_order(stocks,datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        histories,errors=await bars(session,symbols)
        failures+=errors
        ciks,errors=await sec_index(session)
        failures+=errors
        # Full universe is attempted. SEC secondary coverage is separately counted.
        for symbol,stock in stocks.items():
            stock["bars"]=histories.get(symbol,[])
            stock["volume"]=stock["bars"][-1]["volume"] if stock["bars"] else None
            stock["price"]=stock["bars"][-1]["close"] if stock["bars"] else None
            stock["price_as_of"]=stock["bars"][-1]["time"] if stock["bars"] else None
            stock["change_pct"]=(stock["price"]/stock["bars"][-2]["close"]-1)*100 if len(stock["bars"])>1 else None
            stock.update({"float":None,"outstanding":None,"market_cap":None,"toss_orderable":config.get("toss_orderable",{}).get(symbol),"short":{"status":"연결 필요: ChartExchange/Fintel 라이선스 데이터"},"sec":{"status":"원문 분석 대기","reviewed":False},"price_source":"https://docs.alpaca.markets/docs/historical-stock-data-1","feed":"IEX 부분 거래소 일봉; 통합 거래량 아님","chartexchange":"https://chartexchange.com/symbol/"+symbol.lower()+"/"})
        # Transparent SEC budget; never presented as full SEC scan.
        priority=sorted((s for s in stocks.values() if s["bars"]),key=lambda s:s["volume"] or 0,reverse=True)
        sec_count=0
        for stock in priority[:config.get("sec_budget",20)]:
            cik=ciks.get(stock["ticker"])
            if cik:
                stock["sec"]=await sec_timeline(session,cik)
                sec_count+=1
                await asyncio.sleep(.3)
        return list(stocks.values()),{"universe":len(stocks),"attempted":len(symbols) if os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET") else 0,"processed":sum(bool(s["bars"]) for s in stocks.values()),"universe_complete":not any("source" in e for e in failures),"sec_processed":sec_count,"failures":failures,"market_cap_filter_status":"시가총액 데이터 미연결; eligibility pending","halt_filter_status":"거래정지 데이터 연결 필요"}
