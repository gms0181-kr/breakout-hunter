"""Independent 30/25/40/5 evidence score. Never renormalize missing inputs.
Daily OHLCV supports daily structures only; turnover is NOT net capital flow.
"""
from datetime import datetime, timezone, timedelta
from statistics import mean
from urllib.parse import urlparse
from .core import known, ratio

WEIGHTS={'capital':30,'structure':25,'dilution':40,'short':5}
INSTRUMENTS=('ATM','ELOC','PIPE','RD','SHELF','RESALE','WARRANT','CONVERTIBLE')

def instant(v):
    try:
        d=datetime.fromisoformat(str(v).replace('Z','+00:00'))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except (ValueError,TypeError): return None

def available(record,cutoff,field='known_at'):
    d=instant(record.get(field));return bool(d and d<=cutoff)

def rsi(closes,n=14):
    if len(closes)<n+1:return None
    changes=[b-a for a,b in zip(closes,closes[1:])]
    up=mean(max(x,0) for x in changes[:n]);down=mean(max(-x,0) for x in changes[:n])
    for x in changes[n:]:up=(up*(n-1)+max(x,0))/n;down=(down*(n-1)+max(-x,0))/n
    return 100-100/(1+up/down) if down else 100 if up else 50

def market(stock,as_of):
    cutoff=instant(as_of)
    bars=[b for b in stock.get('bars',[]) if cutoff and b.get('complete',True) is True and available(b,cutoff,'available_at') and instant(b.get('time')) and instant(b['time'])<=cutoff]
    bars=sorted(bars,key=lambda b:b['time'])[-100:]
    valid=lambda b:all(known(b.get(k)) and b[k]>0 for k in ('open','high','low','close')) and known(b.get('volume')) and b['volume']>=0 and b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']
    if len(bars)<21 or not all(valid(b) for b in bars):return {'capital':None,'structure':None,'confirmed_capital':False,'confirmed_structure':False,'metrics':{},'checks':{},'missing':['기준 시각이 확인된 OHLCV 21개 미만 또는 오류'],'price_as_of':None}
    b=bars[-1];past=bars[-21:-1];c=b['close'];v=b['volume'];cl=[x['close'] for x in bars]
    turnover=c*v;turnover_ratio=ratio(turnover,mean(x['close']*x['volume'] for x in past))
    rv=ratio(v,mean(x['volume'] for x in past));vw=b.get('vwap')
    vw_ok=known(vw) and vw>0
    above=c>=vw if vw_ok else None
    pv=bars[-2].get('vwap');reclaim=above and known(pv) and pv>0 and bars[-2]['close']<pv
    obv=[0]
    for a,z in zip(bars[-21:],bars[-20:]):obv.append(obv[-1]+(z['volume'] if z['close']>a['close'] else -z['volume'] if z['close']<a['close'] else 0))
    obv_rising=obv[-1]>obv[-6]
    # A prior burst must be followed by price retention; current volume alone earns no hold points.
    bursts=[i for i in range(len(bars)-5,len(bars)-1) if i>=20 and ratio(bars[i]['volume'],mean(x['volume'] for x in bars[i-20:i])) is not None and ratio(bars[i]['volume'],mean(x['volume'] for x in bars[i-20:i]))>=2]
    hold=any(c>=bars[i]['close']*.97 and min(x['low'] for x in bars[i+1:])>=bars[i]['low']*.98 for i in bursts)
    floor=min(x['low'] for x in bars[-10:-1]);unbroken=b['low']>=floor*.98
    touches=sum(x['low']<=floor*1.03 for x in bars[-10:-1]);repeated=touches>=2 and unbroken
    nearvol=abs(c/floor-1)<=.08 and rv is not None and rv>=1.5 and unbroken
    higher=min(x['low'] for x in bars[-3:])>min(x['low'] for x in bars[-6:-3])
    drawdown=c/max(x['high'] for x in bars[-21:])-1
    flat=(max(x['high'] for x in bars[-4:])/min(x['low'] for x in bars[-4:])-1)<=.12
    down=[x['volume'] for a,x in zip(bars[-11:-1],bars[-10:]) if x['close']<a['close']]
    down_contract=len(down)>=2 and down[-1]<down[0]*.8
    dry=drawdown<=-.2 and unbroken and mean(x['volume'] for x in bars[-3:])<mean(x['volume'] for x in bars[-8:-3])*.7
    rebound=c>bars[-2]['close'] and rv is not None and rv>=1.5
    recovery=c>bars[-2]['close'] and c>=b['open'] and c>=b['low']+(b['high']-b['low'])*.6
    r=rsi(cl);recent_r=[rsi(cl[:-i]) if i else r for i in range(4)]
    oversold=any(x is not None and x<=30 for x in recent_r)
    support_checks={'repeated_lows':repeated,'support_volume':nearvol,'higher_lows':higher,'vwap_reclaim':bool(reclaim) if vw_ok and known(pv) else None,'support_intact':unbroken}
    oversold_checks={'rsi_oversold':oversold,'drop_then_flat':drawdown<=-.2 and flat,'declining_sell_volume':down_contract,'early_rebound_volume':rebound,'price_recovery':recovery}
    support_score=sum(5 for x in support_checks.values() if x is True)
    oversold_score=sum(5 for x in oversold_checks.values() if x is True)
    support_pass=repeated and unbroken and support_score>=15 and (nearvol or higher or reclaim)
    oversold_pass=oversold and drawdown<=-.2 and flat and (rebound or recovery) and oversold_score>=15
    pressure=stock.get('trade_pressure') or {}
    pressure_ok=available(pressure,cutoff) and pressure.get('method')=='classified_trades' and pressure.get('source') and known(pressure.get('buy_fraction')) and 0<=pressure['buy_fraction']<=1
    pressure_value=pressure['buy_fraction'] if pressure_ok else None
    capital_checks={'turnover_ratio':turnover_ratio,'above_vwap':above,'vwap_reclaim':bool(reclaim) if vw_ok and known(pv) else None,'obv_rising':obv_rising,'post_burst_hold':hold,'dry_volume_floor_defense':dry,'buy_pressure':pressure_value}
    capital=(8 if turnover_ratio is not None and turnover_ratio>=5 else 6 if turnover_ratio is not None and turnover_ratio>=3 else 4 if turnover_ratio is not None and turnover_ratio>=2 else 0)+(6 if reclaim else 3 if above else 0)+(5 if obv_rising else 0)+(5 if hold else 0)+(4 if dry else 0)+(2 if pressure_value is not None and pressure_value>=.6 else 0)
    confirm_capital=bool(turnover_ratio is not None and turnover_ratio>=2 and capital>=14 and sum(x is True for x in (above,obv_rising,hold,dry))>=2)
    return {'capital_coverage':22+(6 if vw_ok else 0)+(2 if pressure_ok else 0),'capital':capital,'structure':max(support_score,oversold_score),'confirmed_capital':confirm_capital,'confirmed_structure':bool(support_pass or oversold_pass),'structure_type':'SUPPORT + OVERSOLD' if support_pass and oversold_pass else 'SUPPORT' if support_pass else 'OVERSOLD' if oversold_pass else '관찰','metrics':{'turnover_proxy':turnover,'turnover_ratio20':turnover_ratio,'rvol20':rv,'vwap':vw if vw_ok else None,'close_vs_vwap_pct':(c/vw-1)*100 if vw_ok else None,'rsi14':r,'obv_change5':obv[-1]-obv[-6],'support':floor,'drawdown20_pct':drawdown*100},'checks':{'capital':capital_checks,'support':support_checks,'oversold':oversold_checks},'missing':([] if vw_ok else ['VWAP 미수집'])+([] if pressure_ok else ['매수·매도 체결 압력 미수집']),'price_as_of':b['time'],'scope':stock.get('feed','공급 범위 미확인'),'note':'자금 유입 정황: 종가×거래량 근사치이며 실제 순유입 아님. 일봉 구조; 장중 진입 신호 아님.'}

def dilution(sec,as_of):
    cutoff=instant(as_of)
    docs=[d for d in sec.get('documents',[]) if cutoff and available(d,cutoff) and urlparse(d.get('source','')).hostname in ('www.sec.gov','sec.gov') and d.get('sha256') and (not d.get('accepted_at') or available(d,cutoff,'accepted_at'))]
    # Structured, reviewed, instrument-level evidence is required for legal supply assertions.
    facts=[f for f in sec.get('supply_facts',[]) if cutoff and available(f,cutoff) and f.get('reviewed') is True and f.get('source') in {d['source'] for d in docs} and f.get('evidence') and f.get('security_id') and f.get('share_basis_verified') is True]
    latest={}
    for f in sorted(facts,key=lambda x:x['known_at']):latest[f['security_id']]=f
    facts=list(latest.values())
    active=[f for f in facts if instant(f.get('valid_until')) and instant(f['valid_until'])>=cutoff and instant(f.get('effective_at')) and instant(f['effective_at'])<=cutoff]
    risky=[f for f in active if f.get('new_issuance_now') is True or f.get('free_sale_now') is True]
    coverage=sec.get('supply_coverage') or {}
    complete=bool(cutoff and available(sec,cutoff,'review_known_at') and instant(sec.get('review_valid_until')) and instant(sec['review_valid_until'])>=cutoff) and sec.get('coverage_complete') is True and sec.get('reviewed') is True and all(coverage.get(k) is True for k in INSTRUMENTS) and bool(facts) and len(active)==len(facts)
    low=complete and all(f.get('new_issuance_now') is False and f.get('free_sale_now') is False for f in active)
    status='즉시 희석 위험 높음' if risky else '즉시 출회 부담 낮음' if low else '추가 검증 필요' if docs else '검증 불가'
    return {'score':0 if risky else 40 if low else None,'status':status,'gap_candidate':bool(low),'facts':facts,'documents':docs,'coverage_complete':complete,'missing_instruments':[k for k in INSTRUMENTS if coverage.get(k) is not True],'note':'등록·클로징·blocker·키워드만으로 자유매도 또는 희석 공백을 확정하지 않음'}

def short_pressure(stock,as_of):
    cutoff=instant(as_of);short=stock.get('short') or {};points=0;covered=0;checks={}
    for key in ('ctb','available','official_interest','interest_change','short_volume_ratio'):
        observations=[x for x in short.get('observations',[]) if cutoff and x.get('metric')==key and available(x,cutoff) and available(x,cutoff,'as_of') and known(x.get('value')) and (cutoff-instant(x['as_of']))<=timedelta(days=45 if key in ('official_interest','interest_change') else 2)]
        domains={urlparse(x.get('source','')).hostname or '' for x in observations}
        paired=any(d=='chartexchange.com' or d.endswith('.chartexchange.com') for d in domains) and any(d=='fintel.io' or d.endswith('.fintel.io') for d in domains)
        # Compare same settlement/borrow timestamp window, not just source booleans.
        if paired:
            vals=[x['value'] for x in observations];stamps=[instant(x['as_of']) for x in observations]
            paired=(max(stamps)-min(stamps))<=timedelta(hours=1) and max(vals)-min(vals)<=max(1,abs(max(vals))*.05)
        if key in ('official_interest','interest_change'):paired=paired and any(x.get('official_source') for x in observations)
        if paired:
            covered+=1;value=observations[0]['value'];points+=int(value>=30 if key=='ctb' else value==0 if key=='available' else value>0 if key in ('official_interest','interest_change') else value>=.5)
        checks[key]={'verified':bool(paired),'observations':observations}
    history=[x for x in stock.get('enrichment',{}).get('borrow_history',[]) if cutoff and available(x,cutoff,'observed_at') and available(x,cutoff,'as_of')]
    return {'borrow_history':history,'score':points if covered else None,'coverage':covered,'checks':checks,'note':'Short Volume는 공매도 잔고가 아님. 대차 0주·CTB 상승만으로 숏스퀴즈 확정하지 않음','source_observation':(stock.get('enrichment',{}).get('borrow',{}) if cutoff and available(stock.get('enrichment',{}).get('borrow',{}),cutoff,'observed_at') and available(stock.get('enrichment',{}).get('borrow',{}),cutoff,'as_of') else {})}

def verify(stock,as_of=None):
    as_of=as_of or datetime.now(timezone.utc).isoformat()
    m=market(stock,as_of);d=dilution(stock.get('sec') or {},as_of);s=short_pressure(stock,as_of)
    components={'capital':m['capital'],'structure':m['structure'],'dilution':d['score'],'short':s['score']}
    confirmed=m['confirmed_capital'] and m['confirmed_structure']
    grade=('A' if d['gap_candidate'] else 'C' if d['score']==0 else 'B' if d['status']=='추가 검증 필요' else '검증 불가') if confirmed else '검증 불가' if m['capital'] is None or d['status']=='검증 불가' else '관찰'
    covered=(m.get('capital_coverage',0) if m['capital'] is not None else 0)+(25 if m['structure'] is not None else 0)+(40 if d['score'] is not None else 0)+s['coverage']
    return {'version':'1.0','as_of':as_of,'grade':grade,'candidate':bool(confirmed),'score':sum(x for x in components.values() if x is not None) if covered else None,'coverage':covered,'components':components,'market':m,'dilution':d,'short':s,'limitations':['미확인 배점을 재환산하지 않음','A등급은 종합 공급 증거가 확인된 경우만 부여','기존 V/F/S/R 순위와 독립된 검증 결과']}
