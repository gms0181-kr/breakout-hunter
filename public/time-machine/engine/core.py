"""Deterministic scoring. Missing evidence stays None, never earns assumed points."""
from datetime import datetime, timezone
import hashlib
import math

WEIGHTS = {"V":25,"F":20,"S":20,"R":15,"SEC":15,"EVENT":5}

def known(value):
    return isinstance(value, (float,int)) and not isinstance(value,bool) and math.isfinite(value)

def ratio(value, base):
    return value/base if known(value) and known(base) and base>0 else None

def adjusted_bars(bars, splits, as_of):
    """Raw bars -> as-of share basis. Price / factor; volume * factor.
    factor = new shares / old shares, including reverse splits (e.g. 1/25).
    Do NOT apply this function to provider-adjusted bars.
    """
    out=[]
    for bar in bars:
        if bar["time"]>as_of: continue
        item=dict(bar)
        for split in splits:
            if split["date"]<=as_of and bar["time"]<split["date"]:
                factor=split["new"]/split["old"]
                for key in ("open","high","low","close"):
                    if known(item.get(key)): item[key]/=factor
                if known(item.get("volume")): item["volume"]*=factor
        out.append(item)
    return sorted(out,key=lambda b:b["time"])

def volume_metrics(bars):
    if not bars: return {"ratios":{},"trend":None}
    current=bars[-1]["volume"]
    averages={}
    for n in (10,20,50):
        past=[b["volume"] for b in bars[-n-1:-1] if known(b.get("volume"))]
        averages[str(n)]=sum(past)/n if len(past)==n else None
    recent=[b["volume"] for b in bars[-5:] if known(b.get("volume"))]
    return {"averages":averages,"ratios":{k:ratio(current,v) for k,v in averages.items()},
            "trend":ratio(sum(recent[-3:])/3,sum(recent[:2])/2) if len(recent)==5 else None}

def engine_scores(stock):
    bars=stock.get("bars",[])
    metrics=volume_metrics(bars)
    scores={k:None for k in WEIGHTS}
    signals=[]
    rv=metrics["ratios"].get("20")
    if known(rv):
        score=20 if rv>=10 else 16 if rv>=5 else 12 if rv>=3 else 8 if rv>=2 else 0
        trend=metrics.get("trend")
        if trend is not None and trend>=1.5: score+=3
        change=ratio(bars[-1].get("close"),bars[-2].get("close")) if len(bars)>1 else None
        if rv>=2 and change is not None and change<=1.05: score+=2
        scores["V"]=min(25,score)
        if rv>=2: signals.append("거래량 선행형")
    float_value=stock.get("float")
    outstanding=stock.get("outstanding")
    basis=float_value if known(float_value) else outstanding
    rotation=ratio(stock.get("volume"),basis)
    # Outstanding fallback is disclosed but does not earn float-specific points.
    if known(float_value) and float_value>0 and rotation is not None:
        scores["F"]=(10 if float_value<=5000000 else 5 if float_value<=10000000 else 0)+min(10,rotation*10)
        if float_value<=5000000 or rotation>=1: signals.append("저유통·회전율형")
    short=stock.get("short") or {}
    # Each verified short component operates independently; absent values stay missing.
    short_coverage=0
    if short.get("cross_verified") is True and short.get("as_of"):
        points=[]
        if known(short.get("ctb")):
            points.append(6 if short["ctb"]>=100 else 3 if short["ctb"]>=30 else 0); short_coverage+=6
        if known(short.get("available")):
            points.append(4 if short["available"]==0 else 2 if short["available"]<=10000 else 0); short_coverage+=4
        if known(short.get("short_float")):
            points.append(4 if short["short_float"]>=20 else 0); short_coverage+=4
        if known(short.get("interest_change")):
            points.append(3 if short["interest_change"]>0 else 0); short_coverage+=3
        if known(short.get("days_to_cover")):
            points.append(3 if short["days_to_cover"]>=3 else 0); short_coverage+=3
        if points:
            scores["S"]=sum(points)
            if scores["S"]>0: signals.append("숏 스퀴즈형")
    if len(bars)>=64 and all(known(b.get("close")) for b in bars[-64:]) and all(known(b.get("low")) for b in bars[-5:]):
        price=bars[-1]["close"]
        d1=price/bars[-22]["close"]-1
        d3=price/bars[-64]["close"]-1
        defense=min(b["low"] for b in bars[-3:])>=min(b["low"] for b in bars[-5:-3])
        scores["R"]=(6 if d3<=-.7 else 3 if d3<=-.4 else 0)+(3 if d1<=-.2 else 0)+(3 if defense else 0)+(3 if defense and known(rv) and rv>=2 else 0)
        if scores["R"]>=6: signals.append("과매도 반등형")
    sec=stock.get("sec") or {}
    # Only structured reviewed evidence can establish supply state.
    if sec.get("reviewed") is True and sec.get("evidence") and sec.get("as_of"):
        if sec.get("immediately_sellable") is False and sec.get("coverage_complete") is True:
            scores["SEC"]=15
            signals.append("희석 공백형")
        elif sec.get("immediately_sellable") is True:
            scores["SEC"]=0
            signals.append("고위험 희석 동반 반등형")
    event=stock.get("event") or {}
    if event.get("verified") and event.get("source") and event.get("published_at"):
        scores["EVENT"]=5
        signals.append("이벤트 재점화형")
    observed=sum(v for v in scores.values() if v is not None)
    coverage=sum(short_coverage if k=="S" else WEIGHTS[k] for k,v in scores.items() if v is not None)
    return {"scores":scores,"score":round(observed,2) if coverage else None,
            "confidence":coverage,"missing":[k for k,v in scores.items() if v is None],
            "signals":signals,"metrics":metrics,"rotation":rotation,
            "rotation_basis":"float" if known(float_value) else "outstanding_proxy" if known(outstanding) else "unknown",
            "candidate":bool(signals)}

def rank(stocks):
    from .verification import verify
    scored=[{**s,**engine_scores(s),"verification":verify(s)} for s in stocks]
    # Broker orderability is checked by the user and does not gate ranking.
    qualified=[s for s in scored if s["candidate"] and s["score"] is not None]
    return sorted(qualified,key=lambda s:(-s["score"],s["ticker"]))[:10],scored

def scan_order(symbols, run_id):
    return sorted(set(symbols),key=lambda s:hashlib.sha256((run_id+":"+s).encode()).hexdigest())

def deduplicate_supply(events, as_of):
    """Immutable security IDs avoid counting the same warrant across filing stages.
    No summing of stages; actual sales require their own explicit evidence.
    """
    latest={}
    for item in events:
        if item["known_at"]>as_of: continue
        key=item["security_id"]
        if key not in latest or latest[key]["known_at"]<item["known_at"]: latest[key]=item
    return list(latest.values())

def point_in_time(records, as_of):
    return [r for r in records if r.get("known_at") and r["known_at"]<=as_of and r.get("time",r["known_at"])<=as_of]

