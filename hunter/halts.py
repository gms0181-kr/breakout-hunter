"""Official halt RSS + recent IEX trade evidence. No broker-orderability gate."""
import hashlib
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from .core import engine_scores, known

RSS_URL="https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts"
TRADE_URL="https://data.alpaca.markets/v2/stocks/trades/latest"
FEED_MAX_AGE=600
TRADE_MAX_AGE=900
ET_ZONE=ZoneInfo("America/New_York")

def instant(value):
    if isinstance(value,datetime): result=value
    else: result=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if result.tzinfo is None: raise ValueError("timezone_required")
    return result.astimezone(timezone.utc)

def et_time(date,time):
    if not date or not time: return None
    return datetime.strptime(date+" "+time,"%m/%d/%Y %H:%M:%S.%f" if "." in time else "%m/%d/%Y %H:%M:%S").replace(tzinfo=ET_ZONE).astimezone(timezone.utc).isoformat()

def field(node,name):
    return next(((child.text or "").strip() for child in node if child.tag.split("}")[-1]==name),"")

def parse_feed(text,checked_at,http_date):
    now=instant(checked_at)
    root=ET.fromstring(text)
    channel=root.find("channel")
    if root.tag!="rss" or channel is None or "NASDAQ" not in field(channel,"title").upper():
        raise ValueError("invalid_rss")
    published=parsedate_to_datetime(field(channel,"pubDate")).astimezone(timezone.utc)
    served=parsedate_to_datetime(http_date).astimezone(timezone.utc)
    for stamp in (published,served):
        age=(now-stamp).total_seconds()
        if age < -60 or age>FEED_MAX_AGE: raise ValueError("stale_feed")
    items=channel.findall("item")
    count=field(channel,"numItems")
    if not count.isdigit() or int(count)!=len(items): raise ValueError("incomplete_feed")
    events=[]
    for item in items:
        symbol=field(item,"IssueSymbol").upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9. /\-]{0,15}",symbol): raise ValueError("invalid_symbol")
        halted=et_time(field(item,"HaltDate"),field(item,"HaltTime"))
        if not halted: raise ValueError("missing_halt_time")
        resumed=et_time(field(item,"ResumptionDate"),field(item,"ResumptionTradeTime"))
        events.append({"ticker":symbol,"halted_at":halted,"resume_scheduled_at":resumed,
                       "reason":field(item,"ReasonCode"),"market":field(item,"Market")})
    return {"status":"ok","source":RSS_URL,"checked_at":now.isoformat(),"published_at":published.isoformat(),
            "expires_at":min(published+timedelta(seconds=FEED_MAX_AGE),now+timedelta(seconds=FEED_MAX_AGE)).isoformat(),
            "server_date":served.isoformat(),"item_count":len(events),"events":events,
            "sha256":hashlib.sha256(text.encode()).hexdigest(),
            "scope":"official current RSS; latest event plus recent IEX trade; not an exchange status guarantee"}

def request(url,headers=None):
    req=urllib.request.Request(url,headers={"User-Agent":"BREAKOUT-HUNTER/1.0",**(headers or {})})
    with urllib.request.urlopen(req,timeout=40) as response:
        return response.read().decode("utf-8-sig"),response.headers.get("Date","")

def snapshot():
    now=datetime.now(timezone.utc)
    try:
        # A fresh snapshot avoids duplicate Nasdaq queries during concurrent jobs.
        cached=json.loads(Path("public/halts.json").read_text())
        if cached.get("status")=="ok" and 0<=(now-instant(cached["checked_at"])).total_seconds()<60:
            return cached
    except (OSError,ValueError,KeyError,TypeError): pass
    try:
        text,date=request(RSS_URL)
        return parse_feed(text,datetime.now(timezone.utc),date)
    except Exception as exc:
        return {"status":"unavailable","source":RSS_URL,"checked_at":now.isoformat(),"events":[],
                "error":type(exc).__name__+": "+str(exc)[:120]}

def recent_trades(symbols):
    key=os.getenv("ALPACA_API_KEY")
    secret=os.getenv("ALPACA_API_SECRET")
    if not key or not secret: return {},["latest_trade_credentials_missing"]
    from urllib.parse import urlencode
    trades,errors={},[]
    symbols=sorted(set(symbols))
    for i in range(0,len(symbols),100):
        try:
            text,_=request(TRADE_URL+"?"+urlencode({"symbols":",".join(symbols[i:i+100]),"feed":"iex"}),
                {"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret})
            payload=json.loads(text)
            if not isinstance(payload.get("trades"),dict): raise ValueError("invalid_trade_response")
            trades.update(payload["trades"])
        except Exception as exc: errors.append(type(exc).__name__)
    return trades,errors

def classify(ticker,feed,trade,now):
    now=instant(now)
    evidence={"status":"unverified","source":RSS_URL,"checked_at":feed.get("checked_at"),
              "feed_published_at":feed.get("published_at"),"trade_source":TRADE_URL,"trade_feed":"iex"}
    try:
        if feed.get("status")!="ok" or instant(feed["expires_at"])<=now:
            evidence["reason"]="공식 정지 자료 조회 실패 또는 유효시간 만료"; return evidence
        if instant(feed["checked_at"])>now+timedelta(seconds=60):
            raise ValueError("future_snapshot")
        events=sorted([e for e in feed["events"] if e["ticker"]==ticker],key=lambda e:instant(e["halted_at"]),reverse=True)
        event=events[0] if events else None
        if event:
            evidence["event"]=event
            halt_at=instant(event["halted_at"])
            if halt_at>now: raise ValueError("future_halt")
            resume=instant(event["resume_scheduled_at"]) if event.get("resume_scheduled_at") else None
            if not resume or resume>now or event.get("reason")=="D":
                evidence.update(status="halted",reason="정지 기록 존재; 거래재개 체결 미확인")
                return evidence
        stamp=instant((trade or {}).get("t"))
        age=(now-stamp).total_seconds()
        if not known((trade or {}).get("p")) or trade["p"]<=0 or age<0 or age>TRADE_MAX_AGE:
            raise ValueError("no_recent_trade")
        if event and (stamp<instant(event["resume_scheduled_at"]) or stamp<=instant(event["halted_at"])):
            raise ValueError("no_post_resume_trade")
        expiry=min(instant(feed["expires_at"]),stamp+timedelta(seconds=TRADE_MAX_AGE))
        evidence.update(status="resumed" if event else "no_halt_detected",
            reason="재개 예정 시각 이후 체결 확인" if event else "공식 RSS 정지 미감지 + 최근 IEX 체결 확인",
            trade_at=stamp.isoformat(),trade_price=trade["p"],expires_at=expiry.isoformat())
        return evidence
    except (ValueError,TypeError,KeyError,OverflowError):
        evidence["reason"]="최근 15분 IEX 체결 미확인 또는 자료 형식 오류"
        return evidence

def eligible(stock,cap,now=None):
    now=instant(now or datetime.now(timezone.utc))
    value=stock.get("market_cap")
    evidence=stock.get("halt_check") or {}
    try:
        return (known(value) and 0<value<=cap
            and evidence.get("status") in ("no_halt_detected","resumed")
            and instant(evidence["expires_at"])>now
            and instant(evidence["checked_at"])<=now
            and stock.get("halt_status")==evidence["status"])
    except (ValueError,KeyError,TypeError): return False

def check_stocks(stocks,cap):
    feed=snapshot()
    candidate_symbols=[s["ticker"] for s in stocks if known(s.get("market_cap")) and 0<s["market_cap"]<=cap and engine_scores(s)["candidate"]]
    trades,errors=recent_trades(candidate_symbols) if feed["status"]=="ok" else ({},["halt_feed_unavailable"])
    now=datetime.now(timezone.utc)
    for stock in stocks:
        result=classify(stock["ticker"],feed,trades.get(stock["ticker"]),now)
        stock["halt_check"]=result
        stock["halt_status"]=result["status"]
        stock["eligibility"]="eligible" if eligible(stock,cap,now) else "검증 대기"
    counts={}
    for stock in stocks: counts[stock["halt_status"]]=counts.get(stock["halt_status"],0)+1
    feed["trade_errors"]=errors
    feed["status_counts"]=counts
    Path("public/halts.json").write_text(json.dumps(feed,ensure_ascii=False))
    print(json.dumps({"halt_source":feed["status"],"items":feed.get("item_count"),"counts":counts,"trade_error_count":len(errors)}))
    return feed

def refresh_report():
    from .core import rank
    path=Path("public/data.json")
    report=json.loads(path.read_text())
    stocks=list({s["ticker"]:s for group in ("watchlist","research_top10","top10") for s in report.get(group,[])}.values())
    feed=check_stocks(stocks,report.get("config",{}).get("market_cap_max",2000000000))
    top,_=rank([s for s in stocks if s["eligibility"]=="eligible"])
    checked={s["ticker"]:s for s in stocks}
    for group in ("watchlist","research_top10"):
        report[group]=[checked[s["ticker"]] for s in report.get(group,[])]
    if report.get("top10"):
        report["last_top10"]=report["top10"]
        report["last_top10_as_of"]=report.get("ranking_updated_at",report.get("updated_at"))
    report["top10"]=top
    report["halt_check"]={k:v for k,v in feed.items() if k!="events"}
    report["ranking_updated_at"]=feed["checked_at"]
    report["ranking_scope"]="stored watchlist + research list; price scan timestamp unchanged"
    report["top10_status"]="시총·정지 점검 후보; Float·숏·SEC 공급 검증 미완료; 토스 매수 가능 여부 사용자 확인"
    report["coverage"]["halt_filter_status"]="공식 RSS + 최근 IEX 체결 대조; 상태별 유효시간 적용"
    report["limitations"]=[x for x in report.get("limitations",[]) if "halt filters pending" not in x]
    path.write_text(json.dumps(report,ensure_ascii=False,allow_nan=False))
    print(json.dumps({"top10_count":len(top),"tickers":[s["ticker"] for s in top],"ranking_scope":report["ranking_scope"]}))

if __name__=="__main__": refresh_report()
