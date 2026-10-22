"""Public source-reported Float and IBKR CTB; provenance is kept per field."""
import concurrent.futures
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime,timezone,timedelta
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo
from .core import known

CACHE=Path("public/enrichment.json")
class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.skip=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style"):self.skip+=1
    def handle_endtag(self,tag):
        if tag in ("script","style") and self.skip:self.skip-=1
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)
def plain(html):
    p=Text();p.feed(html);return re.sub(r"\s+"," "," ".join(p.parts)).strip()
def number(text):
    match=re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([KMB]?)",str(text).strip().replace(",","").upper())
    if not match:return None
    value=float(match[1])*{"":1,"K":1000,"M":1000000,"B":1000000000}[match[2]]
    return int(round(value)) if value>0 else None
def metric(text,label):
    m=re.search(r"(?:^|\s)"+re.escape(label)+r"\s+([0-9][0-9,.]*[KMB]?)(?=\s|$)",text)
    return (number(m[1]),m[1]) if m else (None,None)
def identity(html,ticker):
    title=re.search(r"<title[^>]*>(.*?)</title>",html,re.I|re.S)
    if not title or not re.search(r"\b"+re.escape(ticker)+r"\b",plain(title[1]),re.I):
        raise ValueError("symbol_identity_mismatch")
def overview(html,ticker):
    identity(html,ticker);text=plain(html)
    value,raw=metric(text,"Float")
    outstanding,_=metric(text,"Shares Out")
    if value is not None and outstanding is not None and value>outstanding*1.02:
        raise ValueError("float_exceeds_outstanding")
    split=re.search(r"Last Split\s+([A-Za-z]{3} \d{1,2}, \d{4})\s*[·•]?\s*([0-9]+-for-[0-9]+(?:\s*\(reverse\))?)",text)
    return {"value":value,"raw":raw,"outstanding_reference":outstanding,
            "source_as_of":None,"date_note":"공급자가 Float 기준일을 명시하지 않음; 조회시각과 구분",
            "approximate":bool(raw and re.search("[KMB]",raw)),
            "last_split":split[0] if split else None,"last_split_date":datetime.strptime(split[1],"%b %d, %Y").date().isoformat() if split else None}
def finviz(html,ticker):
    identity(html,ticker);text=plain(html)
    value,raw=metric(text,"Shs Float")
    return {"value":value,"raw":raw,"approximate":bool(raw and re.search("[KMB]",raw)),
            "source_as_of":None,"date_note":"공급자가 Float 기준일을 명시하지 않음"}
def borrow(html,ticker):
    identity(html,ticker);text=plain(html)
    m=re.search(r"As of\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [AP]M (?:EDT|EST))\s*,\s*there were\s+([\d,]+)\s+shares available with a fee of\s+([\d.]+)\s*%",text)
    if not m:return {"ctb":None,"available":None,"status":"공개 CTB 요약 값 없음"}
    stamp=datetime.strptime(m[1][:-4],"%Y-%m-%d %I:%M:%S %p").replace(tzinfo=ZoneInfo("America/New_York"))
    if stamp.tzname()!=m[1][-3:]:raise ValueError("borrow_timezone_mismatch")
    rate=float(m[3])
    if rate<0 or rate>100000:raise ValueError("invalid_borrow_rate")
    return {"ctb":rate,"available":int(m[2].replace(",","")),"as_of":stamp.astimezone(timezone.utc).isoformat(),
            "lender":"Interactive Brokers","cross_verified":False,"status":"공개 출처 확인 · Fintel 교차 대조 미완료"}
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"BREAKOUT-HUNTER/1.0"})
    with urllib.request.urlopen(req,timeout=18) as res:
        text=res.read().decode("utf-8")
        return text
def observe(url,parser,ticker):
    now=datetime.now(timezone.utc).isoformat()
    try:
        html=get(url);value=parser(html,ticker)
        return {**value,"source":url,"observed_at":now,"http":200,"sha256":hashlib.sha256(html.encode()).hexdigest()}
    except urllib.error.HTTPError as exc:
        return {"source":url,"observed_at":now,"error":"HTTP "+str(exc.code)}
    except Exception as exc:
        return {"source":url,"observed_at":now,"error":type(exc).__name__+": "+str(exc)[:90]}
def combine_float(sources):
    values=[s for s in sources if known(s.get("value")) and s["value"]>0]
    if len(values)>=2:
        low=min(s["value"] for s in values);high=max(s["value"] for s in values)
        if (high-low)/high>0.05:return {"status":"conflict","display_value":None,"sources":sources}
        return {"status":"matched","display_value":values[0]["value"],"approximate":any(s.get("approximate") for s in values),"sources":sources}
    if values:return {"status":"single_source","display_value":values[0]["value"],"approximate":values[0].get("approximate",False),"sources":sources}
    return {"status":"unavailable","display_value":None,"sources":sources}
def enrich_one(stock):
    ticker=stock["ticker"]
    exchange={"NASDAQ":"nasdaq","NYSE":"nyse","NYSE American":"nyseamerican"}.get(stock.get("exchange"))
    if not exchange:return {"ticker":ticker,"observed_at":datetime.now(timezone.utc).isoformat(),"error":"exchange_not_mapped","borrow":{"ctb":None,"available":None,"status":"거래소 매핑 미지원 · CTB 조회 불가"}}
    base="https://chartexchange.com/symbol/"+exchange+"-"+ticker.lower()+"/"
    a=observe(base,overview,ticker);time.sleep(.15)
    b=observe("https://finviz.com/quote.ashx?t="+ticker,finviz,ticker);time.sleep(.15)
    c=observe(base+"borrow-fee/",borrow,ticker)
    from .short_reports import official_interest
    si=observe(base+"short-interest/",official_interest,ticker)
    combined=combine_float([a,b])
    flags=[]
    if "Depositary" in stock.get("name","") or "ADS" in stock.get("name",""):
        flags.append("ADS/원주 환산 기준 추가 확인 필요")
    try:
        if a.get("last_split_date") and (datetime.now(timezone.utc).date()-datetime.fromisoformat(a["last_split_date"]).date()).days<=30:
            flags.append("최근 30일 병합·분할: 수량 기준 추가 확인 필요")
    except ValueError:pass
    combined["flags"]=flags
    return {"ticker":ticker,"name":stock.get("name"),"observed_at":datetime.now(timezone.utc).isoformat(),
            "float":combined,"borrow":c,"short_interest":si,"fintel_url":"https://fintel.io/ss/us/"+ticker.lower()}
def load_cache():
    try:return json.loads(CACHE.read_text())
    except (OSError,ValueError):return {"symbols":{}}
def apply_cached(stocks,cache=None):
    cache=cache or load_cache()
    for s in stocks:
        obs=cache.get("symbols",{}).get(s["ticker"])
        if not obs:continue
        s["enrichment"]=obs
        info=obs.get("float",{})
        # Only agreeing public references, without known share-basis caveats, enter F.
        s["float"]=info.get("display_value") if info.get("status")=="matched" and not info.get("flags") and not info.get("stale") else None
        b=obs.get("borrow",{})
        if known(b.get("ctb")):
            s["short"]={**(s.get("short") or {}),**b,"status":"ChartExchange/IBKR 출처 확인; Fintel 교차 대조 미완료"}
    return stocks
def collection_targets(report,symbols,now=None):
    """Visit every due candidate; unseen symbols first, then oldest attempts.

    A fixed prefix starved new candidates whenever prior observations expired.
    Failed attempts retain a timestamp and a reason instead of looping first.
    """
    now=now or datetime.now(timezone.utc)
    ordered={}
    for group in ("top10","research_top10","last_top10","watchlist","verification_candidates"):
        for stock in report.get(group,[]):ordered.setdefault(stock["ticker"],stock)
    def attempted(ticker):
        try:
            stamp=datetime.fromisoformat(symbols[ticker]["observed_at"].replace('Z','+00:00'))
            return stamp.timestamp() if stamp.tzinfo else 0
        except (KeyError,TypeError,ValueError):return 0
    targets=[s for t,s in ordered.items() if not symbols.get(t,{}).get('borrow') or now.timestamp()-attempted(t)>=900]
    targets.sort(key=lambda s:(bool(symbols.get(s['ticker'],{}).get('borrow')),attempted(s['ticker'])))
    return ordered,targets

def main():
    report=json.loads(Path("public/data.json").read_text())
    cache=load_cache();symbols=cache.setdefault("symbols",{})
    import asyncio
    from .market_session import standalone
    cache["market_calendar"]=asyncio.run(standalone())
    ordered,targets=collection_targets(report,symbols)
    existing={s['ticker'] for s in targets}
    targets += [s for t,s in ordered.items() if t not in existing and 'short_interest' not in symbols.get(t,{})]
    from .short_reports import latest_finra
    daily,volume_status=latest_finra(get)
    cache['short_volume_source']=volume_status
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(enrich_one,targets):
            ticker=result["ticker"]
            prior=symbols.get(ticker)
            history=list((prior or {}).get("borrow_history",[]))
            obs=result.get("borrow",{})
            if known(obs.get("ctb")) and obs.get("as_of") and not any(x.get("as_of")==obs["as_of"] for x in history):
                history.append({k:obs.get(k) for k in ("ctb","available","as_of","observed_at","source","lender")})
            result["borrow_history"]=history[-240:]
            result['short_volume']=daily.get(ticker,{**volume_status,'status':'symbol_not_in_latest_file' if volume_status.get('status')=='ok' else 'source_unavailable'})
            if prior:
                # Keep last observed numbers explicitly historical after a retrieval error.
                for field,key in (("float","display_value"),("borrow","ctb"),("short_interest","shares"),("short_volume","short_volume")):
                    if result.get(field,{}).get(key) is None and prior.get(field,{}).get(key) is not None and result.get(field,{}).get("status")!="conflict":
                        failed=result.get(field,{})
                        result[field]={**prior[field],"stale":True,"refresh_error":failed}
            symbols[ticker]=result
    cache["updated_at"]=datetime.now(timezone.utc).isoformat()
    # Public Fintel access is tested once, not repeatedly against a denied endpoint.
    probe_ticker=targets[0]["ticker"] if targets else next(iter(ordered),"PRSO")
    try:
        page=get("https://fintel.io/ss/us/"+probe_ticker.lower())
        cache["fintel_access"]={"status":"public_page_received","symbol":probe_ticker,"note":"별도 CTB 숫자 파싱·교차 확인 전"}
    except urllib.error.HTTPError as exc:
        cache["fintel_access"]={"status":"HTTP "+str(exc.code),"symbol":probe_ticker,"note":"자동 조회 표본의 접근 거부; 우회하지 않음"}
    except Exception as exc:cache["fintel_access"]={"status":type(exc).__name__,"symbol":probe_ticker}
    CACHE.write_text(json.dumps(cache,ensure_ascii=False,allow_nan=False))
    print(json.dumps({"enriched_this_run":len(targets),"cached_symbols":len(symbols),
        "float_values":sum(s.get("float",{}).get("display_value") is not None for s in symbols.values()),
        "float_matched":sum(s.get("float",{}).get("status")=="matched" for s in symbols.values()),
        "ctb_values":sum(s.get("borrow",{}).get("ctb") is not None for s in symbols.values()),
        "fintel":cache["fintel_access"]},ensure_ascii=False))
if __name__=="__main__":main()

