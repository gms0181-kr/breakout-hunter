"""Future-only reader. Detection never imports this module or accepts its data."""
import copy
from datetime import timedelta
from .squeeze_signals import instant,finite
from .time_machine import digest

def evaluate(selection,outcomes,stop_pct=5,slippage_bps=10,shares=100):
    original={k:v for k,v in selection.items() if k!='selection_hash'}
    if digest(original)!=selection.get('selection_hash'):raise ValueError('후보 확정 해시 불일치')
    if not 0<stop_pct<100 or not 0<=slippage_bps<=1000 or shares<=0:raise ValueError('평가 가정 범위 오류')
    cutoff=instant(selection['as_of']);rows=[]
    for c in selection['candidates']:
        data=outcomes.get(c['ticker'],{});entry={'ticker':c['ticker'],'name':c['name'],'replay_status':c['status'],'status':'NOT EVALUABLE','horizons':{},'fill_verified':False}
        # Intraday executable quotes were not archived: never claim the signal close was fillable.
        bars=sorted([b for b in data.get('bars',[]) if instant(b.get('event_time')) and instant(b['event_time'])>cutoff and instant(b.get('session_open')) and instant(b['session_open'])>cutoff and all(finite(b.get(k)) and b[k]>0 for k in ('open','high','low','close','volume'))],key=lambda b:b['event_time'])
        if not bars:rows.append({**entry,'reason':'신호 이후 새 정규장 일봉·호가 기록 미확보'});continue
        end=instant(bars[min(4,len(bars)-1)]['event_time'])
        splits=[e for e in data.get('split_events',[]) if str(e.get('ex_date',''))[:10]>cutoff.date().isoformat() and str(e.get('ex_date',''))[:10]<=end.date().isoformat()]
        basis=data.get('price_basis_by_snapshot',{}).get(selection.get('source_snapshot'),data.get('price_basis_verified',False))
        if splits or not basis:
            rows.append({**entry,'reason':'병합·수정주가 기준의 시점 간 일치 미검증'});continue
        price=bars[0]['open']*(1+slippage_bps/10000)
        entry.update(status='PROXY ONLY',entry_at=bars[0]['session_open'],entry_price=price,entry_basis='신호 이후 첫 관측 정규장 일봉 시가 + 슬리피지 가정; 실제 체결 가능 가격 아님',source=data.get('source'),liquidity={'shares':shares,'first_day_observed_volume':bars[0]['volume'],'participation_pct':100*shares/bars[0]['volume'],'partial_market':True,'quotes_available':False},session='regular',extended_hours='프리마켓·애프터마켓 체결 재현 불가')
        for n in (1,3,5):
            if len(bars)<n:entry['horizons'][str(n)]={'status':'NOT MATURE'};continue
            part=bars[:n];target=price*1.1;stop=price*(1-stop_pct/100);order='not_hit'
            for b in part:
                hit=b['high']>=target;loss=b['low']<=stop
                if hit and loss:order='ambiguous_same_daily_bar';break
                if loss:order='stop_before_target';break
                if hit:order='target_before_stop';break
            entry['horizons'][str(n)]={'status':'PROXY ONLY','return_pct':100*(part[-1]['close']*(1-slippage_bps/10000)/price-1),'max_up_pct':100*(max(b['high'] for b in part)/price-1),'max_down_pct':100*(min(b['low'] for b in part)/price-1),'target_10_pct':any(b['high']>=target for b in part),'target_stop_order':order,'stop_pct':stop_pct,'commission_included':False}
        rows.append(entry)
    return {'selection_hash':selection['selection_hash'],'rows':rows,'verified_count':0,'verified_success_rate':None,'partial_excluded_from_success_rate':True,'note':'IEX 부분 거래소 일봉 기반 가정 결과. 동일 봉 목표·손절 도달 순서 미확정은 성공으로 세지 않음. 호가·전체 체결·상장폐지 수익 미확보로 검증 성공률 산출 불가.'}
