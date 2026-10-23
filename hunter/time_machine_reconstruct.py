"""External historical reconstruction, isolated from live collection and outcomes.

No archive rows and no future returns are read. The asset catalogue is a discovery
superset only; it is NOT a historical exchange security master. Price existence
cannot prove historical common-stock / small-cap eligibility.
"""
import argparse,asyncio,gzip,json,math,os,re
from collections import Counter
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import aiohttp
from .time_machine import et_instant,run_detection,digest
from .squeeze_signals import instant

SOURCE='https://data.alpaca.markets/v2/stocks/bars'
ASSETS='https://paper-api.alpaca.markets/v2/assets'
ET=ZoneInfo('America/New_York')
MISSING=['당시 전체 상장·상장폐지·심볼 변경 목록 미확보', '과거 CTB·대차 잔량 미확인','당시 SEC 원문·유통주식수·병합 검증 미확인','당시 시가총액·증권 종류·중국계 분류 미확인','IEX 일부 시장 자료; 원본 당시 버전과 최초 공개 시각 미검증']

class Client:
    def __init__(self,session,key,secret):
        self.session=session;self.headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret};self.errors=[];self.calls=0;self.last_status=None;self.failures={}
    async def get(self,url,params):
        # Sequential requests stay below Basic's request budget. Never log headers/body.
        self.last_status=None
        await asyncio.sleep(.35)
        last_status=None
        for attempt in range(3):
            self.calls+=1
            try:
                async with self.session.get(url,headers=self.headers,params=params,timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status==429 or response.status>=500:
                        last_status=response.status
                        await asyncio.sleep(2**attempt);continue
                    if response.status!=200:
                        self.last_status=response.status
                        self.errors.append({'endpoint':'assets' if url==ASSETS else 'bars','status':response.status});return None
                    return await response.json()
            except (aiohttp.ClientError,asyncio.TimeoutError):
                if attempt==2:self.errors.append({'endpoint':'transport','status':'unavailable'})
        if last_status:self.last_status=last_status
        if last_status:self.errors.append({'endpoint':'assets' if url==ASSETS else 'bars','status':last_status,'retry_exhausted':True})
        return None

async def catalogue(client):
    discovered={};counts={}
    for status in ('active','inactive'):
        rows=await client.get(ASSETS,{'status':status,'asset_class':'us_equity'})
        counts[status]=len(rows) if isinstance(rows,list) else None
        for asset in rows if isinstance(rows,list) else []:
            symbol=asset.get('symbol','')
            # Do NOT filter on today's tradable/exchange/name/cap/status. Inactive,
            # OTC and renamed instruments may have been listed on the chosen day.
            if re.fullmatch(r'[A-Z][A-Z0-9.\-/]{0,19}',symbol):discovered[symbol]=True
    return sorted(discovered),counts

async def history(client,symbols,cutoff,timeframe):
    result={};start=cutoff-timedelta(days=120 if timeframe=='1Day' else 1)
    if not hasattr(client,'failures'):client.failures={}
    async def batch(chunk):
        params={'symbols':','.join(chunk),'timeframe':timeframe,'start':start.isoformat(),'end':cutoff.isoformat(),'feed':'iex','adjustment':'raw','asof':cutoff.astimezone(ET).date().isoformat(),'limit':10000,'sort':'asc'}
        seen=set()
        while True:
            data=await client.get(SOURCE,params)
            if not isinstance(data,dict):
                # One unsupported catalogue symbol must not hide 99 valid symbols.
                # Bisect only malformed-request responses, never authentication or
                # entitlement errors. No response body or secrets are logged.
                if getattr(client,'last_status',None)==400 and len(chunk)>1 and not seen:
                    middle=len(chunk)//2;await batch(chunk[:middle]);await batch(chunk[middle:])
                else:client.failures.setdefault(timeframe,[]).extend(chunk)
                break
            for symbol,bars in data.get('bars',{}).items():result.setdefault(symbol,[]).extend(bars)
            token=data.get('next_page_token')
            if not token:break
            if token in seen:raise ValueError('반복된 페이지 토큰; 불완전 수집 중단')
            seen.add(token);params['page_token']=token
    for i in range(0,len(symbols),100):await batch(symbols[i:i+100])
    return result

def normalize(raw,cutoff,timeframe):
    clean=[]
    for b in raw:
        stamp=instant(b.get('t'))
        if not stamp:continue
        # Entire daily aggregate is unsafe during its session. Use next ET midnight
        # plus 20min as a conservative estimated availability, NOT publication proof.
        end=(datetime.combine(stamp.astimezone(ET).date()+timedelta(days=1),datetime.min.time(),ET).astimezone(timezone.utc) if timeframe=='1Day' else stamp+timedelta(minutes=5))
        available=end+timedelta(minutes=20)
        if available>cutoff:continue
        try:
            v={k:float(b[n]) for k,n in [('open','o'),('high','h'),('low','l'),('close','c'),('volume','v')]}
            if not all(math.isfinite(x) for x in v.values()) or min(v.values())<=0 or v['low']>min(v['open'],v['close']) or v['high']<max(v['open'],v['close']):continue
        except (KeyError,TypeError,ValueError):continue
        clean.append({**v,'time':stamp.isoformat(),'event_time':end.isoformat(),'available_at':available.isoformat(),'complete':True,'vwap':b.get('vw'),'source':'Alpaca IEX historical raw','source_adjustment':'raw; historical corrections/vintage unverified'})
    return sorted({b['time']:b for b in clean}.values(),key=lambda b:b['time'])

def envelope(value,event,available,retrieved,basis):
    return {'value':value,'event_time':event,'published_at':None,'available_at':available,'retrieved_at':retrieved,'source':SOURCE,'availability_basis':basis,'availability_verified':False}

async def reconstruct(client,cutoff,scope='all'):
    symbols,counts=await catalogue(client)
    daily=await history(client,symbols,cutoff,'1Day') if symbols else {}
    # Every discovered instrument with historical prices is considered; no future
    # winner lists, saved candidate ranks or short-data gates select this request.
    price_symbols=sorted(s for s in symbols if normalize(daily.get(s,[]),cutoff,'1Day'))
    intra=await history(client,price_symbols,cutoff,'5Min') if price_symbols else {}
    retrieved=datetime.now(timezone.utc).isoformat();rows=[];stats=Counter()
    for symbol in symbols:
        bars=normalize(daily.get(symbol,[]),cutoff,'1Day')
        if not bars:stats['no_completed_daily_bars']+=1;continue
        if len(bars)<22:stats['insufficient_daily_bars']+=1
        else:stats['engine_usable_daily']+=1
        intraday=normalize(intra.get(symbol,[]),cutoff,'5Min')
        if not intraday:stats['no_intraday_bars']+=1
        stock={'ticker':symbol,'name':'당시 회사명·상장 유형 미검증','historical_eligibility':'unverified','price':bars[-1]['close']}
        # Ticker is an index key, not today's issuer/fund/cap metadata. No current
        # asset name/status enters the scoring engine.
        last=bars[-1]
        inputs={'stock':envelope(stock,last['event_time'],last['available_at'],retrieved,'historical price existence; listing and security type unverified'),'bars':envelope(bars,last['event_time'],last['available_at'],retrieved,'completed aggregate + conservative 20min buffer; original publication/vintage unverified')}
        if intraday:
            b=intraday[-1];inputs['intraday']=envelope(intraday,b['event_time'],b['available_at'],retrieved,'5min aggregate end +20min; original publication/vintage unverified')
        rows.append({'inputs':inputs})
    report={'catalogue_source':ASSETS,'price_source':SOURCE,'feed':'iex','adjustment':'raw','catalogue_counts':counts,'requested_symbols':len(symbols),'with_historical_prices':len(rows),'unknown_historical_universe_size':True,'historical_universe_size':None,'missing_universe_count':None,'historical_listing_verified':0,'historical_smallcap_verified':0,'eligibility_unverified':len(rows),**dict(stats),'failed_request_symbols':{k:sorted(set(v)) for k,v in getattr(client,'failures',{}).items()},'api_requests':client.calls,'errors':client.errors,'missing':MISSING,'selection_policy':'active + inactive external catalogue; all symbols queried before scoring; no outcome data','requested_cutoff':cutoff.isoformat()}
    snapshot={**envelope(None,cutoff.isoformat(),cutoff.isoformat(),retrieved,'request boundary only; not a historical universe attestation'),'acquisition_mode':'HISTORICAL RECONSTRUCTION','universe_complete':False,'rows':rows,'coverage_report':report,'source_commit':None}
    result=run_detection(snapshot,cutoff.isoformat(),scope)
    result['missing']=sorted(set(result['missing']+MISSING));result['eligibility_note']='탐색 신호이며 당시 상장 보통주·소형주 적격 후보로 검증되지 않음'
    return {'schema':1,'as_of':cutoff.isoformat(),'retrieved_at':retrieved,'snapshot':snapshot,'result':result,'input_sha256':digest(snapshot)}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--et',required=True);parser.add_argument('--scope',choices=['all','china'],default='all');parser.add_argument('--output',default='public/time-machine/reconstruction-latest.json');args=parser.parse_args()
    cutoff=et_instant(args.et)
    if cutoff>=datetime.now(timezone.utc):raise ValueError('완료된 과거 시각을 선택하세요')
    key=os.environ.get('ALPACA_API_KEY');secret=os.environ.get('ALPACA_API_SECRET')
    if not key or not secret:raise ValueError('기존 Alpaca Secrets 접근 불가; 값은 출력하지 않습니다')
    async def run():
        async with aiohttp.ClientSession() as session:return await reconstruct(Client(session,key,secret),cutoff,args.scope)
    result=asyncio.run(run());path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    # Full collected inputs are evidence artifacts, never a >100MB Git blob.
    evidence=path.with_suffix('.inputs.json.gz')
    with gzip.open(evidence,'wt',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    summary={k:v for k,v in result.items() if k!='snapshot'}
    summary['result']=dict(result['result']);locked=result['result']['frozen']
    summary['result']['frozen']={'selection_hash':locked['selection_hash'],'candidate_count':len(locked['candidates'])}
    summary['evidence_note']='Complete inputs and frozen candidate set retained in GitHub Actions evidence artifact; public report displays TOP20.'
    path.write_text(json.dumps(summary,ensure_ascii=False,allow_nan=False,separators=(',',':'))) 
    print(json.dumps({'status':result['result']['status'],'candidate_count':result['result']['candidate_count'],'coverage':result['result']['coverage_report']},ensure_ascii=False))

if __name__=='__main__':main()
