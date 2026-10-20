"""Reconstruct raw daily observations, not a certified point-in-time ranking."""
import asyncio, os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .providers import fetch,sec_timeline
DATES=("2026-10-12","2026-10-14","2026-10-16","2026-10-19")

async def replay(session):
    key=os.getenv("ALPACA_API_KEY"); secret=os.getenv("ALPACA_API_SECRET")
    result={"status":"partial raw-price reconstruction; historical all-market rank unavailable","HUBC":[]}
    sec=await sec_timeline(session,1905660)
    for day in DATES:
        cutoff=datetime.fromisoformat(day+"T16:00:00").replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
        row={"date":day,"as_of":cutoff.isoformat(),"detected":None,"time":None,"rank":None,"float":None,"short":None,"scores":None,"volume_ratio":None,"sec":{"reviewed":False,"timeline":[x for x in sec.get("timeline",[]) if x.get("accepted",x["filed"])[:10]<day]},"reason":"당시 전체시장 스냅샷 없음; Float/short/SEC 공급 미확인"}
        # Same-day filings without normalized acceptance timestamps are withheld.
        if not key or not secret:
            row["reason"]="시세 인증 정보 없음";result["HUBC"].append(row);continue
        try:
            data=await fetch(session,"https://data.alpaca.markets/v2/stocks/HUBC/bars",headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret},params={"timeframe":"1Day","start":(cutoff-timedelta(days=400)).strftime("%Y-%m-%d"),"end":cutoff.isoformat(),"adjustment":"raw","feed":"iex","limit":1000,"sort":"asc","asof":day})
            bars=[x for x in data.get("bars",[]) if x["t"][:10]<=day]
            market_open=cutoff-timedelta(hours=6,minutes=30)
            minute_data=await fetch(session,"https://data.alpaca.markets/v2/stocks/HUBC/bars",headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret},params={"timeframe":"1Min","start":market_open.isoformat(),"end":cutoff.isoformat(),"adjustment":"raw","feed":"iex","limit":10000,"sort":"asc","asof":day})
            minutes=[x for x in minute_data.get("bars",[]) if market_open<=datetime.fromisoformat(x["t"].replace("Z","+00:00"))<cutoff]
            today=[{"t":market_open.isoformat(),"o":minutes[0]["o"],"h":max(x["h"] for x in minutes),"l":min(x["l"] for x in minutes),"c":minutes[-1]["c"],"v":sum(x["v"] for x in minutes)}] if minutes else []
            row["regular_session_minute_count"]=len(minutes)
            row["bars_count"]=len(bars)
            row["observed_daily_bar"]=today[-1] if today else None
            row["source"]="Alpaca IEX raw regular-session minute bars; historical baseline daily bars not scored"
            row["reason"]="일봉 수집됨; 병합 당시 기준 검증·통합 거래량·과거 전체시장 스냅샷 부족으로 V/R 점수 및 탐지 시각/순위 보류" if today else "해당 날짜 IEX 일봉 없음"
            row["lookahead_guard"]="end/asof=당일; raw prices; 미래 공시 제외. 공급처의 사후 정정 여부 미검증"
        except RuntimeError:
            row["reason"]="과거 시세 API 접근 실패"
        result["HUBC"].append(row)
        await asyncio.sleep(.4)
    return result
