import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .providers import collect
from .core import rank

async def main():
    config=json.loads(Path("config.json").read_text())
    stocks,coverage=await collect(config)
    # Unknown market cap / halt status cannot silently qualify for the small-cap TOP 10.
    for stock in stocks:
        cap=stock.get("market_cap")
        stock["eligibility"]="eligible" if cap is not None and cap<=config["market_cap_max"] and stock.get("halt_status")=="trading" else "검증 대기"
    eligible=[s for s in stocks if s["eligibility"]=="eligible"]
    top,_=rank(eligible)
    _,scored=rank(stocks)
    now=datetime.now(timezone.utc).isoformat()
    report={"updated_at":now,"status":"partial","coverage":coverage,"top10":top,"watchlist":sorted([s for s in scored if s["candidate"]],key=lambda s:-(s["score"] or 0))[:100],"config":config,"fx":None,"limitations":["EOD IEX feed: no consolidated or real-time volume","Float / CTB / short-interest data not connected","SEC timeline only: legal issuance/free-sale analysis pending","Toss order eligibility unverified unless explicitly evidenced","Market cap and halt filters pending: TOP 10 withheld"],"backtest":{"status":"blocked: point-in-time source snapshots absent","HUBC":[{"date":d,"detected":None,"time":None,"scores":None,"rank":None,"float":None,"volume_ratio":None,"short":None,"sec":None,"reason":"당시 이용 가능했던 검증된 가격/Float/SEC 증거 스냅샷 없음; 사용자 게시글 수치를 사실로 사용하지 않음"} for d in ("2026-10-12","2026-10-14","2026-10-16","2026-10-19")]}}
    Path("public").mkdir(exist_ok=True)
    Path("public/data.json").write_text(json.dumps(report,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    Path("public/hubc-backtest.json").write_text(json.dumps(report["backtest"],ensure_ascii=False,indent=2),encoding="utf-8")
    with sqlite3.connect("hunter.sqlite") as db:
        db.execute("CREATE TABLE IF NOT EXISTS snapshots (known_at TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?)",(now,json.dumps(report,ensure_ascii=False)))
    print(json.dumps({"updated_at":now,"coverage":coverage,"top10_count":len(top)},ensure_ascii=False))

if __name__=="__main__": asyncio.run(main())
