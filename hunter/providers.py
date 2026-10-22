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
from .scope import security_reason,scope_reason,MAX_CAP

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
    raise RuntimeError(type(error).__name__ if error else "provider_rate_limit")

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
            if not symbol or not exchange or row.get("ETF")!="N" or row.get("Test Issue")!="N" or security_reason({"name":name}): continue
            if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}",symbol): continue
            stocks[symbol]={"ticker":symbol,"name":name,"exchange":exchange,"universe_source":NASDAQ_ROOT+("nasdaqlisted.txt" if i==0 else "otherlisted.txt"),"security_type_status":"Nasdaq listing name/ETF product exclusion; common shares/ADS","halt_status":"unverified"}
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
        params={"symbols":",".join(group),"timeframe":"1Day","start":(today-timedelta(days=400)).strftime("%Y-%m-%d"),"end":(today-timedelta(minutes=20)).isoformat(),"limit":10000,"adjustment":"split","feed":"iex","sort":"asc"}
        try:
            while True:
                data=await fetch(session,"https://data.alpaca.markets/v2/stocks/bars",headers=headers,params=params)
                for ticker,items in data.get("bars",{}).items():
                    output.setdefault(ticker,[]).extend({"time":b["t"],"open":b["o"],"high":b["h"],"low":b["l"],"close":b["c"],"volume":b["v"],"vwap":b.get("vw"),"available_at":today.isoformat(),"complete":datetime.fromisoformat(b["t"].replace("Z","+00:00"))+timedelta(days=1)<=today-timedelta(minutes=20),"source_adjustment":"split; latest provider basis, historical replay not certified"} for b in items)
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

async def screener_metadata(session):
    url="https://api.nasdaq.com/api/screener/stocks"
    try:
        data=await fetch(session,url,headers={"User-Agent":"BREAKOUT-HUNTER/1.0"},params={"tableonly":"true","limit":"10000"})
        rows=(data.get("data") or {}).get("table",{}).get("rows",[])
        def number(v):
            try: return float(re.sub(r"[^0-9.\\-]","",str(v)))
            except (ValueError,TypeError): return None
        return {r["symbol"]:{"market_cap":number(r.get("marketCap")),"industry":r.get("industry"),"sector":r.get("sector"),"market_cap_source":url,"market_cap_as_of":datetime.now(timezone.utc).isoformat()} for r in rows if r.get("symbol")},[]
    except (RuntimeError,AttributeError):
        return {},[{"provider":"Nasdaq screener","error":"시총 메타데이터 접근 실패; 미확인 유지"}]

async def collect(config):
    async with aiohttp.ClientSession() as session:
        stocks,failures=await universe(session)
        metadata,metadata_errors=await screener_metadata(session)
        failures+=metadata_errors
        source_count=len(stocks)
        excluded={}
        selected={}
        for symbol,stock in stocks.items():
            stock.update(metadata.get(symbol,{}))
            reason=scope_reason(stock,config.get("market_cap_max",MAX_CAP),include_trading=False)
            if reason:excluded[reason]=excluded.get(reason,0)+1
            else:selected[symbol]=stock
        stocks=selected
        symbols=scan_order(stocks,datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        histories,errors=await bars(session,symbols)
        failures+=errors
        missing=[symbol for symbol in symbols if not histories.get(symbol)]
        if missing and os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET"):
            retried,retry_errors=await bars(session,missing)
            failures+=retry_errors
            histories.update({symbol:items for symbol,items in retried.items() if items})
            failures += [{"provider":"Alpaca","ticker":symbol,"error":"no_bars_after_retry"} for symbol in missing if not histories.get(symbol)]
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
            stock.update(metadata.get(symbol,{}))
        from .splits import snapshot as split_snapshot,apply as apply_splits
        split_feed=await split_snapshot(session,fetch)
        apply_splits(stocks.values(),split_feed)
        config['_split_feed']={k:v for k,v in split_feed.items() if k!='events'}
        # Independent signals select SEC enrichment, not alphabetical order.
        from .core import engine_scores
        from .verification import verify
        from .sec import analyze,outstanding_fact
        # Transparent SEC budget; never presented as full SEC scan.
        priority=sorted((s for s in stocks.values() if s["bars"] and scope_reason(s,config.get("market_cap_max",MAX_CAP)) is None),key=lambda s:((verify(s)["market"]["confirmed_capital"] and verify(s)["market"]["confirmed_structure"]),engine_scores(s)["score"] or 0),reverse=True)
        sec_count=0
        selected=priority[:config.get("sec_budget",20)]
        # INLF is a disclosed validation case, not a ranking bonus.
        if "INLF" in stocks and stocks["INLF"] not in selected:selected.append(stocks["INLF"])
        for stock in selected:
            cik=ciks.get(stock["ticker"])
            if cik:
                stock["sec"]=await sec_timeline(session,cik)
                stock["sec"]=await analyze(session,cik,stock["sec"],budget=2)
                fact=await outstanding_fact(session,cik,datetime.now(timezone.utc).isoformat())
                if fact:
                    stock["outstanding"]=fact["value"]
                    stock["outstanding_fact"]=fact
                sec_count+=1
                await asyncio.sleep(.3)
        from .backtest import replay
        replay_result=await replay(session)
        from .inlf_case import replay_inlf
        config["_inlf_case"]=await replay_inlf(session,ciks.get("INLF"))
        try:
            fx=await fetch(session,"https://api.frankfurter.app/latest",params={"from":"USD","to":"KRW"})
            config["_fx"]={"rate":fx["rates"]["KRW"],"as_of":fx["date"],"source":"https://www.frankfurter.app/","type":"daily reference, not live"}
        except (RuntimeError,KeyError): config["_fx"]=None
        config["_backtest"]=replay_result
        return list(stocks.values()),{"universe":len(stocks),"listing_companies_before_cap_filter":source_count,"scope_exclusions":excluded,"attempted":len(symbols) if os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET") else 0,"processed":sum(bool(s["bars"]) for s in stocks.values()),"universe_complete":not any("source" in e for e in failures),"sec_processed":sec_count,"failures":failures,"market_cap_filter_status":"Nasdaq 시총 수집 "+str(len(metadata))+"개; 미확인 별도 보류","halt_filter_status":"거래정지 데이터 연결 필요"}

