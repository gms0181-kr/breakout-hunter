"""SHORT SQUEEZE HUNTER: independent universe, cache, outputs and persistence.

Never calls core.engine_scores/rank or reads their candidate lists.
Authenticated requests run only in Actions using existing Secrets.
"""
import asyncio,concurrent.futures,json,os,time
from pathlib import Path
from datetime import datetime,timedelta,timezone
from collections import Counter
import aiohttp
from . import providers
from .scope import scope_reason
from .squeeze_signals import analyze,instant,finite,update_history,safe_bars
ROOT=Path('public')
def read(name,default):
    try:return json.loads((ROOT/name).read_text())
    except (OSError,ValueError):return default

def due_targets(stocks,cache,now,budget):
    def stamp(s):
        d=instant(cache.get(s['ticker'],{}).get('attempted_at'))
        return d.timestamp() if d else 0
    due=[s for s in stocks if now.timestamp()-stamp(s)>=900]
    # Whole universe fairness, no volume/legacy rank prefilter.
    return sorted(due,key=lambda s:(stamp(s),s['ticker']))[:budget]

def merge_observation(prior,current):
    history={x['as_of']:x for x in prior.get('borrow_history',[]) if x.get('as_of')}
    b=current.get('borrow',{})
    if finite(b.get('ctb')) and b.get('as_of'):history[b['as_of']]={k:b.get(k) for k in ('ctb','available','as_of','observed_at','source','lender')}
    current['borrow_history']=sorted(history.values(),key=lambda x:x['as_of'])[-2400:]
    for field,key in (('borrow','ctb'),('short_interest','shares'),('float','display_value')):
        if current.get(field,{}).get(key) is None and prior.get(field,{}).get(key) is not None:
            current[field]={**prior[field],'stale':True,'refresh_error':current.get(field,{})}
    current['attempted_at']=datetime.now(timezone.utc).isoformat()
    return current

async def intraday(session,stocks):
    key=os.getenv('ALPACA_API_KEY');secret=os.getenv('ALPACA_API_SECRET');output={};errors=[]
    if not key or not secret:return {},['credentials_missing']
    now=datetime.now(timezone.utc);end=now-timedelta(minutes=20)
    for i in range(0,len(stocks),30):
        group=stocks[i:i+30]
        params={'symbols':','.join(s['ticker'] for s in group),'timeframe':'5Min','start':(now-timedelta(days=4)).isoformat(),'end':end.isoformat(),'limit':10000,'adjustment':'split','feed':'iex','sort':'asc'}
        try:
            while True:
                data=await providers.fetch(session,'https://data.alpaca.markets/v2/stocks/bars',headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},params=params)
                for t,rows in data.get('bars',{}).items():
                    output.setdefault(t,[]).extend({'time':b['t'],'open':b['o'],'high':b['h'],'low':b['l'],'close':b['c'],'volume':b['v'],'vwap':b.get('vw',b['c']),'available_at':now.isoformat(),'complete':instant(b['t'])+timedelta(minutes=5)<=end} for b in rows)
                if not data.get('next_page_token'):break
                params['page_token']=data['next_page_token']
        except RuntimeError as e:errors.append(type(e).__name__)
    return output,errors

def session_state(calendar,now):
    from zoneinfo import ZoneInfo
    local=now.astimezone(ZoneInfo('America/New_York'));date=local.date().isoformat()
    if calendar.get('status')!='ok' or calendar.get('date')!=date:return {'name':'검증 불가','source':calendar.get('source')}
    day=calendar.get('session')
    if not day:return {'name':'휴장','source':calendar.get('source')}
    clock=local.strftime('%H:%M');opening=day['open'];closing=day['close']
    state='프리마켓' if day.get('session_open','04:00').replace(':','')<=clock.replace(':','')<opening else '정규장' if opening<=clock<closing else '애프터마켓' if closing<=clock.replace(':','')<day.get('session_close','20:00').replace(':','') else '장외 시간'
    return {'name':state,'source':calendar.get('source'),'checked_at':calendar.get('checked_at'),'date':date,'open':opening,'close':closing,'warning':'프리·애프터마켓 저유동성·스프레드 왜곡 주의' if state in ('프리마켓','애프터마켓') else None}

def replay(archive,rows,now):
    """Forward-only frozen observations. No current CTB is backfilled into history."""
    snapshots=list(archive.get('observations',[]));known={(x['ticker'],x['price_at']) for x in snapshots}
    for s,a in rows:
        m=a['market'];key=(s['ticker'],m.get('as_of'))
        if not m.get('valid') or key in known:continue
        snapshots.append({'ticker':s['ticker'],'observed_at':now.isoformat(),'price_at':m['as_of'],'price':m['price'],'candidate':a['candidate'],'stage':a['stage'],'score':a['observed_score'],'coverage':a['coverage'],'ctb_at':a['ctb'].get('as_of'),'ctb_known_at':a['ctb'].get('observed_at'),'si_known_at':a['official_interest'].get('observed_at'),'dilution_status':a['dilution']['status']})
    snapshots=snapshots[-50000:];cases=[];positives=[];misses=[]
    by={}
    for x in snapshots:by.setdefault(x['ticker'],[]).append(x)
    for ticker,records in by.items():
        records.sort(key=lambda x:x['observed_at'])
        for i,x in enumerate(records):
            future=[y for y in records[i+1:] if instant(y['price_at'])>instant(x['observed_at'])][:5]
            if len(future)<5:continue
            gain=max((y['price']/x['price']-1)*100 for y in future);item={'ticker':ticker,'first_observed_at':x['observed_at'],'max_close_gain_5_observations_pct':gain,'candidate':x['candidate'],'metric':'5개 후속 관측 일봉 종가 중 +10% 도달; 장중 고가·실현수익 아님'}
            if x['candidate']:positives.append(item)
            elif gain>=10:misses.append(item)
    for t in ('SHFS','INLF','NCPL','SAIL','TNGX'):
        r=by.get(t,[])
        cases.append({'ticker':t,'status':'전향 관측 축적 중' if r else '검증 불가','first_observed_at':r[0]['observed_at'] if r else None,'pre_spike_detection':None,'ignition_at':next((x['observed_at'] for x in r if x['stage']=='IGNITION'),None),'reason':'급등 사건 날짜·당시 공개 CTB/잔량·SEC 계약 상태 스냅샷 미확보; 현재값으로 소급하지 않음'})
    false=[x for x in positives if x['max_close_gain_5_observations_pct']<10]
    return {'observations':snapshots,'updated_at':now.isoformat()},{'status':'전향 검증 '+str(len(positives))+'건 성숙' if positives else '검증 불가 · 시점 일치 과거 스냅샷 부족; 전향 기록 시작','cases':cases,'evaluated_signals':len(positives),'false_positive_count':len(false) if positives else None,'false_positive_rate':100*len(false)/len(positives) if positives else None,'missed_count':len(misses) if positives or misses else None,'false_positives':false[-20:],'misses':misses[-20:],'note':'결제일을 공개일로 대체하지 않음. 최초 탐지는 실제 스캔 관측시각. 지연 일봉은 D-3 조기 탐지를 보장하지 않음.'}

async def collect():
    now=datetime.now(timezone.utc);cache=read('squeeze-cache.json',{'symbols':{}});symbols=cache.setdefault('symbols',{});sec_cache=cache.setdefault('sec',{})
    from .float_ctb import load_cache,enrich_one,get
    # Reuse source observations, never legacy candidate selection or ranks.
    shared=load_cache().get('symbols',{})
    for t,o in shared.items():
        if t not in symbols:symbols[t]={**o,'attempted_at':o.get('observed_at')}
    coverage={};failures=[]
    async with aiohttp.ClientSession() as session:
        all_stocks,listing_errors=await providers.universe(session);metadata,errors=await providers.screener_metadata(session);failures+=listing_errors+errors
        coverage['listed']=len(all_stocks);coverage['listing_complete']=not listing_errors;coverage['metadata']=len(metadata)
        stocks={};excluded=Counter()
        for t,s in all_stocks.items():
            s.update(metadata.get(t,{}));reason='warrant_depositary_security' if 'ADW' in s.get('name','') else scope_reason(s,include_trading=False)
            if reason:excluded[reason]+=1
            else:stocks[t]=s
        histories,errors=await providers.bars(session,sorted(stocks));failures+=errors;coverage['daily_attempted']=len(stocks);coverage['daily_received']=len(histories)
        from .splits import snapshot,apply
        split_feed=await snapshot(session,providers.fetch);apply(stocks.values(),split_feed)
        from .market_session import collect as calendar_collect
        calendar=await calendar_collect(session)
        selected=[]
        for t,s in stocks.items():
            s['bars']=histories.get(t,[]);b=s['bars'][-1] if s['bars'] else {};s['price']=b.get('close');s['price_as_of']=b.get('time');s['change_pct']=None
            s['toss_orderable']=None
            reason=scope_reason(s)
            if reason:excluded[reason]+=1
            else:selected.append(s)
        coverage['in_scope']=len(selected);coverage['excluded']=dict(excluded);coverage['split_feed']={k:v for k,v in split_feed.items() if k!='events'}
        budget=int(os.getenv('SQUEEZE_BORROW_BUDGET','160'));targets=due_targets(selected,symbols,now,budget)
        # Existing public adapters enforce identity, source timestamp and denied-source handling.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for result in await asyncio.to_thread(lambda:list(pool.map(enrich_one,targets))):
                t=result['ticker'];symbols[t]=merge_observation(symbols.get(t,{}),result)
        coverage['borrow_attempted_this_run']=len(targets);coverage['borrow_budget']=budget
        # Newly observed splits in public references must also exclude the stock.
        current=[]
        for s in selected:
            s['enrichment']=symbols.get(s['ticker'],{})
            if scope_reason(s):excluded[scope_reason(s)]+=1
            else:current.append(s)
        selected=current;coverage['in_scope']=len(selected);coverage['excluded']=dict(excluded)
        preliminary=[(s,analyze(s,symbols.get(s['ticker'],{}),now)) for s in selected]
        short_watch=[s for s,a in sorted(preliminary,key=lambda x:(len(x[1]['signals']),x[1]['observed_score'] or -1),reverse=True) if len(a['signals'])>=2][:100]
        intra,errors=await intraday(session,short_watch);coverage['intraday_attempted']=len(short_watch);coverage['intraday_received']=len(intra);coverage['intraday_errors']=errors
        ciks,errors=await providers.sec_index(session);failures+=errors
        from .sec import analyze as sec_analyze,outstanding_fact
        # SEC budget independent of legacy engine; oldest lookup among pressure candidates first.
        sec_targets=sorted(short_watch,key=lambda s:sec_cache.get(s['ticker'],{}).get('checked_at',''))[:12]
        for s in sec_targets:
            t=s['ticker'];prior=sec_cache.get(t,{})
            checked=instant(prior.get('checked_at'))
            if checked and (now-checked).total_seconds()<21600:continue
            cik=ciks.get(t)
            if cik:
                filings=await providers.sec_timeline(session,cik);review=await sec_analyze(session,cik,filings,budget=2);fact=await outstanding_fact(session,cik,now.isoformat())
                sec_cache[t]={'checked_at':datetime.now(timezone.utc).isoformat(),'sec':review,'outstanding_fact':fact}
            else:sec_cache[t]={'checked_at':now.isoformat(),'sec':{'status':'SEC 식별·접근 불가','reviewed':False}}
        from .halts import snapshot as halt_snapshot,recent_trades,classify
        halt_feed=await asyncio.to_thread(halt_snapshot);trades,trade_errors=await asyncio.to_thread(recent_trades,[s['ticker'] for s in short_watch])
        coverage['halt_source']=halt_feed.get('status');coverage['trade_errors']=trade_errors
        fx=None
        try:
            f=await providers.fetch(session,'https://api.frankfurter.app/latest',params={'from':'USD','to':'KRW'});fx={'rate':f['rates']['KRW'],'as_of':f['date'],'source':'https://www.frankfurter.app/'}
        except (RuntimeError,KeyError):pass
    finished=datetime.now(timezone.utc);coverage['elapsed_seconds']=round((finished-now).total_seconds());rows=[]
    for s in selected:
        t=s['ticker'];s['intraday']=intra.get(t,[]);s['sec']=sec_cache.get(t,{}).get('sec',{});s['outstanding_fact']=sec_cache.get(t,{}).get('outstanding_fact');s['halt_check']=classify(t,halt_feed,trades.get(t),finished);s['halt_status']=s['halt_check']['status']
        s['change_pct']=((s['bars'][-1]['close']/s['bars'][-2]['close']-1)*100) if len(s['bars'])>=2 else None
        rows.append((s,analyze(s,symbols.get(t,{}),finished)))
    coverage['ctb_valid']=sum(a['ctb']['valid'] for s,a in rows);coverage['si_valid']=sum(a['official_interest']['scoring_valid'] for s,a in rows);coverage['sec_documents']=sum(bool(a['dilution'].get('documents')) for s,a in rows);coverage['unobserved_borrow']=sum(not symbols.get(s['ticker'],{}).get('borrow') for s in selected)
    try:
        probe=next(iter(selected),None)
        if probe:
            page=await asyncio.to_thread(get,'https://fintel.io/ss/us/'+probe['ticker'].lower());fintel={'status':'페이지 수신 · 숫자 교차검증 미완료','cross_verified':False}
        else:fintel={'status':'대상 없음','cross_verified':False}
    except Exception as exc:fintel={'status':'검증 불가 · '+('HTTP '+str(exc.code) if getattr(exc,'code',None) else type(exc).__name__),'cross_verified':False}
    ordered=sorted(rows,key=lambda x:((x[1]['observed_score'] if x[1]['observed_score'] is not None else -1),x[1]['coverage']),reverse=True)
    valid=[(s,a) for s,a in ordered if a['candidate'] and not a['high_risk'] and s['halt_status'] in ('no_halt_detected','resumed')]
    research=valid[:10];actionable=[(s,a) for s,a in valid if a['toss_orderable'] and a['dilution']['status'] in ('희석 공백 확인','즉시 출회 가능성 낮음')][:10]
    risk=[(s,a) for s,a in ordered if a['candidate'] and a['high_risk']]
    state=update_history(read('squeeze-state.json',{}),[a for s,a in rows],finished)
    archive,backtest=replay(read('squeeze-snapshots.json',{}),rows,finished)
    # Detail storage includes independent pressure list and top observations, not legacy lists.
    detail_tickers={s['ticker'] for s in short_watch}|{s['ticker'] for s,a in ordered[:30]}
    details={s['ticker']:{'stock':{**s,'bars':s['bars'][-260:],'intraday':s['intraday'][-300:]},'observation':symbols.get(s['ticker'],{}),'analysis':a} for s,a in rows if s['ticker'] in detail_tickers}
    def summary(pair):
        s,a=pair;return {'ticker':s['ticker'],'name':s['name'],'exchange':s['exchange'],'price':s['price'],'change_pct':s['change_pct'],'market_cap':s.get('market_cap'),'float':symbols.get(s['ticker'],{}).get('float',{}),'outstanding_fact':s.get('outstanding_fact'),'halt_status':s['halt_status'],'analysis':a}
    series={}
    for s,a in rows:
        series.setdefault(s['ticker'][0],{})[s['ticker']]=[[b.get(k) for k in ('time','open','high','low','close','volume','vwap')] for b in safe_bars(s['bars'],finished)[-260:]]
    for letter,values in series.items():(ROOT/('squeeze-series-'+letter+'.json')).write_text(json.dumps(values,separators=(',',':'),allow_nan=False))
    result={'engine':'SHORT SQUEEZE HUNTER 1.0','started_at':now.isoformat(),'updated_at':finished.isoformat(),'status':'partial' if failures or coverage['unobserved_borrow'] else 'collected','source_scope':'NASDAQ/NYSE/NYSE American 전체 상장 목록에서 독립 시작; 기존 후보·점수·순위 미사용','session':session_state(calendar,finished),'market_calendar':calendar,'coverage':coverage,'failures':failures[:100],'top10':[summary(x) for x in actionable],'research_top10':[summary(x) for x in research],'high_risk':[summary(x) for x in risk[:30]],'observations':[summary(x) for x in ordered],'details':details,'fx':fx,'fintel':fintel,'backtest':backtest,'schedule':{'cron':'7,22,37,52 * * * 1-5','nominal_minutes':15,'note':'UTC 평일 · 시장 세션 포함; GitHub Actions 대기·실행 시간으로 지연 가능. 대차 160종목/회 순환; 전체 시세 매 실행 재평가','market_feed':'IEX 부분 거래소 일봉 + 숏 근거 종목 최대100개 5분봉','intraday_delay_minutes_minimum':20},'limits':['실시간·전체 시장 체결 데이터 아님','Fintel 숫자 교차검증 미완료','SEC 원문·계약 조건이 미확정이면 희석 점수 미부여','토스 실제 주문 가능 여부 미확인 종목은 실전 TOP10 제외','D-3~D-1 예측 적중률·거짓양성률 검증 자료 축적 전','공매도 실제 진입가·강제청산·청산완료 비율 추정 금지']}
    for name,value in (('squeeze-hunter.json',result),('squeeze-cache.json',{**cache,'updated_at':finished.isoformat(),'symbols':symbols,'sec':sec_cache}),('squeeze-state.json',state),('squeeze-snapshots.json',archive)):(ROOT/name).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False))
    print(json.dumps({'coverage':coverage,'research_top10':[s['ticker'] for s,a in research],'actionable_top10':len(actionable),'fintel':fintel,'stages':dict(Counter(a['stage'] or '미확정' for s,a in rows))},ensure_ascii=False))
    return result
if __name__=='__main__':asyncio.run(collect())
