"""INLF fixed-cutoff reconstruction; never labels absent PIT snapshots a success."""
import os
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from .providers import fetch,sec_timeline
from .verification import instant

async def replay_inlf(session,cik=None):
    now=datetime.now(timezone.utc)
    result={'ticker':'INLF','name':'INLIF Limited','retrieved_at':now.isoformat(),'status':'partial reconstruction; certified pre-spike detection unavailable','spike_session':None,'detected_before_spike':None,'historical_rank':None,'short_history':None,'limitations':['급등 기준 거래일·시각 미지정: 사후 최고가로 탐지 기준을 최적화하지 않음','과거 공매·대차 시점 스냅샷 없음; 현재 CTB를 과거에 대입하지 않음','raw 일봉의 병합 기준 대조 및 과거 공급자 정정 이력 미검증','가격 재구성은 당시 수집한 원본 스냅샷과 다름'],'sessions':[]}
    sec=await sec_timeline(session,cik) if cik else {}
    result['sec_timeline']=sec.get('timeline',[])
    key=os.getenv('ALPACA_API_KEY');secret=os.getenv('ALPACA_API_SECRET')
    if not key or not secret:result['status']='가격 공급자 인증 없음; 검증 불가';return result
    headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}
    try:
        response=await fetch(session,'https://data.alpaca.markets/v2/stocks/INLF/bars',headers=headers,params={'timeframe':'1Day','start':(now-timedelta(days=160)).strftime('%Y-%m-%d'),'end':now.astimezone(ZoneInfo('America/New_York')).replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),'feed':'iex','adjustment':'raw','sort':'asc','limit':1000})
        bars=response.get('bars',[])
        days=[b['t'][:10] for b in bars[-5:]]
        for day in days:
            cutoff=datetime.fromisoformat(day+'T15:55:00').replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
            start=datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
            raw=await fetch(session,'https://data.alpaca.markets/v2/stocks/INLF/bars',headers=headers,params={'timeframe':'1Min','start':start.isoformat(),'end':cutoff.isoformat(),'feed':'iex','adjustment':'raw','sort':'asc','limit':10000,'asof':day})
            minutes=[b for b in raw.get('bars',[]) if start<=instant(b['t']) and instant(b['t'])+timedelta(minutes=1)<=cutoff]
            prior=[{'time':b['t'],'available_at':(instant(b['t'])+timedelta(days=1)).isoformat(),'open':b['o'],'high':b['h'],'low':b['l'],'close':b['c'],'volume':b['v'],'vwap':b.get('vw')} for b in bars if b['t'][:10]<day]
            if minutes:
                volume=sum(b['v'] for b in minutes)
                vw=sum(b.get('vw',b['c'])*b['v'] for b in minutes)/volume if volume and all(b.get('vw') is not None for b in minutes) else None
                prior.append({'time':start.isoformat(),'available_at':cutoff.isoformat(),'open':minutes[0]['o'],'high':max(b['h'] for b in minutes),'low':min(b['l'] for b in minutes),'close':minutes[-1]['c'],'volume':volume,'vwap':vw})
            filings=[f for f in sec.get('timeline',[]) if instant(f.get('accepted')) and instant(f['accepted'])<=cutoff]
            # No daily/full-session volume ratio: partial 15:55 volume is not comparable
            # to completed all-session daily volume without a matched-time baseline.
            row={'as_of':cutoff.isoformat(),'minute_count':len(minutes),'price_as_of':minutes[-1]['t'] if minutes else None,'observed_price':minutes[-1]['c'] if minutes else None,'partial_session_volume':sum(b['v'] for b in minutes) if minutes else None,'partial_session_turnover_proxy':sum(b['c']*b['v'] for b in minutes) if minutes else None,'partial_session_vwap':prior[-1].get('vwap') if minutes else None,'filings_available_by_cutoff':filings,'capital_inflow_confirmed':None,'support_oversold_confirmed':None,'immediate_dilution':None,'ctb_change':None,'borrow_change':None,'detected':None,'reason':'분봉 재구성; 동일시각 거래대금 기준선·당시 병합 조정·계약 공급 검증·과거 대차 스냅샷 부족','source':'https://data.alpaca.markets/v2/stocks/INLF/bars','feed':'IEX only, raw','lookahead_guard':'현재 날짜 full-day bar 제외; 분봉 종료<=15:55 ET; accepted timestamp<=cutoff인 공시만 포함'}
            result['sessions'].append(row)
    except (RuntimeError,ValueError,TypeError,KeyError) as exc:result['error']=type(exc).__name__
    return result
