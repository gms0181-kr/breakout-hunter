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
from .squeeze_discovery import select_borrow,select_intraday,market_probe
from .squeeze_signals import analyze,instant,finite,update_history,safe_bars
ROOT=Path('public')
def read(name,default):
    try:return json.loads((ROOT/name).read_text())
    except (OSError,ValueError):return default

def due_targets(stocks,cache,now,budget):
    return select_borrow(stocks,cache,now,budget)

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
    """Forward-only: daily observations and actual detection-time signals separate."""
    snapshots=list(archive.get('observations',[]));signals=list(archive.get('signals',[]))
    known={(x['ticker'],x['price_at']) for x in snapshots};signal_days={(x['ticker'],x['observed_at'][:10]) for x in signals}
    for s,a in rows:
        m=a['market'];key=(s['ticker'],m.get('as_of'))
        if not m.get('valid'):continue
        if key not in known:
            snapshots.append({'ticker':s['ticker'],'observed_at':now.isoformat(),'price_at':m['as_of'],'price':m['price'],'candidate':a['candidate'],'candidate_type':a.get('candidate_type','legacy_unknown'),'stage':a['stage'],'score':a['observed_score'],'coverage':a['coverage'],'ctb_at':a['ctb'].get('as_of'),'ctb_known_at':a['ctb'].get('observed_at'),'si_known_at':a['official_interest'].get('observed_at'),'dilution_status':a['dilution']['status']});known.add(key)
        # First actual candidate each UTC date, even if the daily candle is unchanged.
        sk=(s['ticker'],now.date().isoformat())
        if a['candidate'] and sk not in signal_days:
            intra=a.get('intraday',{});signals.append({'ticker':s['ticker'],'observed_at':now.isoformat(),'price':intra['price'] if intra.get('valid') else m['price'],'price_at':intra['as_of'] if intra.get('valid') else m['as_of'],'basis':'지연 IEX 5분봉' if intra.get('valid') else '완료 일봉 · 체결 가능 진입가 아님','candidate_type':a.get('candidate_type','legacy_unknown'),'stage':a['stage'],'score':a['observed_score'],'coverage':a['coverage'],'ctb_known_at':a['ctb'].get('observed_at'),'si_known_at':a['official_interest'].get('observed_at')});signal_days.add(sk)
    snapshots=snapshots[-50000:];signals=signals[-10000:];by={};positives=[];misses=[]
    for x in snapshots:by.setdefault(x['ticker'],[]).append(x)
    for records in by.values():records.sort(key=lambda x:x['price_at'])
    def future_for(x):return [y for y in by.get(x['ticker'],[]) if instant(y['price_at'])>instant(x['observed_at']) and instant(y['observed_at'])>instant(x['observed_at']) and instant(y['observed_at'])-instant(x['observed_at'])<=timedelta(days=12)][:5]
    for x in signals:
        future=future_for(x)
        if len(future)<5:continue
        gain=max((y['price']/x['price']-1)*100 for y in future)
        positives.append({'ticker':x['ticker'],'first_observed_at':x['observed_at'],'candidate_type':x.get('candidate_type','legacy_unknown'),'baseline_basis':x['basis'],'max_close_gain_5_observations_pct':gain,'metric':'탐지 후 관측한 5개 완료 일봉 종가 중 +10% 도달; 장중 스파이크·실현수익 아님'})
    for t,records in by.items():
        for x in records:
            future=future_for(x)
            if len(future)<5:continue
            gains=[(y['price']/x['price']-1)*100 for y in future]
            if max(gains)<10:continue
            reached=future[next(i for i,v in enumerate(gains) if v>=10)]
            if not any(z['ticker']==t and instant(x['observed_at'])<=instant(z['observed_at'])<instant(reached['price_at']) for z in signals):
                misses.append({'ticker':t,'baseline_observed_at':x['observed_at'],'max_close_gain_5_observations_pct':max(gains),'reason':'상승 관측일 이전 저장된 탐지 신호 없음'})
    cases=[]
    for t in ('SHFS','INLF','NCPL','SAIL','TNGX'):
        r=by.get(t,[]);detected=[x for x in signals if x['ticker']==t]
        cases.append({'ticker':t,'status':'전향 관측 축적 중' if r else '검증 불가','first_observed_at':detected[0]['observed_at'] if detected else None,'pre_spike_detection':None,'ignition_at':next((x['observed_at'] for x in detected if x['stage']=='IGNITION'),None),'reason':'지정 급등 사건 날짜·당시 공개 CTB/잔량·SEC 계약 상태 스냅샷 미확보; 현재값으로 소급하지 않음'})
    false=[x for x in positives if x['max_close_gain_5_observations_pct']<10]
    return {'observations':snapshots,'signals':signals,'updated_at':now.isoformat()},{'status':'전향 검증 '+str(len(positives))+'건 성숙' if positives else '검증 불가 · 시점 일치 과거 스냅샷 부족; 전향 기록 시작','cases':cases,'evaluated_signals':len(positives),'false_positive_count':len(false) if positives else None,'false_positive_rate':100*len(false)/len(positives) if positives else None,'missed_count':len(misses) if positives or misses else None,'false_positives':false[-20:],'misses':misses[-20:],'note':'결제일을 공개일로 대체하지 않음. 탐지는 실제 스캔 관측시각, 후속 비교는 12일 내 5개 완료 일봉. 지연 기준가·중복 관측·미탐지 표본 선택 한계가 있어 실전 적중률이 아님.'}

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
        stocks={};excluded=Counter();audit={t:{'listed':True,'name':v.get('name'),'observed_at':now.isoformat(),'listing_source':v.get('universe_source'),'daily_received':False} for t,v in all_stocks.items()}
        for t,s in all_stocks.items():
            s.update(metadata.get(t,{}));reason='warrant_depositary_security' if 'ADW' in s.get('name','') else scope_reason(s,include_trading=False)
            audit[t]['scope_reason']=reason
            if reason:excluded[reason]+=1
            else:stocks[t]=s
        histories,errors=await providers.bars(session,sorted(stocks));failures+=errors;coverage['daily_attempted']=len(stocks);coverage['daily_received']=len(histories)
        from .splits import snapshot,apply
        split_feed=await snapshot(session,providers.fetch);apply(stocks.values(),split_feed)
        from .market_session import collect as calendar_collect
        calendar=await calendar_collect(session)
        selected=[]
        for t,s in stocks.items():
            s['bars']=histories.get(t,[]);b=s['bars'][-1] if s['bars'] else {};s['price']=b.get('close');s['price_as_of']=b.get('time');s['change_pct']=None;audit[t]['daily_received']=bool(s['bars']);audit[t]['price_as_of']=s['price_as_of']
            s['toss_orderable']=None
            reason=scope_reason(s)
            audit[t]['scope_reason']=reason
            if reason:excluded[reason]+=1
            else:selected.append(s)
        coverage['in_scope']=len(selected);coverage['excluded']=dict(excluded);coverage['split_feed']={k:v for k,v in split_feed.items() if k!='events'}
        budget=max(0,min(1000,int(os.getenv('SQUEEZE_BORROW_BUDGET','240'))));targets=due_targets(selected,symbols,datetime.now(timezone.utc),budget)
        # Existing public adapters enforce identity, source timestamp and denied-source handling.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for result in await asyncio.to_thread(lambda:list(pool.map(enrich_one,targets))):
                t=result['ticker'];symbols[t]=merge_observation(symbols.get(t,{}),result)
        coverage['borrow_attempted_this_run']=len(targets);coverage['borrow_budget']=budget
        from .short_reports import latest_finra
        short_volume,short_volume_source=await asyncio.to_thread(latest_finra,get)
        cache['short_volume_source']=short_volume_source
        for stock in selected:
            ticker=stock['ticker'];obs=symbols.setdefault(ticker,{'ticker':ticker,'name':stock.get('name')})
            obs['short_volume']=short_volume.get(ticker,{**short_volume_source,'status':'symbol_not_in_latest_file' if short_volume_source.get('status')=='ok' else 'source_unavailable'})
        coverage['short_volume_received']=sum(stock['ticker'] in short_volume for stock in selected)
        # Newly observed splits in public references must also exclude the stock.
        current=[]
        for s in selected:
            s['enrichment']=symbols.get(s['ticker'],{})
            if scope_reason(s):
                audit[s['ticker']]['scope_reason']=scope_reason(s);excluded[scope_reason(s)]+=1
            else:current.append(s)
        selected=current;coverage['in_scope']=len(selected);coverage['excluded']=dict(excluded)
        screen_at=datetime.now(timezone.utc)
        preliminary=[(s,analyze(s,symbols.get(s['ticker'],{}),screen_at)) for s in selected]
        short_watch=select_intraday(preliminary,symbols,screen_at,max(0,min(1000,int(os.getenv('SQUEEZE_INTRADAY_BUDGET','200')))))
        for stock in short_watch:symbols[stock['ticker']]['intraday_attempted_at']=screen_at.isoformat()
        intra,errors=await intraday(session,short_watch);coverage['intraday_attempted']=len(short_watch);coverage['intraday_received']=len(intra);coverage['intraday_errors']=errors
        coverage['intraday_selection']='가격 선행 + 숏 압박 + 전체 종목 순환; CTB 불필요'
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
    valid=[(s,a) for s,a in ordered if a['candidate'] and a.get('candidate_type')=='short_verified' and not a['high_risk'] and s['halt_status'] in ('no_halt_detected','resumed')]
    early_watch=sorted([(s,a) for s,a in rows if a.get('early_signal',{}).get('triggered') and s['halt_status'] in ('no_halt_detected','resumed')],key=lambda x:((x[1]['early_signal'].get('change_pct') or 0),x[1]['early_signal'].get('dollar_ratio') or 0),reverse=True)[:20]
    research=valid[:10];actionable=[(s,a) for s,a in valid if a['toss_orderable'] and a['dilution']['status'] in ('희석 공백 확인','즉시 출회 가능성 낮음')][:10]
    risk=[(s,a) for s,a in ordered if a['candidate'] and a['high_risk']]
    state=update_history(read('squeeze-state.json',{}),[a for s,a in rows],finished)
    from .squeeze_delivery import deliver
    state['delivery']=deliver(state.get('alerts',[]),read('squeeze-state.json',{}).get('delivery',{}),finished)
    archive,backtest=replay(read('squeeze-snapshots.json',{}),rows,finished)
    # Detail storage includes independent pressure list and top observations, not legacy lists.
    detail_tickers={s['ticker'] for s in short_watch}|{s['ticker'] for s,a in ordered[:30]}
    details={s['ticker']:{'stock':{**s,'bars':s['bars'][-260:],'intraday':s['intraday'][-300:]},'observation':symbols.get(s['ticker'],{}),'analysis':a} for s,a in rows if s['ticker'] in detail_tickers}
    def summary(pair):
        s,a=pair;return {'ticker':s['ticker'],'name':s['name'],'exchange':s['exchange'],'price':s['price'],'price_as_of':s.get('price_as_of'),'change_pct':s['change_pct'],'market_cap':s.get('market_cap'),'float':symbols.get(s['ticker'],{}).get('float',{}),'short_volume':symbols.get(s['ticker'],{}).get('short_volume',{}),'outstanding_fact':s.get('outstanding_fact'),'halt_status':s['halt_status'],'analysis':a}
    from .squeeze_audit import cases
    diagnostics=cases(audit,rows,symbols,targets,short_watch,research,finished)
    series={}
    for s,a in rows:
        series.setdefault(s['ticker'][0],{})[s['ticker']]=[[b.get(k) for k in ('time','open','high','low','close','volume','vwap')] for b in safe_bars(s['bars'],finished)[-260:]]
    for letter,values in series.items():(ROOT/('squeeze-series-'+letter+'.json')).write_text(json.dumps({'schema_version':2,'snapshot_id':finished.isoformat(),'symbols':values},separators=(',',':'),allow_nan=False))
    result={'schema_version':2,'snapshot_id':finished.isoformat(),'monitor':{'updated_at':state['updated_at'],'history':state['history'],'alerts':state['alerts'],'delivery':state['delivery']},'engine':'SHORT SQUEEZE HUNTER 1.0','started_at':now.isoformat(),'updated_at':finished.isoformat(),'status':'partial' if failures or coverage['unobserved_borrow'] else 'collected','source_scope':'NASDAQ/NYSE/NYSE American 전체 상장 목록에서 독립 시작; 기존 후보·점수·순위 미사용','session':session_state(calendar,finished),'market_calendar':calendar,'coverage':coverage,'failures':failures[:100],'diagnostics':diagnostics,'universe_audit':audit,'early_watch':[summary(x) for x in early_watch],'top10':[summary(x) for x in actionable],'research_top10':[summary(x) for x in research],'high_risk':[summary(x) for x in risk[:30]],'observations':[summary(x) for x in ordered],'details':details,'fx':fx,'fintel':fintel,'backtest':backtest,'schedule':{'cron':'7,22,37,52 * * * 1-5','nominal_minutes':15,'note':'UTC 평일 · 시장 세션 포함; GitHub Actions 대기·실행 시간으로 지연 가능. 대차 기본240종목/회: 가격 선행 우선+최소 절반 전체 순환; 전체 시세 매 실행 재평가','market_feed':'IEX 부분 거래소 일봉 + 가격 선행·숏 근거·전체 순환 기본200종목 5분봉','intraday_delay_minutes_minimum':20},'limits':['실시간·전체 시장 체결 데이터 아님','Fintel 숫자 교차검증 미완료','SEC 원문·계약 조건이 미확정이면 희석 점수 미부여','토스 실제 주문 가능 여부 미확인 종목은 실전 TOP10 제외','D-3~D-1 예측 적중률·거짓양성률 검증 자료 축적 전','공매도 실제 진입가·강제청산·청산완료 비율 추정 금지']}
    for name,value in (('squeeze-hunter.json',result),('squeeze-cache.json',{**cache,'updated_at':finished.isoformat(),'symbols':symbols,'sec':sec_cache}),('squeeze-state.json',state),('squeeze-snapshots.json',archive)):(ROOT/name).write_text(json.dumps(value,ensure_ascii=False,allow_nan=False))
    print(json.dumps({'coverage':coverage,'research_top10':[s['ticker'] for s,a in research],'actionable_top10':len(actionable),'fintel':fintel,'stages':dict(Counter(a['stage'] or '미확정' for s,a in rows))},ensure_ascii=False))
    return result
if __name__=='__main__':asyncio.run(collect())
