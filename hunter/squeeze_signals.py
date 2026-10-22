"""Independent observed-data engine. Weights are never renormalized.

Daily signals use completed split-adjusted IEX bars. Intraday confirmation is
separate and may advance/downgrade stages; no future/partial bar is accepted.
"""
import math
from datetime import datetime,timedelta,timezone
from statistics import mean
from zoneinfo import ZoneInfo
WEIGHTS={'short_pressure':30,'capital_inflow':25,'price_structure':20,'dilution_gap':20,'catalyst':5}
STAGES=['DORMANT','FUEL BUILDING','SETUP','IGNITION','EXPANSION']
def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def instant(x):
    try:
        d=datetime.fromisoformat(str(x).replace('Z','+00:00'))
        return d if d.tzinfo else None
    except (ValueError,TypeError):return None
def age_ok(x,now,days):
    t=instant(x);return bool(t and 0<=(now-t).total_seconds()<=days*86400)
def safe_bars(bars,now):
    out={}
    for b in bars or []:
        t=instant(b.get('time'));a=instant(b.get('available_at'))
        if not t or t>now or a and a>now or b.get('complete') is False:continue
        if not all(finite(b.get(k)) for k in ('open','high','low','close','volume')):continue
        if min(b[k] for k in ('open','high','low','close'))<=0 or b['volume']<0:continue
        if b['high']<max(b['open'],b['close'],b['low']) or b['low']>min(b['open'],b['close']):continue
        out[b['time']]=b
    return sorted(out.values(),key=lambda b:b['time'])
def pct(a,b):return 100*(a/b-1) if finite(a) and finite(b) and b>0 else None
def ctb_metrics(obs,now):
    b=obs.get('borrow',{});valid=not b.get('stale') and b.get('lender')=='Interactive Brokers' and 'chartexchange.com/' in b.get('source','') and age_ok(b.get('as_of'),now,2) and age_ok(b.get('observed_at',obs.get('observed_at')),now,2)
    if not valid or not finite(b.get('ctb')) or b['ctb']<0:return {'valid':False,'reason':'현재 CTB 기준시각·출처·조회시각 검증 불가'}
    h={x['as_of']:x for x in obs.get('borrow_history',[]) if x.get('lender')=='Interactive Brokers' and finite(x.get('ctb')) and instant(x.get('as_of')) and instant(x['as_of'])<=instant(b['as_of']) and age_ok(x.get('observed_at'),now,8)}
    h[b['as_of']]=b;history=sorted(h.values(),key=lambda x:x['as_of']);prior=history[-2] if len(history)>1 else None
    result={'valid':True,'current':b['ctb'],'as_of':b['as_of'],'observed_at':b.get('observed_at'),'source':b.get('source'),'available':b.get('available'),'previous':prior.get('ctb') if prior else None,'previous_available':prior.get('available') if prior else None,'cross_verified':False}
    for days,label in ((1,'24h'),(3,'3d'),(5,'5d')):
        boundary=instant(b['as_of'])-timedelta(days=days)
        rows=[x for x in history if boundary-timedelta(hours=12)<=instant(x['as_of'])<=boundary]
        ref=rows[-1] if rows else None
        result[label+'_change_pct']=pct(b['ctb'],ref['ctb']) if ref else None
        result[label+'_change_pp']=b['ctb']-ref['ctb'] if ref else None
        result[label+'_reference_at']=ref.get('as_of') if ref else None
    result['previous_change_pp']=b['ctb']-prior['ctb'] if prior else None
    result['available_drop_pct']=-pct(b.get('available'),prior.get('available')) if prior and pct(b.get('available'),prior.get('available')) is not None else None
    result['resupplied']=bool(prior and prior.get('available')==0 and finite(b.get('available')) and b['available']>0)
    streak=[]
    for x in reversed(history):
        if x.get('available')!=0:break
        if streak and (instant(streak[-1]['as_of'])-instant(x['as_of'])).total_seconds()>3600:break
        streak.append(x)
    result['zero_observed_hours']=(instant(streak[0]['as_of'])-instant(streak[-1]['as_of'])).total_seconds()/3600 if len(streak)>1 else None
    result['zero_note']='관측된 0주 구간; 관측 사이 연속 0주 보장 아님'
    recent=[x['ctb'] for x in history if age_ok(x['as_of'],now,1)]
    result['rising_persistent']=all(y>x for x,y in zip(recent[-3:],recent[-2:])) if len(recent)>=3 else None
    return result

def market_metrics(stock,now):
    bars=safe_bars(stock.get('bars'),now)
    if len(bars)<22:return {'valid':False,'bars':len(bars)}
    b,p=bars[-1],bars[-2];base=bars[-21:-1];closes=[x['close'] for x in bars];vol=mean(x['volume'] for x in base)
    dv=mean(x['close']*x['volume'] for x in base);vwap=b.get('vwap');prior_vwap=p.get('vwap')
    change=pct(b['close'],p['close']);rvol=b['volume']/vol if vol>0 else None;dvr=b['close']*b['volume']/dv if dv>0 else None
    low=min(x['low'] for x in bars[-6:-1]);resistance=max(x['high'] for x in base)
    diffs=[closes[i]-closes[i-1] for i in range(len(closes)-14,len(closes))];g=mean(max(x,0) for x in diffs);loss=mean(max(-x,0) for x in diffs);rsi=100-100/(1+g/loss) if loss>0 else (100 if g>0 else 50)
    obv=[0]
    for a,c in zip(bars,bars[1:]):obv.append(obv[-1]+(c['volume'] if c['close']>a['close'] else -c['volume'] if c['close']<a['close'] else 0))
    recent=bars[-5:];older=bars[-15:-5];range5=mean((x['high']-x['low'])/x['close'] for x in recent);range10=mean((x['high']-x['low'])/x['close'] for x in older)
    m={'valid':True,'as_of':b['time'],'bars':len(bars),'price':b['close'],'change_pct':change,'dollar_volume':b['close']*b['volume'],'dollar_ratio':dvr,'dollar_increase_pct':(dvr-1)*100 if dvr is not None else None,'rvol':rvol,'vwap':vwap,'above_vwap':b['close']>=vwap if finite(vwap) and vwap>0 else None,'vwap_reclaim':p['close']<prior_vwap and b['close']>=vwap if finite(vwap) and finite(prior_vwap) else None,'vwap_distance_pct':pct(b['close'],vwap),'rsi14':rsi,'obv_rising':obv[-1]>obv[-6],'low_defense':b['low']>=low*.98 and b['close']>=low*1.02,'higher_low':b['low']>p['low'],'support':low,'resistance':resistance,'breakout':b['close']>resistance,'near_resistance':resistance*.95<=b['close']<=resistance,'close_retention':(b['close']-b['low'])/(b['high']-b['low']) if b['high']>b['low'] else None,'compression':range5<range10*.7 and mean(x['volume'] for x in recent)<mean(x['volume'] for x in older) and min(x['low'] for x in recent)>=low*.98,'return_5d_pct':pct(b['close'],bars[-6]['close']),'return_20d_pct':pct(b['close'],bars[-21]['close']),'oversold_rebound':rsi<=35 and change>0 and b['low']>=low*.98,'scope':'IEX 부분 거래소 일봉 · 거래대금=종가×거래량 근사 · 순매수 자금 아님'}
    m['chase_risk']=bool(change>=30 or m['return_5d_pct']>=80 or m['return_20d_pct']>=100)
    m['fresh']=age_ok(b['available_at'] if b.get('available_at') else b['time'],now,4) and age_ok(b['time'],now,5)
    return m

def intraday_metrics(stock,now):
    bars=safe_bars(stock.get('intraday'),now)
    if len(bars)<8:return {'valid':False,'reason':'완료된 최근 5분봉 부족'}
    b=bars[-1]
    if not age_ok(b['time'],now,1/24):return {'valid':False,'reason':'5분봉 60분 이상 지연'}
    today=instant(b['time']).astimezone(ZoneInfo('America/New_York')).date()
    bars=[x for x in bars if instant(x['time']).astimezone(ZoneInfo('America/New_York')).date()==today]
    if len(bars)<8:return {'valid':False,'reason':'현재 세션 표본 부족'}
    vols=sum(x['volume'] for x in bars);vwap=sum(x.get('vwap',x['close'])*x['volume'] for x in bars)/vols if vols else None
    base=bars[-7:-1];avg=mean(x['close']*x['volume'] for x in base);ratio=b['close']*b['volume']/avg if avg>0 else None
    return {'valid':True,'as_of':b['time'],'price':b['close'],'vwap':vwap,'above_vwap':b['close']>=vwap if vwap else None,'breakout':b['close']>max(x['high'] for x in base),'dollar_ratio':ratio,'retention':(b['close']-b['low'])/(b['high']-b['low']) if b['high']>b['low'] else None,'low_defense':b['low']>=min(x['low'] for x in base)*.98,'scope':'IEX 5분봉 · 최소20분 지연 · VWAP는 당일 관측 범위'}

def dilution(sec,now):
    # Only a deliberately reviewed, timed, source-backed assessment may score.
    assessment=sec.get('squeeze_assessment',{})
    states={'희석 공백 확인':20,'즉시 출회 가능성 낮음':12,'즉시 출회 위험 높음':0}
    if assessment.get('reviewed') is True and assessment.get('contracts_reconciled') is True and assessment.get('source','').startswith('https://www.sec.gov/Archives/') and age_ok(assessment.get('reviewed_at'),now,1) and age_ok(assessment.get('known_at'),now,1) and assessment.get('status') in states:
        return {'status':assessment['status'],'points':states[assessment['status']],'coverage':20,'source':assessment['source']}
    docs=[x for x in sec.get('documents',[]) if x.get('sha256') and age_ok(x.get('known_at'),now,7)]
    return {'status':'추가 검증 필요' if docs else '검증 불가','points':None,'coverage':0,'flags':sec.get('risk_flags',[]),'documents':docs,'note':'희석 수단 문구와 즉시 신규 발행·자유매도 가능성을 구분; 원문·첨부계약 조건 미확정이면 안전 점수 없음'}

def analyze(stock,obs,now=None):
    now=now or datetime.now(timezone.utc);ctb=ctb_metrics(obs,now);m=market_metrics(stock,now);intra=intraday_metrics(stock,now);si=obs.get('short_interest',{});d=dilution(stock.get('sec',{}),now)
    components={k:{'score':None,'coverage':0,'max':v,'evidence':[]} for k,v in WEIGHTS.items()}
    signals=[];p=components['short_pressure']
    def add(group,points,weight,note):
        v=components[group];v['score']=(v['score'] or 0)+points;v['coverage']+=weight;v['evidence'].append(note)
    if ctb['valid']:
        rate=ctb['current'];level=sum(rate>=x for x in (20,50,100,200,400))
        add('short_pressure',level,5,'IBKR CTB 수준 '+str(rate)+'%')
        if rate>=20:signals.append('ctb_elevated')
        delta=ctb.get('24h_change_pp')
        if finite(delta):
            add('short_pressure',5 if delta>=20 else 3 if delta>=5 else 1 if delta>0 else 0,5,'24시간 CTB 변화 '+str(delta)+'%p')
            if delta>0:signals.append('ctb_rising')
        if ctb.get('rising_persistent') is not None:add('short_pressure',2 if ctb['rising_persistent'] else 0,2,'연속 관측 CTB 상승 지속')
        av=ctb.get('available');drop=ctb.get('available_drop_pct')
        if finite(av):
            add('short_pressure',3 if av==0 else 2 if av<=10000 else 1 if av<=100000 else 0,3,'IBKR 대차 잔량 '+str(av)+'주')
            if av<=10000:signals.append('borrow_tight')
        if finite(drop):
            add('short_pressure',5 if drop>=80 else 3 if drop>=50 else 1 if drop>0 else 0,5,'직전 관측 잔량 감소 '+str(drop)+'%')
            if drop>0:signals.append('borrow_falling')
    # Settlement dates are not public release timestamps. Only observation at/before now.
    split_between=any(instant(str(e.get('ex_date',''))[:10]+'T00:00:00+00:00') and str(e.get('ex_date',''))[:10]>str(si.get('settlement_date','9999')) and instant(str(e['ex_date'])[:10]+'T00:00:00+00:00')<=now for e in stock.get('split_check',{}).get('events',[]))
    si_valid=not split_between and not si.get('stale') and si.get('official_origin')=='FINRA' and 'chartexchange.com/' in si.get('source','') and age_ok(si.get('observed_at'),now,45) and age_ok(si.get('settlement_date','')+'T00:00:00+00:00',now,45) and finite(si.get('float_pct')) and 0<=si['float_pct']<=100 and not obs.get('float',{}).get('flags')
    if si_valid:
        ratio=si['float_pct'];change=si.get('change_pct')
        add('short_pressure',6 if ratio>=20 else 4 if ratio>=10 else 2 if ratio>=5 else 0,6,'공식 잔고/당시 Float '+str(ratio)+'%')
        if ratio>=10:signals.append('interest_high')
        if finite(change):
            add('short_pressure',4 if change>=20 else 2 if change>0 else 0,4,'공식 보고 잔고 증감 '+str(change)+'%')
            if change>0:signals.append('interest_rising')
    if m.get('valid') and m.get('fresh'):
        if finite(m['dollar_ratio']) and finite(m['rvol']):
            support=m['change_pct']>=0 and m['low_defense'] and (m['close_retention'] or 0)>=.5
            add('capital_inflow',10 if support and m['dollar_ratio']>=2 else 5 if support and m['dollar_ratio']>=1.3 else 0,10,'거래대금 증가와 가격 유지 동반 여부')
            add('capital_inflow',5 if support and m['rvol']>=2 else 2 if support and m['rvol']>=1.2 else 0,5,'RVOL과 저점 방어')
        if m['above_vwap'] is not None:add('capital_inflow',5 if m['above_vwap'] and m['change_pct']>=0 else 0,5,'종가/VWAP')
        add('capital_inflow',5 if m['obv_rising'] and m['low_defense'] else 0,5,'OBV 상승·저점 유지')
        add('price_structure',5 if m['oversold_rebound'] else 2 if m['low_defense'] and m['higher_low'] else 0,5,'RSI·과매도 반등·저점 상승')
        if m['vwap_reclaim'] is not None:add('price_structure',5 if m['vwap_reclaim'] else 2 if m['above_vwap'] else 0,5,'VWAP 회복 또는 상단 유지')
        add('price_structure',5 if m['breakout'] else 2 if m['near_resistance'] else 0,5,'20일 고점 저항 돌파·접근')
        add('price_structure',5 if m['compression'] else 0,5,'가격·거래량 압축 및 지지 유지')
    if d['points'] is not None:add('dilution_gap',d['points'],20,d['status'])
    # Filing arrival is a verified event but no claim that it is bullish.
    events=[x for x in stock.get('sec',{}).get('timeline',[]) if x.get('source','').startswith('https://www.sec.gov/Archives/') and age_ok(x.get('accepted'),now,3)]
    if events:add('catalyst',1,5,'72시간 내 SEC 접수 공시; 방향성 미확인')
    observed=sum(x['score'] or 0 for x in components.values()) if any(x['score'] is not None for x in components.values()) else None
    coverage=sum(x['coverage'] for x in components.values());stage,reason=classify(signals,m,intra)
    high_risk=d['status']=='즉시 출회 위험 높음';candidate=len(signals)>=2 and bool(m.get('valid') and m.get('fresh')) and p['coverage']>=8 and coverage>=45
    halted=stock.get('halt_status')=='halted'
    ready='진입 보류 · 핵심 자료 부족' if not candidate else '고위험 관찰' if high_risk else '추격 주의' if m.get('chase_risk') else '조건 관찰 · 희석·토스 주문 확인 필요' if stage in STAGES[2:] else '점화 전 대기'
    return {'ticker':stock['ticker'],'observed_score':observed,'total_score':observed if coverage==100 else None,'coverage':coverage,'components':components,'signals':signals,'stage':stage,'stage_reason':reason,'stage_basis':'지연 5분봉' if intra.get('valid') else '완료 일봉 · 장중 단계 아님','candidate':candidate and not halted,'high_risk':high_risk,'entry_readiness':ready,'dilution':d,'ctb':ctb,'official_interest':{**si,'scoring_valid':si_valid,'published_at':si.get('published_at'),'publication_note':'공급자 최초 공개시각 미제공; 수집시각 이전 소급 사용 금지'},'market':m,'intraday':intra,'events':events,'confidence':'높음' if coverage>=90 else '중간' if coverage>=60 else '낮음','toss_orderable':stock.get('toss_orderable') is True,'as_of':now.isoformat()}

def classify(signals,m,intra):
    """Stateless reassessment defines both entry and downgrade; jumps allowed."""
    if not signals or not m.get('fresh'):return None,'숏 근거 또는 최신 가격 부족 · 단계 미확정'
    pressure=len(signals)>=2
    if not pressure:return 'DORMANT','숏 압박 단일 신호 · 복수 신호 대기'
    r=intra if intra.get('valid') else m;ret=r.get('retention',r.get('close_retention'))
    dollar=r.get('dollar_ratio') or 0
    if r.get('above_vwap') and r.get('low_defense') and dollar>=2 and r.get('breakout'):
        if ret is not None and ret>=.75 and (m.get('return_5d_pct') or 0)>=15 and m.get('change_pct',0)>0:return 'EXPANSION','저항 돌파·거래대금 2배·상단 유지·5일 가속'
        return 'IGNITION','저항 돌파·거래대금 2배·VWAP·저점 유지'
    if r.get('above_vwap') and r.get('low_defense') and dollar>=1.3:return 'SETUP','복수 숏 신호·VWAP 상단·저점 방어·거래대금 1.3배'
    return 'FUEL BUILDING','복수 숏 신호 확인; 가격·거래대금 점화 조건 대기 또는 이탈'

def update_history(previous,rows,now):
    states=dict(previous.get('states',{}));history=list(previous.get('history',[]));alerts=list(previous.get('alerts',[]));last=previous.get('last',{});new_last={};seen={x['id'] for x in alerts}
    def emit(ticker,kind,before,after,evidence,stamp):
        # Source timestamp + signal type identifies an observation, independent of scan time.
        key=ticker+'|'+kind+'|'+str(stamp)
        if key not in seen:
            alerts.append({'id':key,'ticker':ticker,'kind':kind,'occurred_at':now.isoformat(),'source_at':stamp,'previous':before,'current':after,'evidence':evidence,'channel':'사이트 내부 알림'});seen.add(key)
    for a in rows:
        t=a['ticker'];old=states.get(t);stage=a['stage'];prior=last.get(t,{})
        if old!=stage:
            history.append({'ticker':t,'at':now.isoformat(),'previous':old,'current':stage,'reason':a['stage_reason'],'basis':a['stage_basis']})
            if old is not None:emit(t,'stage_change',old,stage,a['stage_reason'],a.get('intraday',{}).get('as_of') or a['market'].get('as_of'))
        states[t]=stage;b=a['ctb'];c=a['components']['short_pressure'];score=c['score'];prev_score=prior.get('pressure_score')
        if b.get('valid'):
            if (b.get('previous_change_pp') or 0)>=20:emit(t,'ctb_surge',b.get('previous'),b.get('current'),'CTB 직전 관측 대비 20%p 이상 상승',b['as_of'])
            if (b.get('available_drop_pct') or 0)>=50:emit(t,'borrow_drop',b.get('previous_available'),b.get('available'),'공급원 잔량 50% 이상 감소',b['as_of'])
        if finite(prev_score) and finite(score) and score-prev_score>=8 and prior.get('pressure_coverage')==c['coverage']:emit(t,'pressure_jump',prev_score,score,'동일 커버리지에서 숏 압박 8점 이상 증가',b.get('as_of'))
        if stage in ('IGNITION','EXPANSION') and a['market'].get('breakout'):emit(t,'breakout_inflow',None,stage,a['stage_reason'],a['market'].get('as_of'))
        risky=set(a['dilution'].get('flags',[])) & {'ATM','ELOC','PIPE','RD','RESALE','CONVERTIBLE','WARRANT'}
        new_flags=risky-set(prior.get('risk_flags',[]))
        if prior and new_flags:emit(t,'new_supply_disclosure',prior.get('risk_flags'),sorted(risky),'신규 희석 관련 문구; 즉시 출회 확정 아님',max((x.get('accepted_at','') for x in a['dilution'].get('documents',[])),default=now.isoformat()))
        new_last[t]={'pressure_score':score,'pressure_coverage':c['coverage'],'risk_flags':sorted(risky)}
    # Missing symbols cannot silently retain an active stage from an earlier run.
    for t in set(states)-{a['ticker'] for a in rows}:
        if states[t] is not None:history.append({'ticker':t,'at':now.isoformat(),'previous':states[t],'current':None,'reason':'현재 탐색 범위 제외 또는 데이터 없음'})
        states[t]=None
    return {'updated_at':now.isoformat(),'states':states,'last':new_last,'history':history[-10000:],'alerts':alerts[-2000:]}
