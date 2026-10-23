"""Read-only point-in-time execution. This module cannot load future outcomes."""
import copy,hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from .squeeze_signals import analyze,instant

SCHEMA=1

def et_instant(value):
    naive=datetime.fromisoformat(value)
    if naive.tzinfo:raise ValueError('ET 현지 날짜와 시각을 입력하세요')
    tz=ZoneInfo('America/New_York');a=naive.replace(tzinfo=tz,fold=0);b=naive.replace(tzinfo=tz,fold=1)
    if a.utcoffset()!=b.utcoffset():raise ValueError('DST 전환의 중복·존재하지 않는 ET 시각입니다')
    if a.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)!=naive:raise ValueError('존재하지 않는 ET 시각')
    return a.astimezone(timezone.utc)

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def known(record,cutoff):
    if not isinstance(record,dict) or not record.get('source'):return False
    dates=[instant(record.get(k)) for k in ('event_time','available_at','retrieved_at')]
    return all(d and d<=cutoff for d in dates) and dates[0]<=dates[1]

def no_future(value,cutoff):
    """Reject, rather than silently accept, nested dated revisions/publications."""
    if isinstance(value,list):return [clean for v in value if (clean:=no_future(v,cutoff)) is not None]
    if not isinstance(value,dict):return value
    for k in ('as_of','observed_at','known_at','accepted','accepted_at','published_at','available_at','retrieved_at','time','timestamp'):
        if value.get(k) and (not instant(value[k]) or instant(value[k])>cutoff):return None
    for k in ('ex_date','settlement_date'):
        if value.get(k) and str(value[k])[:10]>cutoff.date().isoformat():return None
    return {k:no_future(v,cutoff) for k,v in value.items() if no_future(v,cutoff) is not None}

def frozen(candidates,as_of,scope,source):
    selection={'as_of':as_of,'scope':scope,'source_snapshot':source,'candidates':candidates}
    return {**selection,'selection_hash':digest(selection)}

def run_detection(snapshot,as_of,mode='all'):
    cutoff=instant(as_of)
    if not cutoff:raise ValueError('분석 시각에 시간대가 필요합니다')
    if mode not in ('all','china'):raise ValueError('지원하지 않는 탐색 범위')
    base={'as_of':cutoff.isoformat(),'mode':mode,'engine_hash':hashlib.sha256(Path(__file__).with_name('squeeze_signals.py').read_bytes()).hexdigest(),'snapshot_at':snapshot.get('available_at'),'source_commit':snapshot.get('source_commit'),'replay_type':'historical_input_backtest','universe_complete':False,'missing':[]}
    if not known(snapshot,cutoff):
        return {**base,'status':'NOT REPRODUCIBLE','reason':'분석 시각 이전에 저장·이용 가능했던 종목 스냅샷 없음','examined':0,'candidate_count':0,'top20':[],'frozen':frozen([],cutoff.isoformat(),mode,None)}
    results=[];missing=[];examined=0;china_unknown=0;rejected=0
    for row in snapshot.get('rows',[]):
        stock={};obs={};provenance=[];gaps=[]
        for key,record in row.get('inputs',{}).items():
            if not known(record,cutoff):gaps.append(key);rejected+=1;continue
            value=no_future(copy.deepcopy(record.get('value')),cutoff)
            if value is None:gaps.append(key);rejected+=1;continue
            provenance.append({k:record[k] for k in ('event_time','available_at','retrieved_at','source')})
            if key=='stock':stock=value
            elif key=='observation':obs=value
            else:stock[key]=value
        if not stock.get('ticker'):continue
        if mode=='china':
            if stock.get('china_verified') is not True:
                china_unknown+=1;continue
        examined+=1
        analysis=analyze(stock,obs,cutoff)
        if analysis['coverage']<100:gaps.append('엔진 전체 배점 데이터 미완비')
        if not stock.get('intraday'):gaps.append('당시 장중 5분봉 미확보')
        if not stock.get('sec'):gaps.append('당시 SEC 원문·조건 미확보')
        if analysis['candidate']:
            results.append({'ticker':stock['ticker'],'name':stock.get('name',''),'analysis':analysis,'status':'PARTIAL REPLAY' if gaps or not snapshot.get('universe_complete') else 'VERIFIED REPLAY','missing':gaps,'provenance':provenance,'stored_signal':row.get('stored_signal'),'split_events':stock.get('split_check',{}).get('events',[])})
        missing.extend(gaps)
    results.sort(key=lambda r:(-(r['analysis']['observed_score'] if r['analysis']['observed_score'] is not None else -1),-r['analysis']['coverage'],r['ticker']))
    # Commit the complete candidate set before any future-data reader is invoked.
    locked=frozen(results,cutoff.isoformat(),mode,snapshot.get('source_commit'))
    status='VERIFIED REPLAY' if examined and snapshot.get('universe_complete') and not missing and not rejected else 'PARTIAL REPLAY' if examined else 'NOT REPRODUCIBLE'
    return {**base,'status':status,'reason':'과거 저장 입력으로 현재 엔진 재실행 · 당시 저장 신호와 구분; 전체 종목 원자료·공개 시각 완전성 미검증','examined':examined,'archived_listing_count':snapshot.get('listing_count'),'snapshot_lag_minutes':(cutoff-instant(snapshot['available_at'])).total_seconds()/60,'china_unverified':china_unknown,'rejected_inputs':rejected,'missing':sorted(set(missing+['전체 상장 원자료·탈락 종목 메타데이터의 완전성 미검증'])),'candidate_count':len(results),'top20':results[:20],'frozen':locked}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Read-only ET point-in-time replay')
    parser.add_argument('--snapshot',required=True);parser.add_argument('--et',required=True)
    parser.add_argument('--scope',choices=('all','china'),default='all');parser.add_argument('--output')
    args=parser.parse_args();result=run_detection(json.loads(Path(args.snapshot).read_text()),et_instant(args.et).isoformat(),args.scope)
    text=json.dumps(result,ensure_ascii=False,allow_nan=False)
    if args.output:Path(args.output).write_text(text)
    else:print(text)
