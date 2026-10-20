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
    replay_result=config.pop("_backtest",{})
    fx=config.pop("_fx",None)
    from .float_ctb import apply_cached
    apply_cached(stocks)
    from .halts import check_stocks
    halt_feed=check_stocks(stocks,config["market_cap_max"])
    eligible=[s for s in stocks if s["eligibility"]=="eligible"]
    top,_=rank(eligible)
    _,scored=rank(stocks)
    now=datetime.now(timezone.utc).isoformat()
    report={"updated_at":now,"status":"partial","coverage":coverage,"top10":top,"watchlist":sorted([s for s in scored if s["candidate"]],key=lambda s:-(s["score"] or 0))[:100],"config":config,"fx":fx,"limitations":["EOD IEX feed: no consolidated or real-time volume","Float·CTB 공개 출처 관측 연결; 출처 충돌·기준일·ADS/병합 주의사항 별도 표시; 숏 점수는 교차검증 전 보류","SEC timeline only: legal issuance/free-sale analysis pending","Toss orderability excluded from ranking; user checks broker availability","시총·정지 점검 후보: Float·숏·SEC 공급 상태 전체 검증을 의미하지 않음"],"backtest":{"status":"blocked: point-in-time source snapshots absent","HUBC":[{"date":d,"detected":None,"time":None,"scores":None,"rank":None,"float":None,"volume_ratio":None,"short":None,"sec":None,"reason":"당시 이용 가능했던 검증된 가격/Float/SEC 증거 스냅샷 없음; 사용자 게시글 수치를 사실로 사용하지 않음"} for d in ("2026-10-12","2026-10-14","2026-10-16","2026-10-19")]}}
    report["halt_check"]={k:v for k,v in halt_feed.items() if k!="events"}
    report["ranking_updated_at"]=halt_feed["checked_at"]
    report["ranking_scope"]="full collected universe"
    report["top10_status"]="시총·정지 점검 후보; Float·숏·SEC 공급 검증 미완료; 토스 매수 가능 여부 사용자 확인"
    report["coverage"]["halt_filter_status"]="공식 RSS + 최근 IEX 체결 대조; 상태별 유효시간 적용"
    report["backtest"]=replay_result
    report["research_top10"]=sorted([s for s in scored if s["candidate"] and s.get("market_cap") is not None and 0<s["market_cap"]<=config["market_cap_max"]],key=lambda s:-(s["score"] or 0))[:10]
    report["research_top10_status"]="실제 시세·시총 기반 관측점수 순위; 거래정지/Float/숏/공급 검증 대기; 토스 매수 가능 여부는 사용자 확인. 실전 TOP10 아님"
    report["coverage"]["engine_evaluated"]=len(scored)
    report["coverage"]["engine_data_available"]={k:sum(s["scores"].get(k) is not None for s in scored) for k in ("V","F","S","R","SEC","EVENT")}
    try:
        report["connections"]=json.loads(Path("public/connections.json").read_text())
    except (FileNotFoundError,ValueError): report["connections"]=None
    # Retain the last generated candidates as explicitly historical when checks expire.
    try:
        prior=json.loads(Path("public/data.json").read_text())
        report["last_top10"]=prior.get("top10") or prior.get("last_top10",[])
        report["last_top10_as_of"]=prior.get("ranking_updated_at") if prior.get("top10") else prior.get("last_top10_as_of")
    except (OSError,ValueError):
        report["last_top10"]=[]
    Path("public").mkdir(exist_ok=True)
    Path("public/data.json").write_text(json.dumps(report,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    Path("public/hubc-backtest.json").write_text(json.dumps(report["backtest"],ensure_ascii=False,indent=2),encoding="utf-8")
    with sqlite3.connect("hunter.sqlite") as db:
        db.execute("CREATE TABLE IF NOT EXISTS snapshots (known_at TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?)",(now,json.dumps(report,ensure_ascii=False)))
    print(json.dumps({"updated_at":now,"coverage":coverage,"top10_count":len(top)},ensure_ascii=False))

if __name__=="__main__": asyncio.run(main())
