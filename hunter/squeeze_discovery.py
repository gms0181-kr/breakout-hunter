"""Price-first discovery and bounded fair scheduling; never invent short evidence."""
from datetime import timedelta
from statistics import mean
from zoneinfo import ZoneInfo
from .squeeze_signals import instant,finite,safe_bars,market_metrics

def market_probe(stock,now):
    # In-progress daily bars are discovery-only, never added to completed-bar scores.
    bars=safe_bars([{**b,'complete':True} for b in stock.get('bars',[])],now)
    if len(bars)<22:return {'triggered':False,'reason':'일봉 표본 부족'}
    b=bars[-1];at=instant(b['time']);known=instant(b.get('available_at'))
    if at.astimezone(ZoneInfo('America/New_York')).date()!=now.astimezone(ZoneInfo('America/New_York')).date() or not known or not 0<=(now-known).total_seconds()<=3600:return {'triggered':False,'reason':'당일 관측 가격 미확인'}
    base=bars[-21:-1];avg=mean(x['close']*x['volume'] for x in base);ratio=b['close']*b['volume']/avg if avg>0 else None
    change=100*(b['close']/base[-1]['close']-1);ret=(b['close']-b['low'])/(b['high']-b['low']) if b['high']>b['low'] else 0
    trigger=ratio is not None and ratio>=1.3 and change>=5 and ret>=.5
    return {'triggered':trigger,'as_of':b['time'],'observed_at':b.get('available_at'),'price':b['close'],'change_pct':change,'dollar_ratio':ratio,'retention':ret,'basis':'IEX 당일 누적 일봉 · 진행 봉 포함 · 탐색 전용 · 순매수 아님'}

def priority(stock,analysis,now):
    p=market_probe(stock,now);m=analysis.get('market',{})
    return (bool(p.get('triggered')),p.get('dollar_ratio') or 0,len(analysis.get('signals',[])),m.get('dollar_ratio') or 0)

def select_intraday(preliminary,cache,now,budget=200):
    budget=max(0,budget);ranked=sorted(preliminary,key=lambda x:priority(*x,now),reverse=True)
    pressure=[s for s,a in ranked if len(a.get('signals',[]))>=2]
    market=[s for s,a in ranked if market_probe(s,now).get('triggered')]
    # Reserve half for whole-universe rotation, independent of CTB and price signals.
    chosen=[];seen=set()
    for group,quota in ((market,budget//4),(pressure,budget//4)):
        for s in group[:quota]:
            if s['ticker'] not in seen:chosen.append(s);seen.add(s['ticker'])
    fair=sorted((s for s,a in preliminary),key=lambda s:(cache.get(s['ticker'],{}).get('intraday_attempted_at',''),s['ticker']))
    for s in fair:
        if len(chosen)>=budget:break
        if s['ticker'] not in seen:chosen.append(s);seen.add(s['ticker'])
    return chosen

def select_borrow(stocks,cache,now,budget=240):
    def stamp(s):return instant(cache.get(s['ticker'],{}).get('attempted_at'))
    due=[s for s in stocks if not stamp(s) or now-stamp(s)>=timedelta(minutes=15)]
    fair=sorted(due,key=lambda s:(cache.get(s['ticker'],{}).get('attempted_at',''),s['ticker']))
    # At least half the budget remains oldest-first: hot symbols cannot starve coverage.
    chosen=fair[:max(0,budget)//2];seen={s['ticker'] for s in chosen}
    ranked=sorted(due,key=lambda s:(market_probe(s,now).get('triggered',False),cache.get(s['ticker'],{}).get('borrow',{}).get('ctb') or 0),reverse=True)
    for s in ranked:
        if len(chosen)>=budget:break
        if s['ticker'] not in seen:chosen.append(s);seen.add(s['ticker'])
    return chosen

def early_signal(probe,intra):
    if intra.get('valid'):
        hit=(intra.get('daily_change_pct') or 0)>=5 and (intra.get('session_dollar_ratio') or 0)>=.3 and intra.get('above_vwap') and (intra.get('retention') or 0)>=.5
        return {'triggered':bool(hit),'as_of':intra.get('as_of'),'basis':'IEX 지연 5분봉 · 당일 +5%·평균 일 거래대금 0.3배·VWAP 상단·가격 유지','short_verified':False}
    return {**probe,'short_verified':False}
